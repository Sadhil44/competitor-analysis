"""One-off CLI: gets real scraped coverage for the own-brand sub-brands
that previously had ONLY internal-feed pricing (config/own_brands.yaml) —
spring-hill-nurseries, brecks, k-van-bourgondien. Mirrors
crawl_demo_scope.py's pattern (seed both configs, full-catalog crawl per
slug) but for these three specifically; gurneys and gardeners-supply are
deliberately excluded here — they already got this treatment earlier.

Invoke with `-m`, matching scripts/crawl_demo_scope.py's convention:

    docker compose exec backend python -m scripts.crawl_own_brands
"""

import asyncio
import logging
import time

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models import Competitor, CrawlRun
from app.scraping.feed_import import seed_own_brands
from app.scraping.ingest import crawl_competitor, seed_competitors

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("crawl_own_brands")

SLUGS = ["spring-hill-nurseries", "brecks", "k-van-bourgondien"]


async def main() -> None:
    async with async_session_factory() as session:
        await seed_competitors(session)
        await seed_own_brands(session)

        elapsed_by_slug: dict[str, float] = {}
        for slug in SLUGS:
            logger.info("crawling %s (scoped=False, full catalog)...", slug)
            started = time.monotonic()
            await crawl_competitor(session, slug, scoped=False)
            elapsed_by_slug[slug] = time.monotonic() - started
            logger.info("finished %s in %.1fs", slug, elapsed_by_slug[slug])

        logger.info("=== crawl_own_brands summary ===")
        for slug in SLUGS:
            result = await session.execute(
                select(CrawlRun)
                .join(Competitor, Competitor.id == CrawlRun.competitor_id)
                .where(Competitor.slug == slug)
                .order_by(CrawlRun.id.desc())
                .limit(1)
            )
            run = result.scalar_one_or_none()
            if run is None:
                logger.warning("  %-24s no CrawlRun found", slug)
                continue
            logger.info(
                "  %-24s status=%-16s pages_fetched=%-5d %.1fs%s",
                slug,
                run.status,
                run.pages_fetched,
                elapsed_by_slug[slug],
                f"\n    errors: {run.error_log}" if run.error_log else "",
            )


if __name__ == "__main__":
    asyncio.run(main())
