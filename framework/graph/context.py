"""Bundles the live, non-serializable resources (browser driver, vector
memory, LLM client, thresholds) that node closures need but which must never
be placed into LangGraph's serializable state."""
from __future__ import annotations

from dataclasses import dataclass

from config import Settings
from framework.browser.playwright_driver import PlaywrightDriver
from framework.llm.groq_client import GroqClient
from framework.memory.locator_store import LocatorStore


@dataclass
class NodeContext:
    driver: PlaywrightDriver
    store: LocatorStore
    groq: GroqClient
    settings: Settings
