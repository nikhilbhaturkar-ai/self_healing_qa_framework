"""Stage 1 (Test Execution) - first attempt at locating + acting on an
element. Checks the Locator Memory cache first (near-zero cost reuse of a
previously healed locator), then falls back to Playwright's own semantic
locators. Only on failure does the graph route into self-healing.
"""
from __future__ import annotations

from framework.browser.locator_strategies import Candidate, build_locator
from framework.graph.context import NodeContext
from framework.graph.state import GraphState


def make_execute_step(ctx: NodeContext):
    async def execute_step(state: GraphState) -> dict:
        url_pattern, kind, hint = state["url_pattern"], state["kind"], state["hint"]
        op, value = state["op"], state.get("value")

        cached = ctx.store.lookup(url_pattern, kind, hint, n_results=1)
        if cached and cached[0]["similarity"] >= 0.85 and cached[0].get("selector"):
            hit = cached[0]
            candidate = Candidate(
                strategy="chroma_cache",
                selector=hit.get("selector") or None,
                role=hit.get("role") or None,
                accessible_name=hit.get("accessible_name") or None,
            )
            locator = await build_locator(ctx.driver.page, candidate)
            if locator is not None and await ctx.driver.act(locator, op, value):
                return {
                    "initial_success": True,
                    "final_success": True,
                    "locator_strategy": "chroma_cache",
                }

        ok = await ctx.driver.resolve_and_act(kind, hint, op, value)
        if ok:
            return {
                "initial_success": True,
                "final_success": True,
                "locator_strategy": "playwright_semantic",
            }

        return {
            "initial_success": False,
            "old_descriptor": f"initial semantic locator for {kind}:'{hint}'",
            "intent_text": f"{op} on {kind} matching '{hint}'",
        }

    return execute_step
