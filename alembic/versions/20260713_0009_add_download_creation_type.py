"""Add creation type to torrent records.

Revision ID: 20260713_0009
Revises: 20260710_0008
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0009"
down_revision: str | None = "20260710_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("torrent_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "creation_type",
                sa.String(length=32),
                nullable=False,
                server_default="task_created",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("torrent_records") as batch_op:
        batch_op.drop_column("creation_type")
