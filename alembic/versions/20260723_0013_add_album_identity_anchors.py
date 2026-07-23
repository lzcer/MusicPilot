"""Add persistent album identity anchors.

Revision ID: 20260723_0013
Revises: 20260714_0012
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260723_0013"
down_revision: str | None = "20260714_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "album_identity_anchors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("media_server_id", sa.String(length=32), nullable=False),
        sa.Column("album_name", sa.String(length=512), nullable=False),
        sa.Column("normalized_album_name", sa.String(length=512), nullable=False),
        sa.Column("album_artist", sa.String(length=512), nullable=True),
        sa.Column("normalized_album_artist", sa.String(length=512), nullable=True),
        sa.Column("musicbrainz_album_id", sa.String(length=256), nullable=True),
        sa.Column("album_version", sa.String(length=256), nullable=True),
        sa.Column("release_date", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_server_id"],
            ["media_servers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_album_identity_anchors_media_server_id"),
        "album_identity_anchors",
        ["media_server_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_album_identity_anchors_normalized_album_name"),
        "album_identity_anchors",
        ["normalized_album_name"],
        unique=False,
    )
    op.create_table(
        "album_identity_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("anchor_id", sa.Integer(), nullable=False),
        sa.Column("media_server_id", sa.String(length=32), nullable=False),
        sa.Column("library_directory_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["anchor_id"],
            ["album_identity_anchors.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_server_id"],
            ["media_servers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "media_server_id",
            "library_directory_key",
            name="uq_album_identity_location_server_directory",
        ),
    )
    op.create_index(
        op.f("ix_album_identity_locations_anchor_id"),
        "album_identity_locations",
        ["anchor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_album_identity_locations_media_server_id"),
        "album_identity_locations",
        ["media_server_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_album_identity_locations_media_server_id"),
        table_name="album_identity_locations",
    )
    op.drop_index(
        op.f("ix_album_identity_locations_anchor_id"),
        table_name="album_identity_locations",
    )
    op.drop_table("album_identity_locations")
    op.drop_index(
        op.f("ix_album_identity_anchors_normalized_album_name"),
        table_name="album_identity_anchors",
    )
    op.drop_index(
        op.f("ix_album_identity_anchors_media_server_id"),
        table_name="album_identity_anchors",
    )
    op.drop_table("album_identity_anchors")
