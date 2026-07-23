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


async def ingest_page(session: AsyncSession, competitor_slug: str, url: str) -> None:
    """Fetch `url`, extract products, and write Product + PriceObservation
    rows for the competitor identified by `competitor_slug`.
    """
    result = await session.execute(select(Competitor).where(Competitor.slug == competitor_slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise ValueError(f"Unknown competitor slug: {competitor_slug!r} — run seed_competitors first")

    page_text = await fetch_page_text(url)
    extracted = await extract_products(page_text)

    for item in extracted.products:
        result = await session.execute(
            select(Product).where(Product.competitor_id == competitor.id, Product.name == item.name)
        )
        product = result.scalar_one_or_none()
        if product is None:
            product = Product(competitor_id=competitor.id, sku=item.sku, name=item.name, url=url)
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
