from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from framework.custom_locators import resolve_custom_locator
from framework.graph.nodes.execute_step import make_execute_step


class FakeLocator:
    def __init__(self, count=1):
        self.match_count = count

    async def count(self):
        return self.match_count


class FakePage:
    def __init__(self):
        self.calls = []
        self.locator_result = FakeLocator()

    def locator(self, selector):
        self.calls.append(("css", selector))
        return self.locator_result

    def get_by_test_id(self, value):
        self.calls.append(("test_id", value))
        return self.locator_result


def test_resolve_custom_locator_uses_json_mapping(tmp_path, monkeypatch):
    config_path = tmp_path / "custom_locators.json"
    config_path.write_text(
        json.dumps({"fill": {"Username": {"by": "css", "value": "input[name='user']"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("framework.custom_locators.CUSTOM_LOCATORS_PATH", config_path)
    page = FakePage()

    configured, locator = asyncio.run(resolve_custom_locator(page, "fill", " username "))

    assert configured is True
    assert locator is page.locator_result
    assert page.calls == [("css", "input[name='user']")]


def test_resolve_custom_locator_reports_configured_non_unique_match(tmp_path, monkeypatch):
    config_path = tmp_path / "custom_locators.json"
    config_path.write_text(
        json.dumps({"click": {"Submit": {"by": "test_id", "value": "submit"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("framework.custom_locators.CUSTOM_LOCATORS_PATH", config_path)
    page = FakePage()
    page.locator_result = FakeLocator(count=2)

    configured, locator = asyncio.run(resolve_custom_locator(page, "click", "Submit"))

    assert configured is True
    assert locator is None


def test_custom_locator_execution_skips_memory_and_semantic_resolution(tmp_path, monkeypatch):
    config_path = tmp_path / "custom_locators.json"
    config_path.write_text(
        json.dumps({"click": {"Submit": {"by": "css", "value": "#submit"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("framework.custom_locators.CUSTOM_LOCATORS_PATH", config_path)

    class Store:
        def lookup(self, *args, **kwargs):
            raise AssertionError("custom locator must bypass locator memory")

    class Driver:
        page = FakePage()

        async def act(self, locator, op, value):
            return True

        async def resolve_and_act(self, *args):
            raise AssertionError("custom locator must bypass semantic resolution")

    node = make_execute_step(SimpleNamespace(store=Store(), driver=Driver()))
    result = asyncio.run(
        node({"url_pattern": "example.com", "kind": "clickable", "hint": "Submit", "op": "click"})
    )

    assert result["initial_success"] is True
    assert result["final_success"] is True
    assert result["locator_strategy"] == "custom_json"
    assert result["custom_locator_configured"] is True