"""Stage 4 - Apply & Re-execute: swaps in the healed locator, re-runs the
original action, and records the outcome into Locator Memory (stage 5)."""
from __future__ import annotations

from framework.browser.locator_strategies import build_locator, candidate_from_dict
from framework.graph.context import NodeContext
from framework.graph.state import GraphState


def make_apply_reexecute(ctx: NodeContext):
    async def apply_reexecute(state: GraphState) -> dict:
        chosen = state["chosen_candidate"]
        candidate = candidate_from_dict(chosen)
        locator = await build_locator(ctx.driver.page, candidate)

        success = False
        if locator is not None:
            success = await ctx.driver.act(locator, state["op"], state.get("value"))

        ctx.store.record_heal(
            url_pattern=state["url_pattern"],
            kind=state["kind"],
            hint=state["hint"],
            old_descriptor=state["old_descriptor"],
            candidate=chosen,
            confidence=state.get("confidence", 0.0),
            decision=state["decision"],
            applied_success=success,
        )

        healing_event = {
            "hint": state["hint"],
            "kind": state["kind"],
            "old_locator": state["old_descriptor"],
            "new_locator": chosen.get("selector") or chosen.get("accessible_name") or "",
            "strategy": chosen.get("strategy"),
            "confidence": state.get("confidence", 0.0),
            "decision": state["decision"],
            "used_llm": state.get("used_llm", False),
            "applied_success": success,
        }
        return {"applied_success": success, "final_success": success, "healing_event": healing_event}

    return apply_reexecute
