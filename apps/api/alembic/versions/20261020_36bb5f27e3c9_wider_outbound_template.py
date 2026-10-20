"""wider outbound template

Revision ID: 36bb5f27e3c9
Revises: a0b5a0ea618d
Create Date: 2026-10-20 01:33:25.484485

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '36bb5f27e3c9'
down_revision: str | Sequence[str] | None = 'a0b5a0ea618d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('outbound_messages', 'template',
               existing_type=sa.VARCHAR(length=32),
               type_=sa.String(length=64),
               existing_nullable=False)


def downgrade() -> None:
    op.alter_column('outbound_messages', 'template',
               existing_type=sa.String(length=64),
               type_=sa.VARCHAR(length=32),
               existing_nullable=False)
