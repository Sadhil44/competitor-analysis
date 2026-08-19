"""Turns a fetched page into structured product data.

Layered, deterministic-first: schema.org Product/Offer data is trusted
whenever it's present, whether shipped as JSON-LD or as HTML microdata
(itemscope/itemtype/itemprop — some storefronts use one but not the
other; both are the same schema.org data model, just serialized
differently). Next, embedded ecommerce app-state JSON (currently:
Shopify's ProductJson script tags, a narrow, well-documented convention
rather than an attempt at exhaustive SPA-state parsing), then a
competitor-specific selector registry (a real extension point, empty
until a selector set has actually been verified against a real competitor
site), then a generic HTML heuristic pass. The existing multi-pass LLM
extraction is the last resort, used only when none of the above found
anything — an entire page of HTML is never sent to the LLM when
structured data already answered the question.
"""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from anthropic import AsyncAnthropic
from bs4 import BeautifulSoup

from app.schemas.extraction import ExtractedProduct, ExtractedProductList
from app.scraping.fetcher import FetchedPage
from app.scraping.jsonld import extract_jsonld_blocks, iter_jsonld_nodes, node_types

logger = logging.getLogger(__name__)

client = AsyncAnthropic()

EXTRACTION_MODEL = "claude-haiku-4-5"

_PRICE_PATTERN = re.compile(r"\d[\d,]*\.?\d*")
_OUT_OF_STOCK_AVAILABILITY = {"outofstock", "soldout", "discontinued"}


def _parse_price_value(value: object) -> Decimal | None:
    """Robust against the shapes schema.org/embedded JSON actually use: a
    bare number, a numeric string, or a string carrying a currency symbol
    ("$19.99", "USD 19.99", "1,234.56"). Returns None rather than guessing
    when nothing number-shaped is found — never invents a price.
    """
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        match = _PRICE_PATTERN.search(value.replace(",", ""))
        if not match:
            return None
        try:
            return Decimal(match.group())
        except InvalidOperation:
            return None
    return None


def _parse_availability(value: object) -> bool:
    if not isinstance(value, str):
        return True
    token = value.rsplit("/", 1)[-1].strip().lower()
    return token not in _OUT_OF_STOCK_AVAILABILITY


def _extract_brand(value: object) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        name = value.get("name")
        return name if isinstance(name, str) else None
    return None


