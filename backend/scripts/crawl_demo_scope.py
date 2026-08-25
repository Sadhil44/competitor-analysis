"""One-off CLI for the Wednesday demo (Aug 26): seeds the
gardeners-supply/epic-gardening/vego-garden identities from
config/competitors.yaml + config/own_brands.yaml, then crawls each.

Defaults to a full-catalog crawl — same site-wide sitemap discovery every
other tracked competitor already gets (crawl_competitor's default,
scoped=False) — since a single-collection scoped crawl undercounted each
brand's real raised-bed-adjacent assortment (Gardener's Supply alone splits
raised beds across several separate collections: elevated-planters,
composite-elevated-medium, wood-elevated-compact, raised-garden-beds-with-
casters, ...). Pass `--scoped` to fall back to the narrower single-collection
crawl (see app/scraping/ingest.py's `scoped` param) if a future run needs it.

This is the "clean demo crawl command" the PRD asked for — nothing in this
repo currently triggers crawl_competitor/seed_competitors at all (confirmed
by grep before writing this), so there was no existing script to extend.

Invoke with `-m`, matching scripts/import_feed.py's convention:

    docker compose exec backend python -m scripts.crawl_demo_scope
    docker compose exec backend python -m scripts.crawl_demo_scope --scoped
"""

import asyncio
import logging
import sys
import time

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models import Competitor, CrawlRun
from app.scraping.feed_import import seed_own_brands
from app.scraping.ingest import crawl_competitor, seed_competitors

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("crawl_demo_scope")

# The three identities this demo compares. gardeners-supply is our own
# brand (already is_own_brand=True via brand_num 53 in own_brands.yaml) but
# needs seed_competitors() too, since until today it only had a feed-based
# own_brands.yaml entry and no scraped competitors.yaml crawl target.
DEMO_SLUGS = ["gardeners-supply", "epic-gardening", "vego-garden"]


async def main(scoped: bool) -> None:
    async with async_session_factory() as session:
        await seed_competitors(session)
        await seed_own_brands(session)

        elapsed_by_slug: dict[str, float] = {}
        for slug in DEMO_SLUGS:
            logger.info("crawling %s (scoped=%s)...", slug, scoped)
            started = time.monotonic()
            # crawl_competitor rolls back the session on any per-page error,
            # which unconditionally expires every ORM object in it
            # (independent of the session factory's expire_on_commit=False
            # — that only controls commit's behavior, not rollback's) — so
            # the returned CrawlRun may be expired here. Don't touch its
            # attributes; re-query fresh for the summary below instead.
            await crawl_competitor(session, slug, scoped=scoped)
            elapsed_by_slug[slug] = time.monotonic() - started
            logger.info("finished %s in %.1fs", slug, elapsed_by_slug[slug])

        logger.info("=== crawl_demo_scope summary ===")
        for slug in DEMO_SLUGS:
            result = await session.execute(
                select(CrawlRun)
                .join(Competitor, Competitor.id == CrawlRun.competitor_id)
                .where(Competitor.slug == slug)
                .order_by(CrawlRun.id.desc())
                .limit(1)
            )
            run = result.scalar_one_or_none()
            if run is None:
                logger.warning("  %-20s no CrawlRun found", slug)
                continue
            logger.info(
                "  %-20s status=%-16s pages_fetched=%-5d %.1fs%s",
                slug,
                run.status,
                run.pages_fetched,
                elapsed_by_slug[slug],
                f"\n    errors: {run.error_log}" if run.error_log else "",
            )


if __name__ == "__main__":
    asyncio.run(main(scoped="--scoped" in sys.argv[1:]))
