"""Wires the LangGraph StateGraph mapping directly onto the architecture
diagram's boxes 1-4 (the self-healing decision loop for a single element
interaction). Box 5 (memory) and 6 (reporting) are updated as a side effect
of apply_reexecute / by the ScenarioRunner respectively.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from framework.graph.context import NodeContext
from framework.graph.nodes.apply_reexecute import make_apply_reexecute
from framework.graph.nodes.candidate_generation import make_candidate_generation
from framework.graph.nodes.candidate_scoring import make_candidate_scoring
from framework.graph.nodes.capture_context import make_capture_context
from framework.graph.nodes.confidence_decision import make_confidence_decision
from framework.graph.nodes.context_understanding import make_context_understanding
from framework.graph.nodes.execute_step import make_execute_step
from framework.graph.nodes.semantic_ranking import make_semantic_ranking
from framework.graph.nodes.validation import make_validation
from framework.graph.state import GraphState


def build_healing_graph(ctx: NodeContext):
    graph = StateGraph(GraphState)

    graph.add_node("execute_step", make_execute_step(ctx))
    graph.add_node("capture_context", make_capture_context(ctx))
    graph.add_node("context_understanding", make_context_understanding(ctx))
    graph.add_node("candidate_generation", make_candidate_generation(ctx))
    graph.add_node("candidate_scoring", make_candidate_scoring(ctx))
    graph.add_node("semantic_ranking", make_semantic_ranking(ctx))
    graph.add_node("validation", make_validation(ctx))
    graph.add_node("confidence_decision", make_confidence_decision(ctx))
    graph.add_node("apply_reexecute", make_apply_reexecute(ctx))

    graph.add_edge(START, "execute_step")
    graph.add_conditional_edges(
        "execute_step",
        lambda s: "done" if s.get("initial_success") else "heal",
        {"done": END, "heal": "capture_context"},
    )
    graph.add_edge("capture_context", "context_understanding")
    graph.add_edge("context_understanding", "candidate_generation")
    graph.add_edge("candidate_generation", "candidate_scoring")
    graph.add_conditional_edges(
        "candidate_scoring",
        lambda s: "skip" if s.get("skip_llm") else "rank",
        {"skip": "validation", "rank": "semantic_ranking"},
    )
    graph.add_edge("semantic_ranking", "validation")
    graph.add_edge("validation", "confidence_decision")
    graph.add_conditional_edges(
        "confidence_decision",
        lambda s: "apply" if s["decision"] in ("auto_heal", "flag") else "fail",
        {"apply": "apply_reexecute", "fail": END},
    )
    graph.add_edge("apply_reexecute", END)

    return graph.compile()
