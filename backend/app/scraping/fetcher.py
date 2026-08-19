"""Fetches a single page, preferring a plain HTTP request and only paying
for a Playwright browser when the HTTP response turns out not to contain
usable content — most competitor product/category pages render their
price and JSON-LD data server-side, so a browser is the exception, not
the default.
"""

import asyncio
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.scraping.http import USER_AGENT, new_client, rate_limiter
from app.scraping.jsonld import extract_jsonld_blocks, iter_jsonld_nodes, node_types

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

MAX_HTTP_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0
MIN_USABLE_TEXT_LENGTH = 200
_JS_REQUIRED_HINTS = ("enable javascript", "requires javascript", "please turn on javascript")

MAX_CONCURRENT_HTTP_FETCHES = 8
MAX_CONCURRENT_BROWSER_FETCHES = 2
_http_semaphore = asyncio.Semaphore(MAX_CONCURRENT_HTTP_FETCHES)
_browser_semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSER_FETCHES)


class FetchError(Exception):
    """Both the HTTP and (if attempted) browser fetch paths failed."""


@dataclass
class FetchedPage:
    url: str
    html: str
    text: str
    next_page_url: str | None
    fetched_via: str  # "http" or "browser" — surfaced for logging/observability


def _find_next_link_html(soup: BeautifulSoup, base_url: str) -> str | None:
    rel_next = soup.find("link", rel="next") or soup.find("a", rel="next")
    if rel_next and rel_next.get("href"):
        return urljoin(base_url, rel_next["href"])
    for a in soup.find_all("a"):
        label = a.get_text(strip=True).lower()
        aria = (a.get("aria-label") or "").lower()
        if label in ("next", "next page") or "next page" in aria or aria == "next":
            href = a.get("href")
            if href:
                return urljoin(base_url, href)
    return None


def _has_jsonld_product_signal(soup: BeautifulSoup) -> bool:
    for block in extract_jsonld_blocks(soup):
        for node in iter_jsonld_nodes(block):
            types = node_types(node)
            if any(t in types for t in ("Product", "Offer", "AggregateOffer")):
                return True
    return False


def _needs_js_rendering(text: str, soup: BeautifulSoup) -> bool:
    """A page with JSON-LD product/offer data already carries the answer
    regardless of how little visible text renders without JS — only fall
    back to a browser when there's neither structured data nor enough
    plain text to be worth extracting from.
    """
    if _has_jsonld_product_signal(soup):
        return False
    if len(text) < MIN_USABLE_TEXT_LENGTH:
        return True
    lowered = text.lower()
    return any(hint in lowered for hint in _JS_REQUIRED_HINTS)


async def _fetch_via_http(url: str) -> tuple[str, str] | None:
    """Returns (final_url, html) on a usable 2xx response, or None if the
    HTTP path should be abandoned in favor of the browser fallback (after
    retrying transient failures).
    """
    async with _http_semaphore, new_client() as client:
        for attempt in range(MAX_HTTP_RETRIES + 1):
            try:
                response = await client.get(url)
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt < MAX_HTTP_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
                return None
            if response.status_code >= 500 and attempt < MAX_HTTP_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue
            if response.status_code >= 400:
                return None
            return str(response.url), response.text
    return None


async def _fetch_via_browser(url: str) -> FetchedPage:
    async with _browser_semaphore, async_playwright() as pw:
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
            html = await page.content()
            text = await page.inner_text("body")
            next_page_url = await page.evaluate(_FIND_NEXT_LINK_JS)
            return FetchedPage(url=page.url, html=html, text=text, next_page_url=next_page_url, fetched_via="browser")
        finally:
            await browser.close()


async def fetch_page(url: str, *, rate_limit_seconds: float = 2.0) -> FetchedPage:
    """Fetch a page's content and, if present, the URL of its next page.

    Tries a plain HTTP request first; only launches a Playwright browser
    when the HTTP response doesn't contain usable content (e.g. a
    JS-rendered SPA shell) or the HTTP path fails outright.
    """
    await rate_limiter.wait(url, rate_limit_seconds)

    http_result = await _fetch_via_http(url)
    if http_result is not None:
        final_url, html = http_result
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        if not _needs_js_rendering(text, soup):
            return FetchedPage(
                url=final_url,
                html=html,
                text=text,
                next_page_url=_find_next_link_html(soup, final_url),
                fetched_via="http",
            )

    try:
        return await _fetch_via_browser(url)
    except Exception as exc:
        raise FetchError(f"Failed to fetch {url!r} via HTTP or browser") from exc
