"""Stage 6 - Reporting & Observability. Renders a single self-contained HTML
file (inline CSS/JS, no external assets) covering every executed scenario,
step, and healing event, plus the token-minimization/analytics summary.
"""
from __future__ import annotations

import html
from pathlib import Path

_STATUS_COLORS = {"pass": "#16a34a", "fail": "#dc2626", "skipped": "#6b7280"}


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _badge(status: str) -> str:
    color = _STATUS_COLORS.get(status, "#6b7280")
    return f'<span class="badge" style="background:{color}">{_esc(status.upper())}</span>'


def _value_table(rows: list[tuple[str, object]], class_name: str = "data-table") -> str:
  if not rows:
    return '<p class="empty-state">No values to display.</p>'
  body = "".join(
    f"<tr><th scope=\"row\">{_esc(label)}</th><td>{_esc(value)}</td></tr>"
    for label, value in rows
  )
  return f'<table class="{class_name}"><tbody>{body}</tbody></table>'


def _list_table(values: list) -> str:
  if not values:
    return '<p class="empty-state">None</p>'
  rows = "".join(f'<tr><td>{index}</td><td>{_esc(value)}</td></tr>' for index, value in enumerate(values, 1))
  return f'<table class="list-table"><thead><tr><th>#</th><th>Text</th></tr></thead><tbody>{rows}</tbody></table>'


def _execution_detail_html(detail: object) -> str:
  if isinstance(detail, dict):
    rows = []
    sections = []
    for key, value in detail.items():
      if key in {"matched", "missing"} and isinstance(value, list):
        sections.append(
          f"<details class=\"value-section\"><summary>{_esc(key.title())} ({len(value)})</summary>"
          f"{_list_table(value)}</details>"
        )
      elif isinstance(value, (list, dict)):
        rows.append((key.replace("_", " ").title(), json_display(value)))
      else:
        rows.append((key.replace("_", " ").title(), value))
    return _value_table(rows) + "".join(sections)
  if detail is None:
    return '<p class="empty-state">No execution detail.</p>'
  return _value_table([("Result", detail)])


def json_display(value: object) -> str:
  if isinstance(value, dict):
    return "; ".join(f"{key}: {item}" for key, item in value.items())
  return ", ".join(str(item) for item in value)


def _healing_event_html(event: dict, index: int) -> str:
  rows = [(key.replace("_", " ").title(), value) for key, value in event.items()]
  decision_color = {"auto_heal": "#18794e", "flag": "#a15c00", "no_heal": "#b42318"}.get(
    event.get("decision"), "#53615d"
  )
  event_table = _value_table(rows, "data-table healing-table")
  return f"""
  <details class="healing-event">
    <summary>Healing event {index}: {_esc(event.get('hint', 'Locator update'))}
    <span class="decision" style="color:{decision_color}">{_esc(event.get('decision', ''))}</span>
    </summary>
    {event_table}
  </details>
  """


def _step_html(step: dict) -> str:
    status = step.get("status", "unknown")
    healing_events = step.get("healing_events", [])
    heals = "".join(_healing_event_html(event, index) for index, event in enumerate(healing_events, 1))
    if not heals:
        heals = '<p class="empty-state">No AI healing activity for this step.</p>'
    return f"""
    <details class="step">
      <summary class="step-head">{_badge(status)} <span class="step-text">{_esc(step.get('text', ''))}</span></summary>
      <div class="step-content">
        <details class="report-section execution-section">
          <summary>Execution</summary>
          {_value_table([("Action type", step.get("action_type", "")), ("Status", status)])}
          {_execution_detail_html(step.get("detail"))}
        </details>
        <details class="report-section healing-section">
          <summary>AI Healing ({len(healing_events)} event{'s' if len(healing_events) != 1 else ''})</summary>
          {heals}
        </details>
      </div>
    </details>
    """


