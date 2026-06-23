from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import unicodedata
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from secrets import compare_digest
from typing import Any
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from opencc import OpenCC
from sqlalchemy.exc import IntegrityError

from musicpilot.adapters.bots import TelegramBotAdapter, TelegramHttpNotifier
from musicpilot.adapters.downloaders import QBittorrentClient
from musicpilot.adapters.indexers import build_nexusphp_indexers, load_parser_catalog
from musicpilot.adapters.indexers.nexusphp import (
    NexusPHPCrawler,
    NexusPHPParserConfig,
    NexusPHPSiteConfig,
)
from musicpilot.adapters.metadata import (
    MultiSourceMusicProvider,
    MusicBrainzProvider,
    MutagenTagWriter,
    NetEaseMusicProvider,
)
from musicpilot.core.event_bus import EventBus
from musicpilot.core.events import NotifyEvent, SearchEvent, SearchResult
from musicpilot.core.metadata import MetadataCascade
from musicpilot.core.pipeline import MusicPipeline
from musicpilot.core.processor import MediaProcessor
from musicpilot.core.scraping import (
    LibraryTrackSnapshot,
    LocalMusicScraper,
    ScrapingConfig,
    ScrapingFileResult,
    ScrapingSummary,
    scraping_config_from_payload,
)
from musicpilot.infra.api.schemas import (
    DownloadDeleteMode,
    DownloaderCreateRequest,
    DownloaderResponse,
    DownloadRequest,
    DownloadResponse,
    DownloadTaskResponse,
    FileBulkDeleteFailure,
    FileBulkDeleteRequest,
    FileBulkDeleteResponse,
    FileEntryResponse,
    FileListResponse,
    FileOrganizeRequest,
    FileOrganizeResponse,
    HealthResponse,
    IndexerResponse,
    LogEntryResponse,
    LoginRequest,
    LoginResponse,
    MediaBulkDeleteFailure,
    MediaBulkDeleteRequest,
    MediaBulkDeleteResponse,
    MediaCandidateResponse,
    MediaDeleteMode,
    MediaFileResponse,
    MediaServerCreateRequest,
    MediaServerResponse,
    MetadataSearchResponse,
    MetadataSiteSearchRequest,
    MetadataSiteSearchResponse,
    MusicLibraryTrackResponse,
    NexusPHPParserRequest,
    NotifierCreateRequest,
    NotifierResponse,
    ParserFieldRequest,
    QBittorrentWebhookRequest,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
    SiteCreateRequest,
    SiteResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SystemSettingsRequest,
    SystemSettingsResponse,
    TestResponse,
)
from musicpilot.infra.auth import issue_session, require_session
from musicpilot.infra.config import Settings
from musicpilot.infra.db import Database, SqlAlchemyMediaRepository
from musicpilot.infra.db.models import (
    DownloaderConfig,
    IndexerSite,
    MediaFile,
    MediaServerConfig,
    MusicLibraryTrack,
    NotifierChannel,
    TorrentRecord,
)
from musicpilot.infra.scheduler import SubscriptionScheduler
from musicpilot.ports.downloader import DownloadStatus, TorrentFile
from musicpilot.ports.metadata import MediaCandidate

_OPENCC_T2S = OpenCC("t2s")
DOWNLOAD_POLL_INTERVAL_SECONDS = 5
MUSIC_LIBRARY_SYNC_INTERVAL_SECONDS = 3600
MUSIC_LIBRARY_SYNC_AFTER_REFRESH_DELAY_SECONDS = 5


class MetadataSiteSearchTask:
    def __init__(
        self,
        *,
        media: MediaCandidateResponse,
        keywords: list[str],
        total_sites: int,
    ) -> None:
        self.media = media
        self.keywords = keywords
        self.total_sites = total_sites
        self.completed_sites = 0
        self.raw_count = 0
        self.filtered_count = 0
        self.done = False
        self.errors: list[dict[str, str]] = []
        self.results: list[dict[str, Any]] = []
        self._active_keywords: dict[str, int] = {}
        self._subscribers: set[asyncio.Queue[tuple[str, dict[str, Any]]]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    def snapshot(self) -> dict[str, Any]:
        return {
            "media": self.media.model_dump(),
            "keywords": self.keywords,
            "total_sites": self.total_sites,
            "completed_sites": self.completed_sites,
            "active_keywords": sorted(self._active_keywords),
            "raw_count": self.raw_count,
            "filtered_count": self.filtered_count,
            "done": self.done,
            "errors": self.errors,
            "results": self.results,
        }

    async def keyword_started(self, keyword: str) -> None:
        async with self._lock:
            self._active_keywords[keyword] = self._active_keywords.get(keyword, 0) + 1
        await self.publish("progress", self.snapshot())

    async def keyword_finished(self, keyword: str) -> None:
        async with self._lock:
            count = self._active_keywords.get(keyword, 0)
            if count <= 1:
                self._active_keywords.pop(keyword, None)
            else:
                self._active_keywords[keyword] = count - 1
        await self.publish("progress", self.snapshot())

    async def site_done(
        self,
        *,
        site: str,
        raw_count: int,
        filtered_count: int,
        results: list[SearchResultResponse],
        errors: list[str],
    ) -> None:
        async with self._lock:
            self.completed_sites += 1
            self.raw_count += raw_count
            self.filtered_count += filtered_count
            site_payload = {
                "site": site,
                "raw_count": raw_count,
                "filtered_count": filtered_count,
                "results": [item.model_dump() for item in results],
                "errors": errors,
            }
            self.results.extend(site_payload["results"])
        await self.publish("site_done", site_payload)
        await self.publish("progress", self.snapshot())

    async def site_error(self, *, site: str, message: str) -> None:
        async with self._lock:
            self.completed_sites += 1
            self.errors.append({"site": site, "message": message})
        await self.publish("site_error", {"site": site, "message": message})
        await self.publish("progress", self.snapshot())

    async def finish(self) -> None:
        async with self._lock:
            self.done = True
        await self.publish("done", self.snapshot())

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            queue.put_nowait((event, payload))


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logs: deque[dict[str, str]] = deque(maxlen=500)
        self.log_handler = AppLogHandler(self.logs)
        self.event_bus = EventBus()
        self.database = Database(settings.database_url)
        self.parser_catalog = load_parser_catalog(settings.indexer_parser_config)
        self.indexers = ()
        self.repository = SqlAlchemyMediaRepository(self.database)
        self.scheduler = SubscriptionScheduler(
            repository=self.repository,
            interval_minutes=settings.subscription_check_interval_minutes,
            enabled=settings.subscriptions_enabled,
        )
        self.downloader: QBittorrentClient | None = None
        self.metadata = MetadataCascade(
            [
                MultiSourceMusicProvider(),
                NetEaseMusicProvider(),
                MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent),
            ]
        )
        self.scraping_metadata = MetadataCascade([MultiSourceMusicProvider()])
        self.scraper = LocalMusicScraper(
            metadata=self.scraping_metadata,
            tag_writer=MutagenTagWriter(),
        )
        self.configured_notifiers: tuple[TelegramHttpNotifier, ...] = ()
        self.bots = self._build_bots(settings)
        self.notification_sinks = (*self.configured_notifiers, *self.bots)
        self.media_processor = MediaProcessor(
            library_root=settings.music_library_path,
            metadata=self.metadata,
            downloader=self.downloader,
            repository=self.repository,
            tag_writer=MutagenTagWriter() if settings.write_audio_tags else None,
        )
        self.pipeline = MusicPipeline(
            event_bus=self.event_bus,
            indexers=self.indexers,
            downloader=self.downloader,
            media_processor=None,
            notifiers=self.notification_sinks,
        )
        self.download_polling_task: asyncio.Task[None] | None = None
        self.music_library_sync_task: asyncio.Task[None] | None = None
        self.metadata_site_search_task: MetadataSiteSearchTask | None = None
        self.metadata_site_search_worker: asyncio.Task[None] | None = None

    async def reload_indexers(self) -> None:
        self.reload_parser_catalog()
        sites = [_site_payload(site) for site in await self.repository.list_indexer_sites()]
        self.indexers = build_nexusphp_indexers(sites, self.parser_catalog)
        self.pipeline.indexers = self.indexers

    async def migrate_legacy_runtime_config(self) -> None:
        path = self.settings.runtime_config
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.add_log("settings", f"Legacy runtime config migration skipped: {exc}", "WARNING")
            return
        if not isinstance(payload, dict):
            return

        if not await self.repository.list_downloaders():
            for item in payload.get("downloaders", []):
                if isinstance(item, dict):
                    await self.repository.upsert_downloader(
                        payload=_legacy_downloader_payload(item),
                    )

        if not await self.repository.list_notifiers():
            for item in payload.get("notifiers", []):
                if isinstance(item, dict):
                    await self.repository.upsert_notifier(payload=_legacy_notifier_payload(item))

    def reload_parser_catalog(self) -> None:
        self.parser_catalog = load_parser_catalog(self.settings.indexer_parser_config)

    async def reload_downloader(self) -> None:
        if self.downloader is not None:
            await self.downloader.close()
        self.downloader = await self._build_downloader()
        self.pipeline.downloader = self.downloader
        self.media_processor.downloader = self.downloader

    async def reload_notifiers(self) -> None:
        self.configured_notifiers = await self._build_configured_notifiers()
        self.notification_sinks = (*self.configured_notifiers, *self.bots)
        self.pipeline.notifiers = self.notification_sinks

    async def _build_downloader(self) -> QBittorrentClient | None:
        configured = await self.repository.default_downloader()
        if configured is not None:
            return QBittorrentClient(
                configured.base_url,
                username=configured.username,
                password=configured.password,
                download_path=configured.download_path,
            )
        if not (
            self.settings.qbittorrent_base_url
            and self.settings.qbittorrent_username
            and self.settings.qbittorrent_password
        ):
            return None
        return QBittorrentClient(
            self.settings.qbittorrent_base_url,
            username=self.settings.qbittorrent_username,
            password=self.settings.qbittorrent_password,
            download_path=str(self.settings.download_staging_path),
        )

    def _build_bots(self, settings: Settings) -> tuple[TelegramBotAdapter, ...]:
        if not settings.telegram_bot_token:
            return ()
        chat_ids = tuple(
            int(item.strip())
            for item in settings.telegram_chat_ids.split(",")
            if item.strip()
        )
        return (
            TelegramBotAdapter(
                token=settings.telegram_bot_token,
                event_bus=self.event_bus,
                chat_ids=chat_ids,
            ),
        )

    async def _build_configured_notifiers(self) -> tuple[TelegramHttpNotifier, ...]:
        system_settings = await self.repository.get_system_settings()
        notifiers: list[TelegramHttpNotifier] = []
        for item in await self.repository.list_notifiers():
            if not item.enabled or item.type != "telegram":
                continue
            token = item.bot_token.strip()
            if not token:
                continue
            chat_ids = tuple(
                int(chat_id.strip())
                for chat_id in item.chat_ids.split(",")
                if chat_id.strip().isdigit()
            )
            notifiers.append(
                TelegramHttpNotifier(
                    token=token,
                    chat_ids=chat_ids,
                    proxy=_proxy_url(system_settings) if item.use_proxy else None,
                )
            )
        return tuple(notifiers)

    def start_download_polling(self) -> None:
        if self.download_polling_task is not None and not self.download_polling_task.done():
            return
        self.download_polling_task = asyncio.create_task(
            _poll_download_tasks(self),
            name="musicpilot-download-polling",
        )

    async def stop_download_polling(self) -> None:
        if self.download_polling_task is None:
            return
        self.download_polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.download_polling_task

    def start_music_library_sync(self) -> None:
        if self.music_library_sync_task is not None and not self.music_library_sync_task.done():
            return
        self.music_library_sync_task = asyncio.create_task(
            _sync_music_library_periodically(self),
            name="musicpilot-music-library-sync",
        )

    async def stop_music_library_sync(self) -> None:
        if self.music_library_sync_task is None:
            return
        self.music_library_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.music_library_sync_task

    def add_log(self, category: str, message: str, level: str = "INFO") -> None:
        self.logs.appendleft(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "message": message,
                "category": category,
            }
        )


