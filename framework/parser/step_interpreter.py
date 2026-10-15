"""Rule-based (LLM-free) interpretation of a plain-English step into an Action.

Covers the vocabulary shown in the sample scenarios:
  - "Navigate to <url>"
  - 'Enter <field> text "<value>" and click on <target>'
  - 'Enter "<value>" in <field>'
  - "Click on <target>"
  - "<Subject> should show/display/contain <content> [in <section>]"

If none of the rules match, `Action.type == "unknown"` is returned; the graph
layer decides whether to spend a single small Groq call to classify it
(kept out of this module so parsing itself never costs tokens).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Optional

_NAVIGATE_RE = re.compile(r"^(?:navigate|go)\s+to\s+(.+)$", re.IGNORECASE)
_ENTER_AND_CLICK_RE = re.compile(
    r'^enter\s+(?:(?P<field>.+?)\s+text\s+)?"(?P<value>[^"]+)"\s+and\s+click\s+(?:on\s+)?(?P<target>.+)$',
    re.IGNORECASE,
)
_ENTER_ONLY_RE = re.compile(
    r'^enter\s+"(?P<value>[^"]+)"(?:\s+(?:in|into)\s+(?P<field>.+))?$', re.IGNORECASE
)
_CLICK_RE = re.compile(r"^click\s+(?:on\s+)?(.+)$", re.IGNORECASE)
_SCREENSHOT_RE = re.compile(
    r"^(?:capture|take)\s+(?:a\s+)?(?:screenshot|screen\s*shot|screen\s*print)"
    r"(?:\s+(?:for|of)\s+(?:the\s+)?screen)?[.!]?$",
    re.IGNORECASE,
)
_VERIFY_DISPLAY_RE = re.compile(
    r"^verify\s+if\s+(?P<content>.+?)\s+(?:is|are)\s+displaying\.?$", re.IGNORECASE
)
_ASSERT_RE = re.compile(
    r"^(?P<subject>.+?)\s+should\s+(?:show|display|contain)\s+(?P<content>.+)$", re.IGNORECASE
)
_GHERKIN_NAVIGATE_RE = re.compile(r'^I navigate to "(?P<url>[^"]+)"$', re.IGNORECASE)
_GHERKIN_FILL_RE = re.compile(r'^I enter "(?P<value>[^"]+)" into "(?P<field>[^"]+)"$', re.IGNORECASE)
_GHERKIN_SELECT_RE = re.compile(
    r'^I select "(?P<value>[^"]+)" from "(?P<field>[^"]+)"(?: dropdown)?$',
    re.IGNORECASE,
)
_GHERKIN_CLICK_RE = re.compile(r'^I click(?:\s+on)?\s+"(?P<target>[^"]+)"$', re.IGNORECASE)
_GHERKIN_BUTTON_VISIBLE_RE = re.compile(r'^I should see button "(?P<target>[^"]+)"$', re.IGNORECASE)
_GHERKIN_ASSERT_RE = re.compile(r'^I should see (?:text )?"(?P<content>[^"]+)"$', re.IGNORECASE)
_GHERKIN_ASSERT_TABLE_RE = re.compile(r"^I should see all listed texts$", re.IGNORECASE)
_GHERKIN_SCREENSHOT_RE = re.compile(r'^I (?:capture|take) (?:a )?screenshot$', re.IGNORECASE)

_GHERKIN_BINDINGS = [
    ("navigate", "_GHERKIN_NAVIGATE_RE", _GHERKIN_NAVIGATE_RE, 'I navigate to "{string}"', "navigate", False),
    ("fill", "_GHERKIN_FILL_RE", _GHERKIN_FILL_RE, 'I enter "{string}" into "{string}"', "fill", False),
    ("select", "_GHERKIN_SELECT_RE", _GHERKIN_SELECT_RE, 'I select "{string}" from "{string}" dropdown', "select_option", False),
    ("click", "_GHERKIN_CLICK_RE", _GHERKIN_CLICK_RE, 'I click [on] "{string}"', "click", False),
    ("button_visible", "_GHERKIN_BUTTON_VISIBLE_RE", _GHERKIN_BUTTON_VISIBLE_RE, 'I should see button "{string}"', "assert_button_visible", False),
    ("text_visible", "_GHERKIN_ASSERT_RE", _GHERKIN_ASSERT_RE, 'I should see [text] "{string}"', "assert_visible", False),
    ("texts_table", "_GHERKIN_ASSERT_TABLE_RE", _GHERKIN_ASSERT_TABLE_RE, "I should see all listed texts", "assert_visible", True),
    ("screenshot", "_GHERKIN_SCREENSHOT_RE", _GHERKIN_SCREENSHOT_RE, "I [capture|take] [a] screenshot", "screenshot", False),
]


def registered_gherkin_steps() -> list[dict]:
    """Return the runtime binding catalog with stable IDs and source references."""
    source_path = Path(__file__).resolve()
    source_lines = source_path.read_text(encoding="utf-8").splitlines()
    records = []
    for binding_id, declaration, pattern, expression, action_type, requires_table in _GHERKIN_BINDINGS:
        source_line = next(
            (line_number for line_number, line in enumerate(source_lines, 1) if line.startswith(declaration + " =")),
            None,
        )
        stable_id = sha256(f"{source_path.as_posix()}|{binding_id}|{expression}".encode("utf-8")).hexdigest()
        records.append(
            {
                "id": stable_id,
                "binding_id": binding_id,
                "expression": expression,
                "expression_type": "python_regex",
                "action_type": action_type,
                "requires_data_table": requires_table,
                "source_file": source_path.as_posix(),
                "source_line": source_line,
                "status": "implemented",
            }
        )
    return records


def match_gherkin_step_definitions(raw_text: str, data_table: list[list[str]] | None = None) -> list[dict]:
    """Match using the exact regex semantics used by interpret_gherkin_step."""
    text = raw_text.strip().rstrip(".")
    records = {record["binding_id"]: record for record in registered_gherkin_steps()}
    matches = []
    for binding_id, _, pattern, _, _, requires_table in _GHERKIN_BINDINGS:
        table_is_valid = bool(
            data_table
            and len(data_table[0]) == 1
            and data_table[0][0].strip().casefold() in {"text", "expected text", "value"}
            and any(len(row) == 1 and row[0].strip() for row in data_table[1:])
        )
        if pattern.fullmatch(text) and (not requires_table or table_is_valid):
            matches.append(records[binding_id])
    return matches

ActionType = str  # "navigate" | "fill_and_submit" | "fill" | "select_option" | "click" | "assert_visible" | "screenshot" | "unknown"


@dataclass
class Action:
    type: ActionType
    raw_text: str
    url: Optional[str] = None
    value: Optional[str] = None
    input_hint: Optional[str] = None
    target_hint: Optional[str] = None
    content_hint: Optional[str] = None
    content_items: Optional[list[str]] = None
    section_hint: Optional[str] = None
    source: str = "rule"  # "rule" | "llm_fallback"

    @staticmethod
    def from_llm_dict(raw_text: str, data: dict) -> "Action":
        return Action(
            type=data.get("type", "unknown"),
            raw_text=raw_text,
            url=data.get("url"),
            value=data.get("value"),
            input_hint=data.get("input_hint"),
            target_hint=data.get("target_hint"),
            content_hint=data.get("content_hint"),
            section_hint=data.get("section_hint"),
            source="llm_fallback",
        )


def _normalize_url(raw: str) -> str:
    raw = raw.strip().rstrip(".")
    if not re.match(r"^\w+://", raw):
        raw = f"https://{raw}"
    return raw


def _split_content_section(content: str) -> tuple[str, Optional[str]]:
    """'top 5 pixel phones in popular products section' -> (content, section)."""
    match = re.match(r"^(?P<content>.+?)\s+in\s+(?P<section>[^,]+?)\s*$", content, re.IGNORECASE)
    if match:
        return match.group("content").strip(), match.group("section").strip()
    return content.strip(), None


def interpret_step(raw_text: str) -> Action:
    text = raw_text.strip()

    m = _NAVIGATE_RE.match(text)
    if m:
        return Action(type="navigate", raw_text=raw_text, url=_normalize_url(m.group(1)))

    m = _ENTER_AND_CLICK_RE.match(text)
    if m:
        field_hint = (m.group("field") or "search").strip()
        return Action(
            type="fill_and_submit",
            raw_text=raw_text,
            value=m.group("value"),
            input_hint=field_hint,
            target_hint=m.group("target").strip(),
        )

    m = _ENTER_ONLY_RE.match(text)
    if m:
        return Action(
            type="fill",
            raw_text=raw_text,
            value=m.group("value"),
            input_hint=(m.group("field") or "input").strip(),
        )

    if _SCREENSHOT_RE.match(text):
        return Action(type="screenshot", raw_text=raw_text)

    m = _ASSERT_RE.match(text)
    if m:
        content, section = _split_content_section(m.group("content"))
        return Action(
            type="assert_visible",
            raw_text=raw_text,
            content_hint=content,
            section_hint=section,
        )

    m = _VERIFY_DISPLAY_RE.match(text)
    if m:
        return Action(
            type="assert_visible",
            raw_text=raw_text,
            content_hint=m.group("content").strip(),
        )

    m = _CLICK_RE.match(text)
    if m:
        return Action(type="click", raw_text=raw_text, target_hint=m.group(1).strip())

    return Action(type="unknown", raw_text=raw_text)


def interpret_gherkin_step(
    keyword_type: str,
    raw_text: str,
    data_table: list[list[str]] | None = None,
) -> Action:
    """Bind a Gherkin step expression to a supported framework action."""
    text = raw_text.strip().rstrip(".")

    match = _GHERKIN_NAVIGATE_RE.fullmatch(text)
    if match:
        return Action(type="navigate", raw_text=raw_text, url=_normalize_url(match.group("url")))

    match = _GHERKIN_FILL_RE.fullmatch(text)
    if match:
        return Action(
            type="fill",
            raw_text=raw_text,
            value=match.group("value"),
            input_hint=match.group("field"),
        )

    match = _GHERKIN_SELECT_RE.fullmatch(text)
    if match:
        return Action(
            type="select_option",
            raw_text=raw_text,
            value=match.group("value"),
            input_hint=match.group("field"),
        )

    match = _GHERKIN_CLICK_RE.fullmatch(text)
    if match:
        return Action(type="click", raw_text=raw_text, target_hint=match.group("target"))

    match = _GHERKIN_BUTTON_VISIBLE_RE.fullmatch(text)
    if match:
        return Action(type="assert_button_visible", raw_text=raw_text, target_hint=match.group("target"))

    match = _GHERKIN_ASSERT_RE.fullmatch(text)
    if match:
        return Action(type="assert_visible", raw_text=raw_text, content_hint=f'"{match.group("content")}"')

    if _GHERKIN_ASSERT_TABLE_RE.fullmatch(text) and data_table:
        header = [cell.strip().lower() for cell in data_table[0]]
        if len(header) == 1 and header[0] in {"text", "expected text", "value"}:
            content_items = [row[0].strip() for row in data_table[1:] if len(row) == 1 and row[0].strip()]
            if content_items:
                return Action(type="assert_visible", raw_text=raw_text, content_items=content_items)

    if _GHERKIN_SCREENSHOT_RE.fullmatch(text):
        return Action(type="screenshot", raw_text=raw_text)

    return Action(type="unknown", raw_text=raw_text)


@dataclass
class ElementAction:
    """A single element interaction - the unit of work the self-healing
    graph operates on. A Step can expand into more than one of these
    (e.g. fill_and_submit -> fill the input, then click submit)."""

    kind: str  # "input" | "clickable"
    op: str  # "fill" | "select_option" | "click"
    hint: str
    value: Optional[str] = None


def expand_to_element_actions(action: Action) -> list[ElementAction]:
    if action.type == "fill_and_submit":
        return [
            ElementAction(kind="input", op="fill", hint=action.input_hint or "search", value=action.value),
            ElementAction(kind="clickable", op="click", hint=action.target_hint or "search"),
        ]
    if action.type == "fill":
        return [ElementAction(kind="input", op="fill", hint=action.input_hint or "input", value=action.value)]
    if action.type == "select_option":
        return [ElementAction(kind="input", op="select_option", hint=action.input_hint or "dropdown", value=action.value)]
    if action.type == "click":
        return [ElementAction(kind="clickable", op="click", hint=action.target_hint or "")]
    return []
