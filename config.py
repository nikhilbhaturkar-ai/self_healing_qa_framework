"""Central config loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    headless: bool
    browser: str
    confidence_auto_heal: float
    confidence_flag: float
    chroma_dir: str
    reports_dir: str
    locator_history_file: str
    action_timeout_ms: int
    app_ready_selector: str | None

    @property
    def chroma_path(self) -> Path:
        return ROOT_DIR / self.chroma_dir

    @property
    def reports_path(self) -> Path:
        return ROOT_DIR / self.reports_dir

    @property
    def locator_history_path(self) -> Path:
        return ROOT_DIR / self.locator_history_file


def load_settings() -> Settings:
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        headless=_bool("HEADLESS", False),
        browser=os.getenv("BROWSER", "chromium"),
        confidence_auto_heal=_float("CONFIDENCE_AUTO_HEAL", 0.95),
        confidence_flag=_float("CONFIDENCE_FLAG", 0.80),
        chroma_dir=os.getenv("CHROMA_DIR", "chroma_db"),
        reports_dir=os.getenv("REPORTS_DIR", "reports"),
        locator_history_file=os.getenv("LOCATOR_HISTORY_FILE", "locator_history.json"),
        action_timeout_ms=_int("ACTION_TIMEOUT_MS", 15000),
        app_ready_selector=os.getenv("APP_READY_SELECTOR") or None,
    )


SETTINGS = load_settings()
