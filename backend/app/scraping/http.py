"""Shared HTTP plumbing for the scraping pipeline: one User-Agent, one
per-domain rate limiter, and one httpx client factory — so discovery.py's
sitemap/robots requests and fetcher.py's page requests to the same site
share a single polite pace instead of each keeping an independent clock
and unintentionally doubling the real request rate against that domain.
"""

import asyncio
import time
from urllib.parse import urlparse

import httpx

USER_AGENT = "CompetitorAnalysisBot/0.1 (contact: you@example.com)"

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


class DomainRateLimiter:
    """Process-wide, keyed by domain — not per-caller — so every part of
    the pipeline hitting the same site respects one shared minimum
    interval between requests.
    """

    def __init__(self) -> None:
        self._last_request_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, domain: str) -> asyncio.Lock:
        lock = self._locks.get(domain)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[domain] = lock
        return lock

    async def wait(self, url: str, min_interval_seconds: float) -> None:
        domain = urlparse(url).netloc
        async with self._lock_for(domain):
            last = self._last_request_at.get(domain)
            if last is not None:
                remaining = min_interval_seconds - (time.monotonic() - last)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_request_at[domain] = time.monotonic()


rate_limiter = DomainRateLimiter()


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )
