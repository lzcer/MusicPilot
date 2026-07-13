"""Add monitor tag to downloaders.

Revision ID: 20260713_0010
Revises: 20260713_0009
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0010"
down_revision: str | None = "20260713_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("downloaders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "monitor_tag",
                sa.String(length=128),
                nullable=False,
                server_default="MusicPilot",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("downloaders") as batch_op:
        batch_op.drop_column("monitor_tag")