def _scenario_html(scenario: dict) -> str:
    steps = "".join(_step_html(s) for s in scenario["steps"])
    screenshots = scenario.get("screenshots", [])
    screenshot_gallery = "".join(
        f'<figure class="screenshot"><img src="{_esc(item["path"])}" alt="Screenshot after step {_esc(item.get("step", ""))}" loading="lazy">'
        f'<figcaption>Step {_esc(item.get("step", ""))}: {_esc(item.get("text", ""))}</figcaption></figure>'
        for item in screenshots
    )
    screenshot_section = (
        f'<section class="scenario-screenshots"><h3>Screenshots ({len(screenshots)})</h3>'
        f'<div class="screenshot-gallery">{screenshot_gallery}</div></section>'
        if screenshots
        else ""
    )
    return f"""
    <details class="scenario">
      <summary class="scenario-head">
        {_badge(scenario.get('status', 'unknown'))}
        <span class="scenario-title">Scenario {_esc(scenario.get('index', ''))}: {_esc(scenario.get('title', ''))}</span>
        <span class="scenario-count">{len(scenario['steps'])} steps</span>
      </summary>
      <div class="steps">{steps}</div>
      {screenshot_section}
    </details>
    """


def render_html_report(report: dict) -> str:
    scenarios = report["scenarios"]
    total = len(scenarios)
    passed = sum(1 for s in scenarios if s["status"] == "pass")
    failed = total - passed
    analytics = report["analytics"]

    scenarios_html = "".join(_scenario_html(s) for s in scenarios)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Self-Healing QA Report</title>
