"""Async SQLAlchemy engine + session factory.

Uses asyncpg under the hood (via the `postgresql+asyncpg://` DATABASE_URL
scheme) so FastAPI request handlers and the agent's tool functions can both
await DB calls instead of blocking the event loop.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, echo=False)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session, closes it after the request."""
    async with async_session_factory() as session:
        yield session