class AppLogHandler(logging.Handler):
    def __init__(self, entries: deque[dict[str, str]]) -> None:
        super().__init__(level=logging.INFO)
        self.entries = entries

    def emit(self, record: logging.LogRecord) -> None:
        if _skip_app_log_record(record):
            return
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            message = str(record.msg)
        self.entries.appendleft(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "message": message,
                "category": _category_from_logger(record.name),
            }
        )


def create_app() -> FastAPI:
    settings = Settings()
    state = AppState(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.musicpilot = state
        root_logger = logging.getLogger()
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)
        root_logger.addHandler(state.log_handler)
        state.add_log("system", "MusicPilot started")
        await state.database.create_all()
        await state.database.migrate_phase_one_schema()
        await state.migrate_legacy_runtime_config()
        await state.reload_indexers()
        await state.reload_downloader()
        await state.reload_notifiers()
        state.pipeline.start()
        state.start_download_polling()
        state.start_music_library_sync()
        state.scheduler.start()
        for bot in state.bots:
            await bot.start()
        yield
        state.add_log("system", "MusicPilot stopping")
        root_logger.removeHandler(state.log_handler)
        await state.stop_download_polling()
        await state.stop_music_library_sync()
        if state.metadata_site_search_worker is not None:
            state.metadata_site_search_worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.metadata_site_search_worker
        for bot in state.bots:
            await bot.stop()
        state.scheduler.stop()
        await state.pipeline.stop()
        if state.downloader is not None:
            await state.downloader.close()
        for provider in (*state.metadata.providers, *state.scraping_metadata.providers):
            close = getattr(provider, "close", None)
            if close is not None:
                await close()
        await state.database.dispose()

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        dependencies=[Depends(require_session)],
    )

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(app=settings.app_name)

    @app.post("/api/auth/login", response_model=LoginResponse)
    async def login(payload: LoginRequest, response: Response) -> LoginResponse:
        if not (
            compare_digest(payload.username, settings.admin_username)
            and compare_digest(payload.password, settings.admin_password)
        ):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        issue_session(response, username=payload.username, secret=settings.session_secret)
        return LoginResponse(status="ok", username=payload.username)

    @app.post("/api/search", response_model=SearchResponse)
    async def search(payload: SearchRequest) -> SearchResponse:
        state.add_log("search", f"Search started: {payload.query}")
        results = await state.pipeline.search(SearchEvent(payload.query, limit=payload.limit))
        state.add_log("search", f"Search completed: {payload.query}, {len(results)} result(s)")
        return SearchResponse(
            query=payload.query,
            results=[
                SearchResultResponse(
                    title=result.title,
                    download_url=result.download_url,
                    source=result.source,
                    seeders=result.seeders,
                    leechers=result.leechers,
                    size_bytes=result.size_bytes,
                    details_url=result.details_url,
                    subtitle=result.subtitle,
                    published_at=result.published_at,
                    promotion=result.promotion,
                )
                for result in results
            ],
        )

    @app.get("/api/metadata/search", response_model=MetadataSearchResponse)
    async def metadata_search(query: str, limit: int = 10) -> MetadataSearchResponse:
        candidates: list[MediaCandidate] = []
        for provider in state.metadata.providers:
            search = getattr(provider, "search", None)
            if search is None:
                continue
            try:
                provider_candidates = await search(query, limit=min(max(limit * 5, limit), 50))
            except Exception as exc:  # noqa: BLE001
                state.add_log("metadata", f"Metadata provider failed: {exc}", "WARNING")
                continue
            candidates.extend(provider_candidates)
            if len(candidates) >= limit:
                break
        aggregated = _aggregate_media_candidates(candidates, limit=limit)
        state.add_log(
            "metadata",
            f"Metadata search completed: {query}, {len(aggregated)} candidate group(s)",
        )
        return MetadataSearchResponse(query=query, candidates=aggregated)

    @app.post("/api/search/by-metadata", response_model=MetadataSiteSearchResponse)
    async def search_by_metadata(
        payload: MetadataSiteSearchRequest,
    ) -> MetadataSiteSearchResponse:
        selected_ids = set(payload.site_ids)
        indexers = [
            indexer
            for indexer in state.indexers
            if not selected_ids or str(getattr(indexer.config, "site_id", "")) in selected_ids
        ]
        keywords = _metadata_search_keywords(payload.media)
        raw_results: list[SearchResult] = []
        for keyword in keywords:
            groups = await asyncio.gather(
                *(_search_indexer(indexer, keyword, payload.limit) for indexer in indexers),
                return_exceptions=True,
            )
            for group in groups:
                if isinstance(group, Exception):
                    state.add_log("search", f"Metadata site search failed: {group}", "ERROR")
                    continue
                raw_results.extend(group[1])
        merged = _dedupe_results(raw_results)
        filtered = _filter_by_artist(merged, payload.media.artist)
        ranked = sorted(filtered, key=lambda item: item.seeders, reverse=True)[: payload.limit]
        state.add_log(
            "search",
            f"Metadata site search completed: raw={len(merged)}, filtered={len(filtered)}",
        )
        return MetadataSiteSearchResponse(
            raw_count=len(merged),
            filtered_count=len(filtered),
            results=[_search_result_response(item) for item in ranked],
        )

    @app.post("/api/search/by-metadata/stream/start")
    async def start_metadata_site_search_stream(
        payload: MetadataSiteSearchRequest,
    ) -> dict[str, Any]:
        current = state.metadata_site_search_task
        worker = state.metadata_site_search_worker
        if current is not None and not current.done and worker is not None and not worker.done():
            raise HTTPException(status_code=409, detail="已有种子搜索任务正在执行。")

        selected_ids = set(payload.site_ids)
        indexers = [
            indexer
            for indexer in state.indexers
            if not selected_ids or str(getattr(indexer.config, "site_id", "")) in selected_ids
        ]
        keywords = _metadata_search_keywords(payload.media)
        task = MetadataSiteSearchTask(
            media=payload.media,
            keywords=keywords,
            total_sites=len(indexers),
        )
        state.metadata_site_search_task = task
        state.metadata_site_search_worker = asyncio.create_task(
            _run_metadata_site_search_stream(state, task, indexers, payload.limit),
            name="musicpilot-metadata-site-search",
        )
        state.add_log(
            "search",
            f"Streaming metadata site search started: sites={len(indexers)}, "
            f"keywords={len(keywords)}",
        )
        return task.snapshot()

    @app.get("/api/search/by-metadata/stream/current")
    async def current_metadata_site_search_stream() -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            task = state.metadata_site_search_task
            if task is None:
                yield _sse("snapshot", {"done": True, "results": []})
                yield _sse("done", {"done": True, "results": []})
                return

            yield _sse("snapshot", task.snapshot())
            if task.done:
                yield _sse("done", task.snapshot())
                return

            queue = await task.subscribe()
            try:
                while True:
                    event, payload = await queue.get()
                    yield _sse(event, payload)
                    if event == "done":
                        break
            finally:
                await task.unsubscribe(queue)

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/search/stream")
    async def search_stream(query: str, limit: int = 20) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            if not state.indexers:
                state.add_log(
                    "search",
                    f"Search skipped: no indexer configured for {query}",
                    "WARNING",
                )
                yield _sse("done", {"count": 0})
                return

            state.add_log("search", f"Search started: {query}")
            tasks = [
                asyncio.create_task(_search_indexer(indexer, query, limit))
                for indexer in state.indexers
            ]
            count = 0
            for task in asyncio.as_completed(tasks):
                try:
                    _source, results = await task
                except Exception as exc:  # noqa: BLE001
                    state.add_log("search", f"Indexer failed: {exc}", "ERROR")
                    yield _sse("error", {"source": "unknown", "message": str(exc)})
                    continue
                for result in results:
                    count += 1
                    yield _sse(
                        "result",
                        {
                            "title": result.title,
                            "download_url": result.download_url,
                            "source": result.source,
                            "seeders": result.seeders,
                            "leechers": result.leechers,
                            "size_bytes": result.size_bytes,
                            "details_url": result.details_url,
                            "subtitle": result.subtitle,
                            "published_at": result.published_at,
                            "promotion": result.promotion,
                        },
                    )
            state.add_log("search", f"Search completed: {query}, {count} result(s)")
            yield _sse("done", {"count": count})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/downloads", response_model=DownloadResponse, status_code=202)
    async def add_download(payload: DownloadRequest) -> DownloadResponse:
        if state.downloader is None:
            await state.reload_downloader()
        if state.downloader is None:
            state.add_log(
                "download",
                f"Download rejected: no downloader for {payload.title}",
                "ERROR",
            )
            raise HTTPException(status_code=503, detail="No downloader is configured.")
        resource = (payload.resource or SearchResultResponse(**payload.model_dump())).model_dump()
        media_metadata = payload.media_metadata.model_dump() if payload.media_metadata else {}
        task = await state.repository.create_download_task(
            resource=resource,
            media_metadata=media_metadata,
            selected_site_ids=payload.selected_site_ids,
            category=payload.category,
        )
        try:
            torrent_hash = await _submit_torrent_to_downloader(
                state,
                resource,
                payload.selected_site_ids,
                payload.category,
            )
        except Exception as exc:  # noqa: BLE001
            await state.repository.update_download_task(
                task.id,
                status="failed",
                last_error=str(exc),
            )
            raise HTTPException(status_code=502, detail=f"Downloader submit failed: {exc}") from exc
        default_downloader = await state.repository.default_downloader()
        task_changes: dict[str, object] = {
            "status": "submitted",
            "downloader_id": default_downloader.id if default_downloader else None,
            "submitted_at": datetime.now(UTC),
        }
        if torrent_hash:
            task_changes["torrent_hash"] = torrent_hash
        task = await state.repository.update_download_task(task.id, **task_changes)
        await _send_event_notifications(state, "download", task)
        state.add_log("download", f"Download submitted: {payload.title}")
        return DownloadResponse(
            status="submitted",
            task_id=task.id if task else None,
            torrent_hash=torrent_hash or None,
        )

    @app.get("/api/downloads", response_model=list[DownloadTaskResponse])
    async def downloads() -> list[DownloadTaskResponse]:
        tasks = await state.repository.list_download_tasks()
        return [_download_task_response(item) for item in tasks]

    @app.delete("/api/downloads/{task_id}", status_code=204)
    async def delete_download(task_id: int, mode: DownloadDeleteMode = "record_only") -> None:
        task = await state.repository.get_download_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Download task not found.")
        if mode == "all":
            try:
                await _delete_task_torrent(state, task, delete_files=True)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502,
                    detail=f"Download task external delete failed: {exc}",
                ) from exc
        deleted = await state.repository.delete_download_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Download task not found.")

    @app.get("/api/indexers", response_model=list[IndexerResponse])
    async def indexers() -> list[IndexerResponse]:
        return [IndexerResponse(name=indexer.name) for indexer in state.indexers]

    @app.get("/api/sites", response_model=list[SiteResponse])
    async def sites() -> list[SiteResponse]:
        return [
            _site_response(site, _supported_parser_or_422(state, site.base_url))
            for site in await state.repository.list_indexer_sites()
        ]

    @app.post("/api/sites/test", response_model=TestResponse)
    async def test_site(payload: SiteCreateRequest) -> TestResponse:
        parser = _supported_parser_or_422(state, payload.base_url)
        crawler = NexusPHPCrawler(
            NexusPHPSiteConfig(
                name=payload.name,
                base_url=payload.base_url,
                cookie=payload.cookie,
                user_agent=payload.user_agent,
                parser=parser,
                max_concurrency=payload.max_concurrency,
            )
        )
        result = await crawler.test_auth()
        return TestResponse(ok=result.ok, message=result.message)

    @app.post("/api/sites", response_model=SiteResponse, status_code=201)
    async def create_site(payload: SiteCreateRequest) -> SiteResponse:
        parser = _supported_parser_or_422(state, payload.base_url)
        try:
            site = await state.repository.create_indexer_site(**payload.model_dump())
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Site already exists.") from exc
        await state.reload_indexers()
        return _site_response(site, parser)

    @app.put("/api/sites/{site_id}", response_model=SiteResponse)
    async def update_site(site_id: str, payload: SiteCreateRequest) -> SiteResponse:
        parser = _supported_parser_or_422(state, payload.base_url)
        try:
            site = await state.repository.update_indexer_site(site_id, **payload.model_dump())
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Site already exists.") from exc
        if site is None:
            raise HTTPException(status_code=404, detail="Site not found.")
        await state.reload_indexers()
        return _site_response(site, parser)

    @app.delete("/api/sites/{site_id}", status_code=204)
    async def delete_site(site_id: str) -> None:
        deleted = await state.repository.delete_indexer_site(site_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Site not found.")
        await state.reload_indexers()

    @app.get("/api/settings/downloaders", response_model=list[DownloaderResponse])
    async def downloaders() -> list[DownloaderResponse]:
        return [_downloader_response(item) for item in await state.repository.list_downloaders()]

    @app.post("/api/settings/downloaders", response_model=DownloaderResponse, status_code=201)
    async def create_downloader(payload: DownloaderCreateRequest) -> DownloaderResponse:
        if not payload.password:
            raise HTTPException(status_code=422, detail="Password is required.")
        downloader = await state.repository.upsert_downloader(payload=payload.model_dump())
        await state.reload_downloader()
        return _downloader_response(downloader)

    @app.put("/api/settings/downloaders/{downloader_id}", response_model=DownloaderResponse)
    async def update_downloader(
        downloader_id: str,
        payload: DownloaderCreateRequest,
    ) -> DownloaderResponse:
        if await state.repository.get_downloader(downloader_id) is None:
            raise HTTPException(status_code=404, detail="Downloader not found.")
        downloader = await state.repository.upsert_downloader(
            downloader_id=downloader_id,
            payload=payload.model_dump(),
        )
        await state.reload_downloader()
        return _downloader_response(downloader)

    @app.delete("/api/settings/downloaders/{downloader_id}", status_code=204)
    async def delete_downloader(downloader_id: str) -> None:
        deleted = await state.repository.delete_downloader(downloader_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Downloader not found.")
        await state.reload_downloader()

    @app.post("/api/settings/downloaders/test", response_model=TestResponse)
    async def test_downloader(payload: DownloaderCreateRequest) -> TestResponse:
        password = payload.password
        if not password and payload.id:
            existing = await state.repository.get_downloader(payload.id)
            password = existing.password if existing else ""
        if not password:
            return TestResponse(ok=False, message="下载器密码不能为空。")
        client = QBittorrentClient(
            payload.base_url,
            username=payload.username,
            password=password,
            download_path=payload.download_path,
        )
        try:
            await client.test_connection()
        except Exception as exc:  # noqa: BLE001
            return TestResponse(ok=False, message=f"下载器连接失败：{exc}")
        finally:
            await client.close()
        return TestResponse(ok=True, message="qBittorrent 登录成功")

    @app.get("/api/settings/system", response_model=SystemSettingsResponse)
    async def system_settings() -> SystemSettingsResponse:
        return SystemSettingsResponse(**await state.repository.get_system_settings())

    @app.put("/api/settings/system", response_model=SystemSettingsResponse)
    async def update_system_settings(
        payload: SystemSettingsRequest,
    ) -> SystemSettingsResponse:
        return await _save_system_settings(payload)

    @app.post("/api/settings/system", response_model=SystemSettingsResponse)
    async def save_system_settings(
        payload: SystemSettingsRequest,
    ) -> SystemSettingsResponse:
        return await _save_system_settings(payload)

    async def _save_system_settings(
        payload: SystemSettingsRequest,
    ) -> SystemSettingsResponse:
        settings_payload = await state.repository.update_system_settings(payload.model_dump())
        await state.reload_notifiers()
        state.add_log("settings", "System settings saved")
        return SystemSettingsResponse(**settings_payload)

    @app.get("/api/settings/media-servers", response_model=list[MediaServerResponse])
    async def media_servers() -> list[MediaServerResponse]:
        return [
            _media_server_response(item)
            for item in await state.repository.list_media_servers()
        ]

    @app.post("/api/settings/media-servers", response_model=MediaServerResponse, status_code=201)
    async def create_media_server(payload: MediaServerCreateRequest) -> MediaServerResponse:
        server = await state.repository.upsert_media_server(payload=payload.model_dump())
        return _media_server_response(server)

    @app.put("/api/settings/media-servers/{server_id}", response_model=MediaServerResponse)
    async def update_media_server(
        server_id: str,
        payload: MediaServerCreateRequest,
    ) -> MediaServerResponse:
        server = await state.repository.upsert_media_server(
            server_id=server_id,
            payload=payload.model_dump(),
        )
        return _media_server_response(server)

    @app.delete("/api/settings/media-servers/{server_id}", status_code=204)
    async def delete_media_server(server_id: str) -> None:
        deleted = await state.repository.delete_media_server(server_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Media server not found.")

    @app.post("/api/settings/media-servers/test", response_model=TestResponse)
    async def test_media_server(payload: MediaServerCreateRequest) -> TestResponse:
        try:
            async with httpx.AsyncClient(
                base_url=payload.base_url.rstrip("/"),
                timeout=20,
            ) as client:
                response = await client.get("/rest/ping.view", params=_navidrome_params(payload))
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return TestResponse(ok=False, message=f"Navidrome 连接失败：{exc}")
        return TestResponse(ok=True, message="Navidrome 连接成功")

    @app.get("/api/settings/notifiers", response_model=list[NotifierResponse])
    async def notifiers() -> list[NotifierResponse]:
        return [_notifier_response(item) for item in await state.repository.list_notifiers()]

    @app.post("/api/settings/notifiers", response_model=NotifierResponse, status_code=201)
    async def create_notifier(payload: NotifierCreateRequest) -> NotifierResponse:
        if not payload.bot_token:
            raise HTTPException(status_code=422, detail="Bot token is required.")
        notifier = await state.repository.upsert_notifier(payload=payload.model_dump())
        await state.reload_notifiers()
        return _notifier_response(notifier)

    @app.put("/api/settings/notifiers/{notifier_id}", response_model=NotifierResponse)
    async def update_notifier(
        notifier_id: str,
        payload: NotifierCreateRequest,
    ) -> NotifierResponse:
        if await state.repository.get_notifier(notifier_id) is None:
            raise HTTPException(status_code=404, detail="Notifier not found.")
        notifier = await state.repository.upsert_notifier(
            notifier_id=notifier_id,
            payload=payload.model_dump(),
        )
        await state.reload_notifiers()
        return _notifier_response(notifier)

    @app.delete("/api/settings/notifiers/{notifier_id}", status_code=204)
    async def delete_notifier(notifier_id: str) -> None:
        deleted = await state.repository.delete_notifier(notifier_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Notifier not found.")
        await state.reload_notifiers()

    @app.post("/api/settings/notifiers/test", response_model=TestResponse)
    async def test_notifier(payload: NotifierCreateRequest) -> TestResponse:
        bot_token = payload.bot_token
        if not bot_token and payload.id:
            existing = await state.repository.get_notifier(payload.id)
            bot_token = existing.bot_token if existing else ""
        if not bot_token:
            return TestResponse(ok=False, message="Telegram Bot Token 不能为空。")
        proxy = (
            _proxy_url(await state.repository.get_system_settings())
            if payload.use_proxy
            else None
        )
        if payload.use_proxy and proxy is None:
            return TestResponse(ok=False, message="已开启代理，但系统代理地址未配置。")
        state.add_log(
            "notify",
            f"Telegram notifier test started: {payload.name}, proxy={'on' if proxy else 'off'}",
        )
        try:
            async with httpx.AsyncClient(timeout=20, proxy=proxy) as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getMe"
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            message = f"Telegram Bot 测试超时：{exc or '请求超过 20 秒未返回'}"
            state.add_log("notify", message, "ERROR")
            return TestResponse(ok=False, message=message)
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            message = f"Telegram Bot 测试失败：HTTP {exc.response.status_code} {body}"
            state.add_log("notify", message, "ERROR")
            return TestResponse(ok=False, message=message)
        except httpx.RequestError as exc:
            message = f"Telegram Bot 连接失败：{exc.__class__.__name__}: {exc}"
            state.add_log("notify", message, "ERROR")
            return TestResponse(ok=False, message=message)
        except Exception as exc:  # noqa: BLE001
            message = f"Telegram Bot 测试失败：{exc.__class__.__name__}: {exc}"
            state.add_log("notify", message, "ERROR")
            return TestResponse(ok=False, message=message)

        if not data.get("ok"):
            message = str(data.get("description", "Bot 不可用"))
            state.add_log("notify", f"Telegram notifier test failed: {message}", "ERROR")
            return TestResponse(ok=False, message=message)
        username = data.get("result", {}).get("username", "")
        state.add_log("notify", f"Telegram notifier test succeeded: {username}")
        return TestResponse(ok=True, message=f"Telegram Bot 可用：{username}")

    @app.get("/api/logs", response_model=list[LogEntryResponse])
    async def logs(limit: int = 200) -> list[LogEntryResponse]:
        limited = max(1, min(limit, 500))
        return [LogEntryResponse(**entry) for entry in list(state.logs)[:limited]]

    @app.get("/api/files", response_model=FileListResponse)
    async def source_files(path: str = "", query: str = "", limit: int = 500) -> FileListResponse:
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        root = _scraping_source_root_or_409(config)
        target = _resolve_source_relative_path(root, path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="文件或目录不存在。")
        if not target.is_dir():
            raise HTTPException(status_code=422, detail="只能浏览目录。")
        search_query = query.strip()
        limited = max(1, min(limit, 500))
        entries = await asyncio.to_thread(
            _source_search_entries if search_query else _source_directory_entries,
            root,
            target,
            search_query,
            limited,
        )
        return FileListResponse(
            root=str(root),
            path=_source_relative_path(root, target),
            parent=_source_parent_path(root, target),
            entries=entries,
        )

    @app.delete("/api/files", response_model=FileBulkDeleteResponse)
    async def delete_source_files(payload: FileBulkDeleteRequest) -> FileBulkDeleteResponse:
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        root = _scraping_source_root_or_409(config)
        deleted_paths: list[str] = []
        not_found_paths: list[str] = []
        failures: list[FileBulkDeleteFailure] = []
        seen: set[str] = set()
        for item_path in payload.paths:
            if item_path in seen:
                continue
            seen.add(item_path)
            try:
                target = _resolve_source_delete_path(root, item_path)
                if not _path_lexists(target):
                    not_found_paths.append(item_path)
                    continue
                await asyncio.to_thread(_delete_source_path_sync, target)
            except Exception as exc:  # noqa: BLE001
                failures.append(FileBulkDeleteFailure(path=item_path, message=str(exc)))
                continue
            deleted_paths.append(item_path)
        return FileBulkDeleteResponse(
            deleted_paths=deleted_paths,
            not_found_paths=not_found_paths,
            failures=failures,
        )

    @app.post("/api/files/organize", response_model=FileOrganizeResponse, status_code=202)
    async def organize_source_file(payload: FileOrganizeRequest) -> FileOrganizeResponse:
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        if not config.enabled:
            raise HTTPException(status_code=409, detail="请先在刮削设置中开启刮削。")
        root = _scraping_source_root_or_409(config)
        target = _resolve_source_relative_path(root, payload.path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="文件或目录不存在。")
        source_files = await asyncio.to_thread(_source_audio_files, root, target)
        if not source_files:
            raise HTTPException(status_code=422, detail="目标中没有可整理的音频文件。")
        try:
            summary = await _scrape_manual_source_files(state, config, target, source_files)
        except Exception as exc:  # noqa: BLE001
            state.add_log("metadata", f"Manual scraping failed for {target}: {exc}", "ERROR")
            raise HTTPException(status_code=502, detail=f"整理失败：{exc}") from exc
        return FileOrganizeResponse(
            source_files=summary.source_files,
            mapped_files=summary.mapped_files,
            updated_files=summary.updated_files,
            moved_files=summary.moved_files,
            failed_files=summary.failed_files,
            skipped_files=sum(1 for item in summary.results if item.status == "skipped"),
        )

    @app.get("/api/media", response_model=list[MediaFileResponse])
    async def media_files() -> list[MediaFileResponse]:
        rows = await state.repository.list_media_files()
        return [
            MediaFileResponse(
                id=row.id,
                torrent_hash=row.torrent_hash,
                source_path=row.source_path,
                library_path=row.library_path,
                status=row.status,
                operation_time=row.updated_at,
                remark=row.error_message,
                error_message=row.error_message,
                title=row.title,
                artist=row.artist,
                album=row.album,
                year=row.year,
                track_number=row.track_number,
            )
            for row in rows
        ]

    @app.delete("/api/media", response_model=MediaBulkDeleteResponse)
    async def delete_media_files(payload: MediaBulkDeleteRequest) -> MediaBulkDeleteResponse:
        deleted_ids: list[int] = []
        not_found_ids: list[int] = []
        failures: list[MediaBulkDeleteFailure] = []
        seen: set[int] = set()
        for media_id in payload.ids:
            if media_id in seen:
                continue
            seen.add(media_id)
            media = await state.repository.get_media_file(media_id)
            if media is None:
                not_found_ids.append(media_id)
                continue
            try:
                deleted = await _delete_media_record(state, media, payload.mode)
            except Exception as exc:  # noqa: BLE001
                failures.append(MediaBulkDeleteFailure(id=media_id, message=str(exc)))
                continue
            if deleted:
                deleted_ids.append(media_id)
            else:
                not_found_ids.append(media_id)
        return MediaBulkDeleteResponse(
            deleted_ids=deleted_ids,
            not_found_ids=not_found_ids,
            failures=failures,
        )

    @app.delete("/api/media/{media_id}", status_code=204)
    async def delete_media_file(media_id: int, mode: MediaDeleteMode = "record_only") -> None:
        media = await state.repository.get_media_file(media_id)
        if media is None:
            raise HTTPException(status_code=404, detail="Media record not found.")
        try:
            deleted = await _delete_media_record(state, media, mode)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"Media file delete failed: {exc}",
            ) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Media record not found.")

    @app.get("/api/music-library", response_model=list[MusicLibraryTrackResponse])
    async def music_library() -> list[MusicLibraryTrackResponse]:
        return [
            _music_library_track_response(item)
            for item in await state.repository.list_music_library_tracks()
        ]

    @app.post("/api/music-library/sync", response_model=list[MusicLibraryTrackResponse])
    async def sync_music_library() -> list[MusicLibraryTrackResponse]:
        try:
            await _sync_music_library_from_navidrome(state)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Navidrome 音乐库同步失败：{exc}") from exc
        return [
            _music_library_track_response(item)
            for item in await state.repository.list_music_library_tracks()
        ]

    @app.get("/api/subscriptions", response_model=list[SubscriptionResponse])
    async def subscriptions() -> list[SubscriptionResponse]:
        rows = await state.repository.list_subscriptions()
        return [
            SubscriptionResponse(
                id=row.id,
                kind=row.kind,
                name=row.name,
                external_id=row.external_id,
                enabled=row.enabled,
                last_checked_at=row.last_checked_at,
            )
            for row in rows
        ]

    @app.post("/api/subscriptions", response_model=SubscriptionResponse, status_code=201)
    async def create_subscription(payload: SubscriptionCreateRequest) -> SubscriptionResponse:
        row = await state.repository.create_subscription(
            kind=payload.kind,
            name=payload.name,
            external_id=payload.external_id,
            enabled=payload.enabled,
        )
        return SubscriptionResponse(
            id=row.id,
            kind=row.kind,
            name=row.name,
            external_id=row.external_id,
            enabled=row.enabled,
            last_checked_at=row.last_checked_at,
        )

    @app.post("/api/webhooks/qbittorrent/{torrent_hash}", status_code=202)
    async def qbittorrent_webhook(
        torrent_hash: str,
        payload: QBittorrentWebhookRequest | None = None,
    ) -> dict[str, str]:
        download_path = (
            None
            if payload is None or payload.download_path is None
            else Path(payload.download_path)
        )
        await state.repository.mark_torrent_completed(
            torrent_hash=torrent_hash,
            save_path=download_path,
        )
        state.add_log("transfer", f"Download completed webhook accepted: {torrent_hash}")
        return {"status": "accepted", "torrent_hash": torrent_hash}

    if settings.static_dir.exists():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")

    return app


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _search_indexer(
    indexer: object,
    query: str,
    limit: int,
) -> tuple[str, tuple[SearchResult, ...]]:
    results = await indexer.search(query, limit=limit)
    return indexer.name, results


async def _submit_torrent_to_downloader(
    state: AppState,
    resource: dict[str, Any],
    selected_site_ids: list[str],
    category: str,
) -> str:
    if state.downloader is None:
        raise RuntimeError("No downloader is configured.")
    download_url = str(resource.get("download_url") or "")
    site = await _match_torrent_site(state, resource, selected_site_ids)
    if site is None:
        return await state.downloader.add_torrent(download_url, category=category)
    torrent_data = await _download_torrent_file(download_url, site)
    return await state.downloader.add_torrent_file(
        torrent_data,
        filename=_torrent_filename(resource, download_url),
        category=category,
    )


async def _match_torrent_site(
    state: AppState,
    resource: dict[str, Any],
    selected_site_ids: list[str],
) -> IndexerSite | None:
    sites = await state.repository.list_indexer_sites()
    enabled_sites = [site for site in sites if site.enabled]
    selected = [site for site in enabled_sites if site.id in selected_site_ids]
    if len(selected) == 1:
        return selected[0]

    source = str(resource.get("source") or "").strip().casefold()
    for site in enabled_sites:
        if site.name.strip().casefold() == source:
            return site

    download_host = urlparse(str(resource.get("download_url") or "")).netloc.casefold()
    if not download_host:
        return None
    for site in enabled_sites:
        site_host = urlparse(site.base_url).netloc.casefold()
        if site_host and site_host == download_host:
            return site
    return None


async def _download_torrent_file(download_url: str, site: IndexerSite) -> bytes:
    headers: dict[str, str] = {}
    if site.cookie:
        headers["Cookie"] = site.cookie
    if site.user_agent:
        headers["User-Agent"] = site.user_agent
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, http2=True) as client:
        response = await client.get(download_url, headers=headers)
    response.raise_for_status()
    content = response.content
    if not _looks_like_torrent_file(content):
        preview = response.text[:120].replace("\r", " ").replace("\n", " ")
        raise RuntimeError(
            "下载种子文件失败：站点返回的不是 torrent 文件。"
            f"请检查 {site.name} 的 Cookie/UA。返回内容：{preview}"
        )
    return content


def _looks_like_torrent_file(content: bytes) -> bool:
    return content.startswith(b"d") and b"announce" in content[:4096]


def _torrent_filename(resource: dict[str, Any], download_url: str) -> str:
    path_name = unquote(Path(urlparse(download_url).path).name)
    if path_name.endswith(".torrent"):
        return path_name
    title = str(resource.get("title") or "musicpilot").strip()
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title).strip(" .")
    return f"{safe_title or 'musicpilot'}.torrent"


async def _run_metadata_site_search_stream(
    state: AppState,
    task: MetadataSiteSearchTask,
    indexers: list[object],
    limit: int,
) -> None:
    if not indexers:
        await task.finish()
        return
    try:
        await asyncio.gather(
            *(_run_metadata_site_search_for_indexer(task, indexer, limit) for indexer in indexers)
        )
    except Exception as exc:  # noqa: BLE001
        state.add_log("search", f"Streaming metadata site search failed: {exc}", "ERROR")
    finally:
        await task.finish()
        state.add_log(
            "search",
            f"Streaming metadata site search completed: raw={task.raw_count}, "
            f"filtered={task.filtered_count}",
        )


async def _run_metadata_site_search_for_indexer(
    task: MetadataSiteSearchTask,
    indexer: object,
    limit: int,
) -> None:
    site_name = str(getattr(indexer, "name", "unknown"))
    try:
        keywords = task.keywords
        if not keywords:
            await task.site_done(
                site=site_name,
                raw_count=0,
                filtered_count=0,
                results=[],
                errors=[],
            )
            return

        max_concurrency = max(1, int(getattr(indexer.config, "max_concurrency", 1)))
        semaphore = asyncio.Semaphore(max_concurrency)
        raw_results: list[SearchResult] = []
        errors: list[str] = []

        async def search_keyword(keyword: str) -> None:
            async with semaphore:
                await task.keyword_started(keyword)
                try:
                    _source, results = await _search_indexer(indexer, keyword, limit)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{keyword}: {exc}")
                else:
                    raw_results.extend(results)
                finally:
                    await task.keyword_finished(keyword)

        await asyncio.gather(*(search_keyword(keyword) for keyword in keywords))
        merged = _dedupe_results(raw_results)
        filtered = _filter_by_artist(merged, task.media.artist)
        ranked = sorted(filtered, key=lambda item: item.seeders, reverse=True)[:limit]
        await task.site_done(
            site=site_name,
            raw_count=len(merged),
            filtered_count=len(filtered),
            results=[_search_result_response(item) for item in ranked],
            errors=errors,
        )
    except Exception as exc:  # noqa: BLE001
        await task.site_error(site=site_name, message=str(exc))


def _search_result_response(result: SearchResult) -> SearchResultResponse:
    return SearchResultResponse(
        title=result.title,
        download_url=result.download_url,
        source=result.source,
        seeders=result.seeders,
        leechers=result.leechers,
        size_bytes=result.size_bytes,
        details_url=result.details_url,
        subtitle=result.subtitle,
        published_at=result.published_at,
        promotion=result.promotion,
    )


def _candidate_response(item: MediaCandidate) -> MediaCandidateResponse:
    return MediaCandidateResponse(
        title=item.title,
        artist=item.artist,
        album=item.album,
        albums=[item.album] if item.album else [],
        release_date=item.release_date,
        cover_url=item.cover_url,
        source=item.source,
        external_id=item.external_id,
    )


def _aggregate_media_candidates(
    candidates: list[MediaCandidate],
    *,
    limit: int,
) -> list[MediaCandidateResponse]:
    by_key: dict[tuple[str, str], MediaCandidateResponse] = {}
    for candidate in candidates:
        key = (
            normalize_search_text(candidate.title),
            normalize_search_text(candidate.artist or ""),
        )
        current = by_key.get(key)
        if current is None:
            current = _candidate_response(candidate)
            by_key[key] = current
        elif not current.cover_url and candidate.cover_url:
            current.cover_url = candidate.cover_url
        album = candidate.album
        if album and album not in current.albums:
            current.albums.append(album)
        if current.album is None and album:
            current.album = album
        if current.release_date is None and candidate.release_date:
            current.release_date = candidate.release_date
    return list(by_key.values())[:limit]


def _downloader_response(item: DownloaderConfig) -> DownloaderResponse:
    return DownloaderResponse(
        id=item.id,
        name=item.name,
        type=item.type,
        base_url=item.base_url,
        username=item.username,
        download_path=item.download_path,
        listen_mode=item.listen_mode,
        is_default=item.is_default,
        enabled=item.enabled,
    )


def _media_server_response(item: MediaServerConfig) -> MediaServerResponse:
    return MediaServerResponse(
        id=item.id,
        name=item.name,
        type=item.type,
        base_url=item.base_url,
        api_key=item.api_key,
        username=item.username,
        is_default=item.is_default,
        enabled=item.enabled,
    )


def _notifier_response(item: NotifierChannel) -> NotifierResponse:
    return NotifierResponse(
        id=item.id,
        name=item.name,
        type=item.type,
        webhook_url=item.webhook_url,
        chat_ids=item.chat_ids,
        use_proxy=item.use_proxy,
        enable_download_notify=item.enable_download_notify,
        enable_library_notify=item.enable_library_notify,
        enabled=item.enabled,
    )


def _download_task_response(item: TorrentRecord) -> DownloadTaskResponse:
    torrent_hash = None if _is_pending_hash(item.torrent_hash) else item.torrent_hash
    return DownloadTaskResponse(
        id=item.id,
        torrent_hash=torrent_hash,
        name=item.name,
        state=item.status,
        progress=item.progress,
        save_path=item.save_path,
        source=item.source,
        last_error=item.last_error,
    )


def _music_library_track_response(item: MusicLibraryTrack) -> MusicLibraryTrackResponse:
    return MusicLibraryTrackResponse(
        id=item.navidrome_id,
        title=item.title,
        artist=item.artist,
        album=item.album,
        duration=item.duration,
        size=item.size,
        year=item.year,
    )


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


def _is_pending_hash(value: str | None) -> bool:
    return value is None or value.startswith("pending:")


def _site_payload(site: IndexerSite) -> dict[str, object]:
    return {
        "id": site.id,
        "name": site.name,
        "base_url": site.base_url,
        "cookie": site.cookie,
        "user_agent": site.user_agent,
        "max_concurrency": site.max_concurrency,
    }


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    by_key: dict[tuple[str, str], SearchResult] = {}
    for result in results:
        current = by_key.get(result.identity_key)
        if current is None or result.seeders > current.seeders:
            by_key[result.identity_key] = result
    return list(by_key.values())


def _metadata_search_keywords(media: MediaCandidateResponse) -> list[str]:
    keywords: list[str] = []
    albums = media.albums or ([media.album] if media.album else [])
    for value in (media.title, *albums):
        for keyword in _site_keyword_variants(value):
            if keyword and keyword not in keywords:
                keywords.append(keyword)
    return keywords


def _site_keyword_variants(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace("…", "...")
    if normalized == value:
        return [value]
    return [normalized, value]


def _filter_by_artist(results: list[SearchResult], artist: str | None) -> list[SearchResult]:
    if not artist:
        return results
    needle = normalize_search_text(artist)
    compact_needle = _compact_search_text(needle)
    return [
        item
        for item in results
        if _normalized_contains(_resource_text(item), needle, compact_needle)
    ]


def _resource_text(result: SearchResult) -> str:
    values = [
        result.title,
        result.subtitle or "",
        result.source,
        result.details_url or "",
        result.published_at or "",
        result.promotion or "",
        json.dumps(result.metadata, ensure_ascii=False),
    ]
    return " ".join(values)


def normalize_search_text(value: str) -> str:
    normalized = _OPENCC_T2S.convert(unicodedata.normalize("NFKC", value))
    normalized = normalized.replace("…", "...")
    normalized = re.sub(r"\s+", " ", normalized.casefold()).strip()
    return normalized


def _compact_search_text(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def _normalized_contains(text: str, needle: str, compact_needle: str) -> bool:
    haystack = normalize_search_text(text)
    if needle and needle in haystack:
        return True
    return bool(compact_needle and compact_needle in _compact_search_text(haystack))


def _navidrome_params(payload: MediaServerCreateRequest | MediaServerConfig) -> dict[str, str]:
    params = {"v": "1.16.1", "c": "MusicPilot", "f": "json"}
    token = getattr(payload, "api_key", "")
    username = getattr(payload, "username", "")
    password = getattr(payload, "password", "")
    if token:
        params["token"] = token
    if username and password:
        salt = uuid4().hex
        auth_token = hashlib.md5(f"{password}{salt}".encode()).hexdigest()
        params.update({"u": username, "t": auth_token, "s": salt})
    return params


async def _poll_download_tasks(state: AppState) -> None:
    while True:
        try:
            await _poll_download_tasks_once(state)
        except Exception as exc:  # noqa: BLE001
            state.add_log("download", f"Download polling failed: {exc}", "ERROR")
        await asyncio.sleep(DOWNLOAD_POLL_INTERVAL_SECONDS)


async def _sync_music_library_periodically(state: AppState) -> None:
    while True:
        try:
            await _sync_music_library_from_navidrome(state)
        except Exception as exc:  # noqa: BLE001
            state.add_log("library", f"Music library sync failed: {exc}", "ERROR")
        await asyncio.sleep(MUSIC_LIBRARY_SYNC_INTERVAL_SECONDS)


async def _sync_music_library_after_refresh(state: AppState) -> None:
    await asyncio.sleep(MUSIC_LIBRARY_SYNC_AFTER_REFRESH_DELAY_SECONDS)
    try:
        await _sync_music_library_from_navidrome(state)
    except Exception as exc:  # noqa: BLE001
        state.add_log("library", f"Music library sync after refresh failed: {exc}", "ERROR")


async def _sync_music_library_from_navidrome(state: AppState) -> int:
    server = await state.repository.default_media_server()
    if server is None:
        state.add_log("library", "Music library sync skipped: no media server", "WARNING")
        return 0
    tracks = await _fetch_navidrome_music_library(server)
    count = await state.repository.sync_music_library_tracks(tracks)
    state.add_log("library", f"Music library synced: {count} track(s)")
    return count


async def _fetch_navidrome_music_library(server: MediaServerConfig) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    page_size = 500
    offset = 0
    async with httpx.AsyncClient(base_url=server.base_url.rstrip("/"), timeout=30) as client:
        while True:
            params = {
                **_navidrome_params(server),
                "query": "",
                "artistCount": "0",
                "albumCount": "0",
                "songCount": str(page_size),
                "songOffset": str(offset),
            }
            response = await client.get("/rest/search3.view", params=params)
            response.raise_for_status()
            payload = _validate_navidrome_json_response(response)
            search_result = payload.get("searchResult3")
            songs = search_result.get("song", []) if isinstance(search_result, dict) else []
            if not isinstance(songs, list) or not songs:
                break
            tracks.extend(item for item in songs if isinstance(item, dict))
            if len(songs) < page_size:
                break
            offset += page_size
    return tracks


async def _delete_task_torrent(
    state: AppState,
    task: TorrentRecord,
    *,
    delete_files: bool,
) -> None:
    await _delete_torrent_hash(state, task.torrent_hash, delete_files=delete_files)


async def _delete_torrent_hash(
    state: AppState,
    torrent_hash: str | None,
    *,
    delete_files: bool,
) -> None:
    if _is_pending_hash(torrent_hash):
        return
    if state.downloader is None:
        await state.reload_downloader()
    if state.downloader is None:
        raise RuntimeError("Downloader is unavailable.")
    await state.downloader.delete_torrent(torrent_hash or "", delete_files=delete_files)


async def _delete_media_source(state: AppState, media: MediaFile) -> None:
    if media.torrent_hash and not _is_pending_hash(media.torrent_hash):
        await _delete_torrent_hash(state, media.torrent_hash, delete_files=True)
        return
    await _delete_file_path(Path(media.source_path))


async def _delete_media_record(
    state: AppState,
    media: MediaFile,
    mode: MediaDeleteMode,
) -> bool:
    if mode in {"media_file", "all"}:
        if mode == "all":
            await _delete_media_source(state, media)
        if media.status == "success" and media.library_path:
            await _delete_file_path(Path(media.library_path))
    return await state.repository.delete_media_file(media.id)


async def _delete_file_path(path: Path) -> None:
    await asyncio.to_thread(_delete_file_path_sync, path)


def _delete_file_path_sync(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise RuntimeError(f"Refusing to delete non-file path: {path}")
    path.unlink()


def _file_size_or_none(path: str | None) -> int | None:
    if not path:
        return None
    try:
        target = Path(path)
        if target.is_file():
            return target.stat().st_size
    except OSError:
        return None
    return None


def _scraping_source_root_or_409(config: ScrapingConfig) -> Path:
    if config.source_directory is None:
        raise HTTPException(status_code=409, detail="请先配置刮削源文件目录。")
    root = config.source_directory.expanduser().resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail="刮削源文件目录不存在。")
    if not root.is_dir():
        raise HTTPException(status_code=422, detail="刮削源文件目录不是目录。")
    return root


def _resolve_source_relative_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path or "")
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="只能访问源文件目录下的相对路径。")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=403, detail="不能访问源文件目录之外的路径。")
    return target


