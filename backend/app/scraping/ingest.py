import difflib
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_competitors_config
from app.models import Competitor, PriceObservation, Product
from app.scraping.extractor import extract_products_merged
from app.scraping.fetcher import fetch_page


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


def _price_context_fingerprint(text: str) -> str:
    spans = (m.start() for m in re.finditer(re.escape("$"), text))
    return " ".join(text[max(0, s - PRICE_CONTEXT_WINDOW) : s + PRICE_CONTEXT_WINDOW] for s in spans)


async def ingest_page(session: AsyncSession, competitor_slug: str, url: str) -> None:
    """Fetch a competitor's catalog starting at `url`, following whatever
    "next page" link the site itself declares (see fetch_page) for as long
    as one exists, extracting products from each page and writing Product +
    PriceObservation rows for the competitor identified by `competitor_slug`.

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

    seen_names: set[str] = set()
    visited_urls: set[str] = set()
    page_url: str | None = url
    previous_price_context: str | None = None

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

        extracted = await extract_products_merged(fetched.text)
        new_items = [item for item in extracted.products if item.name not in seen_names]
        if not new_items:
            break

        for item in new_items:
            seen_names.add(item.name)
            result = await session.execute(
                select(Product).where(Product.competitor_id == competitor.id, Product.name == item.name)
            )
            product = result.scalar_one_or_none()
            if product is None:
                product = Product(competitor_id=competitor.id, sku=item.sku, name=item.name, url=page_url)
                session.add(product)

            session.add(
                PriceObservation(
                    price=item.price,
                    currency=item.currency,
                    in_stock=item.in_stock,
                    promo_text=item.promo_text,
                    source="scheduled_crawl",
                    product=product,
                )
            )

        await session.commit()
        page_url = fetched.next_page_url
