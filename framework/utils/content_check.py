"""Keyword-containment content assertion (used for 'X should show Y' steps).

This is deliberately NOT locator-based - it's a fuzzy real-page content
check against live page text, appropriate for unpredictable result pages
(e.g. Google SERPs) where an exact element locator would be brittle and
where the diagram's self-healing scope (element locators for actions) does
not apply. No LLM involved.
"""
from __future__ import annotations

import re

_STOPWORDS = {"top", "and", "the", "for", "with", "should", "show", "display", "contain", "in", "of", "a", "an"}


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    return [w for w in words if len(w) >= 2 and w not in _STOPWORDS]


async def assert_content_visible(page, content_hint: str, section_hint: str | None = None) -> dict:
    """Returns {"passed": bool, "matched": [...], "missing": [...]}.

    Only `content_hint` (the actual expected content, e.g. "top 5 google
    pixel phones") is required to appear in the page text. `section_hint`
    (e.g. "popular products section") describes *where* to look, not
    literal page content - most of its words are UI-structure metalanguage
    ("section", "panel", "area"...) that would never appear verbatim on any
    real page, so it is reported for context only and never required.
    """
    keywords = _keywords(content_hint)
    if not keywords:
        return {"passed": False, "matched": [], "missing": [], "reason": "no keywords extracted"}

    try:
        body_text = (await page.inner_text("body")).lower()
    except Exception:
        body_text = ""

    matched = [k for k in keywords if k in body_text]
    missing = [k for k in keywords if k not in body_text]
    fraction = len(matched) / len(keywords)
    passed = fraction >= 0.5
    return {
        "passed": passed,
        "matched": matched,
        "missing": missing,
        "match_fraction": round(fraction, 2),
        "section_hint": section_hint,
    }
