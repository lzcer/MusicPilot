from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class TorrentRecord(TimestampMixin, Base):
    __tablename__ = "torrent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    torrent_hash: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(128), default="")
    download_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default="queued")
    save_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    downloader_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    media_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resource_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    selected_site_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    library_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TorrentRecordItem(TimestampMixin, Base):
    __tablename__ = "torrent_record_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    torrent_record_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("torrent_records.id", ondelete="CASCADE"),
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(Text)
    artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parsed_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_album: Mapped[str | None] = mapped_column(String(512), nullable=True)
    playlist_track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="pending")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MediaFile(TimestampMixin, Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    torrent_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    source_path: Mapped[str] = mapped_column(Text)
    library_path: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    operation_type: Mapped[str] = mapped_column(String(32), default="mapped")
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    album: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class MusicLibraryTrack(TimestampMixin, Base):
    __tablename__ = "music_library_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    navidrome_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    album: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suffix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MusicPlatformConnection(TimestampMixin, Base):
    __tablename__ = "music_platform_connections"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    platform: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(256), default="")
    external_user_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    client_id: Mapped[str] = mapped_column(Text)
    client_secret: Mapped[str] = mapped_column(Text)
    redirect_uri: Mapped[str] = mapped_column(Text)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(64), default="pending")
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Playlist(TimestampMixin, Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_connection_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("music_platform_connections.id", ondelete="CASCADE"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(256), index=True)
    name: Mapped[str] = mapped_column(String(512))
    owner_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(64), default="synced")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_download_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PlaylistTrack(TimestampMixin, Base):
    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("playlists.id", ondelete="CASCADE"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(256), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(512))
    artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    album: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    isrc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    exists_in_library: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_library_track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_status: Mapped[str] = mapped_column(String(64), default="pending")
    torrent_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_download_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(512))
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IndexerSite(TimestampMixin, Base):
    __tablename__ = "indexer_sites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str] = mapped_column(Text, unique=True)
    cookie: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=2)
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class DownloaderConfig(TimestampMixin, Base):
    __tablename__ = "downloaders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(64), default="qbittorrent")
    base_url: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(String(256), default="")
    password: Mapped[str] = mapped_column(Text, default="")
    download_path: Mapped[str] = mapped_column(Text, default="")
    local_path: Mapped[str] = mapped_column(Text, default="")
    listen_mode: Mapped[str] = mapped_column(String(64), default="polling")
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class MediaServerConfig(TimestampMixin, Base):
    __tablename__ = "media_servers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(64), default="navidrome")
    base_url: Mapped[str] = mapped_column(Text)
    api_key: Mapped[str] = mapped_column(Text, default="")
    username: Mapped[str] = mapped_column(String(256), default="")
    password: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NotifierChannel(TimestampMixin, Base):
    __tablename__ = "notifier_channels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(64), default="telegram")
    bot_token: Mapped[str] = mapped_column(Text, default="")
    webhook_url: Mapped[str] = mapped_column(Text, default="")
    chat_ids: Mapped[str] = mapped_column(Text, default="")
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_download_notify: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_library_notify: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SystemTask(TimestampMixin, Base):
    __tablename__ = "system_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="WAIT", index=True)
    chain_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    resource_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    inheritable_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(256),
        unique=True,
        nullable=True,
    )


class SystemTaskResourceLease(TimestampMixin, Base):
    __tablename__ = "system_task_resource_leases"

    resource_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    holder_kind: Mapped[str] = mapped_column(String(32))
    holder_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chain_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Artist(TimestampMixin, Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ArtistAlias(TimestampMixin, Base):
    __tablename__ = "artist_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artist_id: Mapped[int] = mapped_column(Integer, index=True)
    alias: Mapped[str] = mapped_column(String(512), index=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
