import difflib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import CompetitorConfig, load_competitors_config
from app.models import Campaign, Competitor, CrawlRun, PriceObservation, Product
from app.schemas.campaign import DetectedCampaign
from app.intelligence.text import name_matches_query, significant_keywords
from app.schemas.extraction import ExtractedProduct
from app.scraping.campaigns import discover_campaigns
from app.scraping.discovery import discover_urls, extract_product_links
from app.scraping.extractor import extract_products_merged
from app.scraping.fetcher import fetch_page

logger = logging.getLogger(__name__)


async def seed_competitors(session: AsyncSession) -> None:
    """Sync config/competitors.yaml into the competitors table.

    Safe to re-run — only inserts competitors whose slug isn't already there.
    """
    for entry in load_competitors_config():
        result = await session.execute(select(Competitor).where(Competitor.slug == entry.slug))
        existing = result.scalar_one_or_none()
        if existing is None:
            session.add(
                Competitor(
                    slug=entry.slug,
                    name=entry.name,
                    website_url=entry.website_url,
                    notes=entry.notes,
                )
            )
    await session.commit()


MAX_PAGES_PER_CATALOG_URL = 20  # safety cap only — the loop normally stops earlier

# Some sites declare a next-page link that isn't functionally real — it keeps
# incrementing while quietly re-serving the same underlying catalog content
# (seen on Holland Bulb Farms). Comparing whole-page text similarity doesn't
# reliably catch this: two genuinely different real pages already share most
# of their text (nav, footer, filters), so that similarity sits high for
# real pagination too. Comparing only the text immediately surrounding each
# price strips that boilerplate out — on real distinct pages the price
# context differs a lot page to page (~0.2 similarity, measured against
# Fast Growing Trees); on a recycled page it stays high (~0.7, measured
# against Holland Bulb Farms). This also runs before the LLM extraction
# call, so a dead link is caught without paying for a wasted extraction.
PRICE_CONTEXT_WINDOW = 40
PRICE_CONTEXT_SIMILARITY_THRESHOLD = 0.5

# Bounds on how much of a single crawl_competitor() run's discovered URLs
# actually get fetched — discover_urls() already caps total discovery, but
# a large sitemap can still hand back more category/product/promo URLs than
# it's polite to fetch (and, for category URLs, each one is itself up to
# MAX_PAGES_PER_CATALOG_URL further requests via ingest_page's pagination).
# Tracking scope is a competitor's full catalog (not one category), so
# these are generous rather than tight — still a real, finite bound (never
# "unbounded"), just sized for thousands of products rather than a few
# hundred.
MAX_CATEGORY_URLS_PER_CRAWL = 50
MAX_PRODUCT_URLS_PER_CRAWL = 5000
MAX_PROMOTIONAL_URLS_PER_CRAWL = 15


def _price_context_fingerprint(text: str) -> str:
    spans = (m.start() for m in re.finditer(re.escape("$"), text))
    return " ".join(text[max(0, s - PRICE_CONTEXT_WINDOW) : s + PRICE_CONTEXT_WINDOW] for s in spans)


def _dedupe_page_items(items: list[ExtractedProduct]) -> list[ExtractedProduct]:
    """Collapses multiple ExtractedProduct entries from a SINGLE fetched
    page that identify the same real product — keyed by sku when present,
    else by name — to one, preferring whichever has a non-null price (same
    "prefer priced" convention as extract_products_merged's own multi-pass
    dedup in app/scraping/extractor.py).

    Without this, a page whose JSON-LD embeds more than one Product node
    for what's really one item (seen live on gardeners.com product pages:
    a "related products" carousel or per-swatch variant block emitting its
    own Product node alongside the main one) persists every node as a
    separate PriceObservation on the SAME Product row — silently corrupting
    its price history with an unrelated item's price. This is a narrower,
    additional guard alongside _find_or_create_product's sku-vs-name
    matching fix above: that fix stops CROSS-page collisions from merging
    distinct SKUs together; this stops a SINGLE page's own extraction from
    doing the same thing to itself in one pass.
    """
    deduped: dict[str, ExtractedProduct] = {}
    for item in items:
        key = item.sku or item.name
        existing = deduped.get(key)
        if existing is None or (existing.price is None and item.price is not None):
            deduped[key] = item
    return list(deduped.values())


def _select_own_page_item(items: list[ExtractedProduct], page_url: str) -> list[ExtractedProduct]:
    """Individual product-page visits (crawl_competitor's per-product loop)
    expect extraction to return exactly one item — the page's own product,
    which then inherits page_url as its url via _find_or_create_product's
    fallback (item.url or fallback_url). Confirmed live on a vegogarden.com
    product page with no JSON-LD/microdata to extract deterministically:
    extraction fell through to the LLM pass, which doesn't isolate "the"
    product — it returned 43 items pulled from what was actually the site's
    embedded catalog/nav, none carrying their own url (the LLM extraction
    prompt never asks for one). Persisting all of them would silently
    misattribute this one page's url to 42 unrelated real products.

    When more than one item comes back, only one of them is genuinely this
    page's own product — narrowed down to whichever has the most
    significant words in common with the page URL's own slug, the best
    signal available for "which one is actually this page." Falls through
    unchanged when there's already just one item (the normal case).
    """
    if len(items) <= 1:
        return items
    slug = re.sub(r"[-_]", " ", page_url.rstrip("/").split("/")[-1])
    slug_keywords = significant_keywords(slug)
    if not slug_keywords:
        return items[:1]
    best = max(items, key=lambda item: sum(1 for kw in slug_keywords if name_matches_query(item.name, [kw])))
    return [best]


def _utcnow() -> datetime:
    # Product/Campaign/CrawlRun timestamp columns are naive-UTC (see the
    # migrations under app/db/migrations/versions) — matches the existing
    # convention elsewhere in the app (e.g. app/api/prices.py) for producing
    # a value that round-trips cleanly through them.
    return datetime.now(UTC).replace(tzinfo=None)


async def _find_or_create_product(
    session: AsyncSession, competitor_id: int, item: ExtractedProduct, fallback_url: str
) -> Product:
    """Find-or-create keyed by (competitor_id, sku) when the item has a
    sku — a stronger identity signal than name — falling back to the
    existing (competitor_id, name) match (see app/models/product.py) ONLY
    when the item has no sku at all. Deliberately elif, not a second
    unconditional check: when item.sku is present but doesn't match any
    existing row (a genuinely new SKU this competitor hasn't been seen
    with before), that must create a new Product, not fall through to a
    name match. Several sites (e.g. gardeners.com's per-variant
    "-vs-sku-NNNNN" product URLs) render different SKU variants of the same
    base item under near-identical rendered title text; falling through to
    name in that case silently merged distinct SKUs (different sizes/
    configurations, different real prices) into one Product row, corrupting
    its price history with an unrelated variant's price (confirmed live: a
    $1 placeholder-priced variant and a real $999.99 variant merged into one
    row, surfaced downstream as a fake +99,899% "price change").
    """
    product = None
    if item.sku:
        result = await session.execute(
            select(Product).where(Product.competitor_id == competitor_id, Product.sku == item.sku)
        )
        product = result.scalar_one_or_none()
    elif item.name:
        result = await session.execute(
            select(Product).where(Product.competitor_id == competitor_id, Product.name == item.name)
        )
        product = result.scalar_one_or_none()

    url = item.url or fallback_url
    if product is None:
        return Product(
            competitor_id=competitor_id,
            sku=item.sku,
            name=item.name,
            url=url,
            category=item.category or "",
            brand=item.brand,
            description=item.description,
            image_url=item.image_url,
            attributes=dict(item.attributes),
        )

    # Existing row: refresh what's mutable, fill in what was previously
    # missing, never overwrite a real value with an absence.
    product.last_seen_at = _utcnow()
    if item.category:
        product.category = item.category
    if item.sku and not product.sku:
        product.sku = item.sku
    if url:
        product.url = url
    if item.brand and not product.brand:
        product.brand = item.brand
    if item.description and not product.description:
        product.description = item.description
    if item.image_url and not product.image_url:
        product.image_url = item.image_url
    if item.attributes:
        # Per-key fill-when-missing, not a whole-dict overwrite — a later
        # crawl that only found e.g. `material` shouldn't erase a `height`
        # value a JSON-LD pass found earlier. Mutate a fresh dict rather
        # than product.attributes in place so SQLAlchemy's change-tracking
        # on the JSONB column actually notices the update.
        merged = dict(product.attributes)
        for key, value in item.attributes.items():
            if value and not merged.get(key):
                merged[key] = value
        product.attributes = merged
    return product


