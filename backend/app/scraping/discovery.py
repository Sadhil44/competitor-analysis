"""Discovers a competitor's product/category/promotional URLs from a
starting domain, so config/competitors.yaml doesn't need every individual
product URL hand-curated — only a base website_url and (optionally) a few
known-good catalog_urls as seeds, same as it does today.

Discovery order (cheapest/most-authoritative signal first):
1. robots.txt's declared `Sitemap:` entries.
2. The conventional `/sitemap.xml` path, tried regardless of (1).
3. Recursing into sitemap indexes and product/collection sub-sitemaps.
4. The homepage's own navigation links, as a fallback/supplement — sale
   and promo pages in particular often live only in nav, never in a
   sitemap.
5. The competitor's configured `catalog_urls`, always included as
   known-good seeds regardless of what the above did or didn't find.

Deliberately NOT included: a deeper recursive internal-link crawl beyond
the homepage. Category-page pagination is already handled downstream by
ingest.py's existing next-link-following per catalog page; going further
(crawling category pages themselves for more links) would multiply request
volume for real sites without a corresponding gain here, and risks
violating "respect reasonable crawl limits" for large catalogs.

URL classification (product / category / promotional / unknown) is a cheap
path-heuristic first pass (classify_url_by_path); only URLs neither
heuristic confidently matches get a follow-up lightweight plain-HTTP fetch
to check page-level signals (JSON-LD @type, promo language), bounded by
PAGE_SIGNAL_CHECK_BUDGET — checking every discovered URL that way would be
one extra request per URL on top of the one we're already going to make to
extract it.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from app.scraping.campaigns import detect_campaigns_deterministic
from app.scraping.http import new_client, rate_limiter
from app.scraping.jsonld import extract_jsonld_blocks, iter_jsonld_nodes, node_types

# Tracking scope is a competitor's full catalog (not one category), so
# these are generous rather than tight — still a real, finite bound, just
# sized for thousands of products rather than a few hundred.
MAX_DISCOVERED_URLS = 5000  # hard cap regardless of source
MAX_HOMEPAGE_LINKS = 100  # cap on links pulled from the single homepage pass
PAGE_SIGNAL_CHECK_BUDGET = 100  # "unknown" URLs worth spending an extra fetch to classify
SITEMAP_MAX_DEPTH = 3  # sitemapindex nesting guard — real sites rarely nest past 2

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid", "ref",
    "referrer", "_ga", "_gl", "yclid",
}

# Path-based hints only catch one URL convention (Shopify-style
# /products/slug). Sites built on other platforms (e.g. deep taxonomy
# paths like /category/subcategory/product-slug, seen on Holland Bulb
# Farms) don't match any of these, and rely entirely on the page-signal
# fallback below instead.
_PRODUCT_PATH_HINTS = re.compile(r"/(products?|item|p)/", re.IGNORECASE)
_CATEGORY_PATH_HINTS = re.compile(r"/(collections?|categor(y|ies)|shop|catalog)/", re.IGNORECASE)
_PROMO_PATH_HINTS = re.compile(r"/(sale|clearance|deals?|promo(tions?)?|coupons?|specials?)\b", re.IGNORECASE)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@dataclass
class DiscoveredUrls:
    product_urls: set[str] = field(default_factory=set)
    category_urls: set[str] = field(default_factory=set)
    promotional_urls: set[str] = field(default_factory=set)
    unknown_urls: set[str] = field(default_factory=set)

    def all_urls(self) -> set[str]:
        return self.product_urls | self.category_urls | self.promotional_urls | self.unknown_urls


def normalize_url(url: str, *, base_url: str | None = None) -> str:
    """Resolve relative URLs against base_url, then strip whatever doesn't
    change which real page this is: the fragment, known tracking params,
    and a trailing slash (except on the bare root) — so the same page
    reached via three tracking-tagged links only ever counts once.
    """
    if base_url:
        url = urljoin(base_url, url)
    parsed = urlparse(url)
    query_pairs = sorted(
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    )
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    normalized = parsed._replace(path=path or "/", query=urlencode(query_pairs), fragment="")
    return urlunparse(normalized)


def _registrable(netloc: str) -> str:
    return netloc.lower().removeprefix("www.")


def is_same_site(url: str, base_url: str) -> bool:
    return _registrable(urlparse(url).netloc) == _registrable(urlparse(base_url).netloc)


def classify_url_by_path(url: str) -> str:
    """Cheap first pass: guess the URL's kind from its path alone, before
    spending a request on it. Not authoritative — only "unknown" is worth
    a follow-up page-signal check; a path that already looks like a
    product/category/promo page is trusted as-is (double-checking every
    URL would cost one extra fetch each for no real gain on the common
    case, per this module's docstring).
    """
    path = urlparse(url).path
    if _PRODUCT_PATH_HINTS.search(path):
        return "product"
    if _PROMO_PATH_HINTS.search(path):
        return "promotional"
    if _CATEGORY_PATH_HINTS.search(path):
        return "category"
    return "unknown"


def extract_product_links(html: str, page_url: str, base_url: str) -> set[str]:
    """Product-detail links found on a page (typically a tracked category
    listing page). Used to scope individual product-page discovery to
    whatever a competitor's tracked category actually links to, rather
    than that competitor's site-wide product sitemap — a sitemap spans
    every category the site sells, not just the one this project tracks
    (perennials & flowering plants), so sourcing individual product URLs
    from it would silently widen scope per competitor.

    Two signals, since path-naming alone (classify_url_by_path) only
    catches Shopify-style /products/slug URLs: also treat an unclassified
    link as a product candidate when it's nested deeper under this exact
    category page's own path (e.g. a category at /perennials linking to
    /perennials/hosta/first-frost-hosta) — a structural signal from where
    the link was actually found, not a blind naming guess. Worst case for
    a false positive here (an actual sub-category, not a product) is one
    extra page fetch that still gets run through the same multi-product
    extraction the category page itself uses, so any real products on it
    are still captured correctly.
    """
    soup = BeautifulSoup(html, "html.parser")
    page_path = urlparse(page_url).path.rstrip("/")
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        normalized = normalize_url(a["href"], base_url=page_url)
        if not is_same_site(normalized, base_url):
            continue
        kind = classify_url_by_path(normalized)
        if kind == "product":
            links.add(normalized)
            continue
        if kind != "unknown" or not page_path:
            continue
        link_path = urlparse(normalized).path
        if link_path.startswith(page_path + "/") and link_path.count("/") > page_path.count("/"):
            links.add(normalized)
    return links


def _has_product_microdata(soup: BeautifulSoup) -> bool:
    return soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product\b", re.IGNORECASE)}) is not None


async def classify_url_by_page_signals(client: httpx.AsyncClient, url: str) -> str:
    """For a URL the path heuristic couldn't place: fetch it (plain HTTP —
    cheap, no browser) and check page-level signals in priority order:
    schema.org Product/CollectionPage type (JSON-LD or microdata — some
    sites, e.g. Holland Bulb Farms, use microdata and ship no JSON-LD at
    all), the Open Graph `og:type` meta tag (a widely-supported product-page
    signal independent of schema.org), then whether the page has a genuine
    promotional banner element (the same detector campaigns.py uses —
    scoped to banner-shaped containers, not a keyword search over the
    whole page, which would false-positive on an ordinary nav menu that
    happens to link to a "Clearance" category). Never invoked for URLs
    classify_url_by_path already resolved.
    """
    try:
        response = await client.get(url)
    except httpx.HTTPError:
        return "unknown"
    if response.status_code >= 400:
        return "unknown"

    soup = BeautifulSoup(response.text, "html.parser")
    for block in extract_jsonld_blocks(soup):
        for node in iter_jsonld_nodes(block):
            types = node_types(node)
            if "Product" in types:
                return "product"
            if "CollectionPage" in types or "ItemList" in types:
                return "category"

    if _has_product_microdata(soup):
        return "product"

    og_type = soup.find("meta", property="og:type")
    if og_type and og_type.get("content", "").lower() == "product":
        return "product"

    confident, ambiguous = detect_campaigns_deterministic(response.text, url)
    if confident or ambiguous:
        return "promotional"
    return "unknown"


async def _fetch_text(client: httpx.AsyncClient, url: str, rate_limit_seconds: float) -> str | None:
    await rate_limiter.wait(url, rate_limit_seconds)
    try:
        response = await client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    return response.text


async def _sitemap_urls_from_robots(
    client: httpx.AsyncClient, base_url: str, rate_limit_seconds: float
) -> list[str]:
    text = await _fetch_text(client, urljoin(base_url, "/robots.txt"), rate_limit_seconds)
    if not text:
        return []
    return [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lower().startswith("sitemap:")
    ]


async def _parse_sitemap(
    client: httpx.AsyncClient,
    url: str,
    rate_limit_seconds: float,
    *,
    depth: int = 0,
) -> list[str]:
    """Recursively resolve a sitemap URL into leaf <loc> URLs, following
    <sitemapindex> nesting up to SITEMAP_MAX_DEPTH (a loop-safety
    backstop, not a real expectation — real sites rarely nest past 2)."""
    if depth > SITEMAP_MAX_DEPTH:
        return []
    text = await _fetch_text(client, url, rate_limit_seconds)
    if not text:
        return []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return []

    locs = [el.text.strip() for el in root.iterfind(".//sm:loc", _SITEMAP_NS) if el.text]
    tag = root.tag.rsplit("}", 1)[-1]
    if tag == "sitemapindex":
        results: list[str] = []
        for sub_url in locs:
            results.extend(
                await _parse_sitemap(client, sub_url, rate_limit_seconds, depth=depth + 1)
            )
        return results
    return locs


async def discover_urls(
    base_url: str,
    catalog_urls: list[str],
    *,
    rate_limit_seconds: float = 2.0,
    max_urls: int = MAX_DISCOVERED_URLS,
) -> DiscoveredUrls:
    """Find a competitor's product/category/promotional URLs starting from
    `base_url`. Never returns a URL on a different domain (is_same_site
    gates every addition).
    """
    result = DiscoveredUrls()
    seen: set[str] = set()

    def add(url: str, kind: str) -> None:
        normalized = normalize_url(url, base_url=base_url)
        if not is_same_site(normalized, base_url) or normalized in seen:
            return
        if len(seen) >= max_urls:
            return
        seen.add(normalized)
        getattr(result, f"{kind}_urls").add(normalized)

    async with new_client() as client:
        # Known-good human-curated seeds go in FIRST, before anything that
        # counts against max_urls — a large sitemap (thousands of product
        # URLs) can exhaust the shared discovery budget on its own, and the
        # one URL a human actually verified works must never be the thing
        # that gets crowded out by that.
        for url in catalog_urls:
            kind = classify_url_by_path(url)
            add(url, kind if kind != "unknown" else "category")

        sitemap_urls = await _sitemap_urls_from_robots(client, base_url, rate_limit_seconds)
        sitemap_urls.append(urljoin(base_url, "/sitemap.xml"))

        leaf_urls: list[str] = []
        for sitemap_url in dict.fromkeys(sitemap_urls):  # de-dup, keep discovery order
            leaf_urls.extend(await _parse_sitemap(client, sitemap_url, rate_limit_seconds))
        for url in leaf_urls:
            add(url, classify_url_by_path(url))

        # Homepage navigation always runs (one cheap request) — sale/promo
        # pages in particular often live only in nav, never in a sitemap.
        homepage_html = await _fetch_text(client, base_url, rate_limit_seconds)
        if homepage_html:
            soup = BeautifulSoup(homepage_html, "html.parser")
            hrefs = [a.get("href") for a in soup.find_all("a", href=True)][:MAX_HOMEPAGE_LINKS]
            for href in hrefs:
                if href:
                    add(href, classify_url_by_path(href))

        # Bounded page-signal fallback for whatever's still ambiguous.
        to_check = list(result.unknown_urls)[:PAGE_SIGNAL_CHECK_BUDGET]
        for url in to_check:
            await rate_limiter.wait(url, rate_limit_seconds)
            kind = await classify_url_by_page_signals(client, url)
            if kind != "unknown":
                result.unknown_urls.discard(url)
                getattr(result, f"{kind}_urls").add(url)

    return result
