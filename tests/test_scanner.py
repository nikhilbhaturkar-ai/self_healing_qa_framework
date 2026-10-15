"""Unit tests for the repository scanner — validates extraction from .feature files."""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.scenario_generation.scanner import scan_repository

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scan_returns_step_definitions():
    scan = scan_repository(REPO_ROOT)
    assert scan.step_definitions, "Expected at least one step definition"
    assert all(d["document_type"] == "step_definition" for d in scan.step_definitions)


def test_scan_returns_scenario_examples():
    scan = scan_repository(REPO_ROOT)
    assert scan.scenario_examples, "Expected scenario examples from feature files"
    assert all(e["document_type"] == "scenario_example" for e in scan.scenario_examples)


def test_scan_counts_feature_files():
    scan = scan_repository(REPO_ROOT)
    feature_files = list(REPO_ROOT.rglob("*.feature"))
    expected = sum(
        1 for p in feature_files
        if not any(part in {".venv", ".venv-1", "artifacts", "node_modules", ".git"} for part in p.parts)
    )
    assert scan.feature_files_scanned == expected


def test_scan_no_duplicate_expressions():
    scan = scan_repository(REPO_ROOT)
    assert scan.duplicate_expressions == [], f"Duplicate step expressions found: {scan.duplicate_expressions}"


def test_scan_no_warnings():
    scan = scan_repository(REPO_ROOT)
    assert scan.warnings == [], f"Unexpected scanner warnings: {scan.warnings}"


def test_scenario_examples_have_required_fields():
    scan = scan_repository(REPO_ROOT)
    for example in scan.scenario_examples:
        assert "id" in example
        assert "document" in example
        assert "feature_name" in example
        assert "scenario_name" in example
        assert "source_file" in example


def test_step_definitions_have_required_fields():
    scan = scan_repository(REPO_ROOT)
    for defn in scan.step_definitions:
        assert "binding_id" in defn
        assert "expression" in defn
        assert "source_file" in defn
        assert defn.get("status") == "implemented"


def test_requires_data_table_flag_is_present():
    scan = scan_repository(REPO_ROOT)
    table_steps = [d for d in scan.step_definitions if d.get("requires_data_table")]
    binding_ids = {d["binding_id"] for d in table_steps}
    assert "texts_table" in binding_ids, "texts_table binding should have requires_data_table=True"


def test_invalid_repo_path_raises():
    with pytest.raises(ValueError, match="not a directory"):
        scan_repository("/nonexistent/path/xyz")
