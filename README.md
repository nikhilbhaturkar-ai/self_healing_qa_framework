# Self-Healing QA Automation Framework

LangGraph + Playwright + ChromaDB + Groq. Executes Cucumber/Gherkin feature
files as browser actions and self-heals locators when the UI
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

## Writing Features

Write scenarios in standard Gherkin `.feature` files (see
`scenarios/apx_ops.feature`):

```
Feature: Search
   Scenario: Find a page
      Given I navigate to "https://en.wikipedia.org"
      When I enter "Google Pixel" into "search"
      And I click "Search"
      Then I should see text "Google Pixel"
```

Bound step expressions are `I navigate to "<url>"`, `I enter "<value>" into
"<field>"`, `I select "<option>" from "<dropdown>" dropdown`, `I click "<target>"`
(or `I click on "<target>"`), `I should see
button "<accessible name>"`, `I should see text "<text>"`, and `I take a
screenshot` / `I capture a screenshot`. The button assertion checks the
button's accessible name and actual visibility. Gherkin `Background` and `Scenario
Outline` with `Examples` are supported. Unbound Gherkin steps fail explicitly;
they are not sent to the LLM classifier. Existing `.txt` scenario files remain
supported for backward compatibility.

The dropdown-selection step targets a native HTML `<select>` element and
selects the option by its visible label. Locating the dropdown uses the normal
locator cache and self-healing flow.

For a feature target that needs a fixed selector, add an entry to the
repository-root `custom_locators.json`. Keys are operation names (`fill`,
`click`, or `select_option`) and target hints from the feature step. A matching
entry is used before locator memory and automatic resolution, so it does not
invoke LLM locator ranking. Custom selectors must match exactly one element;
otherwise that step fails instead of falling back to automatic healing.

```json
{
   "fill": {
      "username": {
         "by": "css",
         "value": "input[name='username']"
      }
   },
   "click": {
      "Admin Login": {
         "by": "test_id",
         "value": "admin-login"
      }
   }
}
```

Supported `by` values are `css`, `xpath`, `text`, `label`, `placeholder`,
`test_id`, and `role`. For `role`, set `value` to the role name and optionally
set `name` to the accessible name. Target matching ignores surrounding
whitespace and letter case; the operation and target must otherwise match the
feature step, such as `When I enter "admin" into "username"` or
`And I click "Admin Login"`.

Use a one-column DataTable to check multiple complete visible texts:

```
Then I should see all listed texts
   | text |
   | Dashboard |
   | Monitoring |
```

The header can be `text`, `expected text`, or `value`. Each row is checked as a
separate exact-case expected phrase and appears in the report's matched/missing
tables.

## Scenario And Step Hooks

Pass a `StepHooks` subclass when constructing the runner to execute custom
logic around scenarios and steps. `before_scenario` and `after_scenario` run
once per scenario; the after-hook receives the final scenario result.
`before_step` and `after_step` run for each step; the after-hook receives the
step result. After-hooks run when their matching before-hook or execution fails.

```python
from config import SETTINGS
from framework.hooks import StepHooks
from framework.runner import ScenarioRunner


class AuditHooks(StepHooks):
   async def before_scenario(self, scenario, driver):
      print(f"Starting scenario: {scenario.title}")

   async def after_scenario(self, scenario, result, driver):
      print(f"Scenario finished with status: {result['status']}")

   async def before_step(self, scenario, step, driver):
      print(f"Starting {scenario.title}: {step.raw_text}")

   async def after_step(self, scenario, step, result, driver):
      print(f"Finished with status: {result['status']}")


runner = ScenarioRunner(SETTINGS, hooks=AuditHooks())
```

## RAG Scenario Generation

The scenario generator indexes this framework's implemented Gherkin bindings
and existing `.feature` scenarios, retrieves them with Chroma semantic search
plus lexical ranking, and asks Groq to compose a candidate using only retrieved
evidence. Generated steps are parsed and matched against the same regex
bindings used by the runner. Missing, ambiguous, or invalid steps are reported;
they are not silently treated as executable. Generation does not run the
feature. Review its reports and perform any project dry-run before use.

Index or refresh the current repository after changing bindings or feature
examples:

```powershell
.venv\Scripts\python -m framework.scenario_generation.cli index --repo .
```

Generate a candidate and its JSON/Markdown reports under
`artifacts/cucumber_rag/`:

```powershell
.venv\Scripts\python -m framework.scenario_generation.cli generate `
   --repo . `
   --requirement "Verify an administrator can open the dashboard and sign out" `
   --application APX `
   --module Administration `
   --output-name admin_dashboard
```

An optional local REST API exposes `GET /health`, `POST /index`, and
`POST /generate`:

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn framework.scenario_generation.api:app --port 8000
```

The API only accepts repositories under `SCENARIO_GENERATOR_ALLOWED_ROOT`,
which defaults to the workspace root. Add authentication and request limits
before exposing it beyond a trusted local environment. The current scanner
indexes the Python Gherkin bindings in this framework plus repository feature
examples; it does not parse external JavaScript/TypeScript step-definition
registries.

## Running

```powershell
.venv\Scripts\python run.py scenarios/apx_ops.feature
# add --headless for CI, --browser firefox|webkit to switch engines
```

Reports are written to `reports/report_<timestamp>.{html,json}`.
Each scenario runs in its own browser session; the browser is closed after its
scenario hooks complete and relaunched before the next scenario begins.

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

# How to Run scenario
.\.venv-1\Scripts\python.exe run.py scenarios\apx_ops_admin_portal.feature --headed

# How to generate cucumber feature file and steps from scenario 
python run_rag.py generate "verify if user is able to login to apx dashboard using basis admin"
