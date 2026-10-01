"""Stage 6 - Reporting & Observability. Renders a single self-contained HTML
file (inline CSS/JS, no external assets) covering every executed scenario,
step, and healing event, plus the token-minimization/analytics summary.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

_STATUS_COLORS = {"pass": "#16a34a", "fail": "#dc2626", "skipped": "#6b7280"}


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _badge(status: str) -> str:
    color = _STATUS_COLORS.get(status, "#6b7280")
    return f'<span class="badge" style="background:{color}">{_esc(status.upper())}</span>'


def _healing_event_html(event: dict) -> str:
    decision_color = {"auto_heal": "#16a34a", "flag": "#d97706", "no_heal": "#dc2626"}.get(
        event.get("decision", ""), "#6b7280"
    )
    return f"""
    <div class="heal-event">
      <div class="heal-row"><strong>Hint:</strong> {_esc(event.get('hint'))} <span class="tag">{_esc(event.get('kind'))}</span></div>
      <div class="heal-row"><strong>Old locator:</strong> <code>{_esc(event.get('old_locator'))}</code></div>
      <div class="heal-row"><strong>New locator:</strong> <code>{_esc(event.get('new_locator'))}</code>
        <span class="tag">{_esc(event.get('strategy'))}</span></div>
      <div class="heal-row">
        <strong>Confidence:</strong> {_esc(round(event.get('confidence', 0.0), 3))}
        &nbsp;|&nbsp; <strong>Decision:</strong>
        <span class="decision" style="color:{decision_color}">{_esc(event.get('decision'))}</span>
        &nbsp;|&nbsp; <strong>LLM used:</strong> {_esc(event.get('used_llm'))}
        &nbsp;|&nbsp; <strong>Applied OK:</strong> {_esc(event.get('applied_success'))}
      </div>
    </div>
    """


def _step_html(step: dict) -> str:
    detail = step.get("detail")
    detail_str = json.dumps(detail, indent=2, default=str) if isinstance(detail, dict) else str(detail)
    heals = "".join(_healing_event_html(e) for e in step.get("healing_events", []))
    heal_block = f'<div class="heals"><div class="heals-title">Healing events ({len(step["healing_events"])})</div>{heals}</div>' if step.get("healing_events") else ""
    return f"""
    <div class="step">
      <div class="step-head">{_badge(step['status'])} <span class="step-text">{_esc(step['text'])}</span></div>
      <div class="step-detail"><pre>{_esc(detail_str)}</pre></div>
      {heal_block}
    </div>
    """


def _scenario_html(scenario: dict) -> str:
    steps = "".join(_step_html(s) for s in scenario["steps"])
    return f"""
    <div class="scenario">
      <div class="scenario-head">
        {_badge(scenario['status'])}
        <span class="scenario-title">Scenario {_esc(scenario['index'])}: {_esc(scenario['title'])}</span>
      </div>
      <div class="steps">{steps}</div>
    </div>
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
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#f3f4f6; color:#111827; margin:0; padding:32px; }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .subtitle {{ color:#6b7280; margin-bottom:24px; font-size:13px; }}
  .summary {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:28px; }}
  .card {{ background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:14px 18px; min-width:150px; }}
  .card .label {{ font-size:12px; color:#6b7280; text-transform:uppercase; letter-spacing:.04em; }}
  .card .value {{ font-size:22px; font-weight:600; margin-top:4px; }}
  .scenario {{ background:#fff; border:1px solid #e5e7eb; border-radius:10px; margin-bottom:18px; overflow:hidden; }}
  .scenario-head {{ padding:14px 18px; border-bottom:1px solid #e5e7eb; display:flex; align-items:center; gap:10px; background:#f9fafb; }}
  .scenario-title {{ font-weight:600; font-size:15px; }}
  .steps {{ padding:6px 18px 14px; }}
  .step {{ padding:10px 0; border-bottom:1px dashed #e5e7eb; }}
  .step:last-child {{ border-bottom:none; }}
  .step-head {{ display:flex; align-items:center; gap:10px; }}
  .step-text {{ font-size:14px; }}
  .step-detail pre {{ background:#f9fafb; border:1px solid #eef0f2; border-radius:6px; padding:8px 10px; font-size:12px; margin:8px 0 0; white-space:pre-wrap; word-break:break-word; }}
  .badge {{ color:#fff; font-size:11px; font-weight:700; padding:3px 8px; border-radius:999px; letter-spacing:.03em; }}
  .heals {{ margin-top:8px; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 12px; }}
  .heals-title {{ font-weight:700; font-size:12px; margin-bottom:6px; color:#92400e; }}
  .heal-event {{ font-size:12.5px; padding:6px 0; border-top:1px solid #fde68a; }}
  .heal-event:first-child {{ border-top:none; }}
  .heal-row {{ margin:2px 0; }}
  .tag {{ display:inline-block; background:#e5e7eb; border-radius:5px; padding:1px 6px; font-size:11px; margin-left:6px; }}
  code {{ background:#f3f4f6; padding:1px 5px; border-radius:4px; font-size:12px; }}
</style>
</head>
<body>
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
</body>
</html>
"""


def write_html_report(report: dict, out_path: Path) -> None:
    out_path.write_text(render_html_report(report), encoding="utf-8")
