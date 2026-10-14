"""Thin async Playwright wrapper: browser lifecycle + primitive actions.

Kept free of any healing logic - it only knows how to navigate, resolve an
initial locator, perform an operation, and hand back a DOM snapshot on
request. All self-healing decision-making lives in framework/graph/nodes/.
"""
from __future__ import annotations

from pathlib import Path

from playwright.async_api import async_playwright

from framework.browser.dom_snapshot import capture_dom_snapshot
from framework.browser.locator_strategies import resolve_initial_locator


class ElementNotFound(Exception):
    pass


class PlaywrightDriver:
    def __init__(
        self,
        browser_name: str = "chromium",
        headless: bool = False,
        timeout_ms: int = 15000,
        app_ready_selector: str | None = None,
    ):
        self.browser_name = browser_name
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.app_ready_selector = app_ready_selector
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        browser_type = getattr(self._pw, self.browser_name)
        self.browser = await browser_type.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        self.page.set_default_navigation_timeout(self.timeout_ms)

    async def stop(self) -> None:
        context, browser, playwright = self.context, self.browser, self._pw
        self.page = None
        self.context = None
        self.browser = None
        self._pw = None

        shutdown_error = None
        for resource in (context, browser, playwright):
            if resource is None:
                continue
            close = getattr(resource, "close", None) or getattr(resource, "stop", None)
            if close is None:
                continue
            try:
                await close()
            except Exception as exc:  # noqa: BLE001 - attempt to close remaining browser resources
                shutdown_error = shutdown_error or exc
        if shutdown_error:
            raise shutdown_error

    async def navigate(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.wait_for_app_ready()

    async def wait_for_app_ready(self) -> None:
        if self.app_ready_selector:
            await self.page.locator(self.app_ready_selector).wait_for(
                state="visible", timeout=self.timeout_ms
            )

    async def snapshot(self) -> list[dict]:
        return await capture_dom_snapshot(self.page)

    async def resolve_and_act(self, kind: str, hint: str, op: str, value: str | None = None) -> bool:
        """Try the initial semantic-locator resolution + action. Returns True
        on success, False if the element couldn't be found/acted on (which
        triggers the self-healing graph in the caller)."""
        locator = await resolve_initial_locator(self.page, kind, hint)
        if locator is None:
            return False
        return await self.act(locator, op, value)

    async def act(self, locator, op: str, value: str | None = None) -> bool:
        try:
            if op == "fill":
                await locator.fill(value or "")
            elif op == "select_option":
                await locator.select_option(label=value or "")
            elif op == "click":
                await locator.click()
            elif op == "assert_contains":
                await locator.wait_for(state="visible")
                text = (await locator.inner_text()).lower()
                if value and value.lower() not in text:
                    return False
            else:
                raise ValueError(f"Unknown op: {op}")
        except Exception:
            return False

        await self.wait_for_app_ready()
        return True

    async def press_enter(self) -> None:
        await self.page.keyboard.press("Enter")

    async def screenshot_bytes(self) -> bytes:
        return await self.page.screenshot()

    async def save_screenshot(self, path: Path) -> None:
        await self.page.screenshot(path=str(path), full_page=True)
