from dataclasses import dataclass

from playwright.async_api import async_playwright

USER_AGENT = "CompetitorAnalysisBot/0.1 (contact: you@example.com)"

# Reads whatever pagination signal the page itself declares — <link rel="next">,
# <a rel="next">, or a visibly-labeled "Next" link — instead of assuming a URL
# convention like Shopify's `?page=N`. `.href` on a DOM element is always the
# browser-resolved absolute URL, so this works whether the site uses relative
# or absolute hrefs without us having to resolve anything ourselves.
_FIND_NEXT_LINK_JS = """
() => {
    const relNext = document.querySelector('link[rel="next"], a[rel="next"]');
    if (relNext && relNext.href) return relNext.href;
    const textNext = Array.from(document.querySelectorAll('a')).find((a) => {
        const label = (a.textContent || '').trim().toLowerCase();
        const aria = (a.getAttribute('aria-label') || '').toLowerCase();
        return label === 'next' || label === 'next page' || aria.includes('next page') || aria === 'next';
    });
    return textNext ? textNext.href : null;
}
"""


@dataclass
class FetchedPage:
    text: str
    next_page_url: str | None


async def fetch_page(url: str) -> FetchedPage:
    """Render a page with a real browser; return its visible text and the
    URL of the next page, if the page declares one.

    Uses Playwright (not a plain HTTP request) because competitor product
    pages typically render price/stock via JavaScript after initial load.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=USER_AGENT)
            # "networkidle" waits for zero network connections for 500ms —
            # fragile against sites with persistent background chatter (chat
            # widgets, analytics beacons) that never fully go quiet, causing
            # a hard timeout even though the actual page content is ready.
            # "domcontentloaded" + a short fixed wait for JS-rendered content
            # is the more robust standard pattern.
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            text = await page.inner_text("body")
            next_page_url = await page.evaluate(_FIND_NEXT_LINK_JS)
            return FetchedPage(text=text, next_page_url=next_page_url)
        finally:
            await browser.close()
