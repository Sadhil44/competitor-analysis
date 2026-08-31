"""Recurring crawl scheduling: one cron job per active competitor, driven
entirely by each entry's config/competitors.yaml `crawl.cadence_cron` —
nothing here is hardcoded to a specific competitor. Started/stopped from
app/main.py's lifespan.

Single in-process AsyncIOScheduler, one backend instance — if this ever
runs as more than one replica, each replica would register and fire the
same jobs independently (no shared job store/lock across instances). Fine
at this scale; a real multi-replica deployment would need a persistent
jobstore (e.g. SQLAlchemyJobStore) or to move scheduling into its own
single-instance worker process instead.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import load_competitors_config
from app.scheduler.jobs import run_crawl_job

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    for entry in load_competitors_config():
        scheduler.add_job(
            run_crawl_job,
            trigger=CronTrigger.from_crontab(entry.crawl.cadence_cron),
            args=[entry.slug],
            id=f"crawl-{entry.slug}",
            replace_existing=True,
            max_instances=1,
            # If the process was down when a cron fire was due (a redeploy,
            # a crash), still run it up to an hour late instead of silently
            # skipping straight to the next scheduled time.
            misfire_grace_time=3600,
        )
    scheduler.start()
    logger.info("scheduler started, jobs=%s", [job.id for job in scheduler.get_jobs()])


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
