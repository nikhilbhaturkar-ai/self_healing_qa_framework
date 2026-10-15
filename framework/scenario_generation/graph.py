from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from framework.llm.groq_client import GroqClient
from framework.parser.step_interpreter import registered_gherkin_steps
from framework.scenario_generation.index import ScenarioIndex
from framework.scenario_generation.validation import safe_artifact_path, validate_feature


class ScenarioState(TypedDict, total=False):
    repository_root: Path
    repository_revision: str
    requirement: str
    application: str | None
    module: str | None
    role: str | None
    tags: list[str]
    output_name: str | None
    max_retrieved_steps: int
    max_retrieved_examples: int
    retrieved_steps: list[dict]
    retrieved_examples: list[dict]
    selected_step_ids: list[str]
    generated_feature: str
    assumptions: list
    rationale: str
    model_missing_steps: list
    validation: dict
    executable_candidate: bool
    report: dict
    artifact_paths: dict
    error: str


def _current_revision(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _clean_feature(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        text = "\n".join(lines).strip()
    return text + "\n" if text else ""


def _feature_filename(value: str | None) -> str:
    name = Path(value or f"generated_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}").stem
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    if not name:
        raise ValueError("Output name must contain letters or digits")
    return f"{name}.feature"


def build_generation_graph(index: ScenarioIndex, groq: GroqClient):
    def parse_requirement(state: ScenarioState) -> dict:
        requirement = state.get("requirement", "").strip()
        if not requirement:
            return {"error": "Requirement must not be empty."}
        if len(requirement) > 12000:
            return {"error": "Requirement exceeds the 12000 character limit."}
        return {"requirement": requirement}

    def retrieve_candidates(state: ScenarioState) -> dict:
        filters = {key: state[key] for key in ("application", "module", "role") if state.get(key)}
        query = " ".join(str(value) for value in (
            state["requirement"], state.get("application"), state.get("module"),
            state.get("role"), " ".join(state.get("tags", [])),
        ) if value)
        step_hits = index.hybrid_search(
            state["repository_root"], "step_definition", query,
            filters=filters, limit=state.get("max_retrieved_steps", 25),
        )
        example_hits = index.hybrid_search(
            state["repository_root"], "scenario_example", query,
            filters=filters, limit=state.get("max_retrieved_examples", 5),
        )
        return {"retrieved_steps": step_hits, "retrieved_examples": example_hits}

    def generate_feature(state: ScenarioState) -> dict:
        if not state.get("retrieved_steps"):
            return {
                "generated_feature": "",
                "selected_step_ids": [],
                "assumptions": [],
                "model_missing_steps": [{"reason": "No registered steps were retrieved."}],
                "rationale": "Generation stopped because no indexed bindings matched the requirement and scope.",
            }
        retrieved_steps = []
        for hit in state["retrieved_steps"]:
            metadata = hit["metadata"]
            retrieved_steps.append({
                "id": metadata.get("record_key", ""),
                "expression": metadata.get("expression", hit["document"]),
                "expression_type": metadata.get("expression_type", "python_regex"),
                "action_type": metadata.get("action_type", ""),
                "requires_data_table": bool(metadata.get("requires_data_table", False)),
                "source_file": metadata.get("source_file", ""),
                "source_line": None if metadata.get("source_line", -1) < 0 else metadata["source_line"],
                "score": hit["hybrid_score"],
            })
        examples = []
        for hit in state.get("retrieved_examples", []):
            metadata = hit["metadata"]
            examples.append({
                "id": metadata.get("record_key", hit["id"]),
                "feature_name": metadata.get("feature_name", ""),
                "scenario_name": metadata.get("scenario_name", ""),
                "source_file": metadata.get("source_file", ""),
                "source_line": None if metadata.get("source_line", -1) < 0 else metadata["source_line"],
                "steps": hit["document"],
                "score": hit["hybrid_score"],
            })
        response = groq.generate_cucumber_scenario(
            requirement=state["requirement"],
            scope={key: state.get(key) for key in ("application", "module", "role", "tags")},
            registered_steps=retrieved_steps,
            scenario_examples=examples,
        )
        selected_ids = response.get("selected_step_ids", [])
        allowed_ids = {record["id"] for record in retrieved_steps}
        if not isinstance(selected_ids, list) or any(item not in allowed_ids for item in selected_ids):
            return {
                "generated_feature": _clean_feature(response.get("feature_content")),
                "selected_step_ids": [],
                "assumptions": response.get("assumptions", []),
                "model_missing_steps": response.get("missing_steps", []),
                "rationale": "Rejected model references that were not in the retrieval result.",
                "error": "Model selected step IDs outside retrieved evidence.",
            }
        raw_assumptions = response.get("assumptions", [])
        if isinstance(raw_assumptions, str):
            raw_assumptions = [raw_assumptions] if raw_assumptions else []
        raw_missing = response.get("missing_steps", [])
        if isinstance(raw_missing, str):
            raw_missing = [{"reason": raw_missing}] if raw_missing else []
        return {
            "generated_feature": _clean_feature(response.get("feature_content")),
            "selected_step_ids": selected_ids,
            "assumptions": raw_assumptions,
            "model_missing_steps": raw_missing,
            "rationale": response.get("rationale", ""),
        }

    def validate_generated_feature(state: ScenarioState) -> dict:
        validation = validate_feature(state.get("generated_feature", ""), registered_gherkin_steps())
        if state.get("error"):
            validation["validation_errors"].append(state["error"])
        retrieved_ids = {hit["metadata"].get("record_key") for hit in state.get("retrieved_steps", [])}
        selected_ids = set(state.get("selected_step_ids", []))
        for match in validation["reused_steps"]:
            if match["binding_id"] not in retrieved_ids:
                validation["validation_errors"].append(f"Binding was not retrieved as evidence: {match['text']}")
            elif match["binding_id"] not in selected_ids:
                validation["validation_errors"].append(f"Matched binding was not selected by the generator: {match['text']}")
        revision = _current_revision(state["repository_root"])
        if revision != state.get("repository_revision"):
            validation["validation_errors"].append("Repository revision changed since indexing; re-index first.")
        executable = bool(
            validation["syntax_valid"] and validation["step_count"] > 0
            and not validation["missing_steps"] and not validation["ambiguous_steps"]
            and not validation["validation_errors"]
        )
        return {"validation": validation, "repository_revision": revision, "executable_candidate": executable}

    def write_artifacts(state: ScenarioState) -> dict:
        filename = _feature_filename(state.get("output_name"))
        feature_path = safe_artifact_path(state["repository_root"], filename)
        json_path, markdown_path = feature_path.with_suffix(".json"), feature_path.with_suffix(".md")
        report = {
            "requirement": state["requirement"],
            "application": state.get("application"), "module": state.get("module"),
            "role": state.get("role"), "tags": state.get("tags", []),
            "repository_revision": state.get("repository_revision"),
            "feature_path": feature_path.relative_to(state["repository_root"]).as_posix() if state.get("validation", {}).get("syntax_valid") else None,
            "executable_candidate": state.get("executable_candidate", False),
            "validation": {**state.get("validation", {}), "dry_run_status": "not_run", "execution_status": "not_run"},
            "assumptions": state.get("assumptions", []), "rationale": state.get("rationale", ""),
            "selected_step_ids": state.get("selected_step_ids", []),
            "model_reported_missing_steps": state.get("model_missing_steps", []),
            "retrieved_steps": [
                {"id": hit["metadata"].get("record_key"), "expression": hit["metadata"].get("expression"),
                 "source_file": hit["metadata"].get("source_file"), "source_line": hit["metadata"].get("source_line"),
                 "semantic_distance": hit.get("semantic_distance"), "lexical_score": hit.get("lexical_score"),
                 "hybrid_score": hit.get("hybrid_score")}
                for hit in state.get("retrieved_steps", [])
            ],
            "retrieved_scenario_examples": [
                {"id": hit["metadata"].get("record_key"), "feature": hit["metadata"].get("feature_name"),
                 "scenario": hit["metadata"].get("scenario_name"), "source_file": hit["metadata"].get("source_file"),
                 "source_line": hit["metadata"].get("source_line"), "hybrid_score": hit.get("hybrid_score")}
                for hit in state.get("retrieved_examples", [])
            ],
        }
        if state.get("validation", {}).get("syntax_valid"):
            feature_path.write_text(state.get("generated_feature", ""), encoding="utf-8")
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        markdown_path.write_text(_markdown_report(report), encoding="utf-8")
        artifact_paths = {"json_report": str(json_path), "markdown_report": str(markdown_path)}
        if state.get("validation", {}).get("syntax_valid"):
            artifact_paths["feature"] = str(feature_path)
        report["artifact_paths"] = artifact_paths
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        return {"report": report, "artifact_paths": artifact_paths}

    graph = StateGraph(ScenarioState)
    graph.add_node("parse_requirement", parse_requirement)
    graph.add_node("retrieve_candidates", retrieve_candidates)
    graph.add_node("generate_feature", generate_feature)
    graph.add_node("validate_generated_feature", validate_generated_feature)
    graph.add_node("write_artifacts", write_artifacts)
    graph.add_edge(START, "parse_requirement")
    graph.add_conditional_edges("parse_requirement", lambda state: "stop" if state.get("error") else "retrieve", {"stop": END, "retrieve": "retrieve_candidates"})
    graph.add_edge("retrieve_candidates", "generate_feature")
    graph.add_edge("generate_feature", "validate_generated_feature")
    graph.add_edge("validate_generated_feature", "write_artifacts")
    graph.add_edge("write_artifacts", END)
    return graph.compile()


def _markdown_report(report: dict) -> str:
    validation = report["validation"]
    lines = [
        "# Cucumber Scenario Generation Report", "",
        f"- Requirement: {report['requirement']}",
        f"- Repository revision: `{report['repository_revision']}`",
        f"- Executable candidate: **{report['executable_candidate']}**",
        f"- Gherkin syntax valid: **{validation.get('syntax_valid', False)}**",
        "- Cucumber dry-run: **not run**", "- Actual execution: **not run**", "", "## Reused Steps", "",
    ]
    for step in validation.get("reused_steps", []):
        lines.append(f"- `{step['text']}` → `{step['expression']}` ({step['source_file']}:{step['source_line']})")
    if not validation.get("reused_steps"):
        lines.append("- None")
    for title, key in (("Missing Steps", "missing_steps"), ("Ambiguous Steps", "ambiguous_steps"), ("Validation Errors", "validation_errors")):
        lines.extend(["", f"## {title}", ""])
        values = validation.get(key, [])
        lines.extend(f"- {item.get('text', item) if isinstance(item, dict) else item}" for item in values) if values else lines.append("- None")
    lines.extend(["", "## Assumptions", ""])
    lines.extend(f"- {item}" for item in report.get("assumptions", [])) if report.get("assumptions") else lines.append("- None")
    lines.extend(["", "Generation does not execute the feature. Review it and run the project dry-run before use.", ""])
    return "\n".join(lines)