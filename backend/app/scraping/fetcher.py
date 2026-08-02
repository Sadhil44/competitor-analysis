from playwright.async_api import async_playwright

USER_AGENT = "CompetitorAnalysisBot/0.1 (contact: you@example.com)"


async def fetch_page_text(url: str) -> str:
    """Render a page with a real browser and return its visible text.

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
            return await page.inner_text("body")
        finally:
            await browser.close()
