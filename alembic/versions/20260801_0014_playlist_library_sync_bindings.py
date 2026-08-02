"""Add playlist library sync bindings.

Revision ID: 20260801_0014
Revises: 20260723_0013
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0014"
down_revision: str | None = "20260723_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playlist_library_sync_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("media_server_id", sa.String(length=32), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.Column("last_synced_existing_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["media_server_id"],
            ["media_servers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "playlist_id",
            "media_server_id",
            name="uq_playlist_library_sync_binding_playlist_server",
        ),
    )
    op.create_index(
        op.f("ix_playlist_library_sync_bindings_playlist_id"),
        "playlist_library_sync_bindings",
        ["playlist_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_playlist_library_sync_bindings_media_server_id"),
        "playlist_library_sync_bindings",
        ["media_server_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_playlist_library_sync_bindings_media_server_id"),
        table_name="playlist_library_sync_bindings",
    )
    op.drop_index(
        op.f("ix_playlist_library_sync_bindings_playlist_id"),
        table_name="playlist_library_sync_bindings",
    )
    op.drop_table("playlist_library_sync_bindings")
