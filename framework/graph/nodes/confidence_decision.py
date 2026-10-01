"""Stage 3.6 - Confidence Decision: buckets into auto-heal / heal & flag /
do-not-heal using the thresholds from Settings."""
from __future__ import annotations

from framework.graph.context import NodeContext
from framework.graph.state import GraphState


def make_confidence_decision(ctx: NodeContext):
    async def confidence_decision(state: GraphState) -> dict:
        if not state.get("valid"):
            return {"decision": "no_heal"}

        confidence = state.get("confidence", 0.0)
        if confidence >= ctx.settings.confidence_auto_heal:
            decision = "auto_heal"
        elif confidence >= ctx.settings.confidence_flag:
            decision = "flag"
        else:
            decision = "no_heal"
        return {"decision": decision}

    return confidence_decision
