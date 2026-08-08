"""own brands and product grade

Revision ID: 692d5aec25cf
Revises: 46b229a2f7db
Create Date: 2026-08-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '692d5aec25cf'
down_revision: Union[str, None] = '46b229a2f7db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'competitors',
        sa.Column('is_own_brand', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column('competitors', sa.Column('brand_num', sa.Integer(), nullable=True))
    op.create_unique_constraint('uq_competitors_brand_num', 'competitors', ['brand_num'])

    op.add_column('products', sa.Column('grade', sa.String(length=100), nullable=True))

    # Partial unique index: only constrains rows from the first-party feed
    # import, so scraped observations are unaffected. See
    # app/models/price_observation.py for why this exists.
    op.create_index(
        'ix_price_observations_internal_feed_dedup',
        'price_observations',
        ['product_id', 'observed_at', 'source'],
        unique=True,
        postgresql_where=sa.text("source = 'internal_feed'"),
    )


def downgrade() -> None:
    op.drop_index('ix_price_observations_internal_feed_dedup', table_name='price_observations')
    op.drop_column('products', 'grade')
    op.drop_constraint('uq_competitors_brand_num', 'competitors', type_='unique')
    op.drop_column('competitors', 'brand_num')
    op.drop_column('competitors', 'is_own_brand')
