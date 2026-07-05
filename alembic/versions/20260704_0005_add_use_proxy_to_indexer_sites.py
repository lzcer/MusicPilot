"""Add use_proxy column to indexer_sites table.

Revision ID: 20260704_0005
Revises: 20260704_0004
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260704_0005"
down_revision: str | None = "20260704_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("indexer_sites") as batch_op:
        batch_op.add_column(
            sa.Column("use_proxy", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    with op.batch_alter_table("indexer_sites") as batch_op:
        batch_op.drop_column("use_proxy")
