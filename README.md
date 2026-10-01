# Self-Healing QA Automation Framework

LangGraph + Playwright + ChromaDB + Groq. Executes plain-English test
scenarios as real browser actions and self-heals locators when the UI
changes underneath a test, using a deterministic-first pipeline so the
Groq LLM is only called as a last resort.

## Architecture

Maps directly onto the 6-stage self-healing architecture:

1. **Test Execution** (`framework/graph/nodes/execute_step.py`) - checks the
   Locator Memory cache, then tries Playwright's own semantic locators.
2. **Failure Detection & Context Capture** (`capture_context.py`) - pruned
   DOM snapshot of interactive elements only.
3. **Self-Healing Locator Engine** (`context_understanding.py` ->
   `candidate_generation.py` -> `candidate_scoring.py` -> `semantic_ranking.py`
   -> `validation.py` -> `confidence_decision.py`) - deterministic scoring
   first; Groq is called only when the top candidates are ambiguous
   (`candidate_scoring.py`'s gate: score >= 0.80 and a clear margin over the
   runner-up skips the LLM entirely).
4. **Apply & Re-execute** (`apply_reexecute.py`) - swaps in the healed
   locator and re-runs the original action.
5. **Locator Memory & Learning** (`framework/memory/locator_store.py`) -
   ChromaDB collection (local ONNX embeddings, no LLM tokens) + a JSON
   change-history log; future runs reuse a healed locator with zero
   heuristics/LLM cost.
6. **Reporting & Observability** (`framework/reporting/`) - self-contained
   HTML + JSON reports of every scenario/step and healing event.

The LangGraph graph (`framework/graph/build_graph.py`) represents a single
element interaction (one fill or one click); `framework/runner.py` is the
outer loop that walks scenarios -> steps -> element interactions and invokes
the graph once per interaction.

## Setup

```powershell
py -3.14 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example .env
# edit .env and set GROQ_API_KEY
```

## Writing scenarios

Plain English, in a `.txt` file (see `scenarios/sample_scenarios.txt`):

```
Scenario 1: Verify the google search showing correct top 5 google pixel phones
- Navigate to google.co.in
- Enter search text "top 5 google pixel phone" and click on search
- Search result should show top 5 google pixel phones in popular products section
```

Supported step patterns (rule-based, no LLM cost): `Navigate to <url>`,
`Enter <field> text "<value>" and click on <target>`, `Enter "<value>" in
<field>`, `Click on <target>`, `<subject> should show/display/contain
<content> [in <section>]`. A step that matches none of these triggers a
single small Groq call to classify it (logged in the report).

Note: the final "should show ... in <section>" assertion is a real,
unmocked keyword-containment check against the live page's visible text -
it is intentionally not locator-based (self-healing applies to element
*locators* used for actions, per the architecture; content assertions on
unpredictable pages like a Google SERP use fuzzy text matching instead).

## Running

```powershell
.venv\Scripts\python run.py scenarios/sample_scenarios.txt
# add --headless for CI, --browser firefox|webkit to switch engines
```

Reports are written to `reports/report_<timestamp>.{html,json}`.

## Token-minimization strategy

- Chroma embeddings use the local ONNX MiniLM model bundled with chromadb -
  zero LLM tokens for locator memory/similarity search.
- Step parsing is regex/keyword-based; Groq is a fallback only.
- Locator candidate generation and scoring are fully deterministic
  (uniqueness, visibility, stability of the attribute used, semantic text
  similarity via `difflib`, historical success rate, action suitability).
- Groq (`semantic_ranking.py`) is invoked only when the top two candidates'
  deterministic scores are close/ambiguous, and only the top ~6 candidates'
  minimal attributes are sent - never the raw DOM.
- A previously healed locator is cached in Chroma and reused directly on
  future runs with zero heuristics/LLM cost.
- The HTML/JSON report surfaces `llm_calls_made` so token spend is visible.
