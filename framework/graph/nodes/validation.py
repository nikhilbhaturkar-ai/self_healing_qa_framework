"""Stage 3.5 - Validation Engine: re-checks the chosen candidate live in the
DOM before it's ever applied."""
from __future__ import annotations

from framework.browser.locator_strategies import build_locator, candidate_from_dict
from framework.graph.context import NodeContext
from framework.graph.state import GraphState

_EXPECTED_TAGS = {
    "input": {"input", "textarea", "select"},
    "clickable": {"button", "a", "input"},
}


def make_validation(ctx: NodeContext):
    async def validation(state: GraphState) -> dict:
        chosen = state.get("chosen_candidate")
        confidence = state.get("confidence")
        used_llm = state.get("used_llm", False)

        if chosen is None:
            candidates = state.get("candidates") or []
            if not candidates:
                return {"valid": False, "confidence": 0.0, "chosen_candidate": None}
            chosen = candidates[0]
            confidence = chosen.get("score", 0.0)

        candidate = candidate_from_dict(chosen)
        locator = await build_locator(ctx.driver.page, candidate)
        if locator is None:
            return {"valid": False, "confidence": 0.0, "chosen_candidate": chosen, "used_llm": used_llm}

        try:
            count = await locator.count()
        except Exception:
            count = 0

        if count == 0:
            return {"valid": False, "confidence": 0.0, "chosen_candidate": chosen, "used_llm": used_llm}

        try:
            visible = await locator.first.is_visible()
            enabled = await locator.first.is_enabled()
        except Exception:
            visible, enabled = False, False

        correct_type = chosen.get("tag") in _EXPECTED_TAGS.get(state["kind"], set())

        valid = count >= 1 and visible and enabled
        adjusted = confidence
        if count > 1:
            adjusted *= 0.7
        if not correct_type:
            adjusted *= 0.85
        if not visible or not enabled:
            adjusted = 0.0
            valid = False

        return {
            "valid": valid,
            "confidence": round(max(0.0, min(1.0, adjusted)), 4),
            "chosen_candidate": chosen,
            "used_llm": used_llm,
        }

    return validation

