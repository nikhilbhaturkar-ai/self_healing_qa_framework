"""Stage 3.3 - Candidate Scoring (deterministic weighted model).

score = 0.25*uniqueness + 0.15*visibility + 0.20*stability
      + 0.20*semantic_match + 0.10*historical_success + 0.10*action_suitability

Also decides the token-minimization gate: if the top candidate clearly wins,
`skip_llm=True` and stage 3.4 (the only LLM call in the framework) is
bypassed entirely.
"""
from __future__ import annotations

import difflib

from framework.browser.locator_strategies import build_locator, candidate_from_dict, stability_weight
from framework.graph.context import NodeContext
from framework.graph.state import GraphState

GATE_MIN_SCORE = 0.80
GATE_MARGIN = 0.12

_EXPECTED_TAGS = {
    "input": {"input", "textarea", "select"},
    "clickable": {"button", "a", "input"},
}


async def _uniqueness_and_validity(page, candidate_dict: dict) -> tuple[float, int]:
    candidate = candidate_from_dict(candidate_dict)
    locator = await build_locator(page, candidate)
    if locator is None:
        return 0.0, 0
    try:
        count = await locator.count()
    except Exception:
        return 0.0, 0
    if count == 0:
        return 0.0, 0
    if count == 1:
        return 1.0, 1
    return 1.0 / count, count


def make_candidate_scoring(ctx: NodeContext):
    async def candidate_scoring(state: GraphState) -> dict:
        hint = state["hint"]
        kind = state["kind"]
        historical = state.get("historical_success_rate", 0.0)
        scored = []

        for cand in state["candidates"]:
            uniqueness, count = await _uniqueness_and_validity(ctx.driver.page, cand)
            visibility = 1.0 if cand.get("visible", True) else 0.0
            stability = stability_weight(cand.get("strategy", ""))
            name = cand.get("accessible_name") or cand.get("text") or ""
            semantic_match = difflib.SequenceMatcher(a=hint.lower(), b=name.lower()).ratio() if name else 0.0
            suitable = cand.get("tag") in _EXPECTED_TAGS.get(kind, set())
            action_suitability = 1.0 if suitable else 0.5

            score = (
                0.25 * uniqueness
                + 0.15 * visibility
                + 0.20 * stability
                + 0.20 * semantic_match
                + 0.10 * historical
                + 0.10 * action_suitability
            )
            scored.append({**cand, "score": round(score, 4), "match_count": count})

        scored.sort(key=lambda c: c["score"], reverse=True)

        skip_llm = False
        if scored:
            top = scored[0]["score"]
            second = scored[1]["score"] if len(scored) > 1 else 0.0
            if top >= GATE_MIN_SCORE and (len(scored) == 1 or (top - second) >= GATE_MARGIN):
                skip_llm = True

        return {"candidates": scored, "skip_llm": skip_llm}

    return candidate_scoring