def _extract_image(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _extract_image(value[0])
    if isinstance(value, dict):
        url = value.get("url")
        return url if isinstance(url, str) else None
    return None


def _parse_offer(offer: object) -> tuple[Decimal | None, str | None, bool]:
    """Handles a single Offer, an AggregateOffer (lowPrice/highPrice
    instead of price), or a list of Offers (first one wins — good enough
    for "does this product have a price", not a full variant matrix)."""
    if isinstance(offer, list):
        offer = offer[0] if offer else None
    if not isinstance(offer, dict):
        return None, None, True
    price = _parse_price_value(offer.get("price"))
    if price is None:
        price = _parse_price_value(offer.get("lowPrice"))
    currency = offer.get("priceCurrency") if isinstance(offer.get("priceCurrency"), str) else None
    in_stock = _parse_availability(offer.get("availability"))
    return price, currency, in_stock


def _product_from_jsonld_node(node: dict, page_url: str) -> ExtractedProduct | None:
    name = node.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    price, currency, in_stock = _parse_offer(node.get("offers"))
    sku = node.get("sku") or node.get("mpn")
    category = node.get("category") if isinstance(node.get("category"), str) else None
    description = node.get("description") if isinstance(node.get("description"), str) else None
    url = node.get("url") if isinstance(node.get("url"), str) else page_url
    return ExtractedProduct(
        sku=sku if isinstance(sku, str) else None,
        name=name.strip(),
        price=price,
        currency=currency or "USD",
        in_stock=in_stock,
        category=category,
        brand=_extract_brand(node.get("brand")),
        description=description,
        image_url=_extract_image(node.get("image")),
        url=urljoin(page_url, url),
        source="jsonld",
    )


def _extract_from_jsonld(soup: BeautifulSoup, page_url: str) -> list[ExtractedProduct]:
    """Handles every documented JSON-LD shape via jsonld.py's
    flattening: a single object, a list of objects, an @graph wrapper, and
    multiple Product nodes on one page (e.g. a category listing) all fall
    out of the same iteration.
    """
    products = []
    for block in extract_jsonld_blocks(soup):
        for node in iter_jsonld_nodes(block):
            if "Product" not in node_types(node):
                continue
            product = _product_from_jsonld_node(node, page_url)
            if product:
                products.append(product)
    return products


_MICRODATA_PRODUCT_TYPE = re.compile(r"schema\.org/Product\b", re.IGNORECASE)


def _microdata_value(el) -> str | None:
    """An itemprop element's value lives in different places depending on
    tag: `content` (meta/data-style spans), `href` (a/link), `src` (img),
    or failing those, its own text content.
    """
    if el.has_attr("content"):
        return el["content"]
    if el.name in ("a", "link") and el.has_attr("href"):
        return el["href"]
    if el.name == "img" and el.has_attr("src"):
        return el["src"]
    text = el.get_text(strip=True)
    return text or None


def _direct_itemprops(scope_el: BeautifulSoup) -> dict[str, list]:
    """Collects {itemprop_name: [elements]} for descendants of scope_el,
    without crossing into a nested itemscope's own subtree — matching
    HTML microdata's scoping rules, so e.g. a nested `offers` Offer's
    `price` itemprop is never mistaken for the outer Product's own.
    """
    props: dict[str, list] = {}

    def walk(el, in_current_scope: bool) -> None:
        for child in el.find_all(recursive=False):
            child_opens_scope = child.has_attr("itemscope")
            if in_current_scope and child.has_attr("itemprop"):
                props.setdefault(child["itemprop"], []).append(child)
            walk(child, in_current_scope=not child_opens_scope)

    walk(scope_el, in_current_scope=True)
    return props


def _product_from_microdata(scope_el: BeautifulSoup, page_url: str) -> ExtractedProduct | None:
    props = _direct_itemprops(scope_el)
    name_els = props.get("name")
    if not name_els:
        return None
    name = _microdata_value(name_els[0])
    if not name:
        return None

    price = currency = None
    in_stock = True
    if props.get("offers"):
        offer_props = _direct_itemprops(props["offers"][0])
        if offer_props.get("price"):
            price = _parse_price_value(_microdata_value(offer_props["price"][0]))
        if offer_props.get("priceCurrency"):
            currency = _microdata_value(offer_props["priceCurrency"][0])
        if offer_props.get("availability"):
            avail_el = offer_props["availability"][0]
            in_stock = _parse_availability(avail_el.get("href") or _microdata_value(avail_el))

    sku = _microdata_value(props["sku"][0]) if props.get("sku") else None
    description = _microdata_value(props["description"][0]) if props.get("description") else None
    image = _microdata_value(props["image"][0]) if props.get("image") else None
    brand = _microdata_value(props["brand"][0]) if props.get("brand") else None
    category = _microdata_value(props["category"][0]) if props.get("category") else None

    return ExtractedProduct(
        sku=sku,
        name=name.strip(),
        price=price,
        currency=currency or "USD",
        in_stock=in_stock,
        category=category,
        brand=brand,
        description=description,
        image_url=urljoin(page_url, image) if image else None,
        url=page_url,
        source="microdata",
    )


def _extract_from_microdata(soup: BeautifulSoup, page_url: str) -> list[ExtractedProduct]:
    """schema.org Product expressed as HTML microdata (itemscope/itemtype/
    itemprop) rather than JSON-LD — some storefronts (e.g. Holland Bulb
    Farms) ship this instead of, not in addition to, JSON-LD, so without
    this source their product pages would have no deterministic structured
    data at all and would fall straight to the LLM on every single page.
    """
    products = []
    for scope_el in soup.find_all(attrs={"itemtype": _MICRODATA_PRODUCT_TYPE}):
        product = _product_from_microdata(scope_el, page_url)
        if product:
            products.append(product)
    return products


def _strip_html(raw: str) -> str:
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)


