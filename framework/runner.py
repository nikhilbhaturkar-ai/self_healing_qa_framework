"""Orchestrates: parse scenarios -> interpret steps -> execute each element
action through the self-healing graph -> collect results for reporting.

This is the outer loop; the LangGraph graph itself only ever sees one
element interaction at a time (see framework/graph/build_graph.py).
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import Settings
from framework.browser.playwright_driver import PlaywrightDriver
from framework.graph.build_graph import build_healing_graph
from framework.graph.context import NodeContext
from framework.hooks import StepHooks
from framework.llm.groq_client import GroqClient
from framework.memory.locator_store import LocatorStore
from framework.parser.scenario_parser import Scenario, Step, parse_scenarios_file
from framework.parser.step_interpreter import (
    Action,
    expand_to_element_actions,
    interpret_gherkin_step,
    interpret_step,
)
from framework.utils.content_check import assert_content_visible


class ScenarioRunner:
    def __init__(
        self,
        settings: Settings,
        hooks: StepHooks | None = None,
    ):
        self.settings = settings
        self.hooks = hooks or StepHooks()
        self.driver = PlaywrightDriver(
            settings.browser,
            settings.headless,
            settings.action_timeout_ms,
            settings.app_ready_selector,
        )
        self.store = LocatorStore(settings.chroma_path, settings.locator_history_path)
        self.groq = GroqClient(settings.groq_api_key, settings.groq_model)
        self.ctx = NodeContext(driver=self.driver, store=self.store, groq=self.groq, settings=settings)
        self.graph = build_healing_graph(self.ctx)

    async def run(self, scenarios_file: str) -> dict:
        scenarios = parse_scenarios_file(scenarios_file)
        screenshot_run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000_000:09d}"
        report_scenarios = []
        for scenario in scenarios:
            report_scenarios.append(await self._run_scenario(scenario, screenshot_run_id))

        return {
            "scenarios": report_scenarios,
            "analytics": self.store.get_analytics(),
            "llm_calls_made": self.groq.calls_made,
            "generated_at": time.time(),
        }

    async def _run_scenario(self, scenario: Scenario, screenshot_run_id: str) -> dict:
        result = {
            "title": scenario.title,
            "index": scenario.index,
            "status": "fail",
            "steps": [],
            "screenshots": [],
        }
        try:
            await self.driver.start()
            await self.hooks.before_scenario(scenario, self.driver)
            result = await self._execute_scenario_steps(scenario, screenshot_run_id)
        except Exception as exc:  # noqa: BLE001 - report hook and scenario failures
            result = {**result, "error": f"scenario hook or execution error: {exc}"}
        finally:
            try:
                await self.hooks.after_scenario(scenario, result, self.driver)
            except Exception as exc:  # noqa: BLE001 - preserve scenario result on hook failure
                result = {
                    **result,
                    "status": "fail",
                    "after_scenario_error": str(exc),
                }
            try:
                await self.driver.stop()
            except Exception as exc:  # noqa: BLE001 - report browser shutdown failures
                result = {
                    **result,
                    "status": "fail",
                    "browser_shutdown_error": str(exc),
                }
        return result

    async def _execute_scenario_steps(self, scenario: Scenario, screenshot_run_id: str) -> dict:
        step_results = []
        screenshots = []
        scenario_failed = False

        for step in scenario.steps:
            screenshot_relative_path = (
                Path("screenshots")
                / screenshot_run_id
                / f"scenario_{scenario.index}_step_{step.index}.png"
            )
            screenshot_path = self.settings.reports_path / screenshot_relative_path
            result = await self._run_hooked_step(scenario, step, scenario_failed)
            result = await self._capture_step_screenshot(result, screenshot_path, screenshot_relative_path)
            step_results.append(result)
            if result.get("screenshot"):
                screenshots.append(
                    {"step": step.index, "text": step.raw_text, "path": result["screenshot"]}
                )
            if result["status"] == "fail":
                scenario_failed = True

        return {
            "title": scenario.title,
            "index": scenario.index,
            "status": "fail" if scenario_failed else "pass",
            "steps": step_results,
            "screenshots": screenshots,
        }

    async def _run_hooked_step(self, scenario: Scenario, step: Step, scenario_failed: bool) -> dict:
        action = (
            interpret_gherkin_step(step.keyword_type, step.raw_text, step.data_table)
            if step.keyword_type is not None
            else interpret_step(step.raw_text)
        )
        result = {
            "text": step.raw_text,
            "status": "fail",
            "detail": "step did not run",
            "healing_events": [],
        }

        try:
            await self.hooks.before_step(scenario, step, self.driver)
            if scenario_failed and action.type != "screenshot":
                result = {
                    "text": step.raw_text,
                    "status": "skipped",
                    "reason": "prior step failed",
                    "healing_events": [],
                }
            else:
                if action.type == "unknown" and step.keyword_type is None:
                    llm_result = self.groq.classify_step(step.raw_text)
                    action = Action.from_llm_dict(step.raw_text, llm_result)
                result = await self._run_step(action)
        except Exception as exc:  # noqa: BLE001 - hook failures become step failures
            result = {
                "text": step.raw_text,
                "status": "fail",
                "detail": f"step hook error: {exc}",
                "healing_events": [],
            }
        finally:
            try:
                await self.hooks.after_step(scenario, step, result, self.driver)
            except Exception as exc:  # noqa: BLE001 - preserve the original step result
                result = {
                    **result,
                    "status": "fail",
                    "after_step_error": str(exc),
                }
        return {"action_type": action.type, **result}

    async def _capture_step_screenshot(
        self,
        result: dict,
        screenshot_path: Path,
        screenshot_relative_path: Path,
    ) -> dict:
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await self.driver.save_screenshot(screenshot_path)
            return {**result, "screenshot": screenshot_relative_path.as_posix()}
        except Exception as exc:  # noqa: BLE001 - keep the scenario report even if capture fails
            return {**result, "screenshot_error": str(exc)}

    async def _run_step(self, action: Action) -> dict:
        base = {
            "text": action.raw_text,
            "healing_events": [],
            "locator_strategies": [],
            "action_type": action.type,
        }
        try:
            if action.type == "screenshot":
                return {**base, "status": "pass", "detail": "screenshot captured after this step"}

            if action.type == "navigate":
                await self.driver.navigate(action.url)
                return {**base, "status": "pass", "detail": f"navigated to {action.url}"}

            if action.type == "assert_visible":
                check = await assert_content_visible(
                    self.driver.page,
                    action.content_items or action.content_hint or "",
                    action.section_hint,
                    timeout_ms=self.settings.action_timeout_ms,
                )
                return {**base, "status": "pass" if check["passed"] else "fail", "detail": check}

            if action.type == "assert_button_visible":
                button = self.driver.page.get_by_role("button", name=action.target_hint, exact=True)
                try:
                    await button.first.wait_for(state="visible", timeout=self.settings.action_timeout_ms)
                except PlaywrightTimeoutError:
                    return {
                        **base,
                        "status": "fail",
                        "detail": {"visible": False, "role": "button", "name": action.target_hint},
                    }
                return {
                    **base,
                    "status": "pass",
                    "detail": {"visible": True, "role": "button", "name": action.target_hint},
                }

            element_actions = expand_to_element_actions(action)
            if not element_actions:
                return {**base, "status": "fail", "detail": "could not interpret step"}

            for ea in element_actions:
                url_pattern = urlparse(self.driver.page.url).netloc or self.driver.page.url
                initial_state = {
                    "url_pattern": url_pattern,
                    "kind": ea.kind,
                    "hint": ea.hint,
                    "op": ea.op,
                    "value": ea.value,
                }
                result_state = await self.graph.ainvoke(initial_state)
                if result_state.get("healing_event"):
                    event = result_state["healing_event"]
                    base["healing_events"].append(event)
                    base["locator_strategies"].append(
                        {
                            "kind": ea.kind,
                            "hint": ea.hint,
                            "strategy": event.get("strategy"),
                            "selection_method": "LLM ranking" if event.get("used_llm") else "deterministic scoring",
                            "decision": event.get("decision"),
                            "applied_success": event.get("applied_success"),
                        }
                    )
                elif result_state.get("initial_success"):
                    base["locator_strategies"].append(
                        {
                            "kind": ea.kind,
                            "hint": ea.hint,
                            "strategy": result_state.get("locator_strategy", "playwright_semantic"),
                            "selection_method": "cached locator" if result_state.get("locator_strategy") == "chroma_cache" else "Playwright semantic locator",
                            "applied_success": True,
                        }
                    )
                if not result_state.get("final_success"):
                    return {
                        **base,
                        "status": "fail",
                        "detail": f"could not resolve/act on {ea.kind} '{ea.hint}'",
                    }

            return {**base, "status": "pass", "detail": "ok"}
        except Exception as exc:  # noqa: BLE001 - report the real failure, keep the run going
            return {**base, "status": "fail", "detail": f"error: {exc}"}
