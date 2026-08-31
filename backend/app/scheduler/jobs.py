"""The actual scheduled work — kept separate from __init__.py's scheduler
wiring so app/api/scheduler.py (the manual-trigger endpoint) can invoke the
exact same job function a cron firing would use, rather than duplicating
its session-management/error-handling.
"""

import asyncio
import logging

from app.db.session import async_session_factory
from app.scraping.ingest import crawl_competitor

logger = logging.getLogger(__name__)

# Every competitor in config/competitors.yaml currently shares the same
# "06:00 daily" cadence_cron, which would otherwise start ALL of them —
# each spinning up its own Playwright browser — in the same instant. This
# caps how many crawl_competitor() calls actually run concurrently,
# independent of how many cron triggers happen to line up; the rest queue
# behind the semaphore rather than piling on at once.
MAX_CONCURRENT_CRAWLS = 3
_crawl_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CRAWLS)


async def run_crawl_job(slug: str) -> None:
    """One crawl for a single competitor — used both as the function a cron
    trigger calls and as what the manual /scheduler/crawl/{slug} endpoint
    kicks off, so a scheduled run and a manually-triggered one behave
    identically. Owns its own DB session (jobs run outside any request,
    so there's no request-scoped session to reuse) and never lets an
    exception escape: crawl_competitor already records failures onto the
    CrawlRun row itself; a job that raises would otherwise just vanish into
    APScheduler's own logger with nothing user-visible.
    """
    async with _crawl_semaphore:
        logger.info("crawl job starting competitor=%s", slug)
        try:
            async with async_session_factory() as session:
                await crawl_competitor(session, slug, scoped=False)
        except Exception:
            logger.exception("crawl job crashed competitor=%s", slug)