def _product_from_shopify_json(data: dict, page_url: str) -> ExtractedProduct | None:
    """Shopify's `<script type="application/json" id="ProductJson-*">`
    convention: the full product object, prices in integer cents. Widely
    used enough across Shopify storefronts to be worth handling by name,
    unlike a generic SPA-state guesser.
    """
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    variants = data.get("variants") if isinstance(data.get("variants"), list) else []
    first_variant = variants[0] if variants and isinstance(variants[0], dict) else {}

    price_cents = first_variant.get("price", data.get("price"))
    price = Decimal(price_cents) / 100 if isinstance(price_cents, int) else _parse_price_value(price_cents)

    compare_at_cents = first_variant.get("compare_at_price", data.get("compare_at_price"))
    original_price = (
        Decimal(compare_at_cents) / 100 if isinstance(compare_at_cents, int) else _parse_price_value(compare_at_cents)
    )
    if original_price is not None and price is not None and original_price <= price:
        original_price = None  # not actually marked down

    sku = first_variant.get("sku") or data.get("sku")
    description = data.get("description")
    image = data.get("featured_image")
    if not isinstance(image, str):
        images = data.get("images")
        image = images[0] if isinstance(images, list) and images and isinstance(images[0], str) else None

    return ExtractedProduct(
        sku=sku if isinstance(sku, str) else None,
        name=title.strip(),
        price=price,
        original_price=original_price,
        # Shopify's ProductJson doesn't carry an ISO currency code — every
        # currently-configured competitor is a US storefront, so USD is a
        # reasonable default here, not a fabricated observation.
        currency="USD",
        in_stock=bool(first_variant.get("available", True)),
        category=data.get("type") if isinstance(data.get("type"), str) else None,
        brand=data.get("vendor") if isinstance(data.get("vendor"), str) else None,
        description=_strip_html(description) if isinstance(description, str) else None,
        image_url=image,
        url=page_url,
        source="embedded_json",
    )


def _extract_from_embedded_state(soup: BeautifulSoup, page_url: str) -> list[ExtractedProduct]:
    products = []
    for script in soup.find_all("script", type="application/json"):
        script_id = script.get("id") or ""
        if not script_id.lower().startswith("productjson"):
            continue
        raw = script.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        product = _product_from_shopify_json(data, page_url)
        if product:
            products.append(product)
    return products


# Real, documented extension point: map a competitor slug to a function
# that pulls products from that site's specific HTML structure when
# neither JSON-LD nor embedded JSON state is present. Left empty — adding
# an entry for a real competitor without first verifying its actual
# markup would mean guessing at selectors, which risks silently extracting
# nothing (or the wrong thing) rather than falling through to a source
# that's actually been checked. Populate per-competitor as needed.
CompetitorSelectorFn = Callable[[BeautifulSoup, str], list[ExtractedProduct]]
COMPETITOR_SELECTORS: dict[str, CompetitorSelectorFn] = {}


def _extract_with_competitor_selectors(
    soup: BeautifulSoup, page_url: str, competitor_slug: str | None
) -> list[ExtractedProduct]:
    if competitor_slug is None:
        return []
    selector_fn = COMPETITOR_SELECTORS.get(competitor_slug)
    if selector_fn is None:
        return []
    return selector_fn(soup, page_url)


_PRODUCT_CONTAINER_HINTS = re.compile(r"product", re.IGNORECASE)
_PRICE_CLASS_HINTS = re.compile(r"price", re.IGNORECASE)
_TITLE_TAGS = ("h1", "h2", "h3", "h4")


def _extract_from_generic_html(soup: BeautifulSoup, page_url: str) -> list[ExtractedProduct]:
    """Last deterministic resort before the LLM: look for repeated
    "product card"-shaped elements — a container whose class mentions
    "product", holding a heading and a price-looking element. This is a
    broad convention-based heuristic (common across many storefront
    themes), not one competitor's specific structure hardcoded here.
    """
    products = []
    containers = soup.find_all(
        lambda tag: tag.name in ("li", "div", "article")
        and any(_PRODUCT_CONTAINER_HINTS.search(c) for c in tag.get("class", []))
    )
    for container in containers:
        heading = container.find(_TITLE_TAGS)
        if heading is None:
            continue
        name = heading.get_text(strip=True)
        if not name:
            continue
        price_el = container.find(
            lambda tag: tag.name in ("span", "div", "p")
            and any(_PRICE_CLASS_HINTS.search(c) for c in tag.get("class", []))
        )
        price = _parse_price_value(price_el.get_text(strip=True)) if price_el else None
        link = container.find("a", href=True)
        url = urljoin(page_url, link["href"]) if link else page_url
        products.append(
            ExtractedProduct(name=name, price=price, currency="USD", in_stock=True, url=url, source="generic_html")
        )
    return products


