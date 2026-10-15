"""Integration tests for the ChromaDB index — uses a temporary Chroma directory."""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.scenario_generation.index import ScenarioIndex
from framework.scenario_generation.scanner import scan_repository

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def temp_index(tmp_path):
    index = ScenarioIndex(tmp_path / "chroma")
    scan = scan_repository(REPO_ROOT)
    index.index_scan(scan)
    return index, scan


def test_index_scan_counts(temp_index):
    index, scan = temp_index
    result = index.index_scan(scan)
    assert result["step_definitions_indexed"] == len(scan.step_definitions)
    assert result["scenario_examples_indexed"] == len(scan.scenario_examples)


def test_hybrid_search_returns_results(temp_index):
    index, scan = temp_index
    hits = index.hybrid_search(REPO_ROOT, "step_definition", "navigate to url")
    assert hits, "Expected at least one hit for navigate"
    expressions = [h["metadata"]["expression"] for h in hits]
    assert any("navigate" in e.lower() for e in expressions)


def test_hybrid_search_step_limit(temp_index):
    index, scan = temp_index
    hits = index.hybrid_search(REPO_ROOT, "step_definition", "click button", limit=3)
    assert len(hits) <= 3


def test_hybrid_search_examples(temp_index):
    index, scan = temp_index
    hits = index.hybrid_search(REPO_ROOT, "scenario_example", "sign in admin dashboard")
    assert hits, "Expected scenario examples for sign-in query"


def test_indexed_revision(temp_index):
    index, scan = temp_index
    revision = index.indexed_revision(REPO_ROOT)
    assert revision == scan.repository_revision


def test_requires_data_table_stored_in_metadata(temp_index):
    index, scan = temp_index
    hits = index.hybrid_search(REPO_ROOT, "step_definition", "see all listed texts")
    assert hits, "Expected texts_table step to be found"
    table_hit = next((h for h in hits if "all listed" in h["metadata"].get("expression", "")), None)
    assert table_hit is not None
    assert table_hit["metadata"].get("requires_data_table") is True


def test_empty_query_returns_results(temp_index):
    index, scan = temp_index
    hits = index.hybrid_search(REPO_ROOT, "step_definition", "")
    assert len(hits) > 0
