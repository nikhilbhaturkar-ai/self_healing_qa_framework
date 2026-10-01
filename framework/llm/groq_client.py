"""Thin Groq wrapper. This is the ONLY module in the framework that spends
LLM tokens, and it is only ever invoked from semantic_ranking.py (ambiguous
locator tie-breaks) and, as a last resort, step_interpretation fallback.

Every call is temperature=0, small max_tokens, strict JSON-only prompting,
and logged via `calls_made` so the report can surface exactly how many LLM
calls a run actually made (the token-minimization metric).
"""
from __future__ import annotations

import json
import logging
import re

from groq import Groq

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class GroqClient:
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to a .env file (see .env.example) before running."
            )
        self._client = Groq(api_key=api_key)
        self.model = model
        self.calls_made = 0
        self.total_prompt_chars = 0

    def _call(self, system: str, user: str, max_tokens: int = 200) -> str:
        self.calls_made += 1
        self.total_prompt_chars += len(system) + len(user)
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=max_tokens,
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def rank_locator_candidates(self, intent: str, candidates: list[dict]) -> dict:
        """candidates: compact list of {index, strategy, role, accessible_name, tag}.
        Returns {"best_index": int, "confidence": float}."""
        system = (
            "You pick which candidate UI element best matches an automation intent. "
            'Reply with ONLY compact JSON: {"best_index": <int>, "confidence": <0-1 float>}. '
            "No prose, no markdown."
        )
        user = f"Intent: {intent}\nCandidates: {json.dumps(candidates, separators=(',', ':'))}"
        raw = self._call(system, user, max_tokens=150)
        return self._parse_json(raw, default={"best_index": 0, "confidence": 0.5})

    def classify_step(self, step_text: str) -> dict:
        """Last-resort fallback when rule-based step parsing fails.
        Returns an Action-shaped dict."""
        system = (
            "Classify one plain-English QA test step into strict JSON with keys: "
            'type (one of "navigate","fill_and_submit","fill","click","assert_visible"), '
            "url, value, input_hint, target_hint, content_hint, section_hint "
            "(use null for fields that don't apply). Reply with ONLY the JSON object."
        )
        raw = self._call(system, f"Step: {step_text}", max_tokens=250)
        return self._parse_json(raw, default={"type": "unknown"})

    @staticmethod
    def _parse_json(raw: str, default: dict) -> dict:
        match = _JSON_RE.search(raw)
        if not match:
            logger.warning("Groq response had no parseable JSON (likely truncated): %r", raw)
            return default
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("Groq response JSON failed to parse (likely truncated): %r", raw)
            return default
