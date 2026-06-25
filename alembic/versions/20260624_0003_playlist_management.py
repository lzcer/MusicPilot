"""Add playlist management tables.

Revision ID: 20260624_0003
Revises: 20260624_0002
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260624_0003"
down_revision: str | None = "20260624_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "music_platform_connections",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("external_user_id", sa.String(length=256), nullable=True),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform_connection_id", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("owner_name", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("track_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_download_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["platform_connection_id"],
            ["music_platform_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_playlists_external_id"), "playlists", ["external_id"])
    op.create_index(
        op.f("ix_playlists_platform_connection_id"),
        "playlists",
        ["platform_connection_id"],
    )
    op.create_table(
        "playlist_tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("artist", sa.String(length=512), nullable=True),
        sa.Column("album", sa.String(length=512), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("isrc", sa.String(length=64), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("exists_in_library", sa.Boolean(), nullable=False),
        sa.Column("matched_library_track_id", sa.Integer(), nullable=True),
        sa.Column("download_status", sa.String(length=64), nullable=False),
        sa.Column("torrent_record_id", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_download_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_playlist_tracks_external_id"), "playlist_tracks", ["external_id"])
    op.create_index(op.f("ix_playlist_tracks_playlist_id"), "playlist_tracks", ["playlist_id"])
    op.create_table(
        "torrent_record_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("torrent_record_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("artist", sa.String(length=512), nullable=True),
        sa.Column("parsed_title", sa.String(length=512), nullable=True),
        sa.Column("metadata_title", sa.String(length=512), nullable=True),
        sa.Column("metadata_artist", sa.String(length=512), nullable=True),
        sa.Column("metadata_album", sa.String(length=512), nullable=True),
        sa.Column("playlist_track_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["torrent_record_id"], ["torrent_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_torrent_record_items_torrent_record_id"),
        "torrent_record_items",
        ["torrent_record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_torrent_record_items_torrent_record_id"),
        table_name="torrent_record_items",
    )
    op.drop_table("torrent_record_items")
    op.drop_index(op.f("ix_playlist_tracks_playlist_id"), table_name="playlist_tracks")
    op.drop_index(op.f("ix_playlist_tracks_external_id"), table_name="playlist_tracks")
    op.drop_table("playlist_tracks")
    op.drop_index(op.f("ix_playlists_platform_connection_id"), table_name="playlists")
    op.drop_index(op.f("ix_playlists_external_id"), table_name="playlists")
    op.drop_table("playlists")
    op.drop_table("music_platform_connections")
