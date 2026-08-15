"""create campaigns

Revision ID: 3b628824db31
Revises: 692d5aec25cf
Create Date: 2026-08-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3b628824db31'
down_revision: Union[str, None] = '692d5aec25cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('competitor_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('discount_text', sa.String(length=255), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('discovered_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_campaigns_competitor_id', 'campaigns', ['competitor_id'])
    op.create_index('ix_campaigns_product_id', 'campaigns', ['product_id'])


def downgrade() -> None:
    op.drop_index('ix_campaigns_product_id', table_name='campaigns')
    op.drop_index('ix_campaigns_competitor_id', table_name='campaigns')
    op.drop_table('campaigns')
