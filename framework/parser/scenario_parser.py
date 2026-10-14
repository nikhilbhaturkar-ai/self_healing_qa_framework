"""Parses Gherkin features or legacy text scenarios into Scenario/Step objects.

Gherkin `.feature` files use the official parser/compiler. Legacy `.txt` files
retain the original format::

    Scenario 1: <title>
    - <step text>
    - <step text>

Feature outlines and backgrounds are expanded by the Gherkin compiler.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from gherkin import Compiler, Parser

_SCENARIO_HEADER_RE = re.compile(r"^Scenario\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)
_STEP_LINE_RE = re.compile(r"^[-*]\s*(.+)$")


@dataclass
class Step:
    index: int
    raw_text: str
    keyword_type: str | None = None
    data_table: list[list[str]] | None = None


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
    scenario_path = Path(path)
    text = scenario_path.read_text(encoding="utf-8")
    if scenario_path.suffix.lower() != ".feature":
        return parse_scenarios(text)

    document = Parser().parse(text)
    document["uri"] = scenario_path.as_posix()
    pickles = Compiler().compile(document)
    scenarios = [
        Scenario(
            index=index,
            title=pickle["name"],
            steps=[
                Step(
                    index=step_index,
                    raw_text=step["text"],
                    keyword_type=step["type"],
                    data_table=[
                        [cell["value"] for cell in row["cells"]]
                        for row in step.get("argument", {}).get("dataTable", {}).get("rows", [])
                    ] or None,
                )
                for step_index, step in enumerate(pickle["steps"], 1)
            ],
        )
        for index, pickle in enumerate(pickles, 1)
    ]
    if not scenarios:
        raise ValueError(f"No scenarios found in Gherkin feature: {scenario_path}")
    return scenarios
