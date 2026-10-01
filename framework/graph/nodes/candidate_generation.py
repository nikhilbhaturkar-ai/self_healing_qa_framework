"""Stage 3.2 - Candidate Generation (deterministic heuristics only)."""
from __future__ import annotations

from framework.browser.locator_strategies import generate_candidates
from framework.graph.context import NodeContext
from framework.graph.state import GraphState


def make_candidate_generation(ctx: NodeContext):
    async def candidate_generation(state: GraphState) -> dict:
        candidates = generate_candidates(state["dom_snapshot"], state["kind"], state["hint"], top_k=8)
        return {"candidates": [c.to_dict() for c in candidates]}

    return candidate_generation
