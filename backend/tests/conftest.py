"""Shared pytest fixtures.

Tests run inside the backend container against the same dev Postgres the
app itself uses — there's no separate test database. A savepoint-based
rollback-per-test setup was tried first (wrap each test in one outer
transaction, roll it back at the end), but asyncpg rejected the very first
SAVEPOINT attempt with "another operation is in progress" regardless of
whether one session or two shared the connection — not a sharing bug, just
that join_transaction_mode="create_savepoint" isn't reliable in this
asyncpg/SQLAlchemy combination. Simpler and more robust: every test gets a
real session that commits for real, and competitor_factory tracks and
deletes (in FK-safe order) whatever it created, so tests never collide with
each other, with a re-run, or with real data.
"""

import random

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.session import async_session_factory, get_db
from app.main import app
from app.models import Competitor, PriceObservation, Product


@pytest_asyncio.fixture
async def db_session():
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """An httpx client hitting the real FastAPI app in-process (no network),
    with its own DB session per request (via the same DATABASE_URL the app
    normally uses) so it sees whatever a test committed via db_session.
    """

    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def competitor_factory(db_session):
    """Creates one or more Competitor rows for a test, with a random
    slug/brand_num so runs never collide with each other or with real data
    (e.g. the real "gurneys" row), and deletes everything it created —
    competitor, products, and their price observations, in FK-safe order —
    once the test is done.
    """
    created_ids: list[int] = []

    async def _create(**overrides) -> Competitor:
        suffix = random.randint(100000, 999999)
        overrides.setdefault("slug", f"test-competitor-{suffix}")
        overrides.setdefault("name", "Test Competitor")
        overrides.setdefault("website_url", "https://example.com")
        competitor = Competitor(**overrides)
        db_session.add(competitor)
        await db_session.flush()
        created_ids.append(competitor.id)
        return competitor

    yield _create

    if created_ids:
        product_ids = (
            (
                await db_session.execute(
                    select(Product.id).where(Product.competitor_id.in_(created_ids))
                )
            )
            .scalars()
            .all()
        )
        if product_ids:
            await db_session.execute(
                delete(PriceObservation).where(PriceObservation.product_id.in_(product_ids))
            )
            await db_session.execute(delete(Product).where(Product.id.in_(product_ids)))
        await db_session.execute(delete(Competitor).where(Competitor.id.in_(created_ids)))
        await db_session.commit()
