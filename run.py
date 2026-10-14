"""CLI entrypoint.

Usage:
    python run.py scenarios/apx_ops.feature [--headless] [--browser chromium]
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import sys
import time
from pathlib import Path

from config import SETTINGS
from framework.reporting.html_report import write_html_report
from framework.reporting.json_report import write_json_report
from framework.runner import ScenarioRunner
from framework.utils.logging_setup import setup_logging

logger = logging.getLogger("run")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Self-healing Cucumber/Gherkin QA framework runner")
    parser.add_argument("scenarios_file", help="Path to a Gherkin .feature file (legacy .txt is also supported)")
    parser.add_argument("--headless", action="store_true", help="Force headless browser")
    parser.add_argument("--headed", action="store_true", help="Force headed (visible) browser")
    parser.add_argument("--browser", default=None, choices=["chromium", "firefox", "webkit"])
    return parser.parse_args()


async def main() -> int:
    setup_logging()
    args = parse_args()

    settings = SETTINGS
    if args.headless:
        settings = dataclasses.replace(settings, headless=True)
    if args.headed:
        settings = dataclasses.replace(settings, headless=False)
    if args.browser:
        settings = dataclasses.replace(settings, browser=args.browser)

    if not Path(args.scenarios_file).exists():
        logger.error("Scenarios file not found: %s", args.scenarios_file)
        return 1

    settings.reports_path.mkdir(parents=True, exist_ok=True)

    runner = ScenarioRunner(settings)
    logger.info("Running scenarios from %s (browser=%s, headless=%s)", args.scenarios_file, settings.browser, settings.headless)
    report = await runner.run(args.scenarios_file)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    html_path = settings.reports_path / f"report_{timestamp}.html"
    json_path = settings.reports_path / f"report_{timestamp}.json"
    write_html_report(report, html_path)
    write_json_report(report, json_path)

    total = len(report["scenarios"])
    passed = sum(1 for s in report["scenarios"] if s["status"] == "pass")
    logger.info("Done: %d/%d scenarios passed. LLM calls made: %d", passed, total, report["llm_calls_made"])
    logger.info("HTML report: %s", html_path)
    logger.info("JSON report: %s", json_path)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
