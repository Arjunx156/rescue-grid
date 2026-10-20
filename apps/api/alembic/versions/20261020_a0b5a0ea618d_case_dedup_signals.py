"""case dedup signals

Revision ID: a0b5a0ea618d
Revises: 2eb172e27de0
Create Date: 2026-10-20 01:02:45.300434

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a0b5a0ea618d'
down_revision: str | Sequence[str] | None = '2eb172e27de0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('cases', sa.Column('sender_phone_hashes', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False))
    op.add_column('cases', sa.Column('location_anchors', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('cases', 'location_anchors')
    op.drop_column('cases', 'sender_phone_hashes')