async def _persist_extracted_product(
    session: AsyncSession, competitor_id: int, item: ExtractedProduct, page_url: str
) -> Product:
    product = await _find_or_create_product(session, competitor_id, item, page_url)
    session.add(product)

    promo_text = item.promo_text
    if item.original_price is not None and item.original_price != item.price:
        was_text = f"Was {item.currency} {item.original_price}"
        promo_text = f"{promo_text}; {was_text}" if promo_text else was_text

    session.add(
        PriceObservation(
            price=item.price,
            currency=item.currency,
            in_stock=item.in_stock,
            promo_text=promo_text,
            source="scheduled_crawl",
            product=product,
        )
    )
    return product


async def _persist_campaign(
    session: AsyncSession, competitor_id: int, detected: DetectedCampaign, product_id: int | None = None
) -> bool:
    """Returns True if a new Campaign row was inserted. Campaign is
    append-only by design (see app/models/campaign.py) so promo history
    over time is preserved, but that's for tracking a promotion's real
    lifecycle — not for re-inserting the same still-running sitewide banner
    every time a crawl happens to fetch the page it's on.

    Dedups on (competitor, product, discount_text) — deliberately NOT
    title: the same banner gets LLM-normalized into differently-worded
    titles nearly every time it's seen (observed live: one sitewide "free
    shipping" banner produced 26 distinctly-titled rows for a single
    crawl), so requiring an exact title match let all of them through.
    discount_text is far more stable, and including product_id keeps two
    real, different product-specific promotions that happen to share a
    discount_text (e.g. two unrelated "10% off" deals) from colliding.
    """
    result = await session.execute(
        select(Campaign.id).where(
            Campaign.competitor_id == competitor_id,
            Campaign.product_id == product_id,
            Campaign.discount_text == detected.discount_text,
        )
    )
    if result.scalar_one_or_none() is not None:
        return False

    session.add(
        Campaign(
            competitor_id=competitor_id,
            product_id=product_id,
            title=detected.title,
            description=detected.description,
            discount_text=detected.discount_text,
            source_url=detected.source_url,
        )
    )
    return True


@dataclass
class IngestPageResult:
    campaigns_found: int
    # Product-detail links seen on the crawled page(s) — sourced from this
    # one tracked category listing, not the site's full sitemap, so a
    # caller can fetch individual product pages without widening scope
    # beyond the category this competitor is actually being tracked for.
    product_links: set[str]


