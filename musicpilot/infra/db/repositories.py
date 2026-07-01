from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import String, delete, func, or_, select

from musicpilot.infra.db.models import (
    Artist,
    ArtistAlias,
    DownloaderConfig,
    IndexerSite,
    MediaFile,
    MediaServerConfig,
    MusicLibraryTrack,
    MusicPlatformConnection,
    NotifierChannel,
    Playlist,
    PlaylistTrack,
    Subscription,
    SystemSetting,
    TorrentRecord,
    TorrentRecordItem,
)
from musicpilot.infra.db.session import Database
from musicpilot.ports.metadata import TrackMetadata

logger = logging.getLogger(__name__)
SLOW_DB_OPERATION_SECONDS = float(os.getenv("MP_SLOW_DB_OPERATION_SECONDS", "0.5"))


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _log_slow_db_operation(operation: str, started_at: float, **fields: Any) -> None:
    elapsed_ms = _elapsed_ms(started_at)
    if elapsed_ms < SLOW_DB_OPERATION_SECONDS * 1000:
        return
    details = " ".join(f"{key}={value!r}" for key, value in fields.items())
    logger.warning(
        "Slow DB operation: operation=%s elapsed_ms=%.1f %s",
        operation,
        elapsed_ms,
        details,
    )


class SqlAlchemyMediaRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def record_processed_media(
        self,
        *,
        torrent_hash: str,
        source_path: Path,
        library_path: Path,
        metadata: TrackMetadata,
    ) -> None:
        async with self.database.session() as session:
            result = await session.execute(
                select(MediaFile).where(MediaFile.library_path == str(library_path))
            )
            media_file = result.scalars().first()
            if media_file is None:
                media_file = MediaFile(
                    torrent_hash=torrent_hash,
                    source_path=str(source_path),
                    library_path=str(library_path),
                )
                session.add(media_file)

            media_file.torrent_hash = torrent_hash
            media_file.source_path = str(source_path)
            media_file.title = metadata.title
            media_file.artist = metadata.artist
            media_file.album = metadata.album
            media_file.year = metadata.year
            media_file.track_number = metadata.track_number
            media_file.status = "success"
            media_file.error_message = None
            media_file.metadata_payload = asdict(metadata)
            await session.commit()

    async def record_scraping_result(
        self,
        *,
        torrent_hash: str | None,
        source_path: Path,
        library_path: Path | None,
        metadata: TrackMetadata,
        status: str,
        error_message: str | None = None,
    ) -> None:
        operation_started_at = time.perf_counter()
        result_path = str(library_path) if library_path is not None else None
        async with self.database.session() as session:
            media_file = None
            if result_path is not None:
                result = await session.execute(
                    select(MediaFile).where(MediaFile.library_path == result_path)
                )
                media_file = result.scalars().first()
            if media_file is None:
                result = await session.execute(
                    select(MediaFile).where(MediaFile.source_path == str(source_path))
                )
                media_file = result.scalars().first()
            if media_file is None:
                media_file = MediaFile(
                    torrent_hash=torrent_hash,
                    source_path=str(source_path),
                    library_path=result_path,
                )
                session.add(media_file)

            media_file.torrent_hash = torrent_hash
            media_file.source_path = str(source_path)
            media_file.library_path = result_path
            media_file.title = metadata.title
            media_file.artist = metadata.artist
            media_file.album = metadata.album
            media_file.year = metadata.year
            media_file.track_number = metadata.track_number
            media_file.status = status
            media_file.error_message = error_message
            media_file.metadata_payload = asdict(metadata)
            commit_started_at = time.perf_counter()
            await session.commit()
            _log_slow_db_operation(
                "record_scraping_result.commit",
                commit_started_at,
                status=status,
                torrent_hash=torrent_hash,
                source_path=str(source_path),
            )
        _log_slow_db_operation(
            "record_scraping_result.total",
            operation_started_at,
            status=status,
            torrent_hash=torrent_hash,
            source_path=str(source_path),
        )

    async def mark_torrent_completed(
        self,
        *,
        torrent_hash: str,
        save_path: Path | None,
    ) -> TorrentRecord:
        async with self.database.session() as session:
            result = await session.execute(
                select(TorrentRecord).where(TorrentRecord.torrent_hash == torrent_hash)
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = TorrentRecord(
                    torrent_hash=torrent_hash,
                    name=torrent_hash,
                    download_url="",
                )
                session.add(record)
            record.status = "completed"
            record.progress = 1.0
            record.save_path = str(save_path) if save_path is not None else None
            await session.commit()
            await session.refresh(record)
            return record

    async def list_downloaders(self) -> list[DownloaderConfig]:
        async with self.database.session() as session:
            result = await session.execute(select(DownloaderConfig).order_by(DownloaderConfig.name))
            return list(result.scalars().all())

    async def default_downloader(self) -> DownloaderConfig | None:
        async with self.database.session() as session:
            result = await session.execute(
                select(DownloaderConfig)
                .where(DownloaderConfig.enabled.is_(True), DownloaderConfig.is_default.is_(True))
                .order_by(DownloaderConfig.updated_at.desc())
            )
            return result.scalars().first()

    async def get_downloader(self, downloader_id: str) -> DownloaderConfig | None:
        async with self.database.session() as session:
            return await session.get(DownloaderConfig, downloader_id)

    async def delete_downloader(self, downloader_id: str) -> bool:
        async with self.database.session() as session:
            row = await session.get(DownloaderConfig, downloader_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def upsert_downloader(
        self,
        *,
        downloader_id: str | None = None,
        payload: dict[str, Any],
    ) -> DownloaderConfig:
        async with self.database.session() as session:
            row = await session.get(DownloaderConfig, downloader_id) if downloader_id else None
            if row is None:
                row = DownloaderConfig(name=str(payload.get("name") or "qBittorrent"), base_url="")
                session.add(row)
            _assign_config_fields(
                row,
                payload,
                (
                    "name",
                    "type",
                    "base_url",
                    "username",
                    "download_path",
                    "local_path",
                    "listen_mode",
                    "is_default",
                    "enabled",
                ),
            )
            if payload.get("password"):
                row.password = str(payload["password"])
            if row.is_default:
                await session.flush()
                await _clear_other_defaults(session, DownloaderConfig, row.id)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_media_servers(self) -> list[MediaServerConfig]:
        async with self.database.session() as session:
            result = await session.execute(
                select(MediaServerConfig).order_by(MediaServerConfig.name)
            )
            return list(result.scalars().all())

    async def delete_media_server(self, server_id: str) -> bool:
        async with self.database.session() as session:
            row = await session.get(MediaServerConfig, server_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def default_media_server(self) -> MediaServerConfig | None:
        async with self.database.session() as session:
            result = await session.execute(
                select(MediaServerConfig)
                .where(MediaServerConfig.enabled.is_(True))
                .order_by(MediaServerConfig.is_default.desc(), MediaServerConfig.updated_at.desc())
            )
            return result.scalars().first()

    async def upsert_media_server(
        self,
        *,
        server_id: str | None = None,
        payload: dict[str, Any],
    ) -> MediaServerConfig:
        async with self.database.session() as session:
            row = await session.get(MediaServerConfig, server_id) if server_id else None
            if row is None:
                row = MediaServerConfig(name=str(payload.get("name") or "Navidrome"), base_url="")
                session.add(row)
            _assign_config_fields(
                row,
                payload,
                ("name", "type", "base_url", "api_key", "username", "is_default", "enabled"),
            )
            if payload.get("password"):
                row.password = str(payload["password"])
            if row.is_default:
                await session.flush()
                await _clear_other_defaults(session, MediaServerConfig, row.id)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_notifiers(self) -> list[NotifierChannel]:
        async with self.database.session() as session:
            result = await session.execute(            
                select(NotifierChannel).order_by(NotifierChannel.name)
            )
            return list(result.scalars().all())

    async def get_notifier(self, notifier_id: str) -> NotifierChannel | None:
        async with self.database.session() as session:
            return await session.get(NotifierChannel, notifier_id)

    async def delete_notifier(self, notifier_id: str) -> bool:
        async with self.database.session() as session:
            row = await session.get(NotifierChannel, notifier_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def upsert_notifier(
        self,
        *,
        notifier_id: str | None = None,
        payload: dict[str, Any],
    ) -> NotifierChannel:
        async with self.database.session() as session:
            row = await session.get(NotifierChannel, notifier_id) if notifier_id else None
            if row is None:
                row = NotifierChannel(name=str(payload.get("name") or "Telegram Bot"))
                session.add(row)
            _assign_config_fields(
                row,
                payload,
                (
                    "name",
                    "type",
                    "webhook_url",
                    "chat_ids",
                    "use_proxy",
                    "enable_download_notify",
                    "enable_library_notify",
                    "enabled",
                ),
            )
            if payload.get("bot_token"):
                row.bot_token = str(payload["bot_token"])
            await session.commit()
            await session.refresh(row)
            return row

    async def get_system_settings(self) -> dict[str, Any]:
        async with self.database.session() as session:
            row = await session.get(SystemSetting, "runtime")
            return row.value if row is not None else {"proxy": {}}

    async def update_system_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self.database.session() as session:
            row = await session.get(SystemSetting, "runtime")
            if row is None:
                row = SystemSetting(key="runtime", value={})
                session.add(row)
            current = dict(row.value or {})
            current.update(payload)
            row.value = current
            await session.commit()
            await session.refresh(row)
            return row.value

    async def create_download_task(
        self,
        *,
        resource: dict[str, Any],
        media_metadata: dict[str, Any],
        selected_site_ids: list[str],
        category: str,
    ) -> TorrentRecord:
        async with self.database.session() as session:
            record = TorrentRecord(
                torrent_hash=f"pending:{uuid4().hex[:24]}",
                name=str(resource.get("title") or "MusicPilot download"),
                source=str(resource.get("source") or ""),
                download_url=str(resource.get("download_url") or ""),
                status="queued",
                progress=0.0,
                resource_payload=resource,
                media_metadata=media_metadata,
                selected_site_ids=selected_site_ids,
                payload={"category": category},
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def list_download_tasks(self) -> list[TorrentRecord]:
        async with self.database.session() as session:
            result = await session.execute(select(TorrentRecord).order_by(TorrentRecord.id.desc()))
            return list(result.scalars().all())

    async def get_download_task(self, task_id: int) -> TorrentRecord | None:
        async with self.database.session() as session:
            return await session.get(TorrentRecord, task_id)

    async def list_unfinished_download_tasks(self) -> list[TorrentRecord]:
        async with self.database.session() as session:
            result = await session.execute(
                select(TorrentRecord)
                .where(
                    TorrentRecord.status.in_(
                        ("queued", "submitted", "downloading", "completed", "refreshing_library")
                    )
                )
                .order_by(TorrentRecord.id)
            )
            return list(result.scalars().all())

    async def update_download_task(self, task_id: int, **changes: Any) -> TorrentRecord | None:
        operation_started_at = time.perf_counter()
        async with self.database.session() as session:
            row = await session.get(TorrentRecord, task_id)
            if row is None:
                return None
            for key, value in changes.items():
                setattr(row, key, value)
            commit_started_at = time.perf_counter()
            await session.commit()
            _log_slow_db_operation(
                "update_download_task.commit",
                commit_started_at,
                task_id=task_id,
                fields=tuple(changes.keys()),
            )
            await session.refresh(row)
            _log_slow_db_operation(
                "update_download_task.total",
                operation_started_at,
                task_id=task_id,
                fields=tuple(changes.keys()),
            )
            return row

    async def list_download_task_items(self, task_id: int) -> list[TorrentRecordItem]:
        async with self.database.session() as session:
            result = await session.execute(
                select(TorrentRecordItem)
                .where(TorrentRecordItem.torrent_record_id == task_id)
                .order_by(TorrentRecordItem.id)
            )
            return list(result.scalars().all())

    async def get_download_task_item(self, item_id: int) -> TorrentRecordItem | None:
        async with self.database.session() as session:
            return await session.get(TorrentRecordItem, item_id)

    async def replace_download_task_items(
        self,
        task_id: int,
        items: list[dict[str, Any]],
    ) -> list[TorrentRecordItem]:
        async with self.database.session() as session:
            await session.execute(
                delete(TorrentRecordItem).where(TorrentRecordItem.torrent_record_id == task_id)
            )
            rows: list[TorrentRecordItem] = []
            for item in items:
                row = TorrentRecordItem(
                    torrent_record_id=task_id,
                    file_name=str(item["file_name"]),
                    file_path=str(item["file_path"]),
                    artist=_optional_string(item.get("artist")),
                    parsed_title=_optional_string(item.get("parsed_title")),
                    playlist_track_id=_optional_int(item.get("playlist_track_id")),
                    status=str(item.get("status") or "pending"),
                    raw_payload=dict(item.get("raw_payload") or {}),
                )
                session.add(row)
                rows.append(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return rows

    async def update_download_task_item(
        self,
        item_id: int,
        **changes: Any,
    ) -> TorrentRecordItem | None:
        async with self.database.session() as session:
            row = await session.get(TorrentRecordItem, item_id)
            if row is None:
                return None
            for key, value in changes.items():
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_active_download_task_items(self) -> list[TorrentRecordItem]:
        async with self.database.session() as session:
            result = await session.execute(
                select(TorrentRecordItem)
                .join(TorrentRecord, TorrentRecordItem.torrent_record_id == TorrentRecord.id)
                .where(
                    TorrentRecord.status.in_(
                        (
                            "queued",
                            "submitted",
                            "downloading",
                            "completed",
                            "refreshing_library",
                        )
                    )
                )
                .order_by(TorrentRecordItem.id.desc())
            )
            return list(result.scalars().all())

    async def delete_download_task(self, task_id: int) -> bool:
        async with self.database.session() as session:
            row = await session.get(TorrentRecord, task_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_music_platform_connections(self) -> list[MusicPlatformConnection]:
        async with self.database.session() as session:
            result = await session.execute(
                select(MusicPlatformConnection).order_by(
                    MusicPlatformConnection.platform,
                    MusicPlatformConnection.display_name,
                )
            )
            return list(result.scalars().all())

    async def get_music_platform_connection(
        self,
        connection_id: str,
    ) -> MusicPlatformConnection | None:
        async with self.database.session() as session:
            return await session.get(MusicPlatformConnection, connection_id)

    async def create_music_platform_connection(
        self,
        *,
        platform: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> MusicPlatformConnection:
        async with self.database.session() as session:
            row = MusicPlatformConnection(
                platform=platform,
                display_name="",
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scopes=scopes,
                status="pending",
                payload={},
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def get_or_create_url_import_connection(self) -> MusicPlatformConnection:
        async with self.database.session() as session:
            row = await session.get(MusicPlatformConnection, "url_import")
            if row is None:
                row = MusicPlatformConnection(
                    id="url_import",
                    platform="url_import",
                    display_name="公开链接导入",
                    client_id="",
                    client_secret="",
                    redirect_uri="",
                    scopes=[],
                    status="connected",
                    payload={},
                )
                session.add(row)
            else:
                row.status = "connected"
            await session.commit()
            await session.refresh(row)
            return row

    async def update_music_platform_connection(
        self,
        connection_id: str,
        **changes: Any,
    ) -> MusicPlatformConnection | None:
        async with self.database.session() as session:
            row = await session.get(MusicPlatformConnection, connection_id)
            if row is None:
                return None
            for key, value in changes.items():
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return row

    async def delete_music_platform_connection(self, connection_id: str) -> bool:
        async with self.database.session() as session:
            row = await session.get(MusicPlatformConnection, connection_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_playlists(self) -> list[Playlist]:
        async with self.database.session() as session:
            result = await session.execute(select(Playlist).order_by(Playlist.updated_at.desc()))
            return list(result.scalars().all())

    async def get_playlist(self, playlist_id: int) -> Playlist | None:
        async with self.database.session() as session:
            return await session.get(Playlist, playlist_id)

    async def delete_playlist(self, playlist_id: int) -> bool:
        async with self.database.session() as session:
            row = await session.get(Playlist, playlist_id)
            if row is None:
                return False
            await session.execute(
                delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id)
            )
            await session.delete(row)
            await session.commit()
            return True

    async def update_playlist(self, playlist_id: int, **changes: Any) -> Playlist | None:
        async with self.database.session() as session:
            row = await session.get(Playlist, playlist_id)
            if row is None:
                return None
            for key, value in changes.items():
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return row

    async def upsert_playlist(
        self,
        *,
        platform_connection_id: str,
        platform: str,
        external_id: str,
        name: str,
        owner_name: str | None,
        description: str | None,
        cover_url: str | None,
        track_count: int,
        raw_payload: dict[str, Any],
    ) -> Playlist:
        synced_at = datetime.now(UTC)
        async with self.database.session() as session:
            result = await session.execute(
                select(Playlist).where(
                    Playlist.platform_connection_id == platform_connection_id,
                    Playlist.external_id == external_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = Playlist(
                    platform_connection_id=platform_connection_id,
                    platform=platform,
                    external_id=external_id,
                    name=name,
                )
                session.add(row)
            row.name = name
            row.owner_name = owner_name
            row.description = description
            row.cover_url = cover_url
            row.track_count = track_count
            row.status = "synced"
            row.last_synced_at = synced_at
            row.last_error = None
            row.raw_payload = raw_payload
            await session.commit()
            await session.refresh(row)
            return row

    async def list_playlist_tracks(self, playlist_id: int) -> list[PlaylistTrack]:
        async with self.database.session() as session:
            result = await session.execute(
                select(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position, PlaylistTrack.id)
            )
            return list(result.scalars().all())

    async def list_playlist_tracks_page(
        self,
        playlist_id: int,
        *,
        offset: int,
        limit: int,
        title: str | None = None,
        artist: str | None = None,
        download_status: str | None = None,
        exists_in_library: bool | None = None,
    ) -> tuple[list[PlaylistTrack], int]:
        conditions = [PlaylistTrack.playlist_id == playlist_id]
        if title:
            conditions.append(PlaylistTrack.title.ilike(f"%{title}%"))
        if artist:
            conditions.append(PlaylistTrack.artist.ilike(f"%{artist}%"))
        if download_status:
            conditions.append(PlaylistTrack.download_status == download_status)
        if exists_in_library is not None:
            conditions.append(PlaylistTrack.exists_in_library.is_(exists_in_library))
        filter_names = tuple(
            name
            for name, enabled in (
                ("title", bool(title)),
                ("artist", bool(artist)),
                ("download_status", bool(download_status)),
                ("exists_in_library", exists_in_library is not None),
            )
            if enabled
        )
        operation_started_at = time.perf_counter()
        async with self.database.session() as session:
            count_started_at = time.perf_counter()
            total_result = await session.execute(
                select(func.count()).select_from(PlaylistTrack).where(*conditions)
            )
            total = int(total_result.scalar_one())
            _log_slow_db_operation(
                "list_playlist_tracks_page.count",
                count_started_at,
                playlist_id=playlist_id,
                filters=filter_names,
            )
            select_started_at = time.perf_counter()
            result = await session.execute(
                select(PlaylistTrack)
                .where(*conditions)
                .order_by(PlaylistTrack.position, PlaylistTrack.id)
                .offset(offset)
                .limit(limit)
            )
            tracks = list(result.scalars().all())
            _log_slow_db_operation(
                "list_playlist_tracks_page.select",
                select_started_at,
                playlist_id=playlist_id,
                offset=offset,
                limit=limit,
                filters=filter_names,
                rows=len(tracks),
            )
            _log_slow_db_operation(
                "list_playlist_tracks_page.total",
                operation_started_at,
                playlist_id=playlist_id,
                offset=offset,
                limit=limit,
                filters=filter_names,
                rows=len(tracks),
                total=total,
            )
            return tracks, total

    async def list_all_playlist_tracks(self) -> list[PlaylistTrack]:
        async with self.database.session() as session:
            result = await session.execute(
                select(PlaylistTrack).order_by(PlaylistTrack.playlist_id, PlaylistTrack.position)
            )
            return list(result.scalars().all())

    async def get_playlist_track(self, track_id: int) -> PlaylistTrack | None:
        async with self.database.session() as session:
            return await session.get(PlaylistTrack, track_id)

    async def upsert_playlist_tracks(
        self,
        *,
        playlist_id: int,
        platform: str,
        tracks: list[dict[str, Any]],
    ) -> list[PlaylistTrack]:
        seen_external_ids = {str(item["external_id"]) for item in tracks}
        async with self.database.session() as session:
            result = await session.execute(
                select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id)
            )
            existing = {item.external_id: item for item in result.scalars().all()}
            rows: list[PlaylistTrack] = []
            for item in tracks:
                external_id = str(item["external_id"])
                row = existing.get(external_id)
                if row is None:
                    row = PlaylistTrack(
                        playlist_id=playlist_id,
                        platform=platform,
                        external_id=external_id,
                        title=str(item["title"]),
                    )
                    session.add(row)
                row.position = int(item.get("position") or 0)
                row.title = str(item.get("title") or "")
                row.artist = _optional_string(item.get("artist"))
                row.album = _optional_string(item.get("album"))
                row.duration = _optional_int(item.get("duration"))
                row.isrc = _optional_string(item.get("isrc"))
                row.cover_url = _optional_string(item.get("cover_url"))
                row.raw_payload = dict(item.get("raw_payload") or {})
                rows.append(row)
            for external_id, row in existing.items():
                if external_id not in seen_external_ids:
                    await session.delete(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return rows

    async def update_playlist_track(self, track_id: int, **changes: Any) -> PlaylistTrack | None:
        operation_started_at = time.perf_counter()
        async with self.database.session() as session:
            row = await session.get(PlaylistTrack, track_id)
            if row is None:
                return None
            for key, value in changes.items():
                setattr(row, key, value)
            commit_started_at = time.perf_counter()
            await session.commit()
            _log_slow_db_operation(
                "update_playlist_track.commit",
                commit_started_at,
                track_id=track_id,
                fields=tuple(changes.keys()),
                status=changes.get("download_status"),
            )
            await session.refresh(row)
            _log_slow_db_operation(
                "update_playlist_track.total",
                operation_started_at,
                track_id=track_id,
                fields=tuple(changes.keys()),
                status=changes.get("download_status"),
            )
            return row

    async def list_playlist_tracks_by_torrent_record(
        self,
        task_id: int,
    ) -> list[PlaylistTrack]:
        async with self.database.session() as session:
            result = await session.execute(
                select(PlaylistTrack)
                .where(PlaylistTrack.torrent_record_id == task_id)
                .order_by(PlaylistTrack.playlist_id, PlaylistTrack.position, PlaylistTrack.id)
            )
            return list(result.scalars().all())

    async def playlist_track_counts(self, playlist_id: int) -> dict[str, int]:
        tracks = await self.list_playlist_tracks(playlist_id)
        counts: dict[str, int] = {
            "track_count": len(tracks),
            "existing_count": 0,
            "waiting_count": 0,
            "submitted_count": 0,
            "failed_count": 0,
        }
        for track in tracks:
            if track.exists_in_library or track.download_status == "existing":
                counts["existing_count"] += 1
            if track.download_status in {"waiting", "queue"}:
                counts["waiting_count"] += 1
            if track.download_status in {
                "submitted",
                "downloading",
                "completed",
                "refreshing_library",
                "library_refreshed",
            }:
                counts["submitted_count"] += 1
            if track.download_status in {
                "failed",
                "not_found",
                "deleted",
                "source_directory_not_found",
            }:
                counts["failed_count"] += 1
        return counts

    async def list_subscriptions(self) -> list[Subscription]:
        async with self.database.session() as session:
            result = await session.execute(select(Subscription).order_by(Subscription.id))
            return list(result.scalars().all())

    async def list_media_files(self) -> list[MediaFile]:
        async with self.database.session() as session:
            result = await session.execute(select(MediaFile).order_by(MediaFile.id.desc()))
            return list(result.scalars().all())

    async def list_media_files_page(
        self,
        *,
        offset: int,
        limit: int,
        query: str | None = None,
        status: str | None = None,
    ) -> tuple[list[MediaFile], int]:
        conditions = []
        if query:
            pattern = f"%{query}%"
            conditions.append(
                or_(
                    MediaFile.title.ilike(pattern),
                    MediaFile.artist.ilike(pattern),
                    MediaFile.album.ilike(pattern),
                    MediaFile.source_path.ilike(pattern),
                    MediaFile.library_path.ilike(pattern),
                    MediaFile.status.ilike(pattern),
                    MediaFile.error_message.ilike(pattern),
                )
            )
        if status:
            conditions.append(MediaFile.status == status)
        async with self.database.session() as session:
            total_result = await session.execute(
                select(func.count()).select_from(MediaFile).where(*conditions)
            )
            result = await session.execute(
                select(MediaFile)
                .where(*conditions)
                .order_by(MediaFile.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all()), int(total_result.scalar_one())

    async def get_media_file(self, media_id: int) -> MediaFile | None:
        async with self.database.session() as session:
            return await session.get(MediaFile, media_id)

    async def delete_media_file(self, media_id: int) -> bool:
        async with self.database.session() as session:
            row = await session.get(MediaFile, media_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_music_library_tracks(self) -> list[MusicLibraryTrack]:
        async with self.database.session() as session:
            result = await session.execute(
                select(MusicLibraryTrack).order_by(
                    MusicLibraryTrack.artist,
                    MusicLibraryTrack.album,
                    MusicLibraryTrack.title,
                )
            )
            return list(result.scalars().all())

    async def list_music_library_tracks_page(
        self,
        offset: int,
        limit: int,
        query: str | None = None,
    ) -> tuple[list[MusicLibraryTrack], int, int, int]:
        conditions = []
        if query:
            pattern = f"%{query}%"
            conditions.append(
                or_(
                    MusicLibraryTrack.title.ilike(pattern),
                    MusicLibraryTrack.artist.ilike(pattern),
                    MusicLibraryTrack.album.ilike(pattern),
                    MusicLibraryTrack.path.ilike(pattern),
                    MusicLibraryTrack.year.cast(String).ilike(pattern),
                )
            )
        async with self.database.session() as session:
            total_result = await session.execute(
                select(func.count()).select_from(MusicLibraryTrack).where(*conditions)
            )
            album_result = await session.execute(
                select(func.count(func.distinct(func.lower(func.trim(MusicLibraryTrack.album)))))
                .select_from(MusicLibraryTrack)
                .where(
                    *conditions,
                    MusicLibraryTrack.album.isnot(None),
                    func.trim(MusicLibraryTrack.album) != "",
                )
            )
            artist_result = await session.execute(
                select(func.count(func.distinct(func.lower(func.trim(MusicLibraryTrack.artist)))))
                .select_from(MusicLibraryTrack)
                .where(
                    *conditions,
                    MusicLibraryTrack.artist.isnot(None),
                    func.trim(MusicLibraryTrack.artist) != "",
                )
            )
            result = await session.execute(
                select(MusicLibraryTrack)
                .where(*conditions)
                .order_by(
                    MusicLibraryTrack.artist,
                    MusicLibraryTrack.album,
                    MusicLibraryTrack.title,
                )
                .offset(offset)
                .limit(limit)
            )
            return (
                list(result.scalars().all()),
                int(total_result.scalar_one()),
                int(album_result.scalar_one()),
                int(artist_result.scalar_one()),
            )

    async def sync_music_library_tracks(self, tracks: list[dict[str, Any]]) -> int:
        synced_at = datetime.now(UTC)
        seen_ids: set[str] = set()
        async with self.database.session() as session:
            result = await session.execute(select(MusicLibraryTrack))
            existing = {item.navidrome_id: item for item in result.scalars().all()}
            for payload in tracks:
                navidrome_id = str(payload.get("id") or "").strip()
                if not navidrome_id:
                    continue
                seen_ids.add(navidrome_id)
                row = existing.get(navidrome_id)
                if row is None:
                    row = MusicLibraryTrack(navidrome_id=navidrome_id, title="")
                    session.add(row)
                row.title = str(payload.get("title") or payload.get("name") or "-")
                row.artist = _optional_string(payload.get("artist"))
                row.album = _optional_string(payload.get("album"))
                row.duration = _optional_int(payload.get("duration"))
                row.size = _optional_int(payload.get("size"))
                row.year = _optional_int(payload.get("year"))
                row.suffix = _optional_string(payload.get("suffix"))
                row.path = _optional_string(payload.get("path"))
                row.content_type = _optional_string(payload.get("contentType"))
                row.raw_payload = payload
                row.last_synced_at = synced_at
            for navidrome_id, row in existing.items():
                if navidrome_id not in seen_ids:
                    await session.delete(row)
            await session.commit()
        return len(seen_ids)

    async def create_subscription(
        self,
        *,
        kind: str,
        name: str,
        external_id: str | None = None,
        enabled: bool = True,
    ) -> Subscription:
        async with self.database.session() as session:
            subscription = Subscription(
                kind=kind,
                name=name,
                external_id=external_id,
                enabled=enabled,
                payload={},
            )
            session.add(subscription)
            await session.commit()
            await session.refresh(subscription)
            return subscription

    async def mark_subscription_checked(self, subscription_id: int) -> None:
        async with self.database.session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            subscription = result.scalar_one_or_none()
            if subscription is None:
                return
            subscription.last_checked_at = datetime.now(UTC)
            await session.commit()

    async def list_indexer_sites(self) -> list[IndexerSite]:
        async with self.database.session() as session:
            result = await session.execute(select(IndexerSite).order_by(IndexerSite.name))
            return list(result.scalars().all())

    async def create_indexer_site(
        self,
        *,
        name: str,
        base_url: str,
        cookie: str | None = None,
        user_agent: str | None = None,
        max_concurrency: int = 2,
    ) -> IndexerSite:
        async with self.database.session() as session:
            site = IndexerSite(
                name=name,
                base_url=base_url,
                cookie=cookie,
                user_agent=user_agent,
                max_concurrency=max_concurrency,
            )
            session.add(site)
            await session.commit()
            await session.refresh(site)
            return site

    async def update_indexer_site(
        self,
        site_id: str,
        *,
        name: str,
        base_url: str,
        cookie: str | None = None,
        user_agent: str | None = None,
        max_concurrency: int = 2,
    ) -> IndexerSite | None:
        async with self.database.session() as session:
            result = await session.execute(select(IndexerSite).where(IndexerSite.id == site_id))
            site = result.scalar_one_or_none()
            if site is None:
                return None
            site.name = name
            site.base_url = base_url
            site.cookie = cookie
            site.user_agent = user_agent
            site.max_concurrency = max_concurrency
            await session.commit()
            await session.refresh(site)
            return site

    async def delete_indexer_site(self, site_id: str) -> bool:
        async with self.database.session() as session:
            site = await session.get(IndexerSite, site_id)
            if site is None:
                return False
            await session.delete(site)
            await session.commit()
            return True

    # ── Artist queries ──────────────────────────────────────────

    async def find_artist_id_by_alias(self, alias: str) -> int | None:
        async with self.database.session() as session:
            result = await session.execute(
                select(ArtistAlias).where(ArtistAlias.alias == alias).limit(1)
            )
            row = result.scalars().first()
            return row.artist_id if row is not None else None

    async def find_artist_by_normalized(self, normalized: str) -> Artist | None:
        async with self.database.session() as session:
            result = await session.execute(
                select(Artist).where(Artist.normalized_name == normalized).limit(1)
            )
            return result.scalars().first()

    async def get_artist(self, artist_id: int) -> Artist | None:
        async with self.database.session() as session:
            return await session.get(Artist, artist_id)

    async def create_artist(
        self,
        *,
        name: str,
        normalized_name: str,
        external_ids: dict[str, str],
    ) -> Artist:
        async with self.database.session() as session:
            artist = Artist(
                name=name,
                normalized_name=normalized_name,
                external_ids=external_ids,
            )
            session.add(artist)
            await session.commit()
            await session.refresh(artist)
            return artist

    async def delete_artist(self, artist_id: int) -> bool:
        async with self.database.session() as session:
            artist = await session.get(Artist, artist_id)
            if artist is None:
                return False
            await session.delete(artist)
            await session.commit()
            return True

    async def add_alias(self, artist_id: int, alias: str, source: str = "manual") -> None:
        async with self.database.session() as session:
            # Check for duplicate
            result = await session.execute(
                select(ArtistAlias).where(
                    ArtistAlias.artist_id == artist_id, ArtistAlias.alias == alias
                ).limit(1)
            )
            existing = result.scalars().first()
            if existing is not None:
                return
            row = ArtistAlias(artist_id=artist_id, alias=alias, source=source)
            session.add(row)
            await session.commit()

    async def add_aliases(self, artist_id: int, aliases: tuple[tuple[str, str], ...]) -> None:
        if not aliases:
            return
        names = tuple(dict.fromkeys(alias for alias, _source in aliases if alias))
        if not names:
            return
        async with self.database.session() as session:
            result = await session.execute(
                select(ArtistAlias.alias).where(
                    ArtistAlias.artist_id == artist_id,
                    ArtistAlias.alias.in_(names),
                )
            )
            existing = set(result.scalars().all())
            for alias, source in aliases:
                if not alias or alias in existing:
                    continue
                session.add(ArtistAlias(artist_id=artist_id, alias=alias, source=source))
                existing.add(alias)
            await session.commit()

    async def list_artist_aliases(self, artist_id: int) -> list[str]:
        async with self.database.session() as session:
            result = await session.execute(
                select(ArtistAlias).where(ArtistAlias.artist_id == artist_id)
            )
            rows = result.scalars().all()
            artist = await session.get(Artist, artist_id)
            aliases = [artist.name] if artist else []
            artist_name = artist.name if artist else None
            aliases.extend(row.alias for row in rows if row.alias != artist_name)
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for a in aliases:
                if a not in seen:
                    seen.add(a)
                    unique.append(a)
            return unique

    async def reassign_aliases(self, from_artist_id: int, to_artist_id: int) -> int:
        async with self.database.session() as session:
            result = await session.execute(
                select(ArtistAlias).where(ArtistAlias.artist_id == from_artist_id)
            )
            moved = 0
            for row in result.scalars().all():
                row.artist_id = to_artist_id
                moved += 1
            await session.commit()
            return moved

    async def list_all_artists(self) -> list[Artist]:
        async with self.database.session() as session:
            result = await session.execute(select(Artist).order_by(Artist.name))
            return list(result.scalars().all())

    async def list_artists_page(
        self,
        *,
        offset: int,
        limit: int,
        query: str | None = None,
    ) -> tuple[list[Artist], int]:
        conditions = []
        if query:
            pattern = f"%{query}%"
            alias_artist_ids = select(ArtistAlias.artist_id).where(ArtistAlias.alias.ilike(pattern))
            conditions.append(
                or_(
                    Artist.name.ilike(pattern),
                    Artist.normalized_name.ilike(pattern),
                    Artist.id.in_(alias_artist_ids),
                )
            )
        async with self.database.session() as session:
            total_result = await session.execute(
                select(func.count()).select_from(Artist).where(*conditions)
            )
            result = await session.execute(
                select(Artist)
                .where(*conditions)
                .order_by(Artist.name)
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all()), int(total_result.scalar_one())

    async def clear_all_artists(self) -> tuple[int, int]:
        """Delete all artists and aliases. Returns (deleted_aliases, deleted_artists)."""
        async with self.database.session() as session:
            alias_result = await session.execute(select(ArtistAlias))
            aliases = alias_result.scalars().all()
            for row in aliases:
                await session.delete(row)
            artist_result = await session.execute(select(Artist))
            artists = artist_result.scalars().all()
            for row in artists:
                await session.delete(row)
            await session.commit()
            return len(aliases), len(artists)

    async def list_distinct_artists(self) -> list[str]:
        """Return unique artist names from media files, library tracks, and playlists."""
        async with self.database.session() as session:
            media_result = await session.execute(
                select(MediaFile.artist).where(
                    MediaFile.artist.isnot(None),
                    MediaFile.artist != "",
                ).distinct()
            )
            library_result = await session.execute(
                select(MusicLibraryTrack.artist).where(
                    MusicLibraryTrack.artist.isnot(None),
                    MusicLibraryTrack.artist != "",
                ).distinct()
            )
            playlist_result = await session.execute(
                select(PlaylistTrack.artist).where(
                    PlaylistTrack.artist.isnot(None),
                    PlaylistTrack.artist != "",
                ).distinct()
            )
            seen: set[str] = set()
            all_names: list[str] = []
            for (name,) in media_result.fetchall():
                if name and name not in seen:
                    seen.add(name)
                    all_names.append(name)
            for (name,) in library_result.fetchall():
                if name and name not in seen:
                    seen.add(name)
                    all_names.append(name)
            for (name,) in playlist_result.fetchall():
                if name and name not in seen:
                    seen.add(name)
                    all_names.append(name)
            return all_names


def _assign_config_fields(row: object, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in payload:
            setattr(row, field, payload[field])


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _clear_other_defaults(session: object, model: type[object], active_id: str) -> None:
    result = await session.execute(select(model).where(model.id != active_id))
    for row in result.scalars().all():
        row.is_default = False
