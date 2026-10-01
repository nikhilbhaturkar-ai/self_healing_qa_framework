"""Stage 3.4 - Semantic Ranking (LLM).

The ONLY node in the whole framework that calls Groq, and only reached when
candidate_scoring's deterministic gate could not confidently pick a winner.
Sends just the top few candidates' minimal attributes - never the raw DOM.
"""
from __future__ import annotations

from framework.graph.context import NodeContext
from framework.graph.state import GraphState

MAX_CANDIDATES_TO_LLM = 6


def make_semantic_ranking(ctx: NodeContext):
    async def semantic_ranking(state: GraphState) -> dict:
        candidates = state["candidates"][:MAX_CANDIDATES_TO_LLM]
        if not candidates:
            return {"chosen_candidate": None, "confidence": 0.0, "used_llm": False}

        compact = [
            {
                "index": i,
                "strategy": c.get("strategy"),
                "role": c.get("role"),
                "accessible_name": c.get("accessible_name"),
                "tag": c.get("tag"),
                "deterministic_score": c.get("score"),
            }
            for i, c in enumerate(candidates)
        ]
        result = ctx.groq.rank_locator_candidates(state["intent_text"], compact)
        best_index = result.get("best_index", 0)
        if not isinstance(best_index, int) or not (0 <= best_index < len(candidates)):
            best_index = 0
        confidence = result.get("confidence", candidates[best_index].get("score", 0.5))
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = candidates[best_index].get("score", 0.5)
        confidence = max(0.0, min(1.0, confidence))

        return {"chosen_candidate": candidates[best_index], "confidence": confidence, "used_llm": True}

    return semantic_ranking
