"""Keyword-containment content assertion (used for 'X should show Y' steps).

This is deliberately NOT locator-based - it's a fuzzy real-page content
check against live page text, appropriate for unpredictable result pages
(e.g. Google SERPs) where an exact element locator would be brittle and
where the diagram's self-healing scope (element locators for actions) does
not apply. No LLM involved.
"""
from __future__ import annotations

import re

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

_STOPWORDS = {"top", "and", "the", "for", "with", "should", "show", "display", "contain", "in", "of", "a", "an"}


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    return [w for w in words if len(w) >= 2 and w not in _STOPWORDS]


def _quoted_phrases(text: str) -> list[str]:
    return [phrase.strip() for phrase in re.findall(r'"([^"]+)"', text) if phrase.strip()]


def _normalize_dashes(text: str) -> str:
    return text.translate(str.maketrans({chr(codepoint): "-" for codepoint in (*range(0x2010, 0x2016), 0x2212)}))


def _phrase_pattern(phrase: str) -> str:
    parts = re.split(r"(\s+)", _normalize_dashes(phrase).strip())
    pattern = []
    for part in parts:
        if re.fullmatch(r"\s+", part):
            pattern.append(r"[\s\-]*")
        else:
            chunks = re.split(r"([\-]+)", part)
            pattern.extend(
                r"[\-]+" if re.fullmatch(r"[\-]+", chunk)
                else re.escape(chunk)
                for chunk in chunks
                if chunk
            )
    return "".join(pattern)


async def assert_content_visible(
    page,
    content_hint: str | list[str],
    section_hint: str | None = None,
    timeout_ms: int = 15000,
) -> dict:
    """Returns {"passed": bool, "matched": [...], "missing": [...]}.

    Only `content_hint` (the actual expected content, e.g. "top 5 google
    pixel phones") is required to appear in the page text. `section_hint`
    (e.g. "popular products section") describes *where* to look, not
    literal page content - most of its words are UI-structure metalanguage
    ("section", "panel", "area"...) that would never appear verbatim on any
    real page, so it is reported for context only and never required.
    """
    phrases = content_hint if isinstance(content_hint, list) else _quoted_phrases(content_hint)
    if phrases:
        expected = [_phrase_pattern(phrase) for phrase in phrases]
        try:
            await page.wait_for_function(
                """({ expected }) => {
                    const text = (document.body?.innerText || '').replace(/[\\u2010-\\u2015\\u2212]/g, '-');
                    return expected.every(pattern => new RegExp(pattern).test(text));
                }""",
                arg={"expected": expected},
                timeout=timeout_ms,
            )
        except PlaywrightTimeoutError:
            pass

        try:
            body_text = _normalize_dashes(await page.inner_text("body"))
        except Exception:
            body_text = ""
        matched = [phrase for phrase, pattern in zip(phrases, expected) if re.search(pattern, body_text)]
        missing = [phrase for phrase, pattern in zip(phrases, expected) if not re.search(pattern, body_text)]
        return {
            "passed": not missing,
            "matched": matched,
            "missing": missing,
            "match_fraction": round(len(matched) / len(expected), 2),
            "section_hint": section_hint,
        }

    if isinstance(content_hint, list):
        content_hint = " ".join(content_hint)
    keywords = _keywords(content_hint)
    if not keywords:
        return {"passed": False, "matched": [], "missing": [], "reason": "no keywords extracted"}

    try:
        await page.wait_for_function(
            """({ keywords }) => {
                const text = (document.body?.innerText || '').toLowerCase();
                const matched = keywords.filter(keyword => text.includes(keyword));
                return matched.length / keywords.length >= 0.5;
            }""",
            arg={"keywords": keywords},
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        pass

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
