from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_competitors_config
from app.models import Competitor, PriceObservation, Product
from app.scraping.extractor import extract_products
from app.scraping.fetcher import fetch_page_text


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


MAX_PAGES_PER_CATALOG_URL = 5


def _paginated_url(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}page={page_num}"


async def ingest_page(session: AsyncSession, competitor_slug: str, url: str) -> None:
    """Fetch up to MAX_PAGES_PER_CATALOG_URL pages of `url`, extract products
    from each, and write Product + PriceObservation rows for the competitor
    identified by `competitor_slug`.

    Pages beyond the first are requested via a `page=N` query param (the
    common convention, e.g. Shopify's `?page=N`). Not every site uses this —
    stopping early once a page yields zero products we haven't already seen
    this run handles both "reached the real end of the catalog" and "this
    site doesn't support page=N at all and just re-served the same page"
    gracefully, without needing per-site pagination logic.
    """
    result = await session.execute(select(Competitor).where(Competitor.slug == competitor_slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise ValueError(f"Unknown competitor slug: {competitor_slug!r} — run seed_competitors first")

    seen_names: set[str] = set()

    for page_num in range(1, MAX_PAGES_PER_CATALOG_URL + 1):
        page_url = _paginated_url(url, page_num)
        page_text = await fetch_page_text(page_url)
        extracted = await extract_products(page_text)

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
