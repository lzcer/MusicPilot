"""Add PostgreSQL phase-one compatibility columns.

Revision ID: 20260709_0007
Revises: 20260704_0006
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260709_0007"
down_revision: str | None = "20260704_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("downloaders") as batch_op:
        batch_op.add_column(sa.Column("local_path", sa.Text(), nullable=False, server_default=""))

    with op.batch_alter_table("playlist_tracks") as batch_op:
        batch_op.add_column(
            sa.Column("source_key", sa.String(length=768), nullable=False, server_default=""),
        )
        batch_op.add_column(
            sa.Column("original_title", sa.String(length=512), nullable=False, server_default=""),
        )

    op.create_index(op.f("ix_playlist_tracks_source_key"), "playlist_tracks", ["source_key"])


def downgrade() -> None:
    op.drop_index(op.f("ix_playlist_tracks_source_key"), table_name="playlist_tracks")

    with op.batch_alter_table("playlist_tracks") as batch_op:
        batch_op.drop_column("original_title")
        batch_op.drop_column("source_key")

    with op.batch_alter_table("downloaders") as batch_op:
        batch_op.drop_column("local_path")
