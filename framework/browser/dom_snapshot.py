"""Captures a pruned snapshot of interactive/visible DOM elements.

Only interactive elements (links, buttons, inputs, ARIA-roled elements) are
collected, and each is truncated to a handful of short fields. This keeps the
payload small enough that if it's ever summarized into an LLM prompt (stage
3.4), only a handful of candidates - never the raw snapshot - are sent.
"""
from __future__ import annotations

_EXTRACT_JS = """
() => {
  const sel = 'a,button,input,select,textarea,[role],[onclick],[tabindex]';
  const nodes = Array.from(document.querySelectorAll(sel)).slice(0, 400);
  const out = [];
  for (const el of nodes) {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const visible = rect.width > 0 && rect.height > 0
      && style.visibility !== 'hidden' && style.display !== 'none';
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || '')
      .trim().replace(/\\s+/g, ' ').slice(0, 80);
    out.push({
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || null,
      type: el.getAttribute('type') || null,
      id: el.id || null,
      name: el.getAttribute('name') || null,
      test_id: el.getAttribute('data-testid') || el.getAttribute('data-test-id') || null,
      placeholder: el.getAttribute('placeholder') || null,
      title: el.getAttribute('title') || null,
      aria_label: el.getAttribute('aria-label') || null,
      class_name: (typeof el.className === 'string') ? el.className.slice(0, 120) : null,
      text: text,
      href: el.getAttribute('href') || null,
      visible: visible,
      enabled: !el.disabled,
    });
  }
  return out;
}
"""


async def capture_dom_snapshot(page, max_elements: int = 200) -> list[dict]:
    """Returns a pruned list of interactive-element descriptors."""
    try:
        elements = await page.evaluate(_EXTRACT_JS)
    except Exception:
        return []
    return elements[:max_elements]
