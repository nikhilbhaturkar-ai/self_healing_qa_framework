"""Unit tests for the Gherkin validation layer."""
from __future__ import annotations

import pytest

from framework.parser.step_interpreter import registered_gherkin_steps
from framework.scenario_generation.validation import safe_artifact_path, validate_feature

VALID_FEATURE = """\
Feature: Login
  Scenario: User logs in
    Given I navigate to "https://example.com"
    When I enter "user@example.com" into "email"
    And I click "Login"
    Then I should see text "Welcome"
"""

FEATURE_WITH_TABLE_STEP = """\
Feature: Dashboard
  Scenario: Tiles are visible
    Given I navigate to "https://example.com"
    Then I should see all listed texts
      | text  |
      | Tile1 |
      | Tile2 |
"""

INVALID_GHERKIN = "This is not valid gherkin at all"

MISSING_STEP_FEATURE = """\
Feature: Unknown
  Scenario: Unknown action
    Given I navigate to "https://example.com"
    When I do something completely unregistered
"""


def _steps():
    return registered_gherkin_steps()


def test_valid_feature_passes():
    result = validate_feature(VALID_FEATURE, _steps())
    assert result["syntax_valid"] is True
    assert result["scenario_count"] == 1
    assert result["step_count"] == 4
    assert not result["missing_steps"]
    assert not result["ambiguous_steps"]
    assert not result["validation_errors"]


def test_reused_steps_are_reported():
    result = validate_feature(VALID_FEATURE, _steps())
    reused_texts = {s["text"] for s in result["reused_steps"]}
    assert 'I navigate to "https://example.com"' in reused_texts
    assert 'I click "Login"' in reused_texts


def test_feature_with_data_table_passes():
    result = validate_feature(FEATURE_WITH_TABLE_STEP, _steps())
    assert result["syntax_valid"] is True
    assert not result["missing_steps"]


def test_invalid_gherkin_is_reported():
    result = validate_feature(INVALID_GHERKIN, _steps())
    assert result["syntax_valid"] is False
    assert result["validation_errors"]


def test_missing_step_is_reported():
    result = validate_feature(MISSING_STEP_FEATURE, _steps())
    assert result["syntax_valid"] is True
    missing_texts = {s["text"] for s in result["missing_steps"]}
    assert "I do something completely unregistered" in missing_texts


def test_safe_artifact_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        safe_artifact_path(tmp_path, "../../../etc/passwd")
