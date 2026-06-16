from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from musicpilot.infra.db.models import (
    DownloaderConfig,
    IndexerSite,
    MediaFile,
    MediaServerConfig,
    NotifierChannel,
    Subscription,
    SystemSetting,
    TorrentRecord,
)
from musicpilot.infra.db.session import Database
from musicpilot.ports.metadata import TrackMetadata


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
            media_file = result.scalar_one_or_none()
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
            media_file.metadata_payload = asdict(metadata)
            await session.commit()

    async def mark_torrent_completed(
        self,
        *,
        torrent_hash: str,
        save_path: Path | None,
    ) -> None:
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

    async def list_unfinished_download_tasks(self) -> list[TorrentRecord]:
        async with self.database.session() as session:
            result = await session.execute(
                select(TorrentRecord)
                .where(
                    TorrentRecord.status.in_(
                        ("submitted", "downloading", "completed", "refreshing_library")
                    )
                )
                .order_by(TorrentRecord.id)
            )
            return list(result.scalars().all())

    async def update_download_task(self, task_id: int, **changes: Any) -> TorrentRecord | None:
        async with self.database.session() as session:
            row = await session.get(TorrentRecord, task_id)
            if row is None:
                return None
            for key, value in changes.items():
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_subscriptions(self) -> list[Subscription]:
        async with self.database.session() as session:
            result = await session.execute(select(Subscription).order_by(Subscription.id))
            return list(result.scalars().all())

    async def list_media_files(self) -> list[MediaFile]:
        async with self.database.session() as session:
            result = await session.execute(select(MediaFile).order_by(MediaFile.id.desc()))
            return list(result.scalars().all())

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


def _assign_config_fields(row: object, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in payload:
            setattr(row, field, payload[field])


async def _clear_other_defaults(session: object, model: type[object], active_id: str) -> None:
    result = await session.execute(select(model).where(model.id != active_id))
    for row in result.scalars().all():
        row.is_default = False
