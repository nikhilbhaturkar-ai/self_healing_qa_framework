"""Stage 5 - Locator Memory & Learning.

ChromaDB persistent collection = the "Locator Repository": each entry is a
healed (url_pattern, kind, hint) -> locator mapping, embedded with Chroma's
built-in local ONNX embedding function (no network/LLM tokens spent).

A parallel JSON file is the human-readable "Change History & Versioning"
log, and also feeds the analytics used in the report.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import chromadb

COLLECTION_NAME = "locator_memory"


def _doc_id(url_pattern: str, kind: str, hint: str) -> str:
    return hashlib.sha1(f"{url_pattern}|{kind}|{hint}".encode("utf-8")).hexdigest()


class LocatorStore:
    def __init__(self, chroma_path: Path, history_path: Path):
        self._client = chromadb.PersistentClient(path=str(chroma_path))
        self._collection = self._client.get_or_create_collection(COLLECTION_NAME)
        self._history_path = history_path
        if not self._history_path.exists():
            self._history_path.write_text("[]", encoding="utf-8")

    def lookup(self, url_pattern: str, kind: str, hint: str, n_results: int = 1) -> list[dict]:
        """Similarity search for a previously healed locator matching this
        intent. Returns [] if the collection is empty (first run)."""
        if self._collection.count() == 0:
            return []
        result = self._collection.query(
            query_texts=[f"{kind}: {hint}"],
            n_results=min(n_results, self._collection.count()),
            where={"url_pattern": url_pattern},
        )
        hits = []
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for doc_id, meta, dist in zip(ids, metadatas, distances):
            similarity = max(0.0, 1.0 - dist)
            hits.append({"id": doc_id, "similarity": similarity, **meta})
        return hits

    def success_rate_for(self, url_pattern: str, kind: str, hint: str) -> float:
        hits = self.lookup(url_pattern, kind, hint, n_results=1)
        if not hits or hits[0]["similarity"] < 0.85:
            return 0.0
        meta = hits[0]
        total = meta.get("success_count", 0) + meta.get("failure_count", 0)
        return meta.get("success_count", 0) / total if total else 0.0

    def record_heal(
        self,
        url_pattern: str,
        kind: str,
        hint: str,
        old_descriptor: str,
        candidate: dict,
        confidence: float,
        decision: str,
        applied_success: bool,
    ) -> None:
        doc_id = _doc_id(url_pattern, kind, hint)
        existing = self._collection.get(ids=[doc_id])
        success_count = 1 if applied_success else 0
        failure_count = 0 if applied_success else 1
        if existing and existing.get("metadatas") and existing["metadatas"][0]:
            prev = existing["metadatas"][0]
            success_count += prev.get("success_count", 0)
            failure_count += prev.get("failure_count", 0)

        metadata = {
            "url_pattern": url_pattern,
            "kind": kind,
            "hint": hint,
            "strategy": candidate.get("strategy", ""),
            "selector": candidate.get("selector") or "",
            "role": candidate.get("role") or "",
            "accessible_name": candidate.get("accessible_name") or "",
            "confidence": confidence,
            "decision": decision,
            "success_count": success_count,
            "failure_count": failure_count,
            "last_verified": time.time(),
        }
        self._collection.upsert(ids=[doc_id], documents=[f"{kind}: {hint}"], metadatas=[metadata])
        self._append_history(
            {
                "timestamp": time.time(),
                "url_pattern": url_pattern,
                "kind": kind,
                "hint": hint,
                "old_locator": old_descriptor,
                "new_locator": candidate.get("selector") or candidate.get("accessible_name") or "",
                "strategy": candidate.get("strategy", ""),
                "confidence": confidence,
                "decision": decision,
                "applied_success": applied_success,
            }
        )

    def _append_history(self, entry: dict) -> None:
        history = json.loads(self._history_path.read_text(encoding="utf-8"))
        history.append(entry)
        self._history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    def get_analytics(self) -> dict:
        history = json.loads(self._history_path.read_text(encoding="utf-8"))
        total = len(history)
        if total == 0:
            return {
                "total_heals": 0,
                "auto_healed": 0,
                "flagged_for_review": 0,
                "heal_success_rate": 0.0,
                "avg_confidence": 0.0,
            }
        auto = sum(1 for h in history if h["decision"] == "auto_heal")
        flagged = sum(1 for h in history if h["decision"] == "flag")
        successes = sum(1 for h in history if h["applied_success"])
        avg_conf = sum(h["confidence"] for h in history) / total
        return {
            "total_heals": total,
            "auto_healed": auto,
            "flagged_for_review": flagged,
            "heal_success_rate": round(successes / total, 3),
            "avg_confidence": round(avg_conf, 3),
        }
