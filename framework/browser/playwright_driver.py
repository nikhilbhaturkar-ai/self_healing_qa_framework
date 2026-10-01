"""Thin async Playwright wrapper: browser lifecycle + primitive actions.

Kept free of any healing logic - it only knows how to navigate, resolve an
initial locator, perform an operation, and hand back a DOM snapshot on
request. All self-healing decision-making lives in framework/graph/nodes/.
"""
from __future__ import annotations

from playwright.async_api import async_playwright

from framework.browser.dom_snapshot import capture_dom_snapshot
from framework.browser.locator_strategies import resolve_initial_locator


class ElementNotFound(Exception):
    pass


class PlaywrightDriver:
    def __init__(self, browser_name: str = "chromium", headless: bool = False, timeout_ms: int = 5000):
        self.browser_name = browser_name
        self.headless = headless
        self.timeout_ms = timeout_ms
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

    async def stop(self) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    async def navigate(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded")

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
            elif op == "click":
                await locator.click()
            elif op == "assert_contains":
                await locator.wait_for(state="visible")
                text = (await locator.inner_text()).lower()
                if value and value.lower() not in text:
                    return False
            else:
                raise ValueError(f"Unknown op: {op}")
            return True
        except Exception:
            return False

    async def press_enter(self) -> None:
        await self.page.keyboard.press("Enter")

    async def screenshot_bytes(self) -> bytes:
        return await self.page.screenshot()
