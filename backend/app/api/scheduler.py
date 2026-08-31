"""Read the scheduler's registered jobs, and manually kick one off — lets
the dashboard show the automated crawl pipeline is actually live (not just
configured), and lets a demo/operator trigger a real crawl on demand
instead of waiting for its next cron fire.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.config import load_competitors_config
from app.scheduler import scheduler
from app.scheduler.jobs import run_crawl_job
from app.schemas.scheduler import CrawlTriggerResponse, ScheduledJobRead

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/jobs", response_model=list[ScheduledJobRead])
async def list_jobs():
    cron_by_slug = {entry.slug: entry.crawl.cadence_cron for entry in load_competitors_config()}
    jobs = []
    for job in scheduler.get_jobs():
        slug = job.id.removeprefix("crawl-")
        jobs.append(
            ScheduledJobRead(
                id=job.id,
                competitor_slug=slug,
                cron=cron_by_slug.get(slug, str(job.trigger)),
                next_run_time=job.next_run_time,
            )
        )
    return jobs


@router.post("/crawl/{slug}", response_model=CrawlTriggerResponse)
async def trigger_crawl(slug: str, background_tasks: BackgroundTasks):
    if slug not in {entry.slug for entry in load_competitors_config()}:
        raise HTTPException(status_code=404, detail=f"No config/competitors.yaml entry for slug {slug!r}")
    # A crawl can run for minutes (full-catalog discovery + per-product
    # fetches) — respond immediately and let it run in the background rather
    # than holding the request open; progress is visible via the
    # competitor's CrawlRun status (GET /competitors) as it runs.
    background_tasks.add_task(run_crawl_job, slug)
    return CrawlTriggerResponse(competitor_slug=slug, status="started")
