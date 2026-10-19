"""Load and resolve explicit Playwright locators configured by feature target."""
from __future__ import annotations

import json
from typing import Any

from config import ROOT_DIR

CUSTOM_LOCATORS_PATH = ROOT_DIR / "custom_locators.json"


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _build_locator(page: Any, definition: dict[str, Any]):
    by = definition.get("by")
    value = definition.get("value")
    if not isinstance(by, str) or not isinstance(value, str) or not value:
        raise ValueError("Each custom locator requires non-empty string 'by' and 'value' fields")

    by = by.casefold()
    if by == "css":
        return page.locator(value)
    if by == "xpath":
        return page.locator(f"xpath={value}")
    if by == "text":
        return page.get_by_text(value, exact=True)
    if by == "label":
        return page.get_by_label(value, exact=True)
    if by == "placeholder":
        return page.get_by_placeholder(value, exact=True)
    if by in {"test_id", "testid"}:
        return page.get_by_test_id(value)
    if by == "role":
        name = definition.get("name")
        return page.get_by_role(value, name=name, exact=True)

    raise ValueError(f"Unsupported custom locator strategy {by!r}")


async def resolve_custom_locator(page: Any, op: str, hint: str):
    """Return (configured, unique locator); configured entries are authoritative."""
    if not CUSTOM_LOCATORS_PATH.exists():
        return False, None

    with CUSTOM_LOCATORS_PATH.open(encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config, dict):
        raise ValueError("custom_locators.json must contain a JSON object")

    entries = config.get(_normalize(op), {})
    if not isinstance(entries, dict):
        raise ValueError(f"Custom locator section for {op!r} must be a JSON object")

    definition = next(
        (
            item
            for target, item in entries.items()
            if isinstance(target, str) and _normalize(target) == _normalize(hint)
        ),
        None,
    )
    if definition is None:
        return False, None
    if not isinstance(definition, dict):
        raise ValueError(f"Custom locator for {op!r} target {hint!r} must be an object")

    locator = _build_locator(page, definition)
    if await locator.count() != 1:
        return True, None
    return True, locator