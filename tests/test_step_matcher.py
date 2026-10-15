"""Unit tests for the step matcher — validates regex semantics of all registered bindings."""
from __future__ import annotations

import pytest

from framework.parser.step_interpreter import (
    match_gherkin_step_definitions,
    registered_gherkin_steps,
)


def test_registered_steps_are_all_present():
    steps = registered_gherkin_steps()
    ids = {s["binding_id"] for s in steps}
    assert ids == {"navigate", "fill", "select", "click", "button_visible", "text_visible", "texts_table", "screenshot"}


def test_navigate_step_matches():
    matches = match_gherkin_step_definitions('I navigate to "https://example.com"')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "navigate"
    assert matches[0]["action_type"] == "navigate"


def test_fill_step_matches():
    matches = match_gherkin_step_definitions('I enter "hello" into "username"')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "fill"


def test_select_step_matches():
    matches = match_gherkin_step_definitions('I select "Active" from "Status" dropdown')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "select"


def test_click_step_matches():
    matches = match_gherkin_step_definitions('I click "Submit"')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "click"

    matches = match_gherkin_step_definitions('I click on "Submit"')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "click"


def test_button_visible_matches():
    matches = match_gherkin_step_definitions('I should see button "Login"')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "button_visible"


def test_text_visible_matches():
    matches = match_gherkin_step_definitions('I should see "Welcome"')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "text_visible"

    matches = match_gherkin_step_definitions('I should see text "Welcome"')
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "text_visible"


def test_screenshot_matches():
    matches = match_gherkin_step_definitions("I capture a screenshot")
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "screenshot"

    matches = match_gherkin_step_definitions("I take screenshot")
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "screenshot"


def test_texts_table_requires_valid_table():
    valid_table = [["text"], ["SAP Basis Admin"], ["System Monitoring"]]
    matches = match_gherkin_step_definitions("I should see all listed texts", valid_table)
    assert len(matches) == 1
    assert matches[0]["binding_id"] == "texts_table"


def test_texts_table_without_table_does_not_match():
    matches = match_gherkin_step_definitions("I should see all listed texts")
    assert matches == []


def test_texts_table_with_wrong_header_does_not_match():
    bad_table = [["item"], ["SAP Basis Admin"]]
    matches = match_gherkin_step_definitions("I should see all listed texts", bad_table)
    assert matches == []


def test_unknown_step_does_not_match():
    matches = match_gherkin_step_definitions("I do something completely unknown")
    assert matches == []


def test_step_ids_are_stable():
    steps_a = registered_gherkin_steps()
    steps_b = registered_gherkin_steps()
    assert [s["id"] for s in steps_a] == [s["id"] for s in steps_b]
