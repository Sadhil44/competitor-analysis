"""Shared SQLAlchemy declarative base.

Phase 1 model modules (app/models/*.py) will import `Base` from here and
Alembic's env.py imports `Base.metadata` to autogenerate migrations against
whatever models exist at the time.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
