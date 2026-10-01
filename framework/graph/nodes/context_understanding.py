"""Stage 3.1 - Context Understanding.

Purely rule-based: assembles the structured intent from data already in
state (step text, page, previous locator) - no LLM cost.
"""
from __future__ import annotations

from framework.graph.context import NodeContext
from framework.graph.state import GraphState


def make_context_understanding(ctx: NodeContext):
    async def context_understanding(state: GraphState) -> dict:
        rate = ctx.store.success_rate_for(state["url_pattern"], state["kind"], state["hint"])
        return {"historical_success_rate": rate}

    return context_understanding
