"""Tests for the scheduler wiring (app/scheduler) and its API (app/api/
scheduler.py). The scheduler itself never runs during the test suite (see
app/main.py's lifespan — skipped under pytest), so test_list_jobs_* starts
and stops it explicitly rather than relying on app startup.

trigger_crawl's success path is monkeypatched rather than run for real: it
dispatches a live Playwright crawl against a real external site, which has
no place running as part of an automated test (slow, network-dependent,
and not something a CI run should be doing to a real competitor's website).
"""

import app.api.scheduler as scheduler_api
from app.core.config import load_competitors_config
from app.scheduler import shutdown_scheduler, start_scheduler


async def test_trigger_crawl_unknown_slug_returns_404(client):
    response = await client.post("/scheduler/crawl/not-a-real-competitor")
    assert response.status_code == 404


async def test_trigger_crawl_dispatches_job_without_running_it(client, monkeypatch):
    calls: list[str] = []

    async def _fake_run_crawl_job(slug: str) -> None:
        calls.append(slug)

    monkeypatch.setattr(scheduler_api, "run_crawl_job", _fake_run_crawl_job)

    response = await client.post("/scheduler/crawl/gurneys")
    assert response.status_code == 200
    assert response.json() == {"competitor_slug": "gurneys", "status": "started"}
    assert calls == ["gurneys"]


async def test_list_jobs_endpoint_reflects_config(client):
    start_scheduler()
    try:
        configured = {entry.slug: entry.crawl.cadence_cron for entry in load_competitors_config()}

        response = await client.get("/scheduler/jobs")
        assert response.status_code == 200
        jobs = {row["competitor_slug"]: row for row in response.json()}

        assert set(configured) == set(jobs)
        for slug, cron in configured.items():
            assert jobs[slug]["id"] == f"crawl-{slug}"
            assert jobs[slug]["cron"] == cron
            assert jobs[slug]["next_run_time"] is not None
    finally:
        shutdown_scheduler()
