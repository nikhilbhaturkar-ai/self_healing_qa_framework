from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from gherkin import Compiler, Parser

from framework.parser.step_interpreter import registered_gherkin_steps

_EXCLUDED_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    ".venv-1",
    "dist",
    "build",
    "coverage",
    "test-results",
    "artifacts",
    "reports",
    "__pycache__",
}


@dataclass
class RepositoryScan:
    repository_root: Path
    repository_revision: str
    step_definitions: list[dict]
    scenario_examples: list[dict]
    feature_files_scanned: int
    warnings: list[str]
    duplicate_expressions: list[str]


def _revision(root: Path) -> str:
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


def _included(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return not any(part in _EXCLUDED_PARTS or part.startswith(".") for part in relative_parts)


def scan_repository(
    repository_root: str | Path,
    *,
    application: str | None = None,
    module: str | None = None,
    role: str | None = None,
) -> RepositoryScan:
    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Repository path is not a directory: {root}")

    revision = _revision(root)
    definitions = []
    runtime_source_outside = False
    for definition in registered_gherkin_steps():
        source_path = Path(definition["source_file"])
        try:
            source_file = source_path.resolve().relative_to(root).as_posix()
        except ValueError:
            source_file = source_path.as_posix()
            runtime_source_outside = True
        definitions.append(
            {
                **definition,
                "source_file": source_file,
                "application": application,
                "module": module,
                "role": role,
                "functionality": definition["binding_id"],
                "tags": [],
                "repository_revision": revision,
                "document_type": "step_definition",
            }
        )

    examples = []
    warnings = []
    feature_paths = sorted(
        path for path in root.rglob("*.feature") if _included(path, root)
    )
    parser = Parser()
    compiler = Compiler()
    for feature_path in feature_paths:
        relative_path = feature_path.relative_to(root).as_posix()
        try:
            document = parser.parse(feature_path.read_text(encoding="utf-8"))
            feature = document.get("feature") or {}
            document["uri"] = relative_path
            compiled = compiler.compile(document)
        except Exception as exc:  # noqa: BLE001 - record parse problems while scanning remaining files
            warnings.append(f"{relative_path}: Gherkin parse failed: {exc}")
            continue

        for scenario in compiled:
            step_texts = [step["text"] for step in scenario.get("steps", [])]
            examples.append(
                {
                    "id": f"{relative_path}::{scenario.get('id', '')}",
                    "document": "\n".join(step_texts),
                    "feature_name": feature.get("name", ""),
                    "scenario_name": scenario.get("name", ""),
                    "source_file": relative_path,
                    "source_line": scenario.get("location", {}).get("line"),
                    "application": application,
                    "module": module,
                    "role": role,
                    "tags": [tag["name"].lstrip("@") for tag in scenario.get("tags", [])],
                    "repository_revision": revision,
                    "document_type": "scenario_example",
                }
            )

    expression_counts: dict[str, int] = {}
    for definition in definitions:
        expression_counts[definition["expression"]] = expression_counts.get(definition["expression"], 0) + 1
    duplicates = sorted(expression for expression, count in expression_counts.items() if count > 1)
    if runtime_source_outside:
        warnings.append("Runtime binding source is outside the scanned repository; it is used as the authoritative Python registry.")

    return RepositoryScan(
        repository_root=root,
        repository_revision=revision,
        step_definitions=definitions,
        scenario_examples=examples,
        feature_files_scanned=len(feature_paths),
        warnings=warnings,
        duplicate_expressions=duplicates,
    )