from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import String, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from musicpilot.core.defaults import DEFAULT_SEARCH_EXCLUDE_KEYWORDS
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
    SystemTask,
    SystemTaskResourceLease,
    TorrentRecord,
    TorrentRecordItem,
)
from musicpilot.infra.db.session import Database
from musicpilot.ports.metadata import TrackMetadata

DEFAULT_SYSTEM_SETTINGS: dict[str, Any] = {
    "proxy": {},
    "search": {
        "exclude_keywords": DEFAULT_SEARCH_EXCLUDE_KEYWORDS,
        "minimum_seeders": 1,
        "metadata_concurrency": 3,
    },
}

logger = logging.getLogger(__name__)
SLOW_DB_OPERATION_SECONDS = float(os.getenv("MP_SLOW_DB_OPERATION_SECONDS", "0.5"))
SLOW_SYSTEM_TASK_SECONDS = int(os.getenv("MP_SLOW_SYSTEM_TASK_SECONDS", "300"))


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
        operation_type: str = "mapped",
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
            media_file.operation_type = operation_type
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

    async def get_media_server(self, server_id: str) -> MediaServerConfig | None:
        async with self.database.session() as session:
            return await session.get(MediaServerConfig, server_id)

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
            return _merge_system_settings_defaults(row.value if row is not None else {})

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
            return _merge_system_settings_defaults(row.value)

    async def create_system_task(
        self,
        *,
        task_type: str,
        payload: dict[str, Any],
        resource_keys: list[str],
        chain_id: str | None = None,
        parent_task_id: int | None = None,
        inheritable_key: str | None = None,
        priority: int = 0,
        max_attempts: int = 1,
        available_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> SystemTask:
        async with self.database.session() as session:
            if idempotency_key:
                existing_result = await session.execute(
                    select(SystemTask).where(SystemTask.idempotency_key == idempotency_key)
                )
                existing = existing_result.scalars().first()
                if existing is not None:
                    return existing
            now = datetime.now(UTC)
            row = SystemTask(
                task_type=task_type,
                status="WAIT",
                chain_id=chain_id or uuid4().hex,
                parent_task_id=parent_task_id,
                priority=priority,
                resource_keys=_unique_strings(resource_keys),
                inheritable_key=inheritable_key,
                payload=payload,
                result={},
                error_message=None,
                attempts=0,
                max_attempts=max(1, max_attempts),
                available_at=available_at or now,
                idempotency_key=idempotency_key,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if not idempotency_key:
                    raise
                existing_result = await session.execute(
                    select(SystemTask).where(SystemTask.idempotency_key == idempotency_key)
                )
                existing = existing_result.scalars().first()
                if existing is None:
                    raise
                return existing
            await session.refresh(row)
            return row

    async def list_ready_system_tasks(self, *, limit: int = 20) -> list[SystemTask]:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            result = await session.execute(
                select(SystemTask)
                .where(
                    SystemTask.status == "WAIT",
                    SystemTask.available_at <= now,
                )
                .order_by(SystemTask.priority.desc(), SystemTask.created_at, SystemTask.id)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_system_task(self, task_id: int) -> SystemTask | None:
        async with self.database.session() as session:
            return await session.get(SystemTask, task_id)

    async def list_system_tasks(
        self,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[SystemTask]:
        async with self.database.session() as session:
            statement = select(SystemTask)
            if status is not None:
                statement = statement.where(SystemTask.status == status)
            result = await session.execute(
                statement
                .order_by(SystemTask.priority.desc(), SystemTask.created_at, SystemTask.id)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def list_system_tasks_by_ids(self, task_ids: list[int]) -> list[SystemTask]:
        ids = sorted(set(task_ids))
        if not ids:
            return []
        async with self.database.session() as session:
            result = await session.execute(
                select(SystemTask)
                .where(SystemTask.id.in_(ids))
                .order_by(SystemTask.created_at, SystemTask.id)
            )
            return list(result.scalars().all())

    async def list_slow_running_system_tasks(
        self,
        *,
        threshold_seconds: int = SLOW_SYSTEM_TASK_SECONDS,
        limit: int = 200,
    ) -> list[SystemTask]:
        threshold = datetime.now(UTC) - timedelta(seconds=max(1, threshold_seconds))
        async with self.database.session() as session:
            result = await session.execute(
                select(SystemTask)
                .where(
                    SystemTask.status == "RUNNING",
                    SystemTask.started_at.isnot(None),
                    SystemTask.started_at <= threshold,
                )
                .order_by(SystemTask.started_at, SystemTask.id)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_system_task_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> SystemTask | None:
        async with self.database.session() as session:
            result = await session.execute(
                select(SystemTask).where(SystemTask.idempotency_key == idempotency_key)
            )
            return result.scalars().first()

    async def update_waiting_system_task(
        self,
        task_id: int,
        *,
        payload: dict[str, Any] | None = None,
        priority: int | None = None,
        available_at: datetime | None = None,
    ) -> SystemTask | None:
        async with self.database.session() as session:
            task = await session.get(SystemTask, task_id)
            if task is None or task.status != "WAIT":
                return None
            if payload is not None:
                task.payload = payload
            if priority is not None:
                task.priority = max(int(task.priority or 0), priority)
            if available_at is not None:
                task.available_at = available_at
            await session.commit()
            await session.refresh(task)
            return task

    async def try_claim_system_task(
        self,
        task_id: int,
        *,
        lease_seconds: int,
    ) -> SystemTask | None:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self.database.session() as session:
            task = await session.get(SystemTask, task_id)
            if task is None or task.status != "WAIT" or _as_utc(task.available_at) > now:
                return None
            resource_keys = _unique_strings(task.resource_keys or [])
            if task.inheritable_key and task.inheritable_key not in resource_keys:
                resource_keys.append(task.inheritable_key)
            claimed_keys: list[str] = []
            try:
                for resource_key in resource_keys:
                    if resource_key == task.inheritable_key:
                        lease = await _get_active_resource_lease(session, resource_key, now)
                        if (
                            lease is not None
                            and lease.holder_kind == "chain"
                            and lease.holder_id == task.chain_id
                        ):
                            lease.lease_until = lease_until
                            continue
                        if lease is not None:
                            return None
                        session.add(
                            SystemTaskResourceLease(
                                resource_key=resource_key,
                                holder_kind="chain",
                                holder_id=task.chain_id,
                                task_id=None,
                                chain_id=task.chain_id,
                                lease_until=lease_until,
                            )
                        )
                        claimed_keys.append(resource_key)
                        continue
                    claimed_key = await _claim_task_resource_lease(
                        session,
                        resource_key=resource_key,
                        task_id=task.id,
                        chain_id=task.chain_id,
                        lease_until=lease_until,
                        now=now,
                    )
                    if claimed_key is None:
                        await session.rollback()
                        return None
                    claimed_keys.append(claimed_key)
                task.status = "RUNNING"
                task.attempts += 1
                task.started_at = now
                task.heartbeat_at = now
                task.lease_until = lease_until
                task.error_message = None
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
            await session.refresh(task)
            logger.info(
                "System task claimed: id=%s type=%s resources=%s",
                task.id,
                task.task_type,
                claimed_keys,
            )
            return task

    async def try_start_system_task(
        self,
        *,
        task_type: str,
        payload: dict[str, Any],
        resource_keys: list[str],
        lease_seconds: int,
        chain_id: str | None = None,
        parent_task_id: int | None = None,
        inheritable_key: str | None = None,
        priority: int = 0,
        max_attempts: int = 1,
        idempotency_key: str | None = None,
    ) -> SystemTask | None:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)
        chain_value = chain_id or uuid4().hex
        claimed_keys: list[str] = []
        async with self.database.session() as session:
            resource_values = _unique_strings(resource_keys or [])
            if inheritable_key and inheritable_key not in resource_values:
                resource_values.append(inheritable_key)
            try:
                row = SystemTask(
                    task_type=task_type,
                    status="RUNNING",
                    chain_id=chain_value,
                    parent_task_id=parent_task_id,
                    priority=priority,
                    resource_keys=resource_values,
                    inheritable_key=inheritable_key,
                    payload=dict(payload or {}),
                    result={},
                    error_message=None,
                    attempts=1,
                    max_attempts=max(1, max_attempts),
                    available_at=now,
                    started_at=now,
                    heartbeat_at=now,
                    lease_until=lease_until,
                    idempotency_key=idempotency_key,
                )
                session.add(row)
                await session.flush()
                for resource_key in resource_values:
                    if resource_key == inheritable_key:
                        lease = await _get_active_resource_lease(session, resource_key, now)
                        if lease is not None:
                            await session.rollback()
                            return None
                        session.add(
                            SystemTaskResourceLease(
                                resource_key=resource_key,
                                holder_kind="chain",
                                holder_id=chain_value,
                                task_id=None,
                                chain_id=chain_value,
                                lease_until=lease_until,
                            )
                        )
                        claimed_keys.append(resource_key)
                        continue
                    claimed_key = await _claim_task_resource_lease(
                        session,
                        resource_key=resource_key,
                        task_id=row.id,
                        chain_id=chain_value,
                        lease_until=lease_until,
                        now=now,
                    )
                    if claimed_key is None:
                        await session.rollback()
                        return None
                    claimed_keys.append(claimed_key)
                await session.commit()
                await session.refresh(row)
                logger.info(
                    "System task started: id=%s type=%s resources=%s",
                    row.id,
                    row.task_type,
                    claimed_keys,
                )
                return row
            except IntegrityError:
                await session.rollback()
                return None

    async def complete_system_task(
        self,
        task_id: int,
        *,
        result: dict[str, Any],
        next_tasks: list[dict[str, Any]],
    ) -> SystemTask | None:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            task = await session.get(SystemTask, task_id)
            if task is None or task.status != "RUNNING":
                return None
            task.status = "SUCCEEDED"
            task.result = result
            task.error_message = None
            task.finished_at = now
            task.heartbeat_at = now
            task.lease_until = None
            created_next: list[SystemTask] = []
            for payload in next_tasks:
                next_task = SystemTask(
                    task_type=str(payload["task_type"]),
                    status="WAIT",
                    chain_id=str(payload.get("chain_id") or task.chain_id),
                    parent_task_id=_optional_int(payload.get("parent_task_id")) or task.id,
                    priority=_optional_int(payload.get("priority")) or task.priority,
                    resource_keys=_unique_strings(payload.get("resource_keys") or []),
                    inheritable_key=_optional_string(payload.get("inheritable_key")),
                    payload=dict(payload.get("payload") or {}),
                    result={},
                    error_message=None,
                    attempts=0,
                    max_attempts=max(1, _optional_int(payload.get("max_attempts")) or 1),
                    available_at=payload.get("available_at") or now,
                    idempotency_key=_optional_string(payload.get("idempotency_key")),
                )
                session.add(next_task)
                created_next.append(next_task)
            await session.execute(
                delete(SystemTaskResourceLease).where(
                    SystemTaskResourceLease.holder_kind == "task",
                    SystemTaskResourceLease.task_id == task.id,
                )
            )
            await session.flush()
            if not created_next:
                active = await _system_task_chain_has_active_tasks(session, task.chain_id, task.id)
                if not active:
                    await session.execute(
                        delete(SystemTaskResourceLease).where(
                            SystemTaskResourceLease.holder_kind == "chain",
                            SystemTaskResourceLease.chain_id == task.chain_id,
                        )
                    )
            await session.commit()
            await session.refresh(task)
            return task

    async def fail_system_task(
        self,
        task_id: int,
        *,
        error_message: str,
        retry_delay_seconds: int = 60,
    ) -> SystemTask | None:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            task = await session.get(SystemTask, task_id)
            if task is None or task.status != "RUNNING":
                return None
            should_retry = task.attempts < task.max_attempts
            task.status = "WAIT" if should_retry else "FAILED"
            task.error_message = error_message
            task.heartbeat_at = now
            task.lease_until = None
            task.finished_at = None if should_retry else now
            if should_retry:
                task.available_at = now + timedelta(seconds=retry_delay_seconds)
            await session.execute(
                delete(SystemTaskResourceLease).where(
                    SystemTaskResourceLease.holder_kind == "task",
                    SystemTaskResourceLease.task_id == task.id,
                )
            )
            await session.flush()
            if not should_retry:
                active = await _system_task_chain_has_active_tasks(session, task.chain_id, task.id)
                if not active:
                    await session.execute(
                        delete(SystemTaskResourceLease).where(
                            SystemTaskResourceLease.holder_kind == "chain",
                            SystemTaskResourceLease.chain_id == task.chain_id,
                        )
                    )
            await session.commit()
            await session.refresh(task)
            return task

    async def interrupt_waiting_system_tasks(
        self,
        task_ids: list[int],
        *,
        error_message: str,
    ) -> list[SystemTask]:
        ids = sorted(set(task_ids))
        if not ids:
            return []
        now = datetime.now(UTC)
        async with self.database.session() as session:
            result = await session.execute(
                select(SystemTask)
                .where(SystemTask.id.in_(ids), SystemTask.status == "WAIT")
                .order_by(SystemTask.created_at, SystemTask.id)
            )
            tasks = list(result.scalars().all())
            if not tasks:
                return []
            for task in tasks:
                task.status = "INTERRUPTED"
                task.error_message = error_message
                task.finished_at = now
                task.heartbeat_at = now
                task.lease_until = None
            await session.execute(
                delete(SystemTaskResourceLease).where(
                    SystemTaskResourceLease.holder_kind == "task",
                    SystemTaskResourceLease.task_id.in_([task.id for task in tasks]),
                )
            )
            await session.flush()
            for chain_id in {task.chain_id for task in tasks}:
                active_result = await session.execute(
                    select(func.count())
                    .select_from(SystemTask)
                    .where(
                        SystemTask.chain_id == chain_id,
                        SystemTask.status.in_(("WAIT", "RUNNING")),
                    )
                )
                if int(active_result.scalar_one()) == 0:
                    await session.execute(
                        delete(SystemTaskResourceLease).where(
                            SystemTaskResourceLease.holder_kind == "chain",
                            SystemTaskResourceLease.chain_id == chain_id,
                        )
                    )
            await session.commit()
            for task in tasks:
                await session.refresh(task)
            return tasks

    async def interrupt_running_system_tasks(
        self,
        task_ids: list[int],
        *,
        error_message: str,
    ) -> list[SystemTask]:
        ids = sorted(set(task_ids))
        if not ids:
            return []
        now = datetime.now(UTC)
        async with self.database.session() as session:
            result = await session.execute(
                select(SystemTask)
                .where(SystemTask.id.in_(ids), SystemTask.status == "RUNNING")
                .order_by(SystemTask.created_at, SystemTask.id)
            )
            tasks = list(result.scalars().all())
            if not tasks:
                return []
            for task in tasks:
                task.status = "INTERRUPTED"
                task.error_message = error_message
                task.finished_at = now
                task.heartbeat_at = now
                task.lease_until = None
            await session.execute(
                delete(SystemTaskResourceLease).where(
                    or_(
                        SystemTaskResourceLease.task_id.in_([task.id for task in tasks]),
                        SystemTaskResourceLease.chain_id.in_({task.chain_id for task in tasks}),
                    )
                )
            )
            await session.commit()
            for task in tasks:
                await session.refresh(task)
            return tasks

    async def refresh_system_task_lease(
        self,
        task_id: int,
        *,
        lease_seconds: int,
    ) -> bool:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self.database.session() as session:
            task = await session.get(SystemTask, task_id)
            if task is None or task.status != "RUNNING":
                return False
            task.heartbeat_at = now
            task.lease_until = lease_until
            await session.execute(
                update(SystemTaskResourceLease)
                .where(
                    or_(
                        SystemTaskResourceLease.task_id == task.id,
                        SystemTaskResourceLease.chain_id == task.chain_id,
                    )
                )
                .values(lease_until=lease_until)
            )
            await session.commit()
            return True

    async def requeue_system_task(
        self,
        task_id: int,
        *,
        error_message: str,
    ) -> SystemTask | None:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            task = await session.get(SystemTask, task_id)
            if task is None:
                return None
            task.status = "WAIT"
            task.error_message = error_message
            task.available_at = now
            task.heartbeat_at = now
            task.lease_until = None
            await session.execute(
                delete(SystemTaskResourceLease).where(
                    SystemTaskResourceLease.holder_kind == "task",
                    SystemTaskResourceLease.task_id == task.id,
                )
            )
            await session.commit()
            await session.refresh(task)
            return task

    async def recover_stale_system_tasks(self, *, recover_all_running: bool = False) -> int:
        now = datetime.now(UTC)
        recovered = 0
        async with self.database.session() as session:
            filters = [SystemTask.status == "RUNNING"]
            if not recover_all_running:
                filters.extend(
                    [
                        SystemTask.lease_until.isnot(None),
                        SystemTask.lease_until <= now,
                    ]
                )
            result = await session.execute(
                select(SystemTask).where(*filters)
            )
            for task in result.scalars().all():
                task.status = "WAIT"
                task.lease_until = None
                task.heartbeat_at = now
                task.error_message = (
                    "Task restored after scheduler restart."
                    if recover_all_running
                    else "Task lease expired; restored to WAIT."
                )
                recovered += 1
            if recover_all_running:
                await session.execute(delete(SystemTaskResourceLease))
            else:
                await session.execute(
                    delete(SystemTaskResourceLease).where(
                        SystemTaskResourceLease.lease_until <= now
                    )
                )
            await session.commit()
        return recovered

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
            existing_result = await session.execute(
                select(TorrentRecordItem)
                .where(TorrentRecordItem.torrent_record_id == task_id)
                .order_by(TorrentRecordItem.id)
            )
            existing_rows = list(existing_result.scalars().all())
            existing_by_path = {row.file_path: row for row in existing_rows}
            seen_paths: set[str] = set()
            rows: list[TorrentRecordItem] = []
            for item in items:
                file_path = str(item["file_path"])
                seen_paths.add(file_path)
                row = existing_by_path.get(file_path)
                if row is None:
                    row = TorrentRecordItem(
                        torrent_record_id=task_id,
                        file_name=str(item["file_name"]),
                        file_path=file_path,
                        artist=_optional_string(item.get("artist")),
                        parsed_title=_optional_string(item.get("parsed_title")),
                        playlist_track_id=_optional_int(item.get("playlist_track_id")),
                        status=str(item.get("status") or "pending"),
                        raw_payload=dict(item.get("raw_payload") or {}),
                    )
                    session.add(row)
                else:
                    row.file_name = str(item["file_name"])
                    row.artist = _optional_string(item.get("artist"))
                    row.parsed_title = _optional_string(item.get("parsed_title"))
                    row.raw_payload = dict(item.get("raw_payload") or {})
                    playlist_track_id = _optional_int(item.get("playlist_track_id"))
                    if playlist_track_id is not None:
                        row.playlist_track_id = playlist_track_id
                rows.append(row)
            for row in existing_rows:
                if row.file_path not in seen_paths:
                    await session.delete(row)
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
        operation_started_at = time.perf_counter()
        async with self.database.session() as session:
            get_started_at = time.perf_counter()
            playlist = await session.get(Playlist, playlist_id)
            _log_slow_db_operation(
                "get_playlist.get",
                get_started_at,
                playlist_id=playlist_id,
                found=playlist is not None,
            )
            _log_slow_db_operation(
                "get_playlist.total",
                operation_started_at,
                playlist_id=playlist_id,
                found=playlist is not None,
            )
            return playlist

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

    async def migrate_playlist_track_source_keys(self) -> int:
        async with self.database.session() as session:
            result = await session.execute(
                select(PlaylistTrack).order_by(
                    PlaylistTrack.playlist_id,
                    PlaylistTrack.position,
                    PlaylistTrack.id,
                )
            )
            rows = list(result.scalars().all())
            counters: dict[int, dict[str, int]] = {}
            updated = 0
            for row in rows:
                original_title = row.original_title or row.title
                normalized = _normalize_playlist_source_title(original_title)
                playlist_counters = counters.setdefault(row.playlist_id, {})
                occurrence_index = playlist_counters.get(normalized, 0) + 1
                playlist_counters[normalized] = occurrence_index
                source_key = _playlist_track_source_key(original_title, occurrence_index)
                if row.original_title != original_title or row.source_key != source_key:
                    row.original_title = original_title
                    row.source_key = source_key
                    updated += 1
            if updated:
                await session.commit()
            return updated

    async def upsert_playlist_tracks(
        self,
        *,
        playlist_id: int,
        platform: str,
        tracks: list[dict[str, Any]],
    ) -> list[PlaylistTrack]:
        prepared_tracks = _playlist_tracks_with_source_keys(tracks)
        seen_source_keys = {item["source_key"] for item in prepared_tracks}
        async with self.database.session() as session:
            result = await session.execute(
                select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id)
            )
            existing = {item.source_key: item for item in result.scalars().all()}
            rows: list[PlaylistTrack] = []
            for item in prepared_tracks:
                external_id = str(item["external_id"])
                source_key = str(item["source_key"])
                original_title = str(item["original_title"])
                row = existing.get(source_key)
                if row is None:
                    row = PlaylistTrack(
                        playlist_id=playlist_id,
                        platform=platform,
                        external_id=external_id,
                        source_key=source_key,
                        original_title=original_title,
                        title=str(item["title"]),
                    )
                    session.add(row)
                    row.artist = _optional_string(item.get("artist"))
                    row.album = _optional_string(item.get("album"))
                    row.duration = _optional_int(item.get("duration"))
                    row.isrc = _optional_string(item.get("isrc"))
                    row.cover_url = _optional_string(item.get("cover_url"))
                row.platform = platform
                row.external_id = external_id
                row.position = int(item.get("position") or 0)
                row.raw_payload = dict(item.get("raw_payload") or {})
                rows.append(row)
            for source_key, row in existing.items():
                if source_key not in seen_source_keys:
                    await session.delete(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return rows

    async def update_playlist_track(self, track_id: int, **changes: Any) -> PlaylistTrack | None:
        operation_started_at = time.perf_counter()
        async with self.database.session() as session:
            get_started_at = time.perf_counter()
            row = await session.get(PlaylistTrack, track_id)
            _log_slow_db_operation(
                "update_playlist_track.get",
                get_started_at,
                track_id=track_id,
                fields=tuple(changes.keys()),
            )
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
            refresh_started_at = time.perf_counter()
            await session.refresh(row)
            _log_slow_db_operation(
                "update_playlist_track.refresh",
                refresh_started_at,
                track_id=track_id,
                fields=tuple(changes.keys()),
                status=changes.get("download_status"),
            )
            _log_slow_db_operation(
                "update_playlist_track.total",
                operation_started_at,
                track_id=track_id,
                fields=tuple(changes.keys()),
                status=changes.get("download_status"),
            )
            return row

    async def reset_waiting_playlist_tracks(self) -> int:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            result = await session.execute(
                update(PlaylistTrack)
                .where(PlaylistTrack.download_status == "waiting")
                .values(
                    download_status="pending",
                    torrent_record_id=None,
                    last_error=None,
                    updated_at=now,
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

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

    async def list_matched_playlist_library_tracks(
        self,
        playlist_id: int,
    ) -> list[tuple[PlaylistTrack, MusicLibraryTrack]]:
        async with self.database.session() as session:
            result = await session.execute(
                select(PlaylistTrack, MusicLibraryTrack)
                .join(
                    MusicLibraryTrack,
                    PlaylistTrack.matched_library_track_id == MusicLibraryTrack.id,
                )
                .where(
                    PlaylistTrack.playlist_id == playlist_id,
                    PlaylistTrack.exists_in_library.is_(True),
                    PlaylistTrack.matched_library_track_id.isnot(None),
                )
                .order_by(PlaylistTrack.position, PlaylistTrack.id)
            )
            return [(track, library_track) for track, library_track in result.all()]

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
            if track.download_status == "queue":
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

    async def dashboard_summary(self) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=7)
        async with self.database.session() as session:
            library_total = await session.execute(
                select(func.count()).select_from(MusicLibraryTrack)
            )
            library_albums = await session.execute(
                select(func.count(func.distinct(func.lower(func.trim(MusicLibraryTrack.album)))))
                .select_from(MusicLibraryTrack)
                .where(
                    MusicLibraryTrack.album.isnot(None),
                    func.trim(MusicLibraryTrack.album) != "",
                )
            )
            library_artists = await session.execute(
                select(func.count(func.distinct(func.lower(func.trim(MusicLibraryTrack.artist)))))
                .select_from(MusicLibraryTrack)
                .where(
                    MusicLibraryTrack.artist.isnot(None),
                    func.trim(MusicLibraryTrack.artist) != "",
                )
            )
            recent_library = await session.execute(
                select(func.count())
                .select_from(MusicLibraryTrack)
                .where(MusicLibraryTrack.created_at >= since)
            )
            last_library_synced = await session.execute(
                select(func.max(MusicLibraryTrack.last_synced_at)).select_from(MusicLibraryTrack)
            )

            playlist_total = await session.execute(select(func.count()).select_from(Playlist))
            playlist_tracks = await session.execute(
                select(func.count()).select_from(PlaylistTrack)
            )
            playlist_existing = await session.execute(
                select(func.count())
                .select_from(PlaylistTrack)
                .where(
                    or_(
                        PlaylistTrack.exists_in_library.is_(True),
                        PlaylistTrack.download_status == "existing",
                    )
                )
            )
            playlist_pending = await session.execute(
                select(func.count())
                .select_from(PlaylistTrack)
                .where(PlaylistTrack.download_status.in_(("pending", "queue", "searching")))
            )
            playlist_failed = await session.execute(
                select(func.count())
                .select_from(PlaylistTrack)
                .where(
                    PlaylistTrack.download_status.in_(
                        ("failed", "not_found", "deleted", "source_directory_not_found")
                    )
                )
            )

            download_total = await session.execute(
                select(func.count()).select_from(TorrentRecord)
            )
            download_active = await session.execute(
                select(func.count())
                .select_from(TorrentRecord)
                .where(TorrentRecord.status.not_in(("library_refreshed", "interrupted")))
            )
            download_completed_7d = await session.execute(
                select(func.count())
                .select_from(TorrentRecord)
                .where(
                    or_(
                        TorrentRecord.completed_at >= since,
                        TorrentRecord.library_refreshed_at >= since,
                    )
                )
            )
            download_failed = await session.execute(
                select(func.count())
                .select_from(TorrentRecord)
                .where(TorrentRecord.status.in_(("failed", "source_directory_not_found")))
            )
            download_status_rows = await session.execute(
                select(TorrentRecord.status, func.count())
                .select_from(TorrentRecord)
                .group_by(TorrentRecord.status)
            )
            recent_downloads = await session.execute(
                select(TorrentRecord).order_by(TorrentRecord.updated_at.desc()).limit(5)
            )

            media_total = await session.execute(select(func.count()).select_from(MediaFile))
            media_success = await session.execute(
                select(func.count()).select_from(MediaFile).where(MediaFile.status == "success")
            )
            media_failed = await session.execute(
                select(func.count()).select_from(MediaFile).where(MediaFile.status == "failed")
            )
            media_recent_7d = await session.execute(
                select(func.count()).select_from(MediaFile).where(MediaFile.created_at >= since)
            )
            recent_media = await session.execute(
                select(MediaFile).order_by(MediaFile.updated_at.desc()).limit(5)
            )

            task_status_rows = await session.execute(
                select(SystemTask.status, func.count())
                .select_from(SystemTask)
                .group_by(SystemTask.status)
            )
            slow_task_threshold = datetime.now(UTC) - timedelta(seconds=SLOW_SYSTEM_TASK_SECONDS)
            slow_tasks = await session.execute(
                select(func.count())
                .select_from(SystemTask)
                .where(
                    SystemTask.status == "RUNNING",
                    SystemTask.started_at.isnot(None),
                    SystemTask.started_at <= slow_task_threshold,
                )
            )

            task_counts = {str(status): int(count) for status, count in task_status_rows.all()}
            return {
                "library": {
                    "songs": int(library_total.scalar_one()),
                    "albums": int(library_albums.scalar_one()),
                    "artists": int(library_artists.scalar_one()),
                    "recent_7d_songs": int(recent_library.scalar_one()),
                    "last_synced_at": last_library_synced.scalar_one(),
                },
                "playlists": {
                    "playlists": int(playlist_total.scalar_one()),
                    "tracks": int(playlist_tracks.scalar_one()),
                    "existing_tracks": int(playlist_existing.scalar_one()),
                    "pending_tracks": int(playlist_pending.scalar_one()),
                    "failed_tracks": int(playlist_failed.scalar_one()),
                },
                "downloads": {
                    "total": int(download_total.scalar_one()),
                    "active": int(download_active.scalar_one()),
                    "completed_7d": int(download_completed_7d.scalar_one()),
                    "failed": int(download_failed.scalar_one()),
                    "status_counts": {
                        str(status): int(count) for status, count in download_status_rows.all()
                    },
                    "recent": list(recent_downloads.scalars().all()),
                },
                "media": {
                    "total": int(media_total.scalar_one()),
                    "success": int(media_success.scalar_one()),
                    "failed": int(media_failed.scalar_one()),
                    "recent_7d": int(media_recent_7d.scalar_one()),
                    "recent": list(recent_media.scalars().all()),
                },
                "tasks": {
                    "waiting": task_counts.get("WAIT", 0),
                    "running": task_counts.get("RUNNING", 0),
                    "failed": task_counts.get("FAILED", 0),
                    "slow": int(slow_tasks.scalar_one()),
                },
            }

    async def get_media_file(self, media_id: int) -> MediaFile | None:
        async with self.database.session() as session:
            return await session.get(MediaFile, media_id)

    async def get_media_file_by_source_path(self, source_path: Path) -> MediaFile | None:
        async with self.database.session() as session:
            result = await session.execute(
                select(MediaFile).where(MediaFile.source_path == str(source_path))
            )
            return result.scalars().first()

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
                row.content_type = _optional_string(
                    payload.get("contentType") or payload.get("content_type")
                )
                raw_payload = payload.get("raw_payload")
                row.raw_payload = raw_payload if isinstance(raw_payload, dict) else payload
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
            result = await session.execute(
                select(IndexerSite).order_by(IndexerSite.priority, IndexerSite.name, IndexerSite.id)
            )
            return list(result.scalars().all())

    async def create_indexer_site(
        self,
        *,
        name: str,
        base_url: str,
        cookie: str | None = None,
        user_agent: str | None = None,
        priority: int = 100,
        max_concurrency: int = 2,
        use_proxy: bool = False,
        enabled: bool = True,
    ) -> IndexerSite:
        async with self.database.session() as session:
            site = IndexerSite(
                name=name,
                base_url=base_url,
                cookie=cookie,
                user_agent=user_agent,
                priority=priority,
                max_concurrency=max_concurrency,
                use_proxy=use_proxy,
                enabled=enabled,
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
        priority: int = 100,
        max_concurrency: int = 2,
        use_proxy: bool = False,
        enabled: bool = True,
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
            site.priority = priority
            site.max_concurrency = max_concurrency
            site.use_proxy = use_proxy
            site.enabled = enabled
            await session.commit()
            await session.refresh(site)
            return site

    async def reorder_indexer_sites(self, site_ids: list[str]) -> list[IndexerSite]:
        async with self.database.session() as session:
            result = await session.execute(select(IndexerSite))
            sites_by_id = {site.id: site for site in result.scalars().all()}
            if set(site_ids) != set(sites_by_id) or len(site_ids) != len(sites_by_id):
                raise ValueError("Site order must include every configured site exactly once.")
            for priority, site_id in enumerate(site_ids, start=1):
                sites_by_id[site_id].priority = priority
            await session.commit()
            return [sites_by_id[site_id] for site_id in site_ids]

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

    async def update_artist_profile(
        self,
        artist_id: int,
        *,
        name: str,
        normalized_name: str,
        aliases: tuple[tuple[str, str], ...],
    ) -> Artist | None:
        async with self.database.session() as session:
            artist = await session.get(Artist, artist_id)
            if artist is None:
                return None
            artist.name = name
            artist.normalized_name = normalized_name
            await session.execute(delete(ArtistAlias).where(ArtistAlias.artist_id == artist_id))
            seen: set[str] = set()
            for alias, source in aliases:
                alias_name = alias.strip()
                if not alias_name or alias_name in seen:
                    continue
                session.add(ArtistAlias(artist_id=artist_id, alias=alias_name, source=source))
                seen.add(alias_name)
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


def _merge_system_settings_defaults(value: object) -> dict[str, Any]:
    settings = dict(value) if isinstance(value, dict) else {}
    return _merge_dict_defaults(settings, DEFAULT_SYSTEM_SETTINGS)


def _merge_dict_defaults(value: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = dict(value)
    for key, default_value in defaults.items():
        current = merged.get(key)
        if isinstance(default_value, dict):
            merged[key] = _merge_dict_defaults(
                current if isinstance(current, dict) else {},
                default_value,
            )
        elif key not in merged:
            merged[key] = default_value
    return merged


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


def _unique_strings(values: object) -> list[str]:
    if not isinstance(values, list | tuple | set):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _pooled_resource_slots(resource_key: str) -> tuple[str, ...]:
    parts = resource_key.split(":", 2)
    if len(parts) != 3 or parts[0] != "pool":
        return ()
    limit = _optional_int(parts[1]) or 1
    limit = min(max(limit, 1), 20)
    base_key = parts[2].strip()
    if not base_key:
        return ()
    return tuple(f"{base_key}:slot:{index}" for index in range(limit))


def _playlist_tracks_with_source_keys(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for item in tracks:
        original_title = str(item.get("original_title") or item.get("title") or "").strip()
        normalized = _normalize_playlist_source_title(original_title)
        occurrence_index = counters.get(normalized, 0) + 1
        counters[normalized] = occurrence_index
        result.append(
            {
                **item,
                "original_title": original_title,
                "source_key": _playlist_track_source_key(original_title, occurrence_index),
            }
        )
    return result


def _playlist_track_source_key(original_title: str, occurrence_index: int) -> str:
    normalized = _normalize_playlist_source_title(original_title)
    return f"title:{normalized}:{occurrence_index}"


def _normalize_playlist_source_title(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text or "untitled"


async def _get_active_resource_lease(
    session: object,
    resource_key: str,
    now: datetime,
) -> SystemTaskResourceLease | None:
    lease = await session.get(SystemTaskResourceLease, resource_key)
    if lease is not None and _as_utc(lease.lease_until) <= now:
        await session.delete(lease)
        await session.flush()
        return None
    return lease


async def _claim_task_resource_lease(
    session: object,
    *,
    resource_key: str,
    task_id: int,
    chain_id: str,
    lease_until: datetime,
    now: datetime,
) -> str | None:
    candidate_keys = _pooled_resource_slots(resource_key) or (resource_key,)
    for candidate_key in candidate_keys:
        lease = await _get_active_resource_lease(session, candidate_key, now)
        if lease is not None:
            continue
        session.add(
            SystemTaskResourceLease(
                resource_key=candidate_key,
                holder_kind="task",
                holder_id=str(task_id),
                task_id=task_id,
                chain_id=chain_id,
                lease_until=lease_until,
            )
        )
        return candidate_key
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _system_task_chain_has_active_tasks(
    session: object,
    chain_id: str,
    excluding_task_id: int,
) -> bool:
    result = await session.execute(
        select(func.count())
        .select_from(SystemTask)
        .where(
            SystemTask.chain_id == chain_id,
            SystemTask.id != excluding_task_id,
            SystemTask.status.in_(("WAIT", "RUNNING")),
        )
    )
    return int(result.scalar_one()) > 0


async def _clear_other_defaults(session: object, model: type[object], active_id: str) -> None:
    result = await session.execute(select(model).where(model.id != active_id))
    for row in result.scalars().all():
        row.is_default = False