<style>
  :root {{ color-scheme: light; --ink:#172c2a; --muted:#60716e; --line:#d7e1dd; --paper:#fff; --wash:#f2f6f3; --mint:#e5f3ec; --amber:#fff5df; --teal:#126b60; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Segoe UI", sans-serif; background:var(--wash); color:var(--ink); margin:0; padding:clamp(16px, 3vw, 36px); }}
  main {{ max-width:1120px; margin:0 auto; }}
  h1 {{ margin:0 0 4px; font-size:24px; font-weight:700; }}
  .subtitle {{ color:var(--muted); margin-bottom:24px; font-size:13px; }}
  .summary {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:24px; }}
  .card {{ background:var(--paper); border:1px solid var(--line); border-radius:6px; padding:12px 15px; min-width:0; }}
  .card .label {{ font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
  .card .value {{ font-size:21px; font-weight:700; margin-top:4px; }}
  .scenario {{ background:var(--paper); border:1px solid var(--line); border-radius:6px; margin-bottom:12px; overflow:hidden; }}
  summary {{ cursor:pointer; }}
  summary:focus-visible {{ outline:3px solid #63a99a; outline-offset:2px; }}
  .scenario-head {{ min-height:54px; padding:12px 16px; display:flex; align-items:center; gap:10px; background:#eaf2ee; list-style:none; }}
  summary::-webkit-details-marker {{ display:none; }}
  summary::before {{ content:"+"; color:var(--teal); font-size:18px; font-weight:600; width:16px; flex:none; }}
  details[open] > summary::before {{ content:"−"; }}
  .scenario-title {{ font-weight:650; font-size:14px; min-width:0; }}
  .scenario-count {{ margin-left:auto; color:var(--muted); font-size:12px; white-space:nowrap; }}
  .steps {{ padding:4px 16px 12px; }}
  .step {{ border-bottom:1px solid var(--line); }}
  .step:last-child {{ border-bottom:0; }}
  .step-head {{ min-height:46px; display:flex; align-items:center; gap:10px; list-style:none; }}
  .step-text {{ font-size:13px; line-height:1.5; overflow-wrap:anywhere; }}
  .badge {{ color:#fff; font-size:10px; font-weight:700; padding:3px 7px; border-radius:3px; flex:none; }}
  .step-content {{ padding:0 0 12px 26px; }}
  .report-section {{ margin-top:8px; border:1px solid var(--line); border-radius:5px; overflow:hidden; }}
  .report-section > summary {{ padding:9px 11px; background:#f5f8f6; color:var(--ink); font-size:12px; font-weight:700; list-style:none; }}
  .report-section > summary::before {{ display:inline-block; width:20px; }}
  .execution-section > summary {{ border-left:3px solid var(--teal); }}
  .healing-section > summary {{ background:var(--amber); border-left:3px solid #bb7a16; }}
  .data-table, .list-table {{ width:100%; border-collapse:collapse; font-size:12px; table-layout:fixed; }}
  .data-table th, .data-table td, .list-table th, .list-table td {{ padding:7px 10px; border-bottom:1px solid #e8eeeb; text-align:left; vertical-align:top; overflow-wrap:anywhere; }}
  .data-table tr:last-child th, .data-table tr:last-child td, .list-table tr:last-child td {{ border-bottom:0; }}
  .data-table th {{ width:190px; color:var(--muted); font-weight:600; }}
  .list-table thead {{ background:#f4f7f5; color:var(--muted); }}
  .list-table th:first-child, .list-table td:first-child {{ width:44px; }}
  .value-section {{ border-top:1px solid #e8eeeb; }}
  .value-section > summary {{ padding:8px 10px; color:var(--teal); font-size:12px; font-weight:650; list-style:none; }}
  .value-section > summary::before {{ display:inline-block; width:20px; }}
  .healing-event {{ margin:8px; border:1px solid #ecdcb7; border-radius:4px; overflow:hidden; }}
  .healing-event > summary {{ padding:8px 10px; background:#fffaf0; font-size:12px; font-weight:650; list-style:none; }}
  .healing-event > summary::before {{ display:inline-block; width:20px; }}
  .healing-table th {{ width:190px; }}
  .decision {{ margin-left:8px; font-size:11px; }}
  .empty-state {{ margin:0; padding:10px; color:var(--muted); font-size:12px; }}
  .scenario-screenshots {{ border-top:1px solid var(--line); padding:12px 16px 16px; }}
  .scenario-screenshots h3 {{ margin:0 0 10px; font-size:13px; }}
  .screenshot-gallery {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 360px), 1fr)); gap:12px; }}
  .screenshot {{ margin:0; min-width:0; border:1px solid var(--line); border-radius:5px; overflow:hidden; background:#f7faf8; }}
  .screenshot img {{ display:block; width:100%; height:auto; }}
  .screenshot figcaption {{ padding:8px 10px; color:var(--muted); font-size:11px; overflow-wrap:anywhere; }}
  @media (max-width:600px) {{
    .scenario-head {{ align-items:flex-start; flex-wrap:wrap; }}
    .scenario-count {{ margin-left:26px; width:100%; }}
    .steps {{ padding-left:10px; padding-right:10px; }}
    .step-content {{ padding-left:0; }}
    .data-table th, .healing-table th {{ width:120px; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Self-Healing QA Report</h1>
  <div class="subtitle">Generated by LangGraph self-healing QA framework</div>

  <div class="summary">
    <div class="card"><div class="label">Scenarios</div><div class="value">{total}</div></div>
    <div class="card"><div class="label">Passed</div><div class="value" style="color:#16a34a">{passed}</div></div>
    <div class="card"><div class="label">Failed</div><div class="value" style="color:#dc2626">{failed}</div></div>
    <div class="card"><div class="label">Total heals</div><div class="value">{analytics['total_heals']}</div></div>
    <div class="card"><div class="label">Heal success rate</div><div class="value">{analytics['heal_success_rate']*100:.0f}%</div></div>
    <div class="card"><div class="label">Avg heal confidence</div><div class="value">{analytics['avg_confidence']*100:.0f}%</div></div>
    <div class="card"><div class="label">LLM calls made</div><div class="value">{report['llm_calls_made']}</div></div>
  </div>

  {scenarios_html}
</main>
</body>
</html>
"""


def write_html_report(report: dict, out_path: Path) -> None:
    out_path.write_text(render_html_report(report), encoding="utf-8")
