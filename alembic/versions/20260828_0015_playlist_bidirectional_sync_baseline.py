"""Add playlist bidirectional sync baseline.

Revision ID: 20260828_0015
Revises: 20260801_0014
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0015"
down_revision: str | None = "20260801_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "playlist_library_sync_bindings",
        sa.Column(
            "last_synced_song_ids",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("playlist_library_sync_bindings", "last_synced_song_ids")