async def ingest_page(session: AsyncSession, competitor_slug: str, url: str) -> IngestPageResult:
    """Fetch a competitor's catalog starting at `url`, following whatever
    "next page" link the site itself declares (see fetch_page) for as long
    as one exists, extracting products from each page and writing Product +
    PriceObservation rows for the competitor identified by `competitor_slug`.
    Also scans each fetched page for promotional banner content (persisting
    any new Campaign rows found) and collects product-detail links seen on
    the page, for the caller to optionally crawl individually.

    Stops when: the page declares no next link, the declared next link
    points somewhere we've already visited (guards against a "Next" link
    that stays present past the real last page), the next page's pricing
    content is too similar to the current page's (guards against a next-link
    that keeps advancing without the underlying content actually changing),
    or a page yields zero products we haven't already seen this run. No
    per-site pagination logic needed — sites without any real pagination (a
    single long page) simply stop after page one because there's no next
    link to follow.
    """
    result = await session.execute(select(Competitor).where(Competitor.slug == competitor_slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise ValueError(f"Unknown competitor slug: {competitor_slug!r} — run seed_competitors first")
    # Captured once as plain values, not re-read via `competitor.id` later:
    # a session.rollback() (see crawl_competitor, which shares this session)
    # expires every ORM object it's tracking, and a bare attribute read on
    # an expired async-ORM object outside an explicit await raises
    # sqlalchemy.exc.MissingGreenlet — confirmed live on a real crawl.
    competitor_id = competitor.id
    competitor_website_url = competitor.website_url

    seen_names: set[str] = set()
    visited_urls: set[str] = set()
    page_url: str | None = url
    previous_price_context: str | None = None
    campaigns_found = 0
    product_links: set[str] = set()

    for _ in range(MAX_PAGES_PER_CATALOG_URL):
        if page_url is None or page_url in visited_urls:
            break
        visited_urls.add(page_url)

        fetched = await fetch_page(page_url)
        price_context = _price_context_fingerprint(fetched.text)
        if previous_price_context is not None:
            similarity = difflib.SequenceMatcher(None, previous_price_context, price_context).ratio()
            if similarity > PRICE_CONTEXT_SIMILARITY_THRESHOLD:
                break
        previous_price_context = price_context

        extracted = await extract_products_merged(fetched, competitor_slug=competitor_slug)
        extracted_products = _dedupe_page_items(extracted.products)

        for detected in await discover_campaigns(fetched.html, page_url):
            if await _persist_campaign(session, competitor_id, detected):
                campaigns_found += 1

        page_product_links = extract_product_links(fetched.html, page_url, competitor_website_url)
        new_links = page_product_links - product_links
        product_links |= page_product_links

        new_items = [item for item in extracted_products if item.name not in seen_names]
        # A listing page contributes two independent things: products
        # extracted directly from its own content, and links to individual
        # product pages. A collection page with no inline JSON-LD/microdata
        # (common — that data usually lives on the product page, not the
        # listing) can legitimately extract zero products here while still
        # linking to dozens of real ones; stopping pagination on that would
        # silently cap discovery at whatever fit on page one. Only stop once
        # a page contributes nothing new on *either* front.
        if not new_items and not new_links:
            break

        for item in new_items:
            seen_names.add(item.name)
            await _persist_extracted_product(session, competitor_id, item, page_url)

        await session.commit()
        page_url = fetched.next_page_url

    logger.info(
        "ingest_page done competitor=%s start_url=%s pages=%d products=%d campaigns=%d product_links=%d",
        competitor_slug,
        url,
        len(visited_urls),
        len(seen_names),
        campaigns_found,
        len(product_links),
    )
    return IngestPageResult(campaigns_found=campaigns_found, product_links=product_links)


async def _find_competitor_config(slug: str) -> CompetitorConfig:
    for entry in load_competitors_config():
        if entry.slug == slug:
            return entry
    raise ValueError(f"No config/competitors.yaml entry for competitor slug: {slug!r}")


async def crawl_competitor(session: AsyncSession, competitor_slug: str, *, scoped: bool = False) -> CrawlRun:
    """Full pipeline for one competitor: discover URLs from its configured
    website_url/catalog_urls (see app/scraping/discovery.py), fetch and
    extract each, persist Products/PriceObservations/Campaigns, and record
    a CrawlRun. A failure fetching or processing any single URL is caught
    and logged into the CrawlRun's error_log, not raised — one bad page
    must not abort the whole competitor's crawl.

    `scoped=True` skips discover_urls() entirely and crawls only the
    configured catalog_urls — for a competitor whose catalog_urls is a
    single collection (e.g. "raised garden beds") rather than "everything."
    This isn't just about the site-wide sitemap *product* union: discover_urls'
    `category_urls` is every /collections/-shaped URL the site's sitemap
    contains, not just the configured one, so without this branch the
    category loop below would crawl up to MAX_CATEGORY_URLS_PER_CRAWL
    unrelated categories too (confirmed live — gardeners.com's sitemap
    surfaced 561 category URLs from one catalog_urls entry). Also skips the
    expensive sitemap walk + per-URL page-signal classification discover_urls
    does for its own sake, which scoped crawls have no use for.
    """
    result = await session.execute(select(Competitor).where(Competitor.slug == competitor_slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise ValueError(f"Unknown competitor slug: {competitor_slug!r} — run seed_competitors first")
    # Captured once as a plain value — see the matching comment in
    # ingest_page for why `competitor.id` can't just be re-read later:
    # this session sees many session.rollback() calls across the loops
    # below, each of which expires every ORM object it's tracking, and a
    # bare attribute read on an expired object outside an explicit await
    # raises sqlalchemy.exc.MissingGreenlet.
    competitor_id = competitor.id

    config = await _find_competitor_config(competitor_slug)

    crawl_run = CrawlRun(competitor_id=competitor_id, status="running")
    session.add(crawl_run)
    await session.commit()

    errors: list[str] = []
    pages_fetched = 0
    campaigns_found = 0

    try:
        if scoped:
            discovered = None
            category_urls_to_crawl = list(config.crawl.catalog_urls)[:MAX_CATEGORY_URLS_PER_CRAWL]
            logger.info(
                "scoped crawl competitor=%s catalog_urls=%d (skipping site-wide discovery)",
                competitor_slug,
                len(category_urls_to_crawl),
            )
        else:
            discovered = await discover_urls(
                config.website_url, config.crawl.catalog_urls, rate_limit_seconds=config.crawl.rate_limit_seconds
            )
            logger.info(
                "discovery competitor=%s products=%d categories=%d promos=%d unknown=%d",
                competitor_slug,
                len(discovered.product_urls),
                len(discovered.category_urls),
                len(discovered.promotional_urls),
                len(discovered.unknown_urls),
            )
            category_urls_to_crawl = list(discovered.category_urls)[:MAX_CATEGORY_URLS_PER_CRAWL]

        # Category/listing pages: fetch + extract + follow pagination via
        # the existing ingest_page loop, which also runs campaign detection
        # and collects product-detail links on every page (including
        # paginated ones) it visits.
        category_product_urls: set[str] = set()
        for category_url in category_urls_to_crawl:
            try:
                page_result = await ingest_page(session, competitor_slug, category_url)
                campaigns_found += page_result.campaigns_found
                category_product_urls |= page_result.product_links
                pages_fetched += 1
            except Exception:
                logger.warning("category crawl failed url=%s", category_url, exc_info=True)
                errors.append(f"category {category_url}: fetch/extract failed")
                # A failed flush/commit leaves the session unusable until
                # rolled back — without this, one bad category page would
                # take down every URL processed after it, not just itself.
                await session.rollback()

        # Individual product-detail pages. Normally the union of links found
        # on the crawled category page(s) and the site-wide sitemap —
        # tracking scope is a competitor's full catalog, so both signals are
        # used together rather than one being a fallback for the other (the
        # sitemap may miss products a category listing links to and vice
        # versa). When scoped=True, there's no sitemap-wide pass at all
        # (discovered is None) — category_product_urls, already scoped to
        # catalog_urls, is the only source.
        sitemap_product_urls = discovered.product_urls if discovered else set()
        product_url_source = category_product_urls if scoped else category_product_urls | sitemap_product_urls
        logger.info(
            "product URLs for competitor=%s: %d from category pages, %d from sitemap, %d combined (scoped=%s)",
            competitor_slug,
            len(category_product_urls),
            len(sitemap_product_urls),
            len(product_url_source),
            scoped,
        )

        for product_url in list(product_url_source)[:MAX_PRODUCT_URLS_PER_CRAWL]:
            try:
                fetched = await fetch_page(product_url, rate_limit_seconds=config.crawl.rate_limit_seconds)
                pages_fetched += 1
                extracted = await extract_products_merged(fetched, competitor_slug=competitor_slug)
                items = _select_own_page_item(_dedupe_page_items(extracted.products), product_url)
                for item in items:
                    await _persist_extracted_product(session, competitor_id, item, product_url)
                await session.commit()
            except Exception:
                logger.warning("product page fetch failed url=%s", product_url, exc_info=True)
                errors.append(f"product {product_url}: fetch/extract failed")
                await session.rollback()

        # Promotional/sale landing pages: campaign detection only — these
        # pages are marketing copy, not clean product listings. Only
        # meaningful when full discovery ran (scoped crawls skip it — see
        # above); the homepage banner check just below still runs either
        # way, so a scoped crawl isn't blind to sitewide promos entirely.
        for promo_url in list(discovered.promotional_urls)[:MAX_PROMOTIONAL_URLS_PER_CRAWL] if discovered else []:
            try:
                fetched = await fetch_page(promo_url, rate_limit_seconds=config.crawl.rate_limit_seconds)
                pages_fetched += 1
                for detected in await discover_campaigns(fetched.html, promo_url):
                    if await _persist_campaign(session, competitor_id, detected):
                        campaigns_found += 1
                await session.commit()
            except Exception:
                logger.warning("promo page fetch failed url=%s", promo_url, exc_info=True)
                errors.append(f"promo {promo_url}: fetch/extract failed")
                await session.rollback()

        # The homepage itself is also a common home for an announcement bar
        # or hero banner, and isn't necessarily one of the discovered
        # category/promo URLs above.
        try:
            homepage = await fetch_page(config.website_url, rate_limit_seconds=config.crawl.rate_limit_seconds)
            pages_fetched += 1
            for detected in await discover_campaigns(homepage.html, config.website_url):
                if await _persist_campaign(session, competitor_id, detected):
                    campaigns_found += 1
            await session.commit()
        except Exception:
            logger.warning("homepage fetch failed url=%s", config.website_url, exc_info=True)
            errors.append(f"homepage {config.website_url}: fetch failed")
            await session.rollback()

        final_status = "failed" if errors and pages_fetched == 0 else ("partial_failure" if errors else "success")
    except Exception as exc:
        # A failure in discover_urls() itself (e.g. the site is entirely
        # unreachable) — nothing above ran, but the CrawlRun still records
        # the attempt rather than leaving it stuck at "running" forever.
        logger.exception("crawl failed competitor=%s", competitor_slug)
        errors.append(f"discovery: {exc}")
        final_status = "failed"
        await session.rollback()

    crawl_run.status = final_status
    crawl_run.finished_at = _utcnow()
    crawl_run.pages_fetched = pages_fetched
    crawl_run.error_log = "\n".join(errors) if errors else None
    await session.commit()

    # Not `crawl_run.status` — commit() (like rollback()) expires every ORM
    # object in the session by default, and a bare attribute read on an
    # expired async-ORM object outside an explicit await raises
    # sqlalchemy.exc.MissingGreenlet (see the comments above competitor_id).
    logger.info(
        "crawl finished competitor=%s status=%s pages_fetched=%d campaigns_found=%d errors=%d",
        competitor_slug,
        final_status,
        pages_fetched,
        campaigns_found,
        len(errors),
    )
    return crawl_run
