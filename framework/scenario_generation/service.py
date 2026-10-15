from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from config import SETTINGS
from framework.llm.groq_client import GroqClient
from framework.scenario_generation.graph import build_generation_graph
from framework.scenario_generation.index import ScenarioIndex
from framework.scenario_generation.scanner import scan_repository


def current_revision(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def index_repository(
    repository_root: str | Path,
    *,
    chroma_path: str | Path | None = None,
    application: str | None = None,
    module: str | None = None,
    role: str | None = None,
) -> dict:
    root = Path(repository_root).expanduser().resolve()
    scan = scan_repository(root, application=application, module=module, role=role)
    index = ScenarioIndex(chroma_path or SETTINGS.chroma_path)
    summary = index.index_scan(scan)
    return {
        **summary,
        "repository_root": root.as_posix(),
        "step_definitions_found": len(scan.step_definitions),
        "scenario_examples_found": len(scan.scenario_examples),
        "warnings": scan.warnings,
        "duplicate_expressions": scan.duplicate_expressions,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def generate_feature(
    repository_root: str | Path,
    requirement: str,
    *,
    application: str | None = None,
    module: str | None = None,
    role: str | None = None,
    tags: list[str] | None = None,
    output_name: str | None = None,
    chroma_path: str | Path | None = None,
    groq_client: Any | None = None,
    max_retrieved_steps: int = 25,
    max_retrieved_examples: int = 5,
) -> dict:
    root = Path(repository_root).expanduser().resolve()
    index = ScenarioIndex(chroma_path or SETTINGS.chroma_path)
    stored_revision = index.indexed_revision(root)
    if stored_revision is None:
        raise ValueError("Repository is not indexed. Run the generator's index command first.")
    revision = current_revision(root)
    if stored_revision != revision:
        raise ValueError(
            f"Repository index is stale (indexed {stored_revision}, current {revision}); re-index before generation."
        )
    client = groq_client or GroqClient(SETTINGS.groq_api_key, SETTINGS.groq_model)
    graph = build_generation_graph(index, client)
    result = graph.invoke({
        "repository_root": root,
        "repository_revision": revision,
        "requirement": requirement,
        "application": application,
        "module": module,
        "role": role,
        "tags": tags or [],
        "output_name": output_name,
        "max_retrieved_steps": max_retrieved_steps,
        "max_retrieved_examples": max_retrieved_examples,
    })
    if result.get("error"):
        raise ValueError(result["error"])
    report = result.get("report", {})
    return _json_safe({
        "report": report,
        "artifact_paths": result.get("artifact_paths", {}),
    })