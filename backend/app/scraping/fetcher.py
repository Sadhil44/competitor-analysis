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
            await page.goto(url, wait_until="networkidle")
            return await page.inner_text("body")
        finally:
            await browser.close()