async def extract_products(page_text: str) -> ExtractedProductList:
    """Turn scraped page text into structured product/price data via the
    LLM. Last-resort path — see extract_products_merged, which only calls
    this when every deterministic source above found nothing.

    Uses Claude's native structured-output support (client.messages.parse)
    rather than a separate library — the response is validated against
    ExtractedProductList automatically. Haiku tier: this runs once per page
    per crawl, potentially many times, so cost matters more here than for
    the agent's own reasoning (which uses a stronger model in Phase 3).
    """
    # The SDK refuses a non-streaming call whose max_tokens ceiling makes it
    # *estimate* the request could exceed 10 minutes — a conservative,
    # ceiling-based heuristic, not a reflection of actual usage (these calls
    # finish in seconds). Extending the client timeout suppresses that guard
    # without needing to restructure this as a streaming call.
    response = await client.with_options(timeout=600.0).messages.parse(
        model=EXTRACTION_MODEL,
        # 4096 truncated mid-JSON on a real catalog page; 16000 still
        # under-extracted on a single long page with ~140 products (the
        # model satisficed rather than running out of room) — 32000 gives
        # real headroom (Haiku 4.5 supports up to 64K output).
        max_tokens=32000,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract EVERY product listed on this page — do not skip any, "
                    "even if there are 100+ products. Some pages list a large "
                    "number of items; be exhaustive, not selective.\n\n"
                    "For each product, extract: name, price, currency, stock status, "
                    "and sku if a SKU or item number is shown (e.g. 'SKU: 12345') — "
                    "leave sku null only if none is visible.\n\n"
                    "Some listings show a current/sale price alongside a crossed-out "
                    "original price (e.g. '$17.98 Was: $44.95') — extract the "
                    "current/sale price into price, and the crossed-out original into "
                    "original_price. Leave original_price null if there's no markdown.\n\n"
                    "Some out-of-stock or 'notify me' listings show no price at all — "
                    "set price to null in that case rather than guessing a number.\n\n"
                    "Page content:\n\n" + page_text
                ),
            }
        ],
        output_format=ExtractedProductList,
    )
    for item in response.parsed_output.products:
        item.source = "llm"
    return response.parsed_output


EXTRACTION_PASSES = 2


async def _extract_products_llm_merged(page_text: str, passes: int = EXTRACTION_PASSES) -> ExtractedProductList:
    """Run extract_products multiple times over the same page and merge by
    product name, taking the union.

    A single call over a long, dense page isn't fully exhaustive or
    deterministic — repeated calls on identical input have been observed to
    vary more than 2x in how many products they capture (52 to 112 products
    from the same Holland Bulb Farms page across separate calls). Multiple
    passes catch items any single pass missed; where a name is captured by
    more than one pass, prefer whichever result has a non-null price.
    """
    results = await asyncio.gather(*[extract_products(page_text) for _ in range(passes)])

    merged: dict[str, ExtractedProduct] = {}
    for result in results:
        for item in result.products:
            existing = merged.get(item.name)
            if existing is None or (existing.price is None and item.price is not None):
                merged[item.name] = item
    return ExtractedProductList(products=list(merged.values()))


async def extract_products_merged(fetched: FetchedPage, *, competitor_slug: str | None = None) -> ExtractedProductList:
    """Top-level entry point for the extraction stage: try deterministic
    sources in priority order, falling back to the multi-pass LLM
    extraction only when none of them found anything. Never sends the raw
    HTML/text to the LLM when a deterministic source already answered.
    """
    if fetched.html:
        soup = BeautifulSoup(fetched.html, "html.parser")

        for source_name, products in (
            ("jsonld", _extract_from_jsonld(soup, fetched.url)),
            ("microdata", _extract_from_microdata(soup, fetched.url)),
            ("embedded_json", _extract_from_embedded_state(soup, fetched.url)),
            ("competitor_selector", _extract_with_competitor_selectors(soup, fetched.url, competitor_slug)),
        ):
            if products:
                logger.info(
                    "extraction source=%s count=%d url=%s", source_name, len(products), fetched.url
                )
                return ExtractedProductList(products=products)

        generic = _extract_from_generic_html(soup, fetched.url)
        priced = [p for p in generic if p.price is not None]
        # Only trust the generic heuristic pass over the LLM fallback when
        # it's finding real prices for a real share of what it matched —
        # otherwise a page whose theme doesn't match the heuristic (rather
        # than genuinely having no products) would silently return nothing
        # useful instead of falling through to the LLM.
        if generic and len(priced) >= max(1, len(generic) // 2):
            logger.info("extraction source=generic_html count=%d url=%s", len(generic), fetched.url)
            return ExtractedProductList(products=generic)

    logger.info("extraction falling back to LLM url=%s", fetched.url)
    return await _extract_products_llm_merged(fetched.text)
