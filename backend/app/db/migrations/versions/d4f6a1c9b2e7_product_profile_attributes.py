"""product profile attributes

Revision ID: d4f6a1c9b2e7
Revises: 3b628824db31
Create Date: 2026-08-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd4f6a1c9b2e7'
down_revision: Union[str, None] = '3b628824db31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('brand', sa.String(length=255), nullable=True))
    op.add_column('products', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('image_url', sa.Text(), nullable=True))
    op.add_column(
        'products',
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('products', 'attributes')
    op.drop_column('products', 'image_url')
    op.drop_column('products', 'description')
    op.drop_column('products', 'brand')
