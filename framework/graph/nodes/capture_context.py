"""Stage 2 - Failure Detection & Context Capture."""
from __future__ import annotations

from framework.graph.context import NodeContext
from framework.graph.state import GraphState


def make_capture_context(ctx: NodeContext):
    async def capture_context(state: GraphState) -> dict:
        snapshot = await ctx.driver.snapshot()
        return {"dom_snapshot": snapshot}

    return capture_context
