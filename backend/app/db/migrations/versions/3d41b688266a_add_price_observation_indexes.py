"""add price observation indexes

price_observations had no index beyond its primary key and the
internal_feed dedup partial unique index — every "latest price per
product" lookup (comparable products, product price trend, the search
page's price column) and the price-moves window-function query
(app/intelligence/price_moves.py) were doing a sequential scan + sort
over the whole table. Confirmed live: GET /activity/price-changes (the
dashboard's price-move feed) took ~3s on ~135K rows before this,
dominating the homepage's load time.

Revision ID: 3d41b688266a
Revises: d4f6a1c9b2e7
Create Date: 2026-08-31 06:13:07.806903
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3d41b688266a'
down_revision: Union[str, None] = 'd4f6a1c9b2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Supports every "most recent observation per product" pattern
    # (ORDER BY product_id, observed_at DESC / DISTINCT ON (product_id)) —
    # no source predicate, so source can't be part of this index's key.
    op.create_index(
        "ix_price_observations_product_observed",
        "price_observations",
        ["product_id", sa.text("observed_at DESC")],
    )
    # Supports find_price_moves' row_number() OVER (PARTITION BY product_id,
    # source ORDER BY observed_at) — matches the partition/order columns
    # exactly so Postgres can walk the index instead of sorting the table.
    op.create_index(
        "ix_price_observations_product_source_observed",
        "price_observations",
        ["product_id", "source", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_observations_product_source_observed", table_name="price_observations")
    op.drop_index("ix_price_observations_product_observed", table_name="price_observations")
