"""Async extension points around each scenario step."""
from __future__ import annotations

from framework.browser.playwright_driver import PlaywrightDriver
from framework.parser.scenario_parser import Scenario, Step


class StepHooks:
    """Override lifecycle methods to run custom scenario and step logic."""

    async def before_scenario(self, scenario: Scenario, driver: PlaywrightDriver) -> None:
        """Run once before the steps of a scenario."""

    async def after_scenario(
        self,
        scenario: Scenario,
        result: dict,
        driver: PlaywrightDriver,
    ) -> None:
        """Run once after a scenario result is produced, including on failure."""
      
    async def before_step(self, scenario: Scenario, step: Step, driver: PlaywrightDriver) -> None:
        """Run immediately before a step is executed or marked skipped."""

    async def after_step(
        self,
        scenario: Scenario,
        step: Step,
        result: dict,
        driver: PlaywrightDriver,
    ) -> None:
        """Run after a step result is produced, including on failure."""