def _resolve_source_delete_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path or "")
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="只能访问源文件目录下的相对路径。")
    if not relative.parts:
        raise HTTPException(status_code=400, detail="不能删除源文件目录。")
    parent = (root / relative).parent.resolve()
    if not parent.is_relative_to(root):
        raise HTTPException(status_code=403, detail="不能访问源文件目录之外的路径。")
    return parent / relative.name


def _source_relative_path(root: Path, path: Path) -> str:
    if path == root:
        return ""
    return path.relative_to(root).as_posix()


def _source_parent_path(root: Path, path: Path) -> str | None:
    if path == root:
        return None
    return _source_relative_path(root, path.parent)


def _source_directory_entries(
    root: Path,
    directory: Path,
    query: str = "",
    limit: int = 500,
) -> list[FileEntryResponse]:
    entries: list[FileEntryResponse] = []
    for item in directory.iterdir():
        entry = _source_entry_response(root, item)
        if entry is None:
            continue
        entries.append(entry)
    entries.sort(key=lambda item: (item.type != "directory", item.name.casefold()))
    return entries


def _source_search_entries(
    root: Path,
    directory: Path,
    query: str,
    limit: int = 500,
) -> list[FileEntryResponse]:
    needle = query.casefold()
    entries: list[FileEntryResponse] = []
    for item in directory.rglob("*"):
        entry = _source_entry_response(root, item)
        if entry is None:
            continue
        text = f"{entry.name} {entry.path}".casefold()
        if needle not in text:
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break
    entries.sort(key=lambda item: (item.type != "directory", item.path.casefold()))
    return entries


def _source_entry_response(root: Path, path: Path) -> FileEntryResponse | None:
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            return None
        stat = resolved.stat()
    except OSError:
        return None
    if resolved.is_dir():
        entry_type = "directory"
        size = None
    elif resolved.is_file():
        entry_type = "file"
        size = stat.st_size
    else:
        return None
    return FileEntryResponse(
        name=path.name,
        path=_source_relative_path(root, resolved),
        type=entry_type,
        size=size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
    )


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _delete_source_path_sync(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    if not _path_lexists(path):
        return
    raise RuntimeError(f"不支持删除该路径类型：{path}")


def _source_audio_files(root: Path, target: Path) -> tuple[Path, ...]:
    candidates = (target,) if target.is_file() else tuple(target.rglob("*"))
    files: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (
            resolved in seen
            or not resolved.is_relative_to(root)
            or not resolved.is_file()
            or not _is_audio_file(resolved)
        ):
            continue
        seen.add(resolved)
        files.append(resolved)
    return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))


async def _scrape_manual_source_files(
    state: AppState,
    config: ScrapingConfig,
    target: Path,
    source_files: tuple[Path, ...],
) -> ScrapingSummary:
    try:
        await _sync_music_library_from_navidrome(state)
    except Exception as exc:  # noqa: BLE001
        state.add_log(
            "library",
            f"Music library sync before manual scraping failed: {exc}",
            "WARNING",
        )
    library_tracks = tuple(
        LibraryTrackSnapshot(
            title=item.title,
            artist=item.artist,
            album=item.album,
            size=item.size,
            path=item.path,
        )
        for item in await state.repository.list_music_library_tracks()
    )
    media_history = tuple(
        LibraryTrackSnapshot(
            title=item.title or "",
            artist=item.artist,
            album=item.album,
            size=_file_size_or_none(item.library_path),
            path=item.library_path,
        )
        for item in await state.repository.list_media_files()
        if item.title
    )
    summary = await state.scraper.process_download(
        task_name=target.name or "manual",
        save_path=None,
        config=config,
        source_files=source_files,
        library_tracks=library_tracks,
        media_history=media_history,
    )
    for item in summary.results:
        await state.repository.record_scraping_result(
            torrent_hash=None,
            source_path=item.source_path,
            library_path=item.library_path,
            metadata=item.metadata,
            status=item.status,
            error_message=item.error_message,
        )
        state.add_log(
            "metadata",
            _scraping_file_log_message(target.name or "manual", item),
            "WARNING" if item.status == "failed" else "INFO",
        )
    state.add_log(
        "metadata",
        "Manual scraping completed for "
        f"{target}: files={summary.source_files}, mapped={summary.mapped_files}, "
        f"updated={summary.updated_files}, moved={summary.moved_files}, "
        f"failed={summary.failed_files}, "
        f"skipped={sum(1 for item in summary.results if item.status == 'skipped')}",
    )
    return summary


async def _poll_download_tasks_once(state: AppState) -> None:
    tasks = await state.repository.list_unfinished_download_tasks()
    if not tasks:
        return

    active_tasks: list[TorrentRecord] = []
    for task in tasks:
        if task.status in {"completed", "refreshing_library"}:
            await _refresh_library_for_task(state, task)
            continue
        if task.status in {"queued", "submitted", "downloading"}:
            active_tasks.append(task)

    if not active_tasks:
        return

    default = await state.repository.default_downloader()
    if default is None or default.listen_mode != "polling" or not default.enabled:
        return
    if state.downloader is None:
        await state.reload_downloader()
    if state.downloader is None:
        return

    statuses = await state.downloader.list_statuses()
    by_hash = {item.torrent_hash: item for item in statuses if item.torrent_hash}
    for task in active_tasks:
        has_real_hash = not _is_pending_hash(task.torrent_hash)
        status = by_hash.get(task.torrent_hash or "") if has_real_hash else None
        if status is None and not has_real_hash:
            status = _match_status_by_name(statuses, task)
            if status is not None:
                await state.repository.update_download_task(
                    task.id,
                    torrent_hash=status.torrent_hash,
                )
        if status is None:
            if has_real_hash:
                await state.repository.update_download_task(
                    task.id,
                    status="deleted",
                    last_error="qBittorrent 中未找到该任务，可能已被删除。",
                )
            continue
        changes: dict[str, object] = {
            "progress": status.progress,
            "save_path": str(status.save_path) if status.save_path is not None else None,
        }
        if status.progress >= 1:
            changes.update({"status": "completed", "completed_at": datetime.now(UTC)})
        else:
            changes["status"] = "downloading"
            if task.download_started_at is None:
                changes["download_started_at"] = datetime.now(UTC)
        await state.repository.update_download_task(task.id, **changes)


def _match_status_by_name(statuses: tuple[object, ...], task: TorrentRecord) -> object | None:
    name = _normalize_match_text(task.name)
    for status in statuses:
        status_name = _normalize_match_text(getattr(status, "name", ""))
        if not name or not status_name:
            continue
        if name in status_name or status_name in name:
            return status
    task_tokens = _match_tokens(task.name)
    best_status = None
    best_score = 0.0
    for status in statuses:
        status_tokens = _match_tokens(getattr(status, "name", ""))
        if not task_tokens or not status_tokens:
            continue
        score = len(task_tokens & status_tokens) / len(status_tokens)
        if score > best_score:
            best_score = score
            best_status = status
    if best_score >= 0.7:
        return best_status
    return None


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _match_tokens(value: str) -> set[str]:
    normalized = _normalize_match_text(value)
    return {
        token
        for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff.]+", normalized)
        if len(token) >= 2
    }


async def _refresh_library_for_task(state: AppState, task: TorrentRecord) -> None:
    if task.status != "refreshing_library":
        await state.repository.update_download_task(task.id, status="refreshing_library")
    await _scrape_download_for_task(state, task)
    server = await state.repository.default_media_server()
    if server is None:
        await state.repository.update_download_task(
            task.id,
            status="failed",
            last_error="No enabled default media server is configured.",
        )
        state.add_log(
            "library",
            f"Library refresh failed for {task.name}: no media server",
            "ERROR",
        )
        return
    try:
        state.add_log("library", f"Refreshing media library via {server.name}: {task.name}")
        async with httpx.AsyncClient(base_url=server.base_url.rstrip("/"), timeout=30) as client:
            response = await client.get("/rest/startScan.view", params=_navidrome_params(server))
            _validate_navidrome_scan_response(response)
    except Exception as exc:  # noqa: BLE001
        await state.repository.update_download_task(task.id, status="failed", last_error=str(exc))
        state.add_log("library", f"Library refresh failed for {task.name}: {exc}", "ERROR")
        return
    refreshed = await state.repository.update_download_task(
        task.id,
        status="library_refreshed",
        library_refreshed_at=datetime.now(UTC),
    )
    state.add_log("library", f"Media library refresh requested: {task.name}")
    asyncio.create_task(
        _sync_music_library_after_refresh(state),
        name="musicpilot-music-library-sync-after-refresh",
    )
    await _send_event_notifications(state, "library", refreshed or task)


async def _scrape_download_for_task(state: AppState, task: TorrentRecord) -> None:
    settings_payload = await state.repository.get_system_settings()
    config = scraping_config_from_payload(settings_payload)
    if not config.enabled:
        return
    if (task.payload or {}).get("scraping_completed"):
        return
    try:
        try:
            await _sync_music_library_from_navidrome(state)
        except Exception as exc:  # noqa: BLE001
            state.add_log("library", f"Music library sync before scraping failed: {exc}", "WARNING")
        library_tracks = tuple(
            LibraryTrackSnapshot(
                title=item.title,
                artist=item.artist,
                album=item.album,
                size=item.size,
                path=item.path,
            )
            for item in await state.repository.list_music_library_tracks()
        )
        media_history = tuple(
            LibraryTrackSnapshot(
                title=item.title or "",
                artist=item.artist,
                album=item.album,
                size=_file_size_or_none(item.library_path),
                path=item.library_path,
            )
            for item in await state.repository.list_media_files()
            if item.title
        )
        source_files = await _scraping_source_files_for_task(state, task)
        if source_files is None:
            return
        summary = await state.scraper.process_download(
            task_name=task.name,
            save_path=task.save_path,
            config=config,
            source_files=source_files,
            library_tracks=library_tracks,
            media_history=media_history,
        )
    except Exception as exc:  # noqa: BLE001
        state.add_log("metadata", f"Scraping failed for {task.name}: {exc}", "WARNING")
        return
    payload = dict(task.payload or {})
    payload["scraping_completed"] = True
    await state.repository.update_download_task(task.id, payload=payload)
    for item in summary.results:
        await state.repository.record_scraping_result(
            torrent_hash=task.torrent_hash,
            source_path=item.source_path,
            library_path=item.library_path,
            metadata=item.metadata,
            status=item.status,
            error_message=item.error_message,
        )
        state.add_log(
            "metadata",
            _scraping_file_log_message(task.name, item),
            "WARNING" if item.status == "failed" else "INFO",
        )
    state.add_log(
        "metadata",
        "Scraping completed for "
        f"{task.name}: files={summary.source_files}, mapped={summary.mapped_files}, "
        f"updated={summary.updated_files}, moved={summary.moved_files}, "
        f"failed={summary.failed_files}, "
        f"skipped={sum(1 for item in summary.results if item.status == 'skipped')}",
    )


async def _scraping_source_files_for_task(
    state: AppState,
    task: TorrentRecord,
) -> tuple[Path, ...] | None:
    if state.downloader is None:
        await state.reload_downloader()
    if state.downloader is None:
        state.add_log(
            "metadata",
            f"Scraping skipped for {task.name}: downloader is unavailable.",
            "WARNING",
        )
        return None
    if _is_pending_hash(task.torrent_hash):
        state.add_log(
            "metadata",
            f"Scraping skipped for {task.name}: torrent hash is not resolved.",
            "WARNING",
        )
        return None
    try:
        status = await state.downloader.get_status(task.torrent_hash or "")
        torrent_files = await state.downloader.list_files(task.torrent_hash or "")
    except Exception as exc:  # noqa: BLE001
        state.add_log(
            "metadata",
            f"Scraping skipped for {task.name}: qBittorrent file list failed: {exc}",
            "WARNING",
        )
        return None
    source_files = _resolve_torrent_audio_files(task, status, torrent_files)
    state.add_log(
        "metadata",
        f"Scraping source files resolved for {task.name}: files={len(source_files)}",
    )
    return source_files


def _resolve_torrent_audio_files(
    task: TorrentRecord,
    status: DownloadStatus,
    torrent_files: tuple[TorrentFile, ...],
) -> tuple[Path, ...]:
    seen: set[Path] = set()
    source_files: list[Path] = []
    for torrent_file in torrent_files:
        if torrent_file.progress < 1:
            continue
        for candidate in _torrent_file_candidates(task, status, torrent_file.path):
            if not candidate.is_file() or not _is_audio_file(candidate):
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                break
            seen.add(resolved)
            source_files.append(resolved)
            break
    return tuple(source_files)


def _torrent_file_candidates(
    task: TorrentRecord,
    status: DownloadStatus,
    relative_path: Path,
) -> tuple[Path, ...]:
    if relative_path.is_absolute():
        return (relative_path,)
    candidates: list[Path] = []
    content_path = status.content_path
    if content_path is not None:
        if content_path.is_file():
            candidates.append(content_path)
        else:
            candidates.append(content_path / relative_path)
            candidates.append(content_path.parent / relative_path)
    roots = [
        Path(task.save_path) if task.save_path else None,
        status.save_path,
    ]
    for root in roots:
        if root is None:
            continue
        if task.name:
            candidates.append(root / task.name / relative_path)
        candidates.append(root / relative_path)
    return tuple(_dedupe_paths(candidates))


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _is_audio_file(path: Path) -> bool:
    return path.suffix.casefold() in {
        ".aac",
        ".aiff",
        ".alac",
        ".ape",
        ".flac",
        ".m4a",
        ".mp3",
        ".ogg",
        ".opus",
        ".wav",
        ".wma",
    }


def _scraping_file_log_message(task_name: str, item: ScrapingFileResult) -> str:
    metadata = item.metadata
    parts = [
        f"Scraping file {item.status} for {task_name}",
        f"source={item.source_path}",
        f"title={metadata.title!r}",
        f"artist={metadata.artist!r}",
        f"album={metadata.album!r}",
        f"needs_update={item.needs_metadata_update}",
        f"candidates={item.candidate_count}",
        f"stage={item.stage}",
    ]
    if item.library_path is not None:
        parts.append(f"library={item.library_path}")
    if item.error_message:
        parts.append(f"reason={item.error_message}")
    return ", ".join(parts)


def _validate_navidrome_scan_response(response: httpx.Response) -> None:
    response.raise_for_status()
    body = _validate_navidrome_json_response(response)
    status = str(body.get("status") or "").casefold()
    if status == "ok":
        return
    raise RuntimeError(f"Navidrome scan failed: {_navidrome_error_message(body, status)}")


def _validate_navidrome_json_response(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Navidrome returned a non-JSON response.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Navidrome returned an invalid response.")
    body = payload.get("subsonic-response")
    if not isinstance(body, dict):
        raise RuntimeError("Navidrome response is missing subsonic-response.")
    status = str(body.get("status") or "").casefold()
    if status == "ok":
        return body
    raise RuntimeError(f"Navidrome request failed: {_navidrome_error_message(body, status)}")


def _navidrome_error_message(body: dict[str, object], status: str) -> str:
    error = body.get("error")
    message = ""
    if isinstance(error, dict):
        code = error.get("code")
        detail = error.get("message")
        if code and detail:
            message = f"{code}: {detail}"
        elif detail:
            message = str(detail)
    if not message:
        message = f"unexpected status {status or '<missing>'}"
    return message


async def _send_event_notifications(
    state: AppState,
    event_name: str,
    task: TorrentRecord | None,
) -> None:
    if task is None:
        return
    await state.reload_notifiers()
    channels = await state.repository.list_notifiers()
    enabled = [
        item for item in channels
        if item.enabled and (
            (event_name == "download" and item.enable_download_notify)
            or (event_name == "library" and item.enable_library_notify)
        )
    ]
    if not enabled:
        return
    title = "MusicPilot 已提交下载" if event_name == "download" else "MusicPilot 媒体库已刷新"
    text = _notification_body(event_name, task)
    system_settings = await state.repository.get_system_settings()
    notifiers = [
        TelegramHttpNotifier(
            token=item.bot_token,
            chat_ids=tuple(
                int(chat_id.strip())
                for chat_id in item.chat_ids.split(",")
                if chat_id.strip().isdigit()
            ),
            proxy=_proxy_url(system_settings) if item.use_proxy else None,
        )
        for item in enabled
        if item.type == "telegram" and item.bot_token.strip()
    ]
    await asyncio.gather(
        *(notifier.notify(NotifyEvent(title=title, text=text)) for notifier in notifiers),
        return_exceptions=True,
    )


def _notification_body(event_name: str, task: TorrentRecord) -> str:
    if event_name == "download":
        return _download_notification_body(task)
    return _library_notification_body(task)


def _download_notification_body(task: TorrentRecord) -> str:
    resource = task.resource_payload or {}
    return "\n".join(
        [
            _notification_line("种子名称", task.name),
            _notification_line("大小", _format_size_bytes(resource.get("size_bytes"))),
            _notification_line("站点", task.source or resource.get("source")),
            _notification_line("促销信息", resource.get("promotion")),
            _notification_line("发布时间", resource.get("published_at")),
        ]
    )


def _library_notification_body(task: TorrentRecord) -> str:
    resource = task.resource_payload or {}
    return "\n".join(
        [
            _notification_line("种子名称", task.name),
            _notification_line("大小", _format_size_bytes(resource.get("size_bytes"))),
            _notification_line("入库时间", _format_datetime(task.library_refreshed_at)),
        ]
    )


def _notification_line(label: str, value: object) -> str:
    return f"<b>{escape(label)}：</b>{escape(_display_value(value))}"


def _display_value(value: object) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text or "-"


def _format_size_bytes(value: object) -> str:
    if value is None:
        return "-"
    try:
        size = float(value)
    except (TypeError, ValueError):
        return _display_value(value)
    if size <= 0:
        return "-"
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _site_response(site: IndexerSite, parser: NexusPHPParserConfig) -> SiteResponse:
    return SiteResponse(**_site_payload(site), parser=_parser_response(parser))


def _legacy_downloader_payload(item: dict[str, object]) -> dict[str, object]:
    return {
        "name": str(item.get("name") or "qBittorrent"),
        "type": str(item.get("type") or "qbittorrent"),
        "base_url": str(item.get("base_url") or ""),
        "username": str(item.get("username") or ""),
        "password": str(item.get("password") or ""),
        "download_path": str(item.get("download_path") or ""),
        "listen_mode": str(item.get("listen_mode") or "polling"),
        "is_default": bool(item.get("is_default", True)),
        "enabled": bool(item.get("enabled", True)),
    }


def _legacy_notifier_payload(item: dict[str, object]) -> dict[str, object]:
    return {
        "name": str(item.get("name") or "Telegram Bot"),
        "type": str(item.get("type") or "telegram"),
        "bot_token": str(item.get("bot_token") or ""),
        "webhook_url": str(item.get("webhook_url") or ""),
        "chat_ids": str(item.get("chat_ids") or ""),
        "use_proxy": bool(item.get("use_proxy", False)),
        "enable_download_notify": bool(item.get("enable_download_notify", True)),
        "enable_library_notify": bool(item.get("enable_library_notify", True)),
        "enabled": bool(item.get("enabled", True)),
    }


def _parser_response(parser: NexusPHPParserConfig) -> NexusPHPParserRequest:
    return NexusPHPParserRequest(
        list_selector=parser.list_selector,
        fields={
            name: ParserFieldRequest(
                selector=field.selector,
                attribute=field.attribute,
                regex=field.regex,
                index=field.index,
                remove=list(field.remove),
                filters=list(field.filters),
            )
            for name, field in parser.fields.items()
        },
    )


def _supported_parser_or_422(state: AppState, base_url: str) -> NexusPHPParserConfig:
    state.reload_parser_catalog()
    entry = state.parser_catalog.match(base_url)
    if entry is None:
        raise HTTPException(
            status_code=422,
            detail="当前站点暂不支持，请先在 sites.parser.yaml 中配置解析器。",
        )
    return entry.parser


def _proxy_url(settings_payload: dict[str, object]) -> str | None:
    proxy = settings_payload.get("proxy", {})
    if not isinstance(proxy, dict):
        return None
    host = str(proxy.get("host", "")).strip()
    if not host:
        return None
    port = int(proxy.get("port") or 0)
    username = str(proxy.get("username", "")).strip()
    password = str(proxy.get("password", "")).strip()
    auth = ""
    if username:
        auth = quote(username)
        if password:
            auth = f"{auth}:{quote(password)}"
        auth = f"{auth}@"
    if host.startswith(("http://", "https://", "socks5://", "socks4://")):
        scheme, rest = host.split("://", 1)
        return f"{scheme}://{auth}{rest}"
    if port:
        return f"http://{auth}{host}:{port}"
    return f"http://{auth}{host}"


def _category_from_logger(name: str) -> str:
    if "indexer" in name:
        return "search"
    if "download" in name:
        return "download"
    if "processor" in name or "library" in name or "metadata" in name:
        return "transfer"
    if "notifier" in name or "bot" in name:
        return "notify"
    return "system"


def _skip_app_log_record(record: logging.LogRecord) -> bool:
    if record.name.startswith(("httpx", "httpcore")) and record.levelno < logging.WARNING:
        return True
    return False
