from __future__ import annotations

import json
from pathlib import Path


def write_json_report(report: dict, out_path: Path) -> None:
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
