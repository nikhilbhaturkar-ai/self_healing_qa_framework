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

ActionType = str  # "navigate" | "fill_and_submit" | "fill" | "click" | "assert_visible" | "unknown"


@dataclass
class Action:
    type: ActionType
    raw_text: str
    url: Optional[str] = None
    value: Optional[str] = None
    input_hint: Optional[str] = None
    target_hint: Optional[str] = None
    content_hint: Optional[str] = None
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


@dataclass
class ElementAction:
    """A single element interaction - the unit of work the self-healing
    graph operates on. A Step can expand into more than one of these
    (e.g. fill_and_submit -> fill the input, then click submit)."""

    kind: str  # "input" | "clickable"
    op: str  # "fill" | "click"
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
    if action.type == "click":
        return [ElementAction(kind="clickable", op="click", hint=action.target_hint or "")]
    return []
