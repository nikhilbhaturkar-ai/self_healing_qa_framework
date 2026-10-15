from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import chromadb

from framework.scenario_generation.scanner import RepositoryScan

STEP_COLLECTION = "cucumber_registered_steps"
EXAMPLE_COLLECTION = "cucumber_scenario_examples"
_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def _stable_id(repository_root: Path, document_type: str, record_id: str) -> str:
    key = f"{repository_root.as_posix()}|{document_type}|{record_id}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _metadata(record: dict, repository_root: Path) -> dict:
    metadata = {
        "repo_path": repository_root.as_posix(),
        "document_type": record["document_type"],
        "source_file": record.get("source_file", ""),
        "source_line": int(record.get("source_line") or -1),
        "revision": record.get("repository_revision", "unknown"),
        "tags": ",".join(record.get("tags", [])),
        "status": record.get("status", "implemented"),
        "record_key": str(record.get("id") or record.get("binding_id") or ""),
    }
    for field in (
        "application", "module", "role", "binding_id", "expression", "expression_type",
        "action_type", "feature_name", "scenario_name",
    ):
        value = record.get(field)
        if value is not None:
            metadata[field] = str(value)
    requires_table = record.get("requires_data_table")
    if requires_table is not None:
        metadata["requires_data_table"] = bool(requires_table)
    return metadata


class ScenarioIndex:
    def __init__(self, persist_path: str | Path):
        self.client = chromadb.PersistentClient(path=str(persist_path))
        self.steps = self.client.get_or_create_collection(STEP_COLLECTION)
        self.examples = self.client.get_or_create_collection(EXAMPLE_COLLECTION)

    @staticmethod
    def _upsert_records(collection, records: list[dict], repository_root: Path, document_type: str) -> int:
        current_ids = collection.get(where={"repo_path": repository_root.as_posix()}, include=[]).get("ids", [])
        ids = []
        documents = []
        metadatas = []
        for record in records:
            record_key = str(record.get("id") or record.get("binding_id") or record["expression"])
            document_id = _stable_id(repository_root, document_type, record_key)
            document = record.get("document") or record.get("expression") or ""
            if record.get("application") or record.get("module") or record.get("role"):
                document += " " + " ".join(
                    str(record[key]) for key in ("application", "module", "role") if record.get(key)
                )
            ids.append(document_id)
            documents.append(document)
            metadatas.append(_metadata(record, repository_root))
        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        stale_ids = sorted(set(current_ids) - set(ids))
        if stale_ids:
            collection.delete(ids=stale_ids)
        return len(ids)

    def index_scan(self, scan: RepositoryScan) -> dict:
        return {
            "step_definitions_indexed": self._upsert_records(
                self.steps, scan.step_definitions, scan.repository_root, "step_definition"
            ),
            "scenario_examples_indexed": self._upsert_records(
                self.examples, scan.scenario_examples, scan.repository_root, "scenario_example"
            ),
            "feature_files_scanned": scan.feature_files_scanned,
            "repository_revision": scan.repository_revision,
            "warnings": scan.warnings,
            "duplicate_expressions": scan.duplicate_expressions,
        }

    def indexed_revision(self, repository_root: Path) -> str | None:
        result = self.steps.get(
            where={"repo_path": repository_root.as_posix()},
            include=["metadatas"],
            limit=1,
        )
        metadatas = result.get("metadatas", [])
        return metadatas[0].get("revision") if metadatas else None

    @staticmethod
    def _query_filter(repository_root: Path, document_type: str, filters: dict[str, str | None]) -> dict:
        clauses = [
            {"repo_path": repository_root.as_posix()},
            {"document_type": document_type},
        ]
        clauses.extend({field: value} for field, value in filters.items() if value)
        return {"$and": clauses}

    @staticmethod
    def _lexical_rank(records: list[dict], query: str) -> list[tuple[str, float]]:
        query_terms = [token.casefold() for token in _TOKEN_RE.findall(query)]
        if not query_terms or not records:
            return []
        tokenized = [
            [token.casefold() for token in _TOKEN_RE.findall(record.get("document") or "")]
            for record in records
        ]
        document_frequency = {
            term: sum(term in set(tokens) for tokens in tokenized)
            for term in set(query_terms)
        }
        ranked = []
        for record, tokens in zip(records, tokenized):
            frequencies = {term: tokens.count(term) for term in set(query_terms)}
            length_norm = 1.0 + 0.25 * (len(tokens) / max(1, sum(len(row) for row in tokenized) / len(tokenized)))
            score = 0.0
            for term in set(query_terms):
                tf = frequencies[term]
                if tf:
                    idf = math.log(1 + (len(records) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                    score += idf * (tf * 2.2) / (tf + 1.2 * length_norm)
            if score:
                ranked.append((record["id"], score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    def hybrid_search(
        self,
        repository_root: Path,
        document_type: str,
        query: str,
        *,
        filters: dict[str, str | None] | None = None,
        limit: int = 25,
    ) -> list[dict]:
        collection = self.steps if document_type == "step_definition" else self.examples
        optional_filters = filters or {}
        where = self._query_filter(repository_root, document_type, optional_filters)
        count = len(collection.get(where=where, include=[]).get("ids", []))
        if not count:
            return []

        semantic = collection.query(
            query_texts=[query],
            n_results=min(count, max(limit * 3, 10)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        semantic_rows = list(
            zip(
                semantic.get("ids", [[]])[0],
                semantic.get("documents", [[]])[0],
                semantic.get("metadatas", [[]])[0],
                semantic.get("distances", [[]])[0],
            )
        )

        lexical_data = collection.get(
            where={"$and": [{"repo_path": repository_root.as_posix()}, {"document_type": document_type}]},
            include=["documents", "metadatas"],
        )
        lexical_records = [
            {"id": record_id, "document": document, "metadata": metadata}
            for record_id, document, metadata in zip(
                lexical_data.get("ids", []),
                lexical_data.get("documents", []),
                lexical_data.get("metadatas", []),
            )
            if all(not value or metadata.get(key) == value for key, value in optional_filters.items())
        ]
        lexical_ranked = self._lexical_rank(lexical_records, query)

        combined: dict[str, dict] = {}
        for rank, (record_id, document, metadata, distance) in enumerate(semantic_rows, 1):
            combined[record_id] = {
                "id": record_id,
                "document": document,
                "metadata": metadata,
                "semantic_distance": float(distance),
                "semantic_rank": rank,
                "hybrid_score": 1 / (60 + rank),
            }
        for rank, (record_id, score) in enumerate(lexical_ranked, 1):
            if record_id not in combined:
                record = next(row for row in lexical_records if row["id"] == record_id)
                combined[record_id] = {
                    "id": record_id,
                    "document": record["document"],
                    "metadata": record["metadata"],
                    "semantic_distance": None,
                    "semantic_rank": None,
                    "hybrid_score": 0.0,
                }
            combined[record_id]["lexical_score"] = score
            combined[record_id]["lexical_rank"] = rank
            combined[record_id]["hybrid_score"] += 1 / (60 + rank)

        ranked = sorted(combined.values(), key=lambda row: row["hybrid_score"], reverse=True)
        return ranked[:limit]