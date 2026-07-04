"""Add operation type to media files.

Revision ID: 20260704_0006
Revises: 20260704_0005
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260704_0006"
down_revision: str | None = "20260704_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("media_files") as batch_op:
        batch_op.add_column(
            sa.Column(
                "operation_type",
                sa.String(length=32),
                nullable=False,
                server_default="mapped",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("media_files") as batch_op:
        batch_op.drop_column("operation_type")
