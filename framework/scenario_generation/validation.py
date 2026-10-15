from __future__ import annotations

from pathlib import Path

from gherkin import Compiler, Parser

from framework.parser.step_interpreter import match_gherkin_step_definitions


def validate_feature(feature_content: str, registered_steps: list[dict], uri: str = "generated.feature") -> dict:
    result = {
        "syntax_valid": False,
        "reused_steps": [],
        "missing_steps": [],
        "ambiguous_steps": [],
        "validation_errors": [],
        "scenario_count": 0,
        "step_count": 0,
    }
    try:
        document = Parser().parse(feature_content)
        document["uri"] = uri
        scenarios = Compiler().compile(document)
    except Exception as exc:  # noqa: BLE001 - report Gherkin parse errors as validation data
        result["validation_errors"].append(f"Gherkin parse error: {exc}")
        return result

    result["syntax_valid"] = True
    result["scenario_count"] = len(scenarios)
    registry_by_id = {record["id"]: record for record in registered_steps}
    for scenario in scenarios:
        for step in scenario.get("steps", []):
            result["step_count"] += 1
            table = [
                [cell["value"] for cell in row["cells"]]
                for row in step.get("argument", {}).get("dataTable", {}).get("rows", [])
            ] or None
            matches = match_gherkin_step_definitions(step["text"], table)
            step_info = {
                "text": step["text"],
                "keyword_type": step.get("type"),
                "scenario": scenario.get("name", ""),
            }
            if not matches:
                result["missing_steps"].append(step_info)
            elif len(matches) > 1:
                result["ambiguous_steps"].append({**step_info, "candidates": matches})
            else:
                match = matches[0]
                source = registry_by_id.get(match["id"], match)
                result["reused_steps"].append(
                    {
                        **step_info,
                        "expression": source["expression"],
                        "binding_id": source["id"],
                        "source_file": source["source_file"],
                        "source_line": source["source_line"],
                    }
                )
    return result


def safe_artifact_path(repository_root: Path, filename: str) -> Path:
    artifact_root = (repository_root / "artifacts" / "cucumber_rag").resolve()
    target = (artifact_root / filename).resolve()
    if target != artifact_root and artifact_root not in target.parents:
        raise ValueError("Artifact filename escapes the approved artifacts directory")
    artifact_root.mkdir(parents=True, exist_ok=True)
    return target