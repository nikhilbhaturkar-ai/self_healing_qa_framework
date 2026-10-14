"""Deterministic locator generation - used both for the very first attempt at
finding an element and for regenerating candidates during self-healing.

No LLM involved anywhere in this module.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from typing import Optional

# Maps an HTML tag / input type to the ARIA role Playwright's get_by_role expects.
_TAG_ROLE_MAP = {
    "button": "button",
    "a": "link",
    "select": "combobox",
    "textarea": "textbox",
}
_INPUT_TYPE_ROLE_MAP = {
    "submit": "button",
    "button": "button",
    "image": "button",
    "text": "textbox",
    "search": "searchbox",
    "email": "textbox",
    "password": "textbox",
}

INPUT_KIND_TAGS = {"input", "textarea", "select"}
CLICKABLE_TAGS = {"button", "a"}


def _element_role(el: dict) -> Optional[str]:
    if el.get("role"):
        return el["role"]
    tag = el.get("tag")
    if tag == "input":
        return _INPUT_TYPE_ROLE_MAP.get(el.get("type") or "text", "textbox")
    return _TAG_ROLE_MAP.get(tag)


def _accessible_name(el: dict) -> str:
    return (el.get("aria_label") or el.get("placeholder") or el.get("text") or el.get("name") or "").strip()


def _is_input_kind(el: dict) -> bool:
    if el.get("tag") in INPUT_KIND_TAGS:
        if el.get("tag") == "input" and el.get("type") in ("submit", "button", "checkbox", "radio", "image"):
            return False
        return True
    role = el.get("role")
    return role in ("textbox", "searchbox", "combobox")


def _is_clickable_kind(el: dict) -> bool:
    if el.get("tag") in CLICKABLE_TAGS:
        return True
    if el.get("tag") == "input" and el.get("type") in ("submit", "button", "image"):
        return True
    role = el.get("role")
    return role in ("button", "link")


@dataclass
class Candidate:
    strategy: str  # data-testid | id | name | role_text | text | css_class
    selector: Optional[str] = None  # CSS selector, when applicable
    role: Optional[str] = None
    accessible_name: Optional[str] = None
    tag: Optional[str] = None
    text: Optional[str] = None
    visible: bool = True
    enabled: bool = True
    element: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "selector": self.selector,
            "role": self.role,
            "accessible_name": self.accessible_name,
            "tag": self.tag,
            "text": self.text,
            "visible": self.visible,
            "enabled": self.enabled,
        }


_STRATEGY_STABILITY = {
    "data-testid": 1.0,
    "id": 0.9,
    "name": 0.8,
    "role_text": 0.6,
    "title_contains": 0.65,
    "aria_label_contains": 0.65,
    "text": 0.45,
    "css_class": 0.3,
    "class_contains": 0.3,
}


def stability_weight(strategy: str) -> float:
    return _STRATEGY_STABILITY.get(strategy, 0.2)


def _candidates_for_element(el: dict, hint: str, kind: str) -> list[Candidate]:
    """An element can yield more than one candidate (attribute-based +
    role/text-based) so scoring can pick whichever is actually most robust."""
    tag = el.get("tag")
    role = _element_role(el)
    name = _accessible_name(el)
    candidates: list[Candidate] = []

    if el.get("test_id"):
        candidates.append(
            Candidate(
                strategy="data-testid",
                selector=f'[data-testid="{el["test_id"]}"], [data-test-id="{el["test_id"]}"]',
                role=role, accessible_name=name, tag=tag, text=el.get("text"),
                visible=el.get("visible", True), enabled=el.get("enabled", True), element=el,
            )
        )
    if el.get("id"):
        candidates.append(
            Candidate(
                strategy="id", selector=f'[id="{el["id"]}"]',
                role=role, accessible_name=name, tag=tag, text=el.get("text"),
                visible=el.get("visible", True), enabled=el.get("enabled", True), element=el,
            )
        )
    if el.get("name"):
        candidates.append(
            Candidate(
                strategy="name", selector=f'{tag}[name="{el["name"]}"]',
                role=role, accessible_name=name, tag=tag, text=el.get("text"),
                visible=el.get("visible", True), enabled=el.get("enabled", True), element=el,
            )
        )
    if kind == "clickable" and hint:
        contains_selector_value = json.dumps(hint, ensure_ascii=True)
        for attribute, value, strategy in (
            ("class", el.get("class_name"), "class_contains"),
            ("title", el.get("title"), "title_contains"),
            ("aria-label", el.get("aria_label"), "aria_label_contains"),
        ):
            if value and hint.casefold() in value.casefold():
                candidates.append(
                    Candidate(
                        strategy=strategy,
                        selector=f'{tag}[{attribute}*={contains_selector_value} i]',
                        role=role,
                        accessible_name=value,
                        tag=tag,
                        text=el.get("text"),
                        visible=el.get("visible", True),
                        enabled=el.get("enabled", True),
                        element=el,
                    )
                )
    if role and name:
        candidates.append(
            Candidate(
                strategy="role_text", selector=None,
                role=role, accessible_name=name, tag=tag, text=el.get("text"),
                visible=el.get("visible", True), enabled=el.get("enabled", True), element=el,
            )
        )
    if not candidates and name:
        candidates.append(
            Candidate(
                strategy="text", selector=None,
                role=role, accessible_name=name, tag=tag, text=el.get("text"),
                visible=el.get("visible", True), enabled=el.get("enabled", True), element=el,
            )
        )
    if not candidates and el.get("class_name"):
        first_class = el["class_name"].split()[0] if el["class_name"].split() else None
        if first_class:
            candidates.append(
                Candidate(
                    strategy="css_class", selector=f'{tag}.{first_class}',
                    role=role, accessible_name=name, tag=tag, text=el.get("text"),
                    visible=el.get("visible", True), enabled=el.get("enabled", True), element=el,
                )
            )
    return candidates


def _is_primary_for_kind(el: dict, kind: str) -> bool:
    """True for the element shapes that are the 'obvious' choice for a kind
    (a real <button>/submit input for clickable, a real <input>/<textarea>
    for input) as opposed to incidental clickable things like nav links.
    Used to stop unrelated but text-similar elements (e.g. a random link
    that happens to share characters with the hint) from crowding out the
    actually-correct element in the pre-scoring shortlist."""
    tag = el.get("tag")
    if kind == "input":
        return tag in ("input", "textarea", "select")
    if tag == "button":
        return True
    if tag == "input" and el.get("type") in ("submit", "button", "image"):
        return True
    return el.get("role") == "button"


def generate_candidates(snapshot: list[dict], kind: str, hint: str, top_k: int = 8) -> list[Candidate]:
    """kind: 'input' | 'clickable'. Returns candidates ranked by structural
    fit + rough text similarity to `hint` (a cheap pre-filter before the
    real weighted scoring in candidate_scoring.py, which also checks live
    uniqueness/visibility/stability)."""
    kind_filter = _is_input_kind if kind == "input" else _is_clickable_kind
    pool = [el for el in snapshot if kind_filter(el) and el.get("visible", True)]

    scored: list[tuple[float, Candidate]] = []
    for el in pool:
        name = _accessible_name(el)
        sim = difflib.SequenceMatcher(a=hint.lower(), b=name.lower()).ratio() if name else 0.0
        priority = (1.5 if _is_primary_for_kind(el, kind) else 0.0) + sim
        for cand in _candidates_for_element(el, hint, kind):
            scored.append((priority, cand))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [cand for _, cand in scored[:top_k]]


def candidate_from_dict(data: dict) -> Candidate:
    return Candidate(
        strategy=data["strategy"],
        selector=data.get("selector"),
        role=data.get("role"),
        accessible_name=data.get("accessible_name"),
        tag=data.get("tag"),
        text=data.get("text"),
        visible=data.get("visible", True),
        enabled=data.get("enabled", True),
    )


async def build_locator(page, candidate: Candidate):
    if candidate.selector:
        return page.locator(candidate.selector).first
    if candidate.role and candidate.accessible_name:
        return page.get_by_role(
            candidate.role, name=re.compile(re.escape(candidate.accessible_name), re.IGNORECASE)
        ).first
    if candidate.text:
        return page.get_by_text(re.compile(re.escape(candidate.text), re.IGNORECASE)).first
    return None


async def resolve_initial_locator(page, kind: str, hint: str):
    """First-attempt locator resolution using Playwright's own semantic
    locators, before any failure/healing has occurred."""
    pattern = re.compile(re.escape(hint), re.IGNORECASE)
    if kind == "input":
        probes = [
            lambda: page.get_by_placeholder(pattern),
            lambda: page.get_by_role("combobox", name=pattern),
            lambda: page.get_by_role("searchbox", name=pattern),
            lambda: page.get_by_role("textbox", name=pattern),
            lambda: page.get_by_label(pattern),
            lambda: page.locator('input[type="text"], input[type="search"], textarea'),
        ]
    else:
        probes = [
            lambda: page.get_by_role("button", name=pattern),
            lambda: page.get_by_role("link", name=pattern),
            lambda: page.get_by_text(pattern),
        ]

    for probe in probes:
        try:
            loc = probe().first
            if await loc.count() > 0:
                return loc
        except Exception:
            continue
    return None
