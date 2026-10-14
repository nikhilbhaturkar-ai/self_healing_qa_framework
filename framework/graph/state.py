"""LangGraph state for the per-element self-healing subgraph.

One graph invocation = one element interaction (fill or click on one
locator). Only JSON-serializable data lives here; the live Playwright
Page/Browser and the Chroma/Groq clients are held by NodeContext (a closure
capture), never put into state.
"""
from __future__ import annotations

from typing import Optional, TypedDict


class GraphState(TypedDict, total=False):
    url_pattern: str
    kind: str  # "input" | "clickable"
    hint: str
    op: str  # "fill" | "click"
    value: Optional[str]
    intent_text: str

    initial_success: bool
    locator_strategy: str
    old_descriptor: str

    dom_snapshot: list[dict]
    candidates: list[dict]
    historical_success_rate: float
    skip_llm: bool
    used_llm: bool

    chosen_candidate: Optional[dict]
    confidence: float
    valid: bool

    decision: str  # "auto_heal" | "flag" | "no_heal"
    applied_success: bool
    healing_event: Optional[dict]
    final_success: bool
