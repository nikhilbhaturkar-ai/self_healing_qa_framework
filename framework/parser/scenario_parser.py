"""Parses a plain-English scenario file into structured Scenario/Step objects.

Expected format (one or more blocks)::

    Scenario 1: <title>
    - <step text>
    - <step text>

No LLM involved - this is pure regex/string splitting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SCENARIO_HEADER_RE = re.compile(r"^Scenario\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)
_STEP_LINE_RE = re.compile(r"^[-*]\s*(.+)$")


@dataclass
class Step:
    index: int
    raw_text: str


@dataclass
class Scenario:
    index: int
    title: str
    steps: list[Step] = field(default_factory=list)


def parse_scenarios(text: str) -> list[Scenario]:
    scenarios: list[Scenario] = []
    current: Scenario | None = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        header_match = _SCENARIO_HEADER_RE.match(line)
        if header_match:
            if current is not None:
                scenarios.append(current)
            current = Scenario(index=int(header_match.group(1)), title=header_match.group(2).strip())
            continue

        step_match = _STEP_LINE_RE.match(line)
        if step_match and current is not None:
            current.steps.append(Step(index=len(current.steps) + 1, raw_text=step_match.group(1).strip()))

    if current is not None:
        scenarios.append(current)

    if not scenarios:
        raise ValueError("No scenarios found. Expected 'Scenario N: <title>' headers with '-' step lines.")

    return scenarios


def parse_scenarios_file(path: str | Path) -> list[Scenario]:
    return parse_scenarios(Path(path).read_text(encoding="utf-8"))
