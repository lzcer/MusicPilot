from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import importlib.metadata
import json
import logging
import os
import re
import shutil
import tempfile
import time
import tomllib
import unicodedata
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from opencc import OpenCC
from sqlalchemy.exc import IntegrityError

from musicpilot.adapters.bots import TelegramBotAdapter, TelegramHttpNotifier
from musicpilot.adapters.downloaders import QBittorrentClient
from musicpilot.adapters.indexers import build_nexusphp_indexers, load_merged_parser_catalog
from musicpilot.adapters.indexers.nexusphp import (
    NexusPHPCrawler,
    NexusPHPParserConfig,
    NexusPHPSiteConfig,
)
from musicpilot.adapters.media_servers import build_media_server_client
from musicpilot.adapters.metadata import (
    MultiSourceMusicProvider,
    MusicBrainzProvider,
    MutagenTagWriter,
    NetEaseMusicProvider,
)
from musicpilot.adapters.music_platforms.public_playlist import (
    PublicPlaylist,
    PublicPlaylistImporter,
    PublicPlaylistParseError,
    UnsupportedPublicPlaylistURL,
)
from musicpilot.adapters.music_platforms.spotify import (
    SPOTIFY_PLAYLIST_SCOPES,
    SpotifyAPIError,
    SpotifyClient,
    refresh_token_expiry,
    token_expiry,
)
from musicpilot.core.artist import ArtistService, normalize_artist_name, split_artist_credit
from musicpilot.core.event_bus import EventBus
from musicpilot.core.events import NotifyEvent, SearchEvent, SearchResult
from musicpilot.core.metadata import MetadataCascade
from musicpilot.core.pipeline import MusicPipeline
from musicpilot.core.processor import MediaProcessor
from musicpilot.core.scraping import (
    ContextualMetadata,
    LibraryTrackSnapshot,
    LocalMusicScraper,
    ScrapingConfig,
    ScrapingFileOutcome,
    ScrapingFileResult,
    ScrapingSummary,
    infer_album_context_metadata,
    infer_metadata_from_paths,
    normalize_metadata_match_text,
    scraping_config_from_payload,
)
from musicpilot.core.task_queue import (
    TaskCreate,
    TaskExecutionResult,
    TaskExecutorRegistry,
    TaskManager,
)
from musicpilot.infra.api.schemas import (
    AboutResponse,
    AddArtistAliasRequest,
    ArtistAliasResponse,
    ArtistBuildStatusResponse,
    ArtistPageResponse,
    ArtistResponse,
    BuildArtistLibraryResponse,
    ClearArtistLibraryResponse,
    DashboardDownloadItemResponse,
    DashboardDownloadSummaryResponse,
    DashboardLibrarySummaryResponse,
    DashboardMediaItemResponse,
    DashboardMediaSummaryResponse,
    DashboardPlaylistSummaryResponse,
    DashboardResponse,
    DashboardTaskSummaryResponse,
    DownloadDeleteMode,
    DownloaderCreateRequest,
    DownloaderResponse,
    DownloadRequest,
    DownloadResponse,
    DownloadTaskItemResponse,
    DownloadTaskResponse,
    FileBulkDeleteFailure,
    FileBulkDeleteRequest,
    FileBulkDeleteResponse,
    FileDirectoryManualOrganizeRequest,
    FileEntryResponse,
    FileListResponse,
    FileManualOrganizeRequest,
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
    MediaFilePageResponse,
    MediaFileResponse,
    MediaManualOrganizeRequest,
    MediaMetadataSearchResponse,
    MediaRetryRequest,
    MediaRetryResponse,
    MediaServerCreateRequest,
    MediaServerResponse,
    MergeArtistsRequest,
    MetadataSearchResponse,
    MetadataSiteSearchRequest,
    MetadataSiteSearchResponse,
    MusicLibraryStatsResponse,
    MusicLibraryTrackPageResponse,
    MusicLibraryTrackResponse,
    MusicPlatformConnectRequest,
    MusicPlatformConnectResponse,
    MusicPlatformResponse,
    NexusPHPParserRequest,
    NotifierCreateRequest,
    NotifierResponse,
    ParserFieldRequest,
    PlaylistAvailableResponse,
    PlaylistDownloadResponse,
    PlaylistImportRequest,
    PlaylistImportResponse,
    PlaylistImportUrlPreviewRequest,
    PlaylistImportUrlPreviewResponse,
    PlaylistImportUrlRequest,
    PlaylistLibrarySyncRequest,
    PlaylistLibrarySyncResponse,
    PlaylistResponse,
    PlaylistTrackDownloadResponse,
    PlaylistTrackPageResponse,
    PlaylistTrackResponse,
    PlaylistTrackUpdateRequest,
    QBittorrentWebhookRequest,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
    SiteCreateRequest,
    SiteResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SystemTaskInterruptRequest,
    SystemTaskInterruptResponse,
    SystemTaskResponse,
    SystemSettingsRequest,
    SystemSettingsResponse,
    TestResponse,
    TrackMetadataResponse,
    UpdateArtistRequest,
)
from musicpilot.infra.auth import issue_session, require_session
from musicpilot.infra.config import Settings
from musicpilot.infra.db import Database, SqlAlchemyMediaRepository
from musicpilot.infra.db.migration import DatabaseMigrationError, DatabaseMigrationService
from musicpilot.infra.db.models import (
    Artist,
    DownloaderConfig,
    IndexerSite,
    MediaFile,
    MediaServerConfig,
    MusicLibraryTrack,
    MusicPlatformConnection,
    NotifierChannel,
    Playlist,
    PlaylistTrack,
    SystemTask,
    TorrentRecord,
    TorrentRecordItem,
)
from musicpilot.infra.scheduler import SubscriptionScheduler
from musicpilot.ports.downloader import DownloadStatus
from musicpilot.ports.metadata import MediaCandidate, TrackMetadata

_OPENCC_T2S = OpenCC("t2s")
_TORRENT_AUDIO_EXTENSIONS = {
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
DOWNLOAD_POLL_INTERVAL_SECONDS = 5
MUSIC_LIBRARY_SYNC_INTERVAL_SECONDS = 3600
MUSIC_LIBRARY_SYNC_AFTER_REFRESH_DELAY_SECONDS = 5
SLOW_API_OPERATION_SECONDS = float(os.getenv("MP_SLOW_API_OPERATION_SECONDS", "0.5"))
PLAYLIST_TRACK_RETRYABLE_STATUSES = {
    "failed",
    "not_found",
    "deleted",
    "source_directory_not_found",
}
PLAYLIST_TRACK_ACTIVE_STATUSES = {
    "queue",
    "searching",
    "submitted",
    "downloading",
    "completed",
    "refreshing_library",
}
PLAYLIST_TRACK_SUCCESS_STATUSES = {"existing", "library_refreshed"}
DOWNLOAD_ITEM_SCRAPE_INCOMPLETE_STATUSES = {"pending", "metadata_searching"}
DOWNLOAD_ITEM_SCRAPE_DONE_STATUSES = {"metadata_found", "metadata_not_found", "failed"}
DOWNLOAD_ITEM_ORGANIZE_ACTIVE_STATUSES = {"organizing"}
DOWNLOAD_ITEM_ORGANIZE_TERMINAL_STATUSES = {
    "organized",
    "organize_failed",
    "organize_skipped",
}
DOWNLOAD_ITEM_TASK_PRIORITY = 50
DOWNLOAD_REFRESH_TASK_PRIORITY = 40
logger = logging.getLogger(__name__)


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


@dataclasses.dataclass(frozen=True)
class SubmittedTorrent:
    torrent_hash: str
    torrent_data: bytes | None = None


class ScrapingSourceDirectoryNotFound(RuntimeError):
    pass


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
        self._site_states: dict[str, dict[str, Any]] = {}
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

    async def site_progress(
        self,
        *,
        site: str,
        raw_count: int,
        filtered_count: int,
        results: list[SearchResultResponse],
        errors: list[str],
    ) -> None:
        async with self._lock:
            self._site_states[site] = {
                "site": site,
                "raw_count": raw_count,
                "filtered_count": filtered_count,
                "results": [item.model_dump() for item in results],
                "errors": errors,
            }
            self._rebuild_search_totals()
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
            site_payload = self._site_states.get(site) or {
                "site": site,
                "raw_count": raw_count,
                "filtered_count": filtered_count,
                "results": [item.model_dump() for item in results],
                "errors": errors,
            }
            site_payload["errors"] = errors
            self._site_states[site] = site_payload
            self._rebuild_search_totals()
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

    def _rebuild_search_totals(self) -> None:
        self.raw_count = sum(int(state["raw_count"]) for state in self._site_states.values())
        self.filtered_count = sum(
            int(state["filtered_count"]) for state in self._site_states.values()
        )
        results = [
            result
            for state in self._site_states.values()
            for result in state["results"]
            if isinstance(result, dict)
        ]
        self.results = sorted(
            results,
            key=lambda item: int(item.get("seeders") or 0),
            reverse=True,
        )


class PlaylistTrackDownloadExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        playlist_id = _optional_int(payload.get("playlist_id"))
        track_id = _optional_int(payload.get("track_id"))
        if playlist_id is None or track_id is None:
            raise ValueError("Playlist track download task payload is incomplete.")
        try:
            status = await _check_and_download_playlist_track(self.state, track_id)
        except Exception as exc:
            await self.state.repository.update_playlist_track(
                track_id,
                download_status="failed",
                last_checked_at=datetime.now(UTC),
                last_error=str(exc),
            )
            await _update_playlist_download_completion(self.state, playlist_id)
            raise
        await _update_playlist_download_completion(self.state, playlist_id)
        return TaskExecutionResult(
            result={
                "playlist_id": playlist_id,
                "track_id": track_id,
                "status": status,
            }
        )


class SearchSiteExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        site_id = str(payload.get("site_id") or "")
        query = str(payload.get("query") or "")
        limit = _optional_int(payload.get("limit")) or 20
        indexer = _find_indexer(self.state, site_id)
        if indexer is None:
            raise RuntimeError(f"Indexer is unavailable: {site_id}")
        site_name = str(getattr(indexer, "name", site_id))
        results = await indexer.search(query, limit=limit)
        return TaskExecutionResult(
            result={
                "source": site_name,
                "results": [_search_result_payload(item) for item in results],
            }
        )


class SearchMediaExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        query = str(payload.get("query") or "")
        artist = _optional_string(payload.get("artist"))
        limit = _optional_int(payload.get("limit")) or 10
        aggregated = await _search_media_candidates_direct(self.state, query, limit, artist=artist)
        return TaskExecutionResult(
            result={"candidates": [item.model_dump() for item in aggregated]}
        )


class SearchSiteCandidatesExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        site_id = str(payload.get("site_id") or "")
        keywords = [
            str(item)
            for item in payload.get("keywords", [])
            if isinstance(item, str) and item.strip()
        ]
        limit = _optional_int(payload.get("limit")) or 50
        indexer = _find_indexer(self.state, site_id)
        if indexer is None:
            raise RuntimeError(f"Indexer is unavailable: {site_id}")
        site_name, results, errors = await _search_site_candidates_direct(
            indexer,
            keywords,
            limit,
        )
        return TaskExecutionResult(
            result={
                "source": site_name,
                "results": [_search_result_payload(item) for item in results],
                "errors": errors,
            }
        )


class DownloadItemScrapeExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        item_id = _optional_int(payload.get("item_id"))
        if item_id is None:
            raise ValueError("Download item scrape task payload is incomplete.")
        item = await _scrape_download_task_item(self.state, item_id)
        if item is not None and bool(payload.get("organize_after_scrape")):
            source_file = _optional_string(payload.get("source_file"))
            if source_file:
                record = await self.state.repository.get_download_task(item.torrent_record_id)
                if record is not None:
                    await _enqueue_download_item_organize(
                        self.state,
                        record,
                        item,
                        Path(source_file),
                    )
        return TaskExecutionResult(
            result={
                "item_id": item_id,
                "status": item.status if item is not None else "missing",
            }
        )


class FileOrganizeExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        task_id = _optional_int(payload.get("torrent_record_id"))
        item_id = _optional_int(payload.get("item_id"))
        source_file = _optional_string(payload.get("source_file"))
        task_name = str(payload.get("task_name") or "download")
        if task_id is None or item_id is None or not source_file:
            raise ValueError("File organize task payload is incomplete.")
        item = await _organize_download_task_item(
            self.state,
            task_id,
            item_id,
            Path(source_file),
            task_name,
        )
        await _finalize_download_refresh_if_ready(self.state, task_id)
        return TaskExecutionResult(
            result={
                "torrent_record_id": task_id,
                "item_id": item_id,
                "status": item.status if item is not None else "missing",
            }
        )


class DownloadRefreshLibraryExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        task_id = _optional_int(payload.get("torrent_record_id"))
        if task_id is None:
            raise ValueError("Download refresh task payload is incomplete.")
        record = await self.state.repository.get_download_task(task_id)
        if record is None:
            return TaskExecutionResult(
                result={
                    "torrent_record_id": task_id,
                    "status": "missing",
                }
            )
        await _refresh_library_for_task(
            self.state,
            record,
            use_scrape_task_manager=False,
        )
        latest = await self.state.repository.get_download_task(task_id)
        return TaskExecutionResult(
            result={
                "torrent_record_id": task_id,
                "status": latest.status if latest is not None else "missing",
            }
        )


class ManualScrapeExecutor:
    def __init__(self, state: AppState) -> None:
        self.state = state

    async def execute(self, task: object) -> TaskExecutionResult:
        payload = getattr(task, "payload", {}) or {}
        task_name = str(payload.get("task_name") or "manual")
        source_files = tuple(
            Path(item)
            for item in payload.get("source_files", [])
            if isinstance(item, str) and item
        )
        manual_metadata = _manual_metadata_by_source_file(payload.get("manual_metadata"))
        contextual_metadata = _contextual_metadata_by_source_file(
            payload.get("contextual_metadata")
        )
        exclude_library_paths = _paths_from_payload(payload.get("exclude_library_paths"))
        if not source_files:
            raise ValueError("Manual scrape task payload is incomplete.")
        settings_payload = await self.state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        if not config.enabled:
            raise RuntimeError("Scraping is disabled.")
        summary = await _scrape_manual_source_files(
            self.state,
            config,
            task_name,
            source_files,
            manual_metadata=manual_metadata,
            contextual_metadata=contextual_metadata,
            exclude_library_paths=exclude_library_paths,
            use_task_manager=False,
        )
        return TaskExecutionResult(result=_scraping_summary_result(summary))


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logs: deque[dict[str, str]] = deque(maxlen=500)
        self.log_handler = AppLogHandler(self.logs)
        self.event_bus = EventBus()
        self.database = Database(settings.database_url)
        self.parser_catalog = load_merged_parser_catalog(
            settings.system_indexer_parser_config,
            settings.indexer_parser_config,
        )
        self.indexers = ()
        self.repository = SqlAlchemyMediaRepository(self.database)
        self.artist_service = ArtistService(repository=self.repository)
        self.task_executors = TaskExecutorRegistry()
        self.task_manager = TaskManager(
            repository=self.repository,
            executors=self.task_executors,
            log=self.add_log,
        )
        self.task_executors.register(
            "PLAYLIST_TRACK_DOWNLOAD",
            PlaylistTrackDownloadExecutor(self),
        )
        self.task_executors.register("SEARCH_SITE", SearchSiteExecutor(self))
        self.task_executors.register("SEARCH_MEDIA", SearchMediaExecutor(self))
        self.task_executors.register(
            "SEARCH_SITE_CANDIDATES",
            SearchSiteCandidatesExecutor(self),
        )
        self.task_executors.register(
            "DOWNLOAD_ITEM_SCRAPE",
            DownloadItemScrapeExecutor(self),
        )
        self.task_executors.register("FILE_ORGANIZE", FileOrganizeExecutor(self))
        self.task_executors.register(
            "DOWNLOAD_REFRESH_LIBRARY",
            DownloadRefreshLibraryExecutor(self),
        )
        self.task_executors.register("MANUAL_SCRAPE", ManualScrapeExecutor(self))
        self.scheduler = SubscriptionScheduler(
            repository=self.repository,
            interval_minutes=settings.subscription_check_interval_minutes,
            enabled=settings.subscriptions_enabled,
        )
        self.downloader: QBittorrentClient | None = None
        self.metadata = MetadataCascade(
            [
                MultiSourceMusicProvider(source_gate=self.run_metadata_source),
                NetEaseMusicProvider(),
                MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent),
            ]
        )
        self.spotify = SpotifyClient()
        self.public_playlist_importer = PublicPlaylistImporter()
        self.oauth_states: dict[str, str] = {}
        self._oauth_state_ttl: dict[str, float] = {}
        self.playlist_import_previews: dict[str, PublicPlaylist] = {}
        self._preview_ttl: dict[str, float] = {}
        self.artist_build_lock = asyncio.Lock()
        self.artist_build_started_at: datetime | None = None
        self.artist_build_finished_at: datetime | None = None
        self.artist_build_last_error: str | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self.scraping_metadata = MetadataCascade(
            [MultiSourceMusicProvider(source_gate=self.run_metadata_source)]
        )
        self.scraper = LocalMusicScraper(
            metadata=self.scraping_metadata,
            tag_writer=MutagenTagWriter(),
            artist_service=self.artist_service,
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
            search_runner=self.search_indexer,
        )
        self.download_polling_task: asyncio.Task[None] | None = None
        self.music_library_sync_task: asyncio.Task[None] | None = None
        self.metadata_site_search_task: MetadataSiteSearchTask | None = None
        self.metadata_site_search_worker: asyncio.Task[None] | None = None

    async def reload_indexers(self) -> None:
        self.reload_parser_catalog()
        sites = [_site_payload(site) for site in await self.repository.list_indexer_sites()]
        system_settings = await self.repository.get_system_settings()
        proxy_url = _proxy_url(system_settings)
        self.indexers = build_nexusphp_indexers(
            sites,
            self.parser_catalog,
            proxy_url=proxy_url,
        )
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
        self.parser_catalog = load_merged_parser_catalog(
            self.settings.system_indexer_parser_config,
            self.settings.indexer_parser_config,
        )

    async def search_indexer(
        self,
        indexer: object,
        query: str,
        limit: int,
    ) -> tuple[str, tuple[SearchResult, ...]]:
        return await _search_indexer(self, indexer, query, limit)

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

    async def run_metadata_source(
        self,
        source: str,
        runner: Callable[[], Awaitable[Any]],
    ) -> Any:
        return await self.task_manager.run_exclusive(
            task_type="METADATA_SOURCE",
            resource_keys=[await _metadata_source_resource_key(self, source)],
            payload={"source": source},
            runner=runner,
            wait_log_message=f"Metadata source waiting for resources: source={source}",
        )

    def add_log(self, category: str, message: str, level: str = "INFO") -> None:
        self.logs.appendleft(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "message": message,
                "category": category,
            }
        )

    @staticmethod
    def _prune_expired(
        data: dict[str, object],
        ttl_map: dict[str, float],
        ttl_seconds: float,
    ) -> None:
        now = time.time()
        expired = [k for k, t in ttl_map.items() if now - t > ttl_seconds]
        for k in expired:
            data.pop(k, None)
            ttl_map.pop(k, None)


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
        migrated_playlist_track_keys = await state.repository.migrate_playlist_track_source_keys()
        if migrated_playlist_track_keys:
            state.add_log(
                "playlist",
                "Migrated playlist track source keys: "
                f"count={migrated_playlist_track_keys}",
            )
        migrated_waiting_tracks = await state.repository.reset_waiting_playlist_tracks()
        if migrated_waiting_tracks:
            state.add_log(
                "playlist",
                f"Reset legacy waiting playlist tracks to pending: count={migrated_waiting_tracks}",
            )
        # Auto-build artist library from existing media files if empty (background,
        # so startup does not block on MusicBrainz API calls)
        artists = await state.repository.list_all_artists()
        if not artists:
            state.add_log("artist", "歌手库为空，后台自动构建中…", "INFO")
            task = asyncio.create_task(
                _auto_build_artist_library(state),
                name="musicpilot-startup-artist-build",
            )
            state._background_tasks.add(task)
            task.add_done_callback(state._background_tasks.discard)
        await state.reload_indexers()
        await state.reload_downloader()
        await state.reload_notifiers()
        await _restore_playlist_download_tasks(state)
        await _restore_pending_download_item_scrapes(state)
        state.pipeline.start()
        state.task_manager.start()
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
        await state.task_manager.stop()
        if state.metadata_site_search_worker is not None:
            state.metadata_site_search_worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.metadata_site_search_worker
        for task in state._background_tasks:
            task.cancel()
        for task in state._background_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for bot in state.bots:
            await bot.stop()
        state.scheduler.stop()
        await state.pipeline.stop()
        if state.downloader is not None:
            await state.downloader.close()
        await state.spotify.close()
        await state.public_playlist_importer.close()
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

    @app.get("/api/about", response_model=AboutResponse)
    async def about() -> AboutResponse:
        return AboutResponse(
            app=settings.app_name,
            version=_current_app_version(),
            repository_name="lzcer/MusicPilot",
            repository_url="https://github.com/lzcer/MusicPilot",
            description="用于自动化处理音乐文件的搜索、元数据刮削、整理等流程。灵感来自于MoviePilot。",
            license="GPL-3.0-only",
        )

    @app.get("/api/dashboard", response_model=DashboardResponse)
    async def dashboard() -> DashboardResponse:
        summary = await state.repository.dashboard_summary()
        return _dashboard_response(summary)

    @app.get("/api/system-tasks", response_model=list[SystemTaskResponse])
    async def system_tasks(
        status: str = Query(default="WAIT", pattern="^(WAIT|RUNNING|FAILED|SLOW)$"),
        limit: int = Query(default=200, ge=1, le=500),
    ) -> list[SystemTaskResponse]:
        if status == "SLOW":
            tasks = await state.repository.list_slow_running_system_tasks(limit=limit)
        else:
            tasks = await state.repository.list_system_tasks(status=status, limit=limit)
        return [_system_task_response(item) for item in tasks]

    @app.post("/api/system-tasks/interrupt", response_model=SystemTaskInterruptResponse)
    async def interrupt_system_tasks(
        payload: SystemTaskInterruptRequest,
    ) -> SystemTaskInterruptResponse:
        ids = sorted(set(payload.ids))
        existing = await state.repository.list_system_tasks_by_ids(ids)
        existing_by_id = {int(task.id): task for task in existing}
        slow_tasks = await state.repository.list_slow_running_system_tasks(limit=500)
        slow_task_ids = {int(task.id) for task in slow_tasks}
        slow_running_ids = [
            task_id
            for task_id in ids
            if existing_by_id.get(task_id) is not None
            and existing_by_id[task_id].status == "RUNNING"
            and task_id in slow_task_ids
        ]
        waiting_ids = [
            task_id
            for task_id in ids
            if existing_by_id.get(task_id) is not None
            and existing_by_id[task_id].status == "WAIT"
        ]
        interrupted = await state.repository.interrupt_waiting_system_tasks(
            waiting_ids,
            error_message="Task interrupted by user.",
        )
        force_interrupted = await state.repository.interrupt_running_system_tasks(
            slow_running_ids,
            error_message="Task force interrupted by user.",
        )
        if force_interrupted:
            await state.task_manager.force_interrupt_system_tasks(
                [int(task.id) for task in force_interrupted]
            )
        interrupted.extend(force_interrupted)
        for task in interrupted:
            await _sync_interrupted_system_task(state, task)
        if interrupted:
            await state.task_manager.wake()
            state.add_log(
                "task",
                f"System task interrupted: ids={','.join(str(task.id) for task in interrupted)}",
                "WARNING",
            )
        interrupted_ids = [int(task.id) for task in interrupted]
        return SystemTaskInterruptResponse(
            interrupted_ids=interrupted_ids,
            skipped_ids=[
                task_id
                for task_id in ids
                if task_id in existing_by_id and task_id not in interrupted_ids
            ],
            not_found_ids=[task_id for task_id in ids if task_id not in existing_by_id],
        )

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
        exclude = await _get_exclude_keywords(state)
        results = _filter_by_exclude_keywords(results, exclude)
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
                    metadata=result.metadata,
                )
                for result in results
            ],
        )

    @app.get("/api/metadata/search", response_model=MetadataSearchResponse)
    async def metadata_search(
        query: str,
        limit: int = 10,
        artist: str | None = None,
    ) -> MetadataSearchResponse:
        artist_text = artist.strip() if artist else None
        aggregated = await _search_media_candidates(
            state,
            query,
            limit,
            artist=artist_text,
            log_category="metadata",
        )
        query_text = f"{query} / {artist_text}" if artist_text else query
        state.add_log(
            "metadata",
            f"Metadata search completed: {query_text}, {len(aggregated)} candidate group(s)",
        )
        return MetadataSearchResponse(query=query, artist=artist_text, candidates=aggregated)

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
                *(
                    _search_indexer(state, indexer, keyword, payload.limit)
                    for indexer in indexers
                ),
                return_exceptions=True,
            )
            for group in groups:
                if isinstance(group, Exception):
                    state.add_log("search", f"Metadata site search failed: {group}", "ERROR")
                    continue
                raw_results.extend(group[1])
        merged = _dedupe_results(raw_results)
        exclude = await _get_exclude_keywords(state)
        merged = _filter_by_exclude_keywords(merged, exclude)
        filtered = await _filter_by_artist_with_aliases(state, merged, payload.media.artist)
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
                asyncio.create_task(_search_indexer(state, indexer, query, limit))
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
                            "metadata": result.metadata,
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
            submitted = await _submit_torrent_to_downloader(
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
        if submitted.torrent_hash:
            task_changes["torrent_hash"] = submitted.torrent_hash
        task = await state.repository.update_download_task(task.id, **task_changes)
        item_ids = await _record_submitted_torrent_items(
            state,
            task.id if task else None,
            submitted.torrent_data,
        )
        await _schedule_download_task_item_scraping(state, task.id if task else None, item_ids)
        await _send_event_notifications(state, "download", task)
        state.add_log("download", f"Download submitted: {payload.title}")
        return DownloadResponse(
            status="submitted",
            task_id=task.id if task else None,
            torrent_hash=submitted.torrent_hash or None,
        )

    @app.get("/api/downloads", response_model=list[DownloadTaskResponse])
    async def downloads() -> list[DownloadTaskResponse]:
        tasks = await state.repository.list_download_tasks()
        return [_download_task_response(item) for item in tasks]

    @app.get("/api/downloads/{task_id}/items", response_model=list[DownloadTaskItemResponse])
    async def download_items(task_id: int) -> list[DownloadTaskItemResponse]:
        task = await state.repository.get_download_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Download task not found.")
        items = await state.repository.list_download_task_items(task_id)
        return [_download_task_item_response(item) for item in items]

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
        await _mark_playlist_tracks_for_deleted_download_task(state, task_id)
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
        proxy_url = None
        if payload.use_proxy:
            system_settings = await state.repository.get_system_settings()
            proxy_url = _proxy_url(system_settings)
        crawler = NexusPHPCrawler(
            NexusPHPSiteConfig(
                name=payload.name,
                base_url=payload.base_url,
                cookie=payload.cookie,
                user_agent=payload.user_agent,
                parser=parser,
                max_concurrency=payload.max_concurrency,
            ),
            proxy_url=proxy_url,
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
        _validate_downloader_paths(payload)
        if not payload.password:
            raise HTTPException(status_code=422, detail="Password is required.")
        downloader = await state.repository.upsert_downloader(payload=_downloader_payload(payload))
        await state.reload_downloader()
        return _downloader_response(downloader)

    @app.put("/api/settings/downloaders/{downloader_id}", response_model=DownloaderResponse)
    async def update_downloader(
        downloader_id: str,
        payload: DownloaderCreateRequest,
    ) -> DownloaderResponse:
        if await state.repository.get_downloader(downloader_id) is None:
            raise HTTPException(status_code=404, detail="Downloader not found.")
        _validate_downloader_paths(payload)
        downloader = await state.repository.upsert_downloader(
            downloader_id=downloader_id,
            payload=_downloader_payload(payload),
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
        path_error = _downloader_path_error(payload)
        if path_error is not None:
            return TestResponse(ok=False, message=path_error)
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
            download_path=payload.download_path.strip(),
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

    @app.get("/api/settings/database/export")
    async def export_database() -> StreamingResponse:
        filename = f"musicpilot-database-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
        fd, path_name = tempfile.mkstemp(prefix="musicpilot-database-", suffix=".zip")
        os.close(fd)
        export_path = Path(path_name)
        try:
            await DatabaseMigrationService(state.database).export_zip_to_path(export_path)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(export_path.unlink)
            raise
        return StreamingResponse(
            _stream_temporary_file(export_path),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            },
        )

    @app.post("/api/settings/database/import")
    async def import_database(request: Request) -> dict[str, Any]:
        content = await request.body()
        if not content:
            raise HTTPException(status_code=422, detail="导入文件不能为空。")
        await state.task_manager.stop()
        try:
            counts = await DatabaseMigrationService(state.database).import_zip(content)
            await state.reload_indexers()
            await state.reload_downloader()
            await state.reload_notifiers()
            state.add_log("settings", "Database imported")
        except DatabaseMigrationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            state.task_manager.start()
        return {"status": "ok", "tables": counts}

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
            client = build_media_server_client(payload)
            await client.ping()
        except Exception as exc:  # noqa: BLE001
            return TestResponse(ok=False, message=f"媒体服务器连接失败：{exc}")
        return TestResponse(ok=True, message="媒体服务器连接成功")

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

    @app.get("/api/music-platforms", response_model=list[MusicPlatformResponse])
    async def music_platforms() -> list[MusicPlatformResponse]:
        rows = await state.repository.list_music_platform_connections()
        return [
            _music_platform_response(item)
            for item in rows
            if item.platform != "url_import"
        ]

    @app.post(
        "/api/music-platforms/connect/start",
        response_model=MusicPlatformConnectResponse,
        status_code=201,
    )
    async def start_music_platform_connect(
        payload: MusicPlatformConnectRequest,
    ) -> MusicPlatformConnectResponse:
        connection = await state.repository.create_music_platform_connection(
            platform=payload.platform,
            client_id=payload.client_id.strip(),
            client_secret=payload.client_secret.strip(),
            redirect_uri=payload.redirect_uri.strip(),
            scopes=list(SPOTIFY_PLAYLIST_SCOPES),
        )
        oauth_state = token_urlsafe(24)
        AppState._prune_expired(state.oauth_states, state._oauth_state_ttl, 600)
        state.oauth_states[oauth_state] = connection.id
        state._oauth_state_ttl[oauth_state] = time.time()
        authorization_url = state.spotify.authorization_url(
            client_id=connection.client_id,
            redirect_uri=connection.redirect_uri,
            state=oauth_state,
            scopes=SPOTIFY_PLAYLIST_SCOPES,
        )
        return MusicPlatformConnectResponse(
            connection_id=connection.id,
            authorization_url=authorization_url,
        )

    @app.post(
        "/api/music-platforms/{connection_id}/reauthorize/start",
        response_model=MusicPlatformConnectResponse,
    )
    async def start_music_platform_reauthorize(
        connection_id: str,
    ) -> MusicPlatformConnectResponse:
        connection = await state.repository.get_music_platform_connection(connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Music platform connection not found.")
        if connection.platform != "spotify":
            raise HTTPException(status_code=422, detail="Unsupported music platform.")
        oauth_state = token_urlsafe(24)
        AppState._prune_expired(state.oauth_states, state._oauth_state_ttl, 600)
        state.oauth_states[oauth_state] = connection.id
        state._oauth_state_ttl[oauth_state] = time.time()
        authorization_url = state.spotify.authorization_url(
            client_id=connection.client_id,
            redirect_uri=connection.redirect_uri,
            state=oauth_state,
            scopes=_spotify_authorization_scopes(connection),
        )
        return MusicPlatformConnectResponse(
            connection_id=connection.id,
            authorization_url=authorization_url,
        )

    @app.get("/api/integrations/spotify/callback", response_class=HTMLResponse)
    async def spotify_callback(
        code: str | None = None,
        oauth_state: str | None = Query(default=None, alias="state"),
        error: str | None = None,
    ) -> HTMLResponse:
        if error:
            return _oauth_html("Spotify authorization failed", error, status_code=400)
        if not code or not oauth_state:
            return _oauth_html(
                "Spotify authorization failed",
                "Missing callback parameters.",
                status_code=400,
            )
        connection_id = state.oauth_states.pop(oauth_state, None)
        state._oauth_state_ttl.pop(oauth_state, None)
        if connection_id is None:
            return _oauth_html(
                "Spotify authorization failed",
                "Authorization state expired.",
                status_code=400,
            )
        connection = await state.repository.get_music_platform_connection(connection_id)
        if connection is None:
            return _oauth_html(
                "Spotify authorization failed",
                "Music platform connection not found.",
                status_code=404,
            )
        try:
            token_payload = await state.spotify.exchange_code(
                client_id=connection.client_id,
                client_secret=connection.client_secret,
                redirect_uri=connection.redirect_uri,
                code=code,
            )
            access_token = str(token_payload.get("access_token") or "")
            if not access_token:
                raise RuntimeError("Spotify did not return an access token.")
            refresh_token = str(
                token_payload.get("refresh_token") or connection.refresh_token or ""
            )
            profile: dict[str, Any] = {}
            profile_warning: str | None = None
            try:
                profile = await state.spotify.profile(access_token)
            except Exception as exc:  # noqa: BLE001
                profile_warning = str(exc)
                state.add_log(
                    "playlist",
                    f"Spotify profile lookup skipped for {connection.id}: {exc}",
                    "WARNING",
                )
            display_name = str(
                profile.get("display_name")
                or profile.get("id")
                or connection.display_name
                or "Spotify"
            )
            updated = await state.repository.update_music_platform_connection(
                connection.id,
                display_name=display_name,
                external_user_id=_optional_string(profile.get("id")),
                access_token=access_token,
                refresh_token=refresh_token or None,
                scopes=str(token_payload.get("scope") or " ".join(SPOTIFY_PLAYLIST_SCOPES)).split(),
                status="connected",
                access_token_expires_at=token_expiry(token_payload.get("expires_in")),
                refresh_token_expires_at=refresh_token_expiry(),
                last_error=profile_warning,
                payload={"profile": profile, "profile_warning": profile_warning},
            )
            if updated is None:
                raise RuntimeError("Music platform connection disappeared.")
        except Exception as exc:  # noqa: BLE001
            await state.repository.update_music_platform_connection(
                connection.id,
                status="failed",
                last_error=str(exc),
            )
            return _oauth_html("Spotify authorization failed", str(exc), status_code=502)
        return _oauth_html(
            "Spotify connected",
            "You can close this window and return to MusicPilot.",
        )

    @app.delete("/api/music-platforms/{connection_id}", status_code=204)
    async def delete_music_platform(connection_id: str) -> None:
        deleted = await state.repository.delete_music_platform_connection(connection_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Music platform connection not found.")

    @app.get("/api/playlists", response_model=list[PlaylistResponse])
    async def playlists() -> list[PlaylistResponse]:
        rows = await state.repository.list_playlists()
        return [await _playlist_response(state, item) for item in rows]

    @app.get("/api/playlists/available", response_model=list[PlaylistAvailableResponse])
    async def available_playlists(connection_id: str) -> list[PlaylistAvailableResponse]:
        connection = await _connected_music_platform_or_404(state, connection_id)
        access_token = await _spotify_access_token(state, connection)
        try:
            items = await state.spotify.playlists(access_token)
        except SpotifyAPIError as exc:
            await _mark_spotify_connection_error(state, connection.id, exc)
            raise _spotify_http_exception(exc) from exc
        await state.repository.update_music_platform_connection(
            connection.id,
            last_synced_at=datetime.now(UTC),
            last_error=None,
        )
        return [_spotify_playlist_response(item) for item in items]

    @app.post("/api/playlists/import", response_model=PlaylistImportResponse, status_code=201)
    async def import_playlists(payload: PlaylistImportRequest) -> PlaylistImportResponse:
        connection = await _connected_music_platform_or_404(state, payload.connection_id)
        access_token = await _spotify_access_token(state, connection)
        selected_ids = set(payload.external_ids)
        try:
            available = await state.spotify.playlists(access_token)
        except SpotifyAPIError as exc:
            await _mark_spotify_connection_error(state, connection.id, exc)
            raise _spotify_http_exception(exc) from exc
        by_id = {str(item.get("id") or ""): item for item in available if item.get("id")}
        imported: list[PlaylistResponse] = []
        for external_id in payload.external_ids:
            item = by_id.get(external_id)
            if item is None:
                continue
            playlist = await _import_spotify_playlist(state, connection, access_token, item)
            imported.append(await _playlist_response(state, playlist))
        if len(imported) != len(selected_ids):
            state.add_log(
                "playlist",
                "Some Spotify playlists were not found during import: "
                f"requested={len(selected_ids)}, imported={len(imported)}",
                "WARNING",
            )
        return PlaylistImportResponse(playlists=imported)

    @app.post(
        "/api/playlists/parse-url",
        response_model=list[PlaylistImportUrlPreviewResponse],
    )
    async def parse_playlist_url(
        payload: PlaylistImportUrlPreviewRequest,
    ) -> list[PlaylistImportUrlPreviewResponse]:
        settings_payload = await state.repository.get_system_settings()
        try:
            parsed = await state.public_playlist_importer.parse(
                payload.url,
                proxy_url=_proxy_url(settings_payload),
            )
        except UnsupportedPublicPlaylistURL as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PublicPlaylistParseError as exc:
            raise HTTPException(status_code=502, detail=f"歌单解析失败：{exc}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"歌单页面请求失败：{exc}") from exc
        import_token = token_urlsafe(24)
        AppState._prune_expired(state.playlist_import_previews, state._preview_ttl, 1800)
        state.playlist_import_previews[import_token] = parsed
        state._preview_ttl[import_token] = time.time()
        return [_playlist_url_preview_response(import_token, parsed)]

    @app.post("/api/playlists/import-url", response_model=PlaylistImportResponse, status_code=201)
    async def import_playlist_url(payload: PlaylistImportUrlRequest) -> PlaylistImportResponse:
        import_token = payload.import_token.strip()
        parsed = state.playlist_import_previews.pop(import_token, None) if import_token else None
        if parsed is not None:
            state._preview_ttl.pop(import_token, None)
        if parsed is None:
            url = payload.url.strip()
            if not url:
                raise HTTPException(status_code=409, detail="请先解析歌单链接。")
            settings_payload = await state.repository.get_system_settings()
            try:
                parsed = await state.public_playlist_importer.parse(
                    url,
                    proxy_url=_proxy_url(settings_payload),
                )
            except UnsupportedPublicPlaylistURL as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except PublicPlaylistParseError as exc:
                raise HTTPException(status_code=502, detail=f"歌单解析失败：{exc}") from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"歌单页面请求失败：{exc}") from exc
        playlist = await _import_public_playlist(state, parsed)
        return PlaylistImportResponse(playlists=[await _playlist_response(state, playlist)])

    @app.get("/api/playlists/{playlist_id}/tracks", response_model=PlaylistTrackPageResponse)
    async def playlist_tracks(
        playlist_id: int,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        title: str | None = Query(default=None),
        artist: str | None = Query(default=None),
        download_status: str | None = Query(default=None),
        exists_in_library: bool | None = Query(default=None),
    ) -> PlaylistTrackPageResponse:
        request_started_at = time.perf_counter()
        playlist_started_at = time.perf_counter()
        playlist = await state.repository.get_playlist(playlist_id)
        playlist_elapsed_ms = _elapsed_ms(playlist_started_at)
        if playlist is None:
            raise HTTPException(status_code=404, detail="Playlist not found.")
        tracks_started_at = time.perf_counter()
        tracks, total = await state.repository.list_playlist_tracks_page(
            playlist_id,
            offset=_page_offset(page, page_size),
            limit=page_size,
            title=_optional_string(title),
            artist=_optional_string(artist),
            download_status=_optional_string(download_status),
            exists_in_library=exists_in_library,
        )
        tracks_elapsed_ms = _elapsed_ms(tracks_started_at)
        elapsed_ms = _elapsed_ms(request_started_at)
        if elapsed_ms >= SLOW_API_OPERATION_SECONDS * 1000:
            logger.warning(
                "Slow playlist tracks request: playlist_id=%s page=%s page_size=%s "
                "total=%s rows=%s elapsed_ms=%.1f get_playlist_ms=%.1f "
                "list_tracks_ms=%.1f title_filter=%s artist_filter=%s "
                "download_status=%r exists_in_library=%r",
                playlist_id,
                page,
                page_size,
                total,
                len(tracks),
                elapsed_ms,
                playlist_elapsed_ms,
                tracks_elapsed_ms,
                bool(_optional_string(title)),
                bool(_optional_string(artist)),
                _optional_string(download_status),
                exists_in_library,
            )
        return PlaylistTrackPageResponse(
            items=[_playlist_track_response(item) for item in tracks],
            total=total,
            page=page,
            page_size=page_size,
        )

    @app.patch(
        "/api/playlists/{playlist_id}/tracks/{track_id}",
        response_model=PlaylistTrackResponse,
    )
    async def update_playlist_track_metadata(
        playlist_id: int,
        track_id: int,
        payload: PlaylistTrackUpdateRequest,
    ) -> PlaylistTrackResponse:
        track = await state.repository.get_playlist_track(track_id)
        if track is None or track.playlist_id != playlist_id:
            raise HTTPException(status_code=404, detail="Playlist track not found.")
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="歌名不能为空。")
        updated = await state.repository.update_playlist_track(
            track_id,
            title=title,
            artist=_optional_string(payload.artist),
            album=_optional_string(payload.album),
            last_error=None,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Playlist track not found.")
        await _refresh_playlist_library_matches(state, playlist_id)
        refreshed = await state.repository.get_playlist_track(track_id)
        return _playlist_track_response(refreshed or updated)

    @app.delete("/api/playlists/{playlist_id}", status_code=204)
    async def delete_playlist(playlist_id: int) -> None:
        deleted = await state.repository.delete_playlist(playlist_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Playlist not found.")

    @app.post("/api/playlists/{playlist_id}/sync", response_model=PlaylistResponse)
    async def sync_playlist(playlist_id: int) -> PlaylistResponse:
        playlist = await state.repository.get_playlist(playlist_id)
        if playlist is None:
            raise HTTPException(status_code=404, detail="Playlist not found.")
        if playlist.platform_connection_id == "url_import":
            source_url = _optional_string(playlist.raw_payload.get("source_url"))
            if not source_url:
                raise HTTPException(status_code=409, detail="该歌单缺少原始链接，请重新导入。")
            settings_payload = await state.repository.get_system_settings()
            try:
                parsed = await state.public_playlist_importer.parse(
                    source_url,
                    proxy_url=_proxy_url(settings_payload),
                )
            except UnsupportedPublicPlaylistURL as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except PublicPlaylistParseError as exc:
                raise HTTPException(status_code=502, detail=f"歌单解析失败：{exc}") from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"歌单页面请求失败：{exc}") from exc
            synced = await _import_public_playlist(state, parsed)
            return await _playlist_response(state, synced)
        connection = await _connected_music_platform_or_404(state, playlist.platform_connection_id)
        access_token = await _spotify_access_token(state, connection)
        try:
            items = await state.spotify.playlists(access_token)
        except SpotifyAPIError as exc:
            await _mark_spotify_connection_error(state, connection.id, exc)
            raise _spotify_http_exception(exc) from exc
        source = next(
            (item for item in items if str(item.get("id") or "") == playlist.external_id),
            None,
        )
        if source is None:
            await state.repository.update_playlist(
                playlist.id,
                status="failed",
                last_error="Spotify playlist not found.",
            )
            raise HTTPException(status_code=404, detail="Spotify playlist not found.")
        synced = await _import_spotify_playlist(state, connection, access_token, source)
        return await _playlist_response(state, synced)

    @app.post(
        "/api/playlists/{playlist_id}/sync-to-library",
        response_model=PlaylistLibrarySyncResponse,
    )
    async def sync_playlist_to_library(
        playlist_id: int,
        payload: PlaylistLibrarySyncRequest | None = None,
    ) -> PlaylistLibrarySyncResponse:
        playlist = await state.repository.get_playlist(playlist_id)
        if playlist is None:
            raise HTTPException(status_code=404, detail="Playlist not found.")
        try:
            library_playlist_id, synced_count, mode = await _sync_playlist_to_media_server(
                state,
                playlist,
                media_server_id=payload.media_server_id if payload else None,
                public=payload.public if payload else True,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"媒体服务器歌单同步失败：{exc}") from exc
        return PlaylistLibrarySyncResponse(
            status="synced",
            playlist_id=playlist.id,
            library_playlist_id=library_playlist_id,
            synced_count=synced_count,
            mode=mode,
        )

    @app.post("/api/playlists/{playlist_id}/download", response_model=PlaylistDownloadResponse)
    async def download_playlist(playlist_id: int) -> PlaylistDownloadResponse:
        playlist = await state.repository.get_playlist(playlist_id)
        if playlist is None:
            raise HTTPException(status_code=404, detail="Playlist not found.")
        if playlist.status == "downloading" and await _playlist_has_active_downloads(
            state,
            playlist_id,
        ):
            state.add_log(
                "playlist",
                f"Playlist download already running: playlist_id={playlist_id}",
            )
            return PlaylistDownloadResponse(status="running", playlist_id=playlist_id)
        await state.repository.update_playlist(
            playlist_id,
            status="downloading",
            last_download_started_at=datetime.now(UTC),
            last_error=None,
        )
        state.add_log(
            "playlist",
            f"Playlist download requested: playlist_id={playlist_id}, name={playlist.name}",
        )
        await _download_playlist_tracks(state, playlist_id)
        return PlaylistDownloadResponse(status="started", playlist_id=playlist_id)

    @app.post(
        "/api/playlists/{playlist_id}/tracks/{track_id}/download",
        response_model=PlaylistTrackDownloadResponse,
    )
    async def download_playlist_track(
        playlist_id: int,
        track_id: int,
    ) -> PlaylistTrackDownloadResponse:
        playlist = await state.repository.get_playlist(playlist_id)
        if playlist is None:
            raise HTTPException(status_code=404, detail="Playlist not found.")
        track = await state.repository.get_playlist_track(track_id)
        if track is None or track.playlist_id != playlist_id:
            raise HTTPException(status_code=404, detail="Playlist track not found.")
        if track.download_status in PLAYLIST_TRACK_ACTIVE_STATUSES:
            state.add_log(
                "playlist",
                "Playlist track download already running: "
                f"playlist_id={playlist_id}, track={_playlist_track_log_text(track)}",
            )
            return PlaylistTrackDownloadResponse(
                status="running",
                playlist_id=playlist_id,
                track_id=track_id,
            )
        if not _playlist_track_can_start_download(track):
            raise HTTPException(
                status_code=409,
                detail="该单曲当前状态不允许下载或重试。",
            )
        state.add_log(
            "playlist",
            "Playlist track download requested: "
            f"playlist_id={playlist_id}, track={_playlist_track_log_text(track)}",
        )
        await state.repository.update_playlist(
            playlist_id,
            status="downloading",
            last_download_started_at=datetime.now(UTC),
            last_error=None,
        )
        await _enqueue_playlist_track_download(state, playlist_id, track_id)
        return PlaylistTrackDownloadResponse(
            status="started",
            playlist_id=playlist_id,
            track_id=track_id,
        )

    @app.get("/api/logs", response_model=list[LogEntryResponse])
    async def logs(limit: int = 200) -> list[LogEntryResponse]:
        limited = max(1, min(limit, 500))
        return [LogEntryResponse(**entry) for entry in list(state.logs)[:limited]]

    @app.get("/api/files", response_model=FileListResponse)
    async def source_files(
        path: str = "",
        query: str = "",
        limit: int = 500,
        root_type: str = Query(default="source", pattern="^(source|mapped)$"),
    ) -> FileListResponse:
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        root = _scraping_file_root_or_409(config, root_type)
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
        root = _scraping_file_root_or_409(config, payload.root_type)
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
        raw_paths = payload.paths or [payload.path]
        targets = [_resolve_source_relative_path(root, item) for item in raw_paths]
        missing = [raw_paths[index] for index, target in enumerate(targets) if not target.exists()]
        if missing:
            raise HTTPException(status_code=404, detail=f"文件或目录不存在：{missing[0] or root}")
        source_files = await asyncio.to_thread(_source_audio_files_for_targets, root, targets)
        if not source_files:
            raise HTTPException(status_code=422, detail="目标中没有可整理的音频文件。")
        if len(targets) == 1:
            task_name = targets[0].name or "manual"
        else:
            task_name = "manual batch"
        try:
            task_id = await state.task_manager.enqueue(
                TaskCreate(
                    task_type="MANUAL_SCRAPE",
                    payload={
                        "task_name": task_name,
                        "source_files": [str(item) for item in source_files],
                    },
                    resource_keys=[
                        _scraping_batch_resource_key("manual-scrape", source_files)
                    ],
                )
            )
            task = await state.task_manager.wait_for_task(task_id)
            if task.status != "SUCCEEDED":
                raise RuntimeError(task.error_message or f"Manual scrape failed: {task_name}")
        except Exception as exc:  # noqa: BLE001
            state.add_log("metadata", f"Manual scraping failed for {task_name}: {exc}", "ERROR")
            raise HTTPException(status_code=502, detail=f"整理失败：{exc}") from exc
        return _file_organize_response_from_task_result(task.result or {})

    @app.post("/api/files/manual-organize", response_model=FileOrganizeResponse)
    async def manual_organize_source_file(
        payload: FileManualOrganizeRequest,
    ) -> FileOrganizeResponse:
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        if not config.enabled:
            raise HTTPException(status_code=409, detail="请先在刮削设置中开启刮削。")
        root = _scraping_source_root_or_409(config)
        source_path = _resolve_source_relative_path(root, payload.path)
        source_is_audio = await asyncio.to_thread(
            lambda: source_path.exists() and source_path.is_file() and _is_audio_file(source_path)
        )
        if not source_is_audio:
            raise HTTPException(status_code=404, detail="源音频文件不存在，无法手动整理。")
        metadata = _track_metadata_from_manual_payload(payload)
        exclude_library_paths = await _prepare_source_file_reorganize(
            state,
            source_path,
            config,
        )
        try:
            task_id = await state.task_manager.enqueue(
                TaskCreate(
                    task_type="MANUAL_SCRAPE",
                    payload={
                        "task_name": f"manual metadata {source_path.name}",
                        "source_files": [str(source_path)],
                        "manual_metadata": {
                            str(source_path): [_track_metadata_payload(metadata)],
                        },
                        "exclude_library_paths": [
                            str(path) for path in exclude_library_paths
                        ],
                    },
                    resource_keys=[
                        _scraping_batch_resource_key("manual-scrape", (source_path,))
                    ],
                )
            )
            task = await state.task_manager.wait_for_task(task_id)
            if task.status != "SUCCEEDED":
                raise RuntimeError(
                    task.error_message or f"Manual scrape failed: {source_path.name}"
                )
        except Exception as exc:  # noqa: BLE001
            state.add_log(
                "metadata",
                f"Manual metadata scraping failed for {source_path}: {exc}",
                "ERROR",
            )
            raise HTTPException(status_code=502, detail=f"手动整理失败：{exc}") from exc
        return _file_organize_response_from_task_result(task.result or {})

    @app.post("/api/files/manual-organize-directory", response_model=FileOrganizeResponse)
    async def manual_organize_source_directory(
        payload: FileDirectoryManualOrganizeRequest,
    ) -> FileOrganizeResponse:
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        if not config.enabled:
            raise HTTPException(status_code=409, detail="请先在刮削设置中开启刮削。")
        root = _scraping_source_root_or_409(config)
        source_dir = _resolve_source_relative_path(root, payload.path)
        source_is_dir = await asyncio.to_thread(
            lambda: source_dir.exists() and source_dir.is_dir()
        )
        if not source_is_dir:
            raise HTTPException(status_code=404, detail="源目录不存在，无法手动整理。")
        source_files = await asyncio.to_thread(_source_audio_files, root, source_dir)
        if not source_files:
            raise HTTPException(status_code=422, detail="目录中没有可整理的音频文件。")
        artist = payload.artist.strip()
        album = payload.album.strip()
        contextual_metadata = infer_album_context_metadata(
            list(source_files),
            artist=artist,
            album=album,
        )
        exclude_paths: list[Path] = []
        for source_file in source_files:
            exclude_paths.extend(
                await _prepare_source_file_reorganize(state, source_file, config)
            )
        try:
            task_id = await state.task_manager.enqueue(
                TaskCreate(
                    task_type="MANUAL_SCRAPE",
                    payload={
                        "task_name": f"manual album {source_dir.name}",
                        "source_files": [str(path) for path in source_files],
                        "contextual_metadata": {
                            str(path): _track_metadata_payload(item.metadata)
                            for path, item in contextual_metadata.items()
                        },
                        "exclude_library_paths": [str(path) for path in exclude_paths],
                    },
                    resource_keys=[
                        _scraping_batch_resource_key("manual-scrape", source_files)
                    ],
                )
            )
            task = await state.task_manager.wait_for_task(task_id)
            if task.status != "SUCCEEDED":
                raise RuntimeError(
                    task.error_message or f"Manual scrape failed: {source_dir.name}"
                )
        except Exception as exc:  # noqa: BLE001
            state.add_log(
                "metadata",
                f"Manual album scraping failed for {source_dir}: {exc}",
                "ERROR",
            )
            raise HTTPException(status_code=502, detail=f"目录手动整理失败：{exc}") from exc
        return _file_organize_response_from_task_result(task.result or {})

    @app.get("/api/media", response_model=MediaFilePageResponse)
    async def media_files(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        q: str | None = Query(default=None),
        status: str | None = Query(default=None),
    ) -> MediaFilePageResponse:
        rows, total = await state.repository.list_media_files_page(
            offset=_page_offset(page, page_size),
            limit=page_size,
            query=_optional_string(q),
            status=_optional_string(status),
        )
        return MediaFilePageResponse(
            items=[_media_file_response(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

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

    @app.post("/api/media/retry", response_model=MediaRetryResponse)
    async def retry_media(payload: MediaRetryRequest) -> MediaRetryResponse:
        media_records: list[MediaFile] = []
        for mid in payload.ids:
            rec = await state.repository.get_media_file(mid)
            if rec and rec.source_path:
                media_records.append(rec)
        if not media_records:
            raise HTTPException(status_code=404, detail="未找到可重试的记录")
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        if not config.enabled:
            raise HTTPException(status_code=409, detail="请先在刮削设置中开启刮削")
        source_files = tuple(Path(rec.source_path) for rec in media_records)
        try:
            summary = await _scrape_manual_source_files(
                state, config, f"retry {len(source_files)} files", source_files
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"重试失败：{exc}") from exc
        return MediaRetryResponse(
            total=len(media_records),
            source_files=summary.source_files,
            failed_files=summary.failed_files,
        )

    @app.get("/api/media/metadata-search", response_model=MediaMetadataSearchResponse)
    async def search_media_metadata(
        q: str = Query(min_length=1),
        source: str = Query(default="qmusic"),
        limit: int = Query(default=8, ge=1, le=20),
    ) -> MediaMetadataSearchResponse:
        query = q.strip()
        source_name = source.strip() or "qmusic"
        try:
            results = await _search_manual_metadata_candidates(
                state,
                query=query,
                source=source_name,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"元数据搜索失败：{exc}") from exc
        return MediaMetadataSearchResponse(
            query=query,
            source=source_name,
            results=[_track_metadata_response(item) for item in results],
        )

    @app.post("/api/media/{media_id}/manual-organize", response_model=FileOrganizeResponse)
    async def manual_organize_media(
        media_id: int,
        payload: MediaManualOrganizeRequest,
    ) -> FileOrganizeResponse:
        media = await state.repository.get_media_file(media_id)
        if media is None:
            raise HTTPException(status_code=404, detail="Media record not found.")
        source_path = Path(media.source_path)
        source_is_file = await asyncio.to_thread(
            lambda: source_path.exists() and source_path.is_file()
        )
        if not source_is_file:
            raise HTTPException(status_code=404, detail="源文件不存在，无法手动整理。")
        settings_payload = await state.repository.get_system_settings()
        config = scraping_config_from_payload(settings_payload)
        if not config.enabled:
            raise HTTPException(status_code=409, detail="请先在刮削设置中开启刮削")
        metadata = _track_metadata_from_manual_payload(payload)
        exclude_library_paths = await _prepare_media_record_reorganize(state, media, config)
        try:
            task_id = await state.task_manager.enqueue(
                TaskCreate(
                    task_type="MANUAL_SCRAPE",
                    payload={
                        "task_name": f"manual metadata {source_path.name}",
                        "source_files": [str(source_path)],
                        "manual_metadata": {
                            str(source_path): [_track_metadata_payload(metadata)],
                        },
                        "exclude_library_paths": [
                            str(path) for path in exclude_library_paths
                        ],
                    },
                    resource_keys=[
                        _scraping_batch_resource_key("manual-scrape", (source_path,))
                    ],
                )
            )
            task = await state.task_manager.wait_for_task(task_id)
            if task.status != "SUCCEEDED":
                raise RuntimeError(
                    task.error_message or f"Manual scrape failed: {source_path.name}"
                )
        except Exception as exc:  # noqa: BLE001
            state.add_log(
                "metadata",
                f"Manual metadata scraping failed for {source_path}: {exc}",
                "ERROR",
            )
            raise HTTPException(status_code=502, detail=f"手动整理失败：{exc}") from exc
        return _file_organize_response_from_task_result(task.result or {})

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

    @app.get("/api/music-library", response_model=MusicLibraryTrackPageResponse)
    async def music_library(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        q: str | None = Query(default=None),
    ) -> MusicLibraryTrackPageResponse:
        rows, total, albums, artists = await state.repository.list_music_library_tracks_page(
            offset=_page_offset(page, page_size),
            limit=page_size,
            query=_optional_string(q),
        )
        return MusicLibraryTrackPageResponse(
            items=[_music_library_track_response(item) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
            stats=MusicLibraryStatsResponse(
                songs=total,
                albums=albums,
                artists=artists,
            ),
        )

    @app.post("/api/music-library/sync", response_model=MusicLibraryTrackPageResponse)
    async def sync_music_library(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        q: str | None = Query(default=None),
    ) -> MusicLibraryTrackPageResponse:
        try:
            await _sync_music_library_from_media_server(state)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"媒体服务器音乐库同步失败：{exc}") from exc
        rows, total, albums, artists = await state.repository.list_music_library_tracks_page(
            offset=_page_offset(page, page_size),
            limit=page_size,
            query=_optional_string(q),
        )
        return MusicLibraryTrackPageResponse(
            items=[_music_library_track_response(item) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
            stats=MusicLibraryStatsResponse(
                songs=total,
                albums=albums,
                artists=artists,
            ),
        )

    # ── Artist API ──────────────────────────────────────────────

    @app.get("/api/artists", response_model=ArtistPageResponse)
    async def list_artists(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        q: str | None = Query(default=None),
    ) -> ArtistPageResponse:
        artists, total = await state.repository.list_artists_page(
            offset=_page_offset(page, page_size),
            limit=page_size,
            query=_optional_string(q),
        )
        return ArtistPageResponse(
            items=[await _artist_response(state, item) for item in artists],
            total=total,
            page=page,
            page_size=page_size,
        )

    @app.get("/api/artists/build-status", response_model=ArtistBuildStatusResponse)
    async def artist_build_status() -> ArtistBuildStatusResponse:
        return ArtistBuildStatusResponse(
            running=state.artist_build_lock.locked(),
            started_at=state.artist_build_started_at,
            finished_at=state.artist_build_finished_at,
            last_error=state.artist_build_last_error,
        )

    @app.post("/api/artists/build-library", response_model=BuildArtistLibraryResponse)
    async def build_artist_library() -> BuildArtistLibraryResponse:
        if state.artist_build_lock.locked():
            raise HTTPException(status_code=409, detail="歌手库正在构建中，请稍后重试")
        # Run build in background so it doesn't block shutdown
        task = asyncio.create_task(
            _run_artist_build(state),
            name="musicpilot-artist-build",
        )
        state._background_tasks.add(task)
        task.add_done_callback(state._background_tasks.discard)
        return BuildArtistLibraryResponse(created=-1)

    @app.delete("/api/artists", response_model=ClearArtistLibraryResponse)
    async def clear_artist_library() -> ClearArtistLibraryResponse:
        deleted_aliases, deleted_artists = await state.repository.clear_all_artists()
        state.add_log(
            "artist",
            f"已清空歌手库：删除 {deleted_aliases} 个别名，{deleted_artists} 个歌手。",
            "INFO",
        )
        return ClearArtistLibraryResponse(
            deleted_artists=deleted_artists,
            deleted_aliases=deleted_aliases,
        )

    @app.post("/api/artists/merge", response_model=ArtistResponse, status_code=200)
    async def merge_artists(payload: MergeArtistsRequest) -> ArtistResponse:
        try:
            artist_info = await state.artist_service.merge_artists(
                target_id=payload.target_id,
                source_id=payload.source_id,
            )
            state.add_log(
                "artist",
                f"已合并歌手 {payload.source_id} → {payload.target_id} ({artist_info.name})",
                "INFO",
            )
            return ArtistResponse(
                id=artist_info.id,
                name=artist_info.name,
                normalized_name=artist_info.normalized_name,
                aliases=[ArtistAliasResponse(alias=a) for a in artist_info.aliases],
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/artists/{artist_id}", response_model=ArtistResponse)
    async def update_artist(artist_id: int, payload: UpdateArtistRequest) -> ArtistResponse:
        try:
            artist_info = await state.artist_service.update_artist(
                artist_id,
                name=payload.name,
                aliases=tuple(payload.aliases),
            )
            state.add_log(
                "artist",
                f"已更新歌手 {artist_id}: {artist_info.name}",
                "INFO",
            )
            return ArtistResponse(
                id=artist_info.id,
                name=artist_info.name,
                normalized_name=artist_info.normalized_name,
                aliases=[ArtistAliasResponse(alias=a) for a in artist_info.aliases],
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/artists/alias", status_code=201)
    async def add_artist_alias(payload: AddArtistAliasRequest) -> dict[str, str]:
        try:
            await state.artist_service.add_alias(
                artist_id=payload.artist_id,
                alias=payload.alias,
                source=payload.source,
            )
            return {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/artists/check-aliases", response_model=list[str])
    async def check_artist_aliases(artist: str = "") -> list[str]:
        aliases = await state.artist_service.get_aliases(artist)
        if not aliases:
            return [artist] if artist else []
        return aliases

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
        task = await state.repository.mark_torrent_completed(
            torrent_hash=torrent_hash,
            save_path=download_path,
        )
        await _sync_playlist_tracks_for_download_task(state, task)
        state.add_log("transfer", f"Download completed webhook accepted: {torrent_hash}")
        return {"status": "accepted", "torrent_hash": torrent_hash}

    if settings.static_dir.exists():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")

    return app


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _connected_music_platform_or_404(
    state: AppState,
    connection_id: str,
) -> MusicPlatformConnection:
    connection = await state.repository.get_music_platform_connection(connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Music platform connection not found.")
    if connection.platform != "spotify":
        raise HTTPException(status_code=422, detail="Unsupported music platform.")
    if connection.status != "connected":
        raise HTTPException(status_code=409, detail="Music platform requires reauthorization.")
    return connection


async def _spotify_access_token(state: AppState, connection: MusicPlatformConnection) -> str:
    if connection.access_token and _future_datetime(connection.access_token_expires_at):
        return connection.access_token
    if not connection.refresh_token:
        await state.repository.update_music_platform_connection(
            connection.id,
            status="reauthorization_required",
            last_error="Spotify refresh token is missing.",
        )
        raise HTTPException(status_code=409, detail="Spotify authorization expired.")
    try:
        token_payload = await state.spotify.refresh_token(
            client_id=connection.client_id,
            client_secret=connection.client_secret,
            refresh_token=connection.refresh_token,
        )
    except Exception as exc:  # noqa: BLE001
        await state.repository.update_music_platform_connection(
            connection.id,
            status="reauthorization_required",
            last_error=str(exc),
        )
        raise HTTPException(status_code=409, detail="Spotify authorization expired.") from exc
    access_token = str(token_payload.get("access_token") or "")
    if not access_token:
        await state.repository.update_music_platform_connection(
            connection.id,
            status="reauthorization_required",
            last_error="Spotify refresh did not return an access token.",
        )
        raise HTTPException(status_code=409, detail="Spotify authorization expired.")
    refresh_token = str(token_payload.get("refresh_token") or connection.refresh_token)
    await state.repository.update_music_platform_connection(
        connection.id,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=token_expiry(token_payload.get("expires_in")),
        refresh_token_expires_at=(
            refresh_token_expiry() if refresh_token != connection.refresh_token
            else connection.refresh_token_expires_at
        ),
        status="connected",
        last_error=None,
    )
    return access_token


async def _mark_spotify_connection_error(
    state: AppState,
    connection_id: str,
    exc: SpotifyAPIError,
) -> None:
    changes: dict[str, object] = {"last_error": str(exc)}
    if exc.status_code == 401:
        changes["status"] = "reauthorization_required"
    await state.repository.update_music_platform_connection(connection_id, **changes)


def _spotify_http_exception(exc: SpotifyAPIError) -> HTTPException:
    status_code = 502
    if exc.status_code in {401, 403}:
        status_code = 409
    elif exc.status_code == 429:
        status_code = 429
    return HTTPException(status_code=status_code, detail=str(exc))


def _future_datetime(value: datetime | None) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value > datetime.now(UTC)


def _music_platform_response(item: MusicPlatformConnection) -> MusicPlatformResponse:
    return MusicPlatformResponse(
        id=item.id,
        platform=item.platform,
        display_name=item.display_name,
        external_user_id=item.external_user_id,
        status=item.status,
        redirect_uri=item.redirect_uri,
        scopes=list(item.scopes or []),
        access_token_expires_at=item.access_token_expires_at,
        refresh_token_expires_at=item.refresh_token_expires_at,
        last_synced_at=item.last_synced_at,
        last_error=item.last_error,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _spotify_authorization_scopes(connection: MusicPlatformConnection) -> tuple[str, ...]:
    scopes = list(connection.scopes or [])
    for scope in SPOTIFY_PLAYLIST_SCOPES:
        if scope not in scopes:
            scopes.append(scope)
    return tuple(scopes)


def _spotify_playlist_response(item: dict[str, Any]) -> PlaylistAvailableResponse:
    return PlaylistAvailableResponse(
        external_id=str(item.get("id") or ""),
        name=str(item.get("name") or "Spotify playlist"),
        owner_name=_spotify_owner_name(item),
        description=_optional_string(item.get("description")),
        cover_url=_spotify_first_image_url(item.get("images")),
        track_count=_spotify_playlist_track_count(item),
        raw_payload=item,
    )


def _playlist_url_preview_response(
    import_token: str,
    item: PublicPlaylist,
) -> PlaylistImportUrlPreviewResponse:
    return PlaylistImportUrlPreviewResponse(
        import_token=import_token,
        platform=item.platform,
        external_id=item.external_id,
        name=item.name,
        owner_name=item.owner_name,
        description=item.description,
        cover_url=item.cover_url,
        track_count=len(item.tracks),
    )


async def _playlist_response(state: AppState, item: Playlist) -> PlaylistResponse:
    counts = await state.repository.playlist_track_counts(item.id)
    return PlaylistResponse(
        id=item.id,
        platform_connection_id=item.platform_connection_id,
        platform=item.platform,
        external_id=item.external_id,
        name=item.name,
        owner_name=item.owner_name,
        description=item.description,
        cover_url=item.cover_url,
        track_count=counts["track_count"],
        existing_count=counts["existing_count"],
        waiting_count=counts["waiting_count"],
        submitted_count=counts["submitted_count"],
        failed_count=counts["failed_count"],
        status=item.status,
        last_synced_at=item.last_synced_at,
        last_download_started_at=item.last_download_started_at,
        last_error=item.last_error,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _playlist_track_response(item: PlaylistTrack) -> PlaylistTrackResponse:
    return PlaylistTrackResponse(
        id=item.id,
        playlist_id=item.playlist_id,
        platform=item.platform,
        external_id=item.external_id,
        source_key=item.source_key,
        position=item.position,
        original_title=item.original_title,
        title=item.title,
        artist=item.artist,
        album=item.album,
        duration=item.duration,
        isrc=item.isrc,
        cover_url=item.cover_url,
        exists_in_library=item.exists_in_library,
        matched_library_track_id=item.matched_library_track_id,
        download_status=item.download_status,
        torrent_record_id=item.torrent_record_id,
        last_checked_at=item.last_checked_at,
        last_download_attempt_at=item.last_download_attempt_at,
        last_error=item.last_error,
    )


def _media_file_response(row: MediaFile) -> MediaFileResponse:
    return MediaFileResponse(
        id=row.id,
        torrent_hash=row.torrent_hash,
        source_path=row.source_path,
        library_path=row.library_path,
        operation_type=row.operation_type,
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


async def _artist_response(state: AppState, artist: Artist) -> ArtistResponse:
    raw_aliases = await state.repository.list_artist_aliases(artist.id)
    aliases_resp: list[ArtistAliasResponse] = []
    seen: set[str] = set()
    for alias_name in raw_aliases:
        if alias_name != artist.name and alias_name not in seen:
            seen.add(alias_name)
            aliases_resp.append(ArtistAliasResponse(alias=alias_name, source="merged"))
    return ArtistResponse(
        id=artist.id,
        name=artist.name,
        normalized_name=artist.normalized_name,
        aliases=aliases_resp,
    )


def _page_offset(page: int, page_size: int) -> int:
    return (page - 1) * page_size


async def _import_spotify_playlist(
    state: AppState,
    connection: MusicPlatformConnection,
    access_token: str,
    item: dict[str, Any],
) -> Playlist:
    playlist_payload = _spotify_playlist_response(item)
    playlist = await state.repository.upsert_playlist(
        platform_connection_id=connection.id,
        platform=connection.platform,
        external_id=playlist_payload.external_id,
        name=playlist_payload.name,
        owner_name=playlist_payload.owner_name,
        description=playlist_payload.description,
        cover_url=playlist_payload.cover_url,
        track_count=playlist_payload.track_count,
        raw_payload=item,
    )
    try:
        raw_tracks = await state.spotify.playlist_tracks(access_token, playlist.external_id)
    except SpotifyAPIError as exc:
        await _mark_spotify_connection_error(state, connection.id, exc)
        raise _spotify_http_exception(exc) from exc
    tracks = [
        _spotify_track_payload(entry, index)
        for index, entry in enumerate(raw_tracks, start=1)
    ]
    await state.repository.upsert_playlist_tracks(
        playlist_id=playlist.id,
        platform=connection.platform,
        tracks=[track for track in tracks if track is not None],
    )
    await _refresh_playlist_library_matches(state, playlist.id)
    await state.repository.update_music_platform_connection(
        connection.id,
        last_synced_at=datetime.now(UTC),
        last_error=None,
    )
    state.add_log("playlist", f"Spotify playlist imported: {playlist.name}")
    return await state.repository.get_playlist(playlist.id) or playlist


async def _import_public_playlist(state: AppState, parsed: PublicPlaylist) -> Playlist:
    connection = await state.repository.get_or_create_url_import_connection()
    playlist = await state.repository.upsert_playlist(
        platform_connection_id=connection.id,
        platform=parsed.platform,
        external_id=parsed.external_id,
        name=parsed.name,
        owner_name=parsed.owner_name,
        description=parsed.description,
        cover_url=parsed.cover_url,
        track_count=len(parsed.tracks),
        raw_payload={"source_url": parsed.source_url, "payload": parsed.raw_payload},
    )
    await state.repository.upsert_playlist_tracks(
        playlist_id=playlist.id,
        platform=parsed.platform,
        tracks=[
            {
                "external_id": track.external_id,
                "position": track.position,
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "duration": track.duration,
                "cover_url": track.cover_url,
                "raw_payload": track.raw_payload,
            }
            for track in parsed.tracks
        ],
    )
    await _refresh_playlist_library_matches(state, playlist.id)
    state.add_log(
        "playlist",
        f"Public playlist imported: {parsed.platform}/{parsed.external_id}, "
        f"{len(parsed.tracks)} track(s)",
    )
    return await state.repository.get_playlist(playlist.id) or playlist


def _spotify_track_payload(entry: dict[str, Any], position: int) -> dict[str, Any] | None:
    track = entry.get("track")
    if not isinstance(track, dict):
        return None
    title = str(track.get("name") or "").strip()
    if not title:
        return None
    track_id = str(track.get("id") or "").strip()
    album = track.get("album") if isinstance(track.get("album"), dict) else {}
    external_ids = track.get("external_ids") if isinstance(track.get("external_ids"), dict) else {}
    return {
        "external_id": track_id or f"local:{position}:{title}",
        "position": position,
        "title": title,
        "artist": _spotify_artists(track.get("artists")),
        "album": _optional_string(album.get("name")),
        "duration": _optional_int(track.get("duration_ms")),
        "isrc": _optional_string(external_ids.get("isrc")),
        "cover_url": _spotify_first_image_url(album.get("images")),
        "raw_payload": entry,
    }


def _spotify_owner_name(item: dict[str, Any]) -> str | None:
    owner = item.get("owner")
    if not isinstance(owner, dict):
        return None
    return _optional_string(owner.get("display_name") or owner.get("id"))


def _spotify_playlist_track_count(item: dict[str, Any]) -> int:
    tracks = item.get("tracks")
    if not isinstance(tracks, dict):
        return 0
    return _optional_int(tracks.get("total")) or 0


def _spotify_first_image_url(images: object) -> str | None:
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict):
            url = _optional_string(image.get("url"))
            if url:
                return url
    return None


def _spotify_artists(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    names = [
        str(item.get("name") or "").strip()
        for item in value
        if isinstance(item, dict) and item.get("name")
    ]
    return ", ".join(names) or None


async def _refresh_playlist_library_matches(
    state: AppState,
    playlist_id: int | None = None,
) -> int:
    library_tracks = await state.repository.list_music_library_tracks()
    playlist_tracks = (
        await state.repository.list_playlist_tracks(playlist_id)
        if playlist_id is not None
        else await state.repository.list_all_playlist_tracks()
    )
    checked_at = datetime.now(UTC)
    artist_values_cache: dict[str, set[str]] = {}
    updated = 0
    for track in playlist_tracks:
        match = await _match_library_track(
            state,
            track.title,
            track.artist,
            library_tracks,
            artist_values_cache=artist_values_cache,
        )
        exists = match is not None
        matched_library_track_id = match.id if match is not None else None
        status = "existing" if exists else track.download_status
        if (
            track.exists_in_library == exists
            and track.matched_library_track_id == matched_library_track_id
            and track.download_status == status
        ):
            continue
        await state.repository.update_playlist_track(
            track.id,
            exists_in_library=exists,
            matched_library_track_id=matched_library_track_id,
            download_status=status,
            last_checked_at=checked_at,
        )
        updated += 1
    return updated


async def _restore_playlist_download_tasks(state: AppState) -> None:
    active = 0
    for playlist in await state.repository.list_playlists():
        if playlist.status != "downloading":
            continue
        tracks = await state.repository.list_playlist_tracks(playlist.id)
        if any(track.download_status in PLAYLIST_TRACK_ACTIVE_STATUSES for track in tracks):
            active += 1
        await _update_playlist_download_completion(state, playlist.id)
    if active:
        state.add_log(
            "playlist",
            f"Restored playlist download state: active={active}",
        )


async def _match_library_track(
    state: AppState,
    title: str,
    artist: str | None,
    library_tracks: list[MusicLibraryTrack],
    *,
    artist_values_cache: dict[str, set[str]] | None = None,
) -> MusicLibraryTrack | None:
    normalized_title = normalize_metadata_match_text(title)
    target_artists = await _artist_credit_match_values_cached(state, artist, artist_values_cache)
    if not normalized_title:
        return None
    for item in library_tracks:
        if normalize_metadata_match_text(item.title) != normalized_title:
            continue
        item_artists = await _artist_credit_match_values_cached(
            state,
            item.artist,
            artist_values_cache,
        )
        if not target_artists or _artist_value_sets_match(item_artists, target_artists):
            return item
    return None


async def _match_active_download_task_item(
    state: AppState,
    title: str,
    artist: str | None,
) -> TorrentRecordItem | None:
    normalized_title = normalize_metadata_match_text(title)
    if not normalized_title:
        return None
    compact_title = _compact_search_text(normalized_title)
    for item in await state.repository.list_active_download_task_items():
        if not await _artist_matches(state, item.metadata_artist or item.artist, artist):
            continue
        for candidate in _download_task_item_titles(item):
            candidate_title = normalize_metadata_match_text(candidate)
            if not candidate_title:
                continue
            if candidate_title == normalized_title:
                return item
            if _normalized_contains(candidate_title, normalized_title, compact_title):
                return item
            candidate_compact = _compact_search_text(candidate_title)
            if _normalized_contains(normalized_title, candidate_title, candidate_compact):
                return item
    return None


def _download_task_item_titles(item: TorrentRecordItem) -> list[str]:
    values = [
        item.metadata_title,
        item.parsed_title,
        Path(item.file_name).stem,
    ]
    return [value for value in values if value]


def _playlist_track_can_start_download(track: PlaylistTrack) -> bool:
    if track.exists_in_library:
        return False
    status = track.download_status
    if status in PLAYLIST_TRACK_ACTIVE_STATUSES | PLAYLIST_TRACK_SUCCESS_STATUSES:
        return False
    return status == "pending" or status in PLAYLIST_TRACK_RETRYABLE_STATUSES


def _playlist_track_log_text(track: PlaylistTrack) -> str:
    return (
        "{"
        f"id={track.id}, title={track.title!r}, artist={track.artist!r}, "
        f"album={track.album!r}, status={track.download_status!r}, "
        f"torrent_record_id={track.torrent_record_id!r}"
        "}"
    )


def _media_candidate_log_text(media: MediaCandidateResponse) -> str:
    return (
        "{"
        f"title={media.title!r}, artist={media.artist!r}, "
        f"album={media.album!r}, source={media.source!r}"
        "}"
    )


def _search_result_log_text(result: SearchResult) -> str:
    return (
        "{"
        f"title={result.title!r}, source={result.source!r}, "
        f"seeders={result.seeders}, size_bytes={result.size_bytes}"
        "}"
    )


async def _download_playlist_tracks(state: AppState, playlist_id: int) -> None:
    try:
        playlist = await state.repository.get_playlist(playlist_id)
        playlist_name = playlist.name if playlist is not None else str(playlist_id)
        state.add_log(
            "playlist",
            f"Playlist download started: playlist_id={playlist_id}, name={playlist_name}",
        )
        await _refresh_playlist_library_matches(state, playlist_id)
        tracks = await state.repository.list_playlist_tracks(playlist_id)
        state.add_log(
            "playlist",
            f"Playlist tracks checked: playlist_id={playlist_id}, total={len(tracks)}",
        )
        track_ids_to_enqueue: list[int] = []
        for track in tracks:
            if track.exists_in_library:
                await state.repository.update_playlist_track(
                    track.id, download_status="existing", last_error=None,
                )
                state.add_log(
                    "playlist",
                    "Playlist track skipped, already in library: "
                    f"{_playlist_track_log_text(track)}",
                )
            elif _playlist_track_can_start_download(track):
                track_ids_to_enqueue.append(track.id)

        state.add_log(
            "playlist",
            f"Playlist tracks enqueueing: playlist_id={playlist_id}, "
            f"count={len(track_ids_to_enqueue)}",
        )
        jobs = [
            _enqueue_playlist_track_download(state, playlist_id, track_id)
            for track_id in track_ids_to_enqueue
        ]
        if jobs:
            await asyncio.gather(*jobs)
        state.add_log(
            "playlist",
            f"Playlist tracks enqueued: playlist_id={playlist_id}, name={playlist_name}",
        )
        await _update_playlist_download_completion(state, playlist_id)
    except Exception as exc:  # noqa: BLE001
        await state.repository.update_playlist(playlist_id, status="failed", last_error=str(exc))
        state.add_log("playlist", f"Playlist download failed: {playlist_id}, {exc}", "ERROR")


async def _enqueue_playlist_track_download(
    state: AppState,
    playlist_id: int,
    track_id: int,
) -> str:
    track = await state.repository.get_playlist_track(track_id)
    if track is None:
        return "failed"
    state.add_log("playlist", f"Playlist track preparing queue: {_playlist_track_log_text(track)}")
    if track.download_status == "waiting" and track.last_download_attempt_at is not None:
        attempt_at = track.last_download_attempt_at
    else:
        attempt_at = datetime.now(UTC)
    if not track.exists_in_library and track.download_status not in {
        "submitted",
        "downloading",
        "completed",
        "refreshing_library",
        "library_refreshed",
    }:
        await state.repository.update_playlist_track(
            track.id,
            download_status="queue",
            torrent_record_id=None,
            last_checked_at=datetime.now(UTC),
            last_download_attempt_at=attempt_at,
            last_error=None,
        )
    resource_keys = await _playlist_track_download_resource_keys(state, track)
    state.add_log(
        "playlist",
        "Playlist track queued: "
        f"resource_keys={','.join(resource_keys)}, playlist_id={playlist_id}, "
        f"track={_playlist_track_log_text(track)}",
    )
    task_id = await state.task_manager.enqueue(
        TaskCreate(
            task_type="PLAYLIST_TRACK_DOWNLOAD",
            payload={
                "playlist_id": playlist_id,
                "track_id": track_id,
                "title": track.title,
                "artist": track.artist,
            },
            resource_keys=list(resource_keys),
            idempotency_key=(
                f"playlist-track:{track_id}:download:"
                f"{attempt_at.isoformat(timespec='seconds')}"
            ),
        )
    )
    state.add_log(
        "playlist",
        f"Playlist track system task enqueued: track={track_id}, task={task_id}",
    )
    return "queue"


async def _playlist_track_artist_queue_keys(
    state: AppState,
    track: PlaylistTrack,
) -> tuple[str, ...]:
    artist_names = split_artist_credit(track.artist)
    if not artist_names:
        return (f"track:{track.id}",)
    keys: list[str] = []
    for artist in artist_names:
        canonical = await state.artist_service.get_canonical_name(artist)
        normalized = normalize_artist_name(canonical or artist)
        compact = _compact_search_text(normalized)
        if compact and compact not in keys:
            keys.append(compact)
    return tuple(keys) or (f"track:{track.id}",)


async def _playlist_track_download_resource_keys(
    state: AppState,
    track: PlaylistTrack,
) -> tuple[str, ...]:
    artist_keys = await _playlist_track_artist_queue_keys(state, track)
    if not artist_keys:
        return (f"playlist-track:{track.id}",)
    return tuple(f"artist:{key}" for key in artist_keys)


def _site_resource_key(indexer: object, site_id: str) -> str:
    max_concurrency = _optional_int(
        getattr(getattr(indexer, "config", None), "max_concurrency", 1)
    ) or 1
    max_concurrency = max(1, max_concurrency)
    return f"pool:{max_concurrency}:site:{site_id}"


async def _media_search_resource_key(state: AppState) -> str:
    settings = await state.repository.get_system_settings()
    search_settings = settings.get("search") if isinstance(settings, dict) else {}
    concurrency = _optional_int(
        search_settings.get("metadata_concurrency")
        if isinstance(search_settings, dict)
        else None
    ) or 3
    concurrency = min(max(concurrency, 1), 20)
    return f"pool:{concurrency}:media-search"


async def _metadata_source_resource_key(state: AppState, source: str) -> str:
    settings = await state.repository.get_system_settings()
    search_settings = settings.get("search") if isinstance(settings, dict) else {}
    concurrency = _optional_int(
        search_settings.get("metadata_concurrency")
        if isinstance(search_settings, dict)
        else None
    ) or 3
    concurrency = min(max(concurrency, 1), 20)
    source_key = _compact_search_text(normalize_search_text(source)) or "unknown"
    return f"pool:{concurrency}:metadata-source:{source_key}"


async def _playlist_has_active_downloads(state: AppState, playlist_id: int) -> bool:
    tracks = await state.repository.list_playlist_tracks(playlist_id)
    return any(track.download_status in PLAYLIST_TRACK_ACTIVE_STATUSES for track in tracks)


async def _update_playlist_download_completion(state: AppState, playlist_id: int) -> None:
    playlist = await state.repository.get_playlist(playlist_id)
    if playlist is None or playlist.status != "downloading":
        return
    if await _playlist_has_active_downloads(state, playlist_id):
        return
    await state.repository.update_playlist(playlist_id, status="synced", last_error=None)
    state.add_log("playlist", f"Playlist download finished: playlist_id={playlist_id}")


async def _check_and_download_playlist_track(
    state: AppState, track_id: int,
) -> str:
    track = await state.repository.get_playlist_track(track_id)
    if track is None:
        return "failed"
    state.add_log("playlist", f"Playlist track processing: {_playlist_track_log_text(track)}")

    library_tracks = await state.repository.list_music_library_tracks()
    match = await _match_library_track(state, track.title, track.artist, library_tracks)
    if match is not None:
        await state.repository.update_playlist_track(
            track.id,
            exists_in_library=True,
            matched_library_track_id=match.id,
            download_status="existing",
            last_checked_at=datetime.now(UTC),
            last_error=None,
        )
        state.add_log(
            "playlist",
            "Playlist track exists in library: "
            f"track={_playlist_track_log_text(track)}, library_id={match.id}",
        )
        return "existing"

    active_item = await _match_active_download_task_item(state, track.title, track.artist)
    if active_item is not None:
        task = await state.repository.get_download_task(active_item.torrent_record_id)
        if task is not None:
            await _bind_playlist_track_to_task(
                state,
                track.id,
                task,
                last_error=f"已绑定到下载任务 #{task.id}。",
            )
            state.add_log(
                "playlist",
                "Playlist track bound to existing task: "
                f"track={_playlist_track_log_text(track)}, task_id={task.id}, "
                f"item_id={active_item.id}, task_status={task.status}",
            )
            return _playlist_download_status_for_task(task)

    return await _execute_playlist_download(state, track)


async def _execute_playlist_download(
    state: AppState, track: PlaylistTrack,
) -> str:
    try:
        await state.repository.update_playlist_track(
            track.id,
            download_status="searching",
            last_checked_at=datetime.now(UTC),
            last_download_attempt_at=datetime.now(UTC),
            last_error=None,
        )
        state.add_log(
            "playlist",
            f"Playlist track search started: {_playlist_track_log_text(track)}",
        )
        candidates = await _playlist_download_results(state, track)
        state.add_log(
            "playlist",
            "Playlist track search completed: "
            f"track={_playlist_track_log_text(track)}, candidates={len(candidates)}",
        )
        if not candidates:
            await state.repository.update_playlist_track(
                track.id,
                download_status="not_found",
                last_error="No artist-matched torrent result found.",
            )
            state.add_log(
                "playlist",
                "Playlist track not found, no torrent candidates: "
                f"{_playlist_track_log_text(track)}",
                "WARNING",
            )
            return "not_found"
        last_error: str | None = None
        for index, (result, media) in enumerate(candidates, start=1):
            state.add_log(
                "playlist",
                "Playlist candidate trying: "
                f"track={_playlist_track_log_text(track)}, "
                f"index={index}/{len(candidates)}, "
                f"media={_media_candidate_log_text(media)}, "
                f"result={_search_result_log_text(result)}",
            )
            try:
                task = await _try_playlist_candidate_download(state, track, result, media)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                state.add_log(
                    "playlist",
                    f"Playlist candidate skipped for {track.title}: {exc}",
                    "WARNING",
                )
                continue
            if task is not None:
                return _playlist_download_status_for_task(task)
        await state.repository.update_playlist_track(
            track.id,
            download_status="not_found",
            last_error=last_error or "No candidate torrent contains the target track.",
        )
        state.add_log(
            "playlist",
            "Playlist track not found in candidate torrents: "
            f"track={_playlist_track_log_text(track)}, tried={len(candidates)}, "
            f"last_error={last_error or ''}",
            "WARNING",
        )
        return "not_found"
    except Exception as exc:  # noqa: BLE001
        await state.repository.update_playlist_track(
            track.id,
            download_status="failed",
            last_error=str(exc),
        )
        state.add_log(
            "playlist",
            f"Playlist track download failed: track={_playlist_track_log_text(track)}, error={exc}",
            "ERROR",
        )
        return "failed"


async def _playlist_download_results(
    state: AppState,
    track: PlaylistTrack,
) -> list[tuple[SearchResult, MediaCandidateResponse]]:
    if not state.indexers:
        return []
    results: list[tuple[SearchResult, MediaCandidateResponse]] = []
    seen: set[tuple[str, str]] = set()
    for media in await _playlist_media_candidates(state, track):
        media_results = await _metadata_download_results(state, media)
        state.add_log(
            "playlist",
            "Playlist media candidate results: "
            f"track={_playlist_track_log_text(track)}, "
            f"media={_media_candidate_log_text(media)}, results={len(media_results)}",
        )
        for result in media_results:
            key = result.identity_key
            if key in seen:
                continue
            seen.add(key)
            results.append((result, media))
    return results


async def _playlist_media_candidates(
    state: AppState,
    track: PlaylistTrack,
) -> list[MediaCandidateResponse]:
    query = str(track.title or "").strip()
    artist = _optional_string(track.artist)
    aggregated = await _search_media_candidates(
        state,
        query,
        10,
        artist=artist,
        log_category="playlist",
        use_task_manager=False,
    )
    matched = [
        candidate
        for candidate in aggregated
        if await _artist_matches(state, candidate.artist, track.artist)
    ]
    fallback = _playlist_media_candidate(track)
    state.add_log(
        "playlist",
        f"Playlist metadata candidates: track={_playlist_track_log_text(track)}, "
        f"aggregated={len(aggregated)}, artist_matched={len(matched)}",
    )
    if track.artist:
        return (matched or [fallback])[:10]
    return (aggregated or [fallback])[:10]


async def _metadata_download_results(
    state: AppState,
    media: MediaCandidateResponse,
) -> list[SearchResult]:
    keywords = _metadata_search_keywords(media)
    if not keywords:
        return []
    raw_results: list[SearchResult] = []
    groups = await asyncio.gather(
        *(
            _search_site_candidates(state, indexer, media, keywords, 50, use_task_manager=False)
            for indexer in state.indexers
        ),
        return_exceptions=True,
    )
    for group in groups:
        if isinstance(group, Exception):
            state.add_log("playlist", f"Playlist track search failed: {group}", "WARNING")
            continue
        raw_results.extend(group[1])
    deduped = _dedupe_results(raw_results)
    exclude = await _get_exclude_keywords(state)
    deduped = _filter_by_exclude_keywords(deduped, exclude)
    filtered = await _filter_by_artist_with_aliases(state, deduped, media.artist)
    ranked = sorted(filtered, key=lambda item: item.seeders, reverse=True)
    state.add_log(
        "search",
        "Playlist site search completed: "
        f"media={_media_candidate_log_text(media)}, raw={len(raw_results)}, "
        f"deduped={len(deduped)}, artist_filtered={len(filtered)}",
    )
    return ranked


async def _try_playlist_candidate_download(
    state: AppState,
    track: PlaylistTrack,
    result: SearchResult,
    media: MediaCandidateResponse,
) -> TorrentRecord | None:
    resource = _search_result_response(result).model_dump()
    state.add_log(
        "playlist",
        "Playlist candidate task creating: "
        f"track={_playlist_track_log_text(track)}, result={_search_result_log_text(result)}",
    )
    task = await state.repository.create_download_task(
        resource=resource,
        media_metadata=media.model_dump(),
        selected_site_ids=[],
        category="MusicPilot",
    )
    try:
        torrent_data = await _download_playlist_candidate_torrent_file(state, resource)
        state.add_log(
            "playlist",
            "Playlist candidate torrent downloaded: "
            f"task={task.id}, bytes={len(torrent_data)}, title={task.name}",
        )
        item_ids = await _record_submitted_torrent_items(
            state,
            task.id,
            torrent_data,
            playlist_track_id=None,
        )
        state.add_log(
            "playlist",
            "Playlist candidate torrent parsed: "
            f"task={task.id}, audio_items={len(item_ids)}, "
            f"track={_playlist_track_log_text(track)}",
        )
        if not item_ids:
            state.add_log(
                "playlist",
                f"Playlist candidate has no audio items: task={task.id}, title={task.name}",
                "WARNING",
            )
            await state.repository.delete_download_task(task.id)
            return None
        submitted = await _scrape_playlist_candidate_items(
            state,
            task,
            track,
            resource,
            torrent_data,
            item_ids,
        )
        if submitted is None:
            state.add_log(
                "playlist",
                f"Playlist candidate rejected: task={task.id}, track={track.title}",
            )
            await state.repository.delete_download_task(task.id)
        return submitted
    except Exception:
        await state.repository.delete_download_task(task.id)
        raise


async def _download_playlist_candidate_torrent_file(
    state: AppState,
    resource: dict[str, Any],
) -> bytes:
    download_url = str(resource.get("download_url") or "")
    site = await _match_torrent_site(state, resource, [])
    if site is None:
        raise RuntimeError("Playlist download requires a parsable torrent file.")
    state.add_log(
        "playlist",
        "Playlist candidate torrent downloading: "
        f"site={site.name}, title={resource.get('title') or ''}",
    )
    proxy_url = await _resolve_proxy_for_site(state, site)
    return await _download_torrent_file(download_url, site, proxy_url=proxy_url)


async def _scrape_playlist_candidate_items(
    state: AppState,
    task: TorrentRecord,
    track: PlaylistTrack,
    resource: dict[str, Any],
    torrent_data: bytes,
    item_ids: list[int],
) -> TorrentRecord | None:
    submitted_task: TorrentRecord | None = None
    state.add_log(
        "playlist",
        "Playlist candidate pre-scraping started: "
        f"task={task.id}, items={len(item_ids)}, track={_playlist_track_log_text(track)}",
    )

    for item_id in item_ids:
        try:
            item = await state.task_manager.run_exclusive(
                task_type="DOWNLOAD_ITEM_SCRAPE",
                resource_keys=[f"download-item:{item_id}"],
                payload={
                    "torrent_record_id": task.id,
                    "item_id": item_id,
                },
                runner=lambda item_id=item_id: _scrape_download_task_item(state, item_id),
                wait_log_message="Playlist candidate metadata scraping waiting for resources.",
            )
        except Exception as exc:  # noqa: BLE001
            state.add_log(
                "playlist",
                f"Playlist candidate item scrape failed: task={task.id}, error={exc}",
                "WARNING",
            )
            continue
        if item is None:
            continue
        if not await _download_task_item_matches_playlist_track(state, item, track):
            continue
        state.add_log(
            "playlist",
            "Playlist candidate target matched: "
            f"task={task.id}, item_id={item.id}, "
            f"track={_playlist_track_log_text(track)}, "
            f"item_title={item.metadata_title or item.parsed_title or item.file_name}",
        )
        updated_item = await state.repository.update_download_task_item(
            item.id,
            playlist_track_id=track.id,
        )
        submitted_task = await _submit_playlist_candidate_to_downloader(
            state,
            task,
            resource,
            torrent_data,
        )
        await _bind_playlist_track_to_task(state, track.id, submitted_task, last_error=None)
        state.add_log(
            "playlist",
            "Playlist candidate accepted: "
            f"task={submitted_task.id}, track={track.title}, "
            f"item={updated_item.id if updated_item else item.id}",
        )
        break
    if submitted_task is None:
        state.add_log(
            "playlist",
            "Playlist candidate pre-scraping completed without target: "
            f"task={task.id}, track={_playlist_track_log_text(track)}",
        )
    return submitted_task


async def _submit_playlist_candidate_to_downloader(
    state: AppState,
    task: TorrentRecord,
    resource: dict[str, Any],
    torrent_data: bytes,
) -> TorrentRecord:
    if state.downloader is None:
        await state.reload_downloader()
    if state.downloader is None:
        raise RuntimeError("No downloader is configured.")
    category = str((task.payload or {}).get("category") or "MusicPilot")
    state.add_log(
        "playlist",
        "Playlist candidate submitting to downloader: "
        f"task={task.id}, category={category}, title={task.name}",
    )
    torrent_hash = await state.downloader.add_torrent_file(
        torrent_data,
        filename=_torrent_filename(resource, str(resource.get("download_url") or "")),
        category=category,
    )
    default_downloader = await state.repository.default_downloader()
    updated = await state.repository.update_download_task(
        task.id,
        status="submitted",
        downloader_id=default_downloader.id if default_downloader else None,
        submitted_at=datetime.now(UTC),
        torrent_hash=torrent_hash,
    )
    await _send_event_notifications(state, "download", updated or task)
    state.add_log(
        "playlist",
        f"Playlist candidate submitted to downloader: task={task.id}, torrent_hash={torrent_hash}",
    )
    return updated or task


async def _download_task_item_matches_playlist_track(
    state: AppState,
    item: TorrentRecordItem,
    track: PlaylistTrack,
) -> bool:
    if not await _artist_matches(state, item.metadata_artist or item.artist, track.artist):
        return False
    normalized_title = normalize_metadata_match_text(track.title)
    if not normalized_title:
        return False
    compact_title = _compact_search_text(normalized_title)
    for candidate in _download_task_item_titles(item):
        candidate_title = normalize_metadata_match_text(candidate)
        if not candidate_title:
            continue
        if candidate_title == normalized_title:
            return True
        if _normalized_contains(candidate_title, normalized_title, compact_title):
            return True
    return False


async def _bind_playlist_track_to_task(
    state: AppState,
    track_id: int,
    task: TorrentRecord,
    *,
    last_error: str | None,
) -> None:
    await state.repository.update_playlist_track(
        track_id,
        exists_in_library=False,
        matched_library_track_id=None,
        download_status=_playlist_download_status_for_task(task),
        torrent_record_id=task.id,
        last_checked_at=datetime.now(UTC),
        last_download_attempt_at=datetime.now(UTC),
        last_error=last_error,
    )


async def _sync_interrupted_system_task(state: AppState, task: SystemTask) -> None:
    payload = task.payload or {}
    reason = "任务已中断。"
    if task.task_type == "PLAYLIST_TRACK_DOWNLOAD":
        playlist_id = _optional_int(payload.get("playlist_id"))
        track_id = _optional_int(payload.get("track_id"))
        if track_id is None:
            return
        track = await state.repository.get_playlist_track(track_id)
        if track is None:
            return
        await state.repository.update_playlist_track(
            track.id,
            download_status="interrupted",
            last_checked_at=datetime.now(UTC),
            last_error=reason,
        )
        await _update_playlist_download_completion(state, playlist_id or track.playlist_id)
        return
    if task.task_type in {"DOWNLOAD_ITEM_SCRAPE", "FILE_ORGANIZE"}:
        item_id = _optional_int(payload.get("item_id"))
        task_id = _optional_int(payload.get("torrent_record_id"))
        if item_id is not None:
            await state.repository.update_download_task_item(
                item_id,
                status="interrupted",
                last_error=reason,
            )
        if task_id is not None:
            record = await state.repository.update_download_task(
                task_id,
                status="interrupted",
                last_error=reason,
            )
            if record is not None:
                await _sync_playlist_tracks_for_download_task(state, record)
        return
    if task.task_type == "DOWNLOAD_REFRESH_LIBRARY":
        task_id = _optional_int(payload.get("torrent_record_id"))
        if task_id is None:
            return
        record = await state.repository.update_download_task(
            task_id,
            status="interrupted",
            last_error=reason,
        )
        if record is not None:
            await _sync_playlist_tracks_for_download_task(state, record)


def _playlist_download_status_for_task(task: TorrentRecord) -> str:
    if task.status in {
        "submitted",
        "downloading",
        "completed",
        "refreshing_library",
        "library_refreshed",
        "source_directory_not_found",
        "failed",
        "deleted",
        "interrupted",
    }:
        return task.status
    return "submitted" if task.status == "queued" else task.status


async def _sync_playlist_tracks_for_download_task(
    state: AppState,
    task: TorrentRecord,
) -> None:
    tracks = await state.repository.list_playlist_tracks_by_torrent_record(task.id)
    if not tracks:
        return
    status = _playlist_download_status_for_task(task)
    last_error = (
        task.last_error
        if status in {"failed", "deleted", "interrupted", "source_directory_not_found"}
        else None
    )
    for track in tracks:
        if track.exists_in_library or track.download_status == "existing":
            continue
        await state.repository.update_playlist_track(
            track.id,
            download_status=status,
            last_checked_at=datetime.now(UTC),
            last_error=last_error,
        )
    for playlist_id in {track.playlist_id for track in tracks}:
        await _update_playlist_download_completion(state, playlist_id)


async def _mark_playlist_tracks_for_deleted_download_task(
    state: AppState,
    task_id: int,
) -> None:
    tracks = await state.repository.list_playlist_tracks_by_torrent_record(task_id)
    for track in tracks:
        if track.exists_in_library or track.download_status == "existing":
            continue
        await state.repository.update_playlist_track(
            track.id,
            download_status="deleted",
            last_checked_at=datetime.now(UTC),
            last_error="下载任务已删除。",
        )
    for playlist_id in {track.playlist_id for track in tracks}:
        await _update_playlist_download_completion(state, playlist_id)


def _playlist_media_candidate(track: PlaylistTrack) -> MediaCandidateResponse:
    return MediaCandidateResponse(
        title=track.title,
        artist=track.artist,
        album=track.album,
        albums=[track.album] if track.album else [],
        source=track.platform,
        external_id=track.external_id,
    )


def _oauth_html(title: str, message: str, *, status_code: int = 200) -> HTMLResponse:
    body = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title></head>"
        "<body style=\"font-family: sans-serif; padding: 32px;\">"
        f"<h1>{escape(title)}</h1><p>{escape(message)}</p>"
        "</body></html>"
    )
    return HTMLResponse(body, status_code=status_code)


async def _search_indexer(
    state: AppState,
    indexer: object,
    query: str,
    limit: int,
) -> tuple[str, tuple[SearchResult, ...]]:
    site_id = str(
        getattr(getattr(indexer, "config", None), "site_id", "") or indexer.name
    )
    site_name = str(getattr(indexer, "name", site_id))
    task_id = await state.task_manager.enqueue(
        TaskCreate(
            task_type="SEARCH_SITE",
            resource_keys=[_site_resource_key(indexer, site_id)],
            payload={
                "site_id": site_id,
                "site_name": site_name,
                "query": query,
                "limit": limit,
            },
        )
    )
    task = await state.task_manager.wait_for_task(task_id)
    if task.status != "SUCCEEDED":
        raise RuntimeError(task.error_message or f"Site search failed: {site_name}")
    results = tuple(
        _search_result_from_payload(item)
        for item in (task.result or {}).get("results", [])
        if isinstance(item, dict)
    )
    return str((task.result or {}).get("source") or site_name), results


async def _search_site_candidates(
    state: AppState,
    indexer: object,
    media: MediaCandidateResponse,
    keywords: list[str],
    limit: int,
    *,
    use_task_manager: bool = True,
) -> tuple[str, tuple[SearchResult, ...]]:
    site_id = str(
        getattr(getattr(indexer, "config", None), "site_id", "") or indexer.name
    )
    site_name = str(getattr(indexer, "name", site_id))
    resource_keys = [_site_resource_key(indexer, site_id)]
    if not use_task_manager:
        source, results_list, errors = await state.task_manager.run_exclusive(
            task_type="SEARCH_SITE_CANDIDATES",
            resource_keys=resource_keys,
            payload={
                "site_id": site_id,
                "site_name": site_name,
                "media": media.model_dump(),
                "keywords": keywords,
                "limit": limit,
            },
            runner=lambda: _search_site_candidates_direct(indexer, keywords, limit),
            wait_log_message="Playlist site candidate search waiting for resources.",
        )
        for error in errors:
            state.add_log(
                "playlist",
                f"Playlist site candidate search failed: site={site_name}, error={error}",
                "WARNING",
            )
        results = tuple(results_list)
        state.add_log(
            "search",
            "Playlist site candidate search completed: "
            f"site={site_name}, media={_media_candidate_log_text(media)}, raw={len(results)}",
        )
        return source, results
    task_id = await state.task_manager.enqueue(
        TaskCreate(
            task_type="SEARCH_SITE_CANDIDATES",
            resource_keys=resource_keys,
            payload={
                "site_id": site_id,
                "site_name": site_name,
                "media": media.model_dump(),
                "keywords": keywords,
                "limit": limit,
            },
        )
    )
    task = await state.task_manager.wait_for_task(task_id)
    if task.status != "SUCCEEDED":
        raise RuntimeError(task.error_message or f"Site candidate search failed: {site_name}")
    result_payload = task.result or {}
    for error in result_payload.get("errors", []):
        state.add_log(
            "playlist",
            f"Playlist site candidate search failed: site={site_name}, error={error}",
            "WARNING",
        )
    results = tuple(
        _search_result_from_payload(item)
        for item in result_payload.get("results", [])
        if isinstance(item, dict)
    )
    state.add_log(
        "search",
        "Playlist site candidate search completed: "
        f"site={site_name}, media={_media_candidate_log_text(media)}, raw={len(results)}",
    )
    return str(result_payload.get("source") or site_name), results


async def _search_site_candidates_direct(
    indexer: object,
    keywords: list[str],
    limit: int,
) -> tuple[str, list[SearchResult], list[str]]:
    site_name = str(getattr(indexer, "name", ""))
    results: list[SearchResult] = []
    errors: list[str] = []
    for keyword in keywords:
        try:
            keyword_results = await indexer.search(keyword, limit=limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{keyword}: {exc}")
            continue
        results.extend(keyword_results)
    return site_name, results, errors


async def _search_media_candidates(
    state: AppState,
    query: str,
    limit: int,
    *,
    artist: str | None = None,
    log_category: str,
    use_task_manager: bool = True,
) -> list[MediaCandidateResponse]:
    if not use_task_manager:
        return await state.task_manager.run_exclusive(
            task_type="SEARCH_MEDIA",
            resource_keys=[await _media_search_resource_key(state)],
            payload={
                "query": query,
                "artist": artist,
                "limit": limit,
                "log_category": log_category,
            },
            runner=lambda: _search_media_candidates_direct(state, query, limit, artist=artist),
            wait_log_message="Playlist metadata search waiting for media-search resource.",
        )
    task_id = await state.task_manager.enqueue(
        TaskCreate(
            task_type="SEARCH_MEDIA",
            resource_keys=[await _media_search_resource_key(state)],
            payload={
                "query": query,
                "artist": artist,
                "limit": limit,
                "log_category": log_category,
            },
        )
    )
    task = await state.task_manager.wait_for_task(task_id)
    if task.status != "SUCCEEDED":
        raise RuntimeError(task.error_message or f"Media search failed: {query}")
    candidates: list[MediaCandidateResponse] = []
    for item in (task.result or {}).get("candidates", []):
        if not isinstance(item, dict):
            continue
        candidates.append(MediaCandidateResponse(**item))
    return candidates


async def _search_media_candidates_direct(
    state: AppState,
    query: str,
    limit: int,
    *,
    artist: str | None = None,
) -> list[MediaCandidateResponse]:
    candidates: list[MediaCandidate] = []
    for provider in state.metadata.providers:
        search = getattr(provider, "search", None)
        if search is None:
            continue
        try:
            search_limit = min(max(limit * 5, limit), 50)
            if artist:
                provider_candidates = await search(query, artist=artist, limit=search_limit)
            else:
                provider_candidates = await search(query, limit=search_limit)
        except Exception as exc:  # noqa: BLE001
            state.add_log("metadata", f"Metadata provider failed: {exc}", "WARNING")
            continue
        candidates.extend(provider_candidates)
        if len(candidates) >= limit:
            break
    return _aggregate_media_candidates(candidates, limit=limit)


def _find_indexer(state: AppState, site_id: str) -> object | None:
    for indexer in state.indexers:
        config = getattr(indexer, "config", None)
        if str(getattr(config, "site_id", "")) == site_id:
            return indexer
        if str(getattr(indexer, "name", "")) == site_id:
            return indexer
    return None


def _search_result_payload(result: SearchResult) -> dict[str, object]:
    return {
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
        "metadata": result.metadata,
    }


def _search_result_from_payload(payload: dict[str, object]) -> SearchResult:
    metadata = payload.get("metadata")
    return SearchResult(
        title=str(payload.get("title") or ""),
        download_url=str(payload.get("download_url") or ""),
        source=str(payload.get("source") or ""),
        seeders=_optional_int(payload.get("seeders")) or 0,
        leechers=_optional_int(payload.get("leechers")) or 0,
        size_bytes=_optional_int(payload.get("size_bytes")),
        details_url=_optional_string(payload.get("details_url")),
        subtitle=_optional_string(payload.get("subtitle")),
        published_at=_optional_string(payload.get("published_at")),
        promotion=_optional_string(payload.get("promotion")),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


async def _submit_torrent_to_downloader(
    state: AppState,
    resource: dict[str, Any],
    selected_site_ids: list[str],
    category: str,
) -> SubmittedTorrent:
    if state.downloader is None:
        raise RuntimeError("No downloader is configured.")
    download_url = str(resource.get("download_url") or "")
    site = await _match_torrent_site(state, resource, selected_site_ids)
    if site is None:
        torrent_hash = await state.downloader.add_torrent(download_url, category=category)
        return SubmittedTorrent(torrent_hash=torrent_hash)
    proxy_url = await _resolve_proxy_for_site(state, site)
    torrent_data = await _download_torrent_file(download_url, site, proxy_url=proxy_url)
    torrent_hash = await state.downloader.add_torrent_file(
        torrent_data,
        filename=_torrent_filename(resource, download_url),
        category=category,
    )
    return SubmittedTorrent(torrent_hash=torrent_hash, torrent_data=torrent_data)


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


async def _download_torrent_file(
    download_url: str,
    site: IndexerSite,
    proxy_url: str | None = None,
) -> bytes:
    headers: dict[str, str] = {}
    if site.cookie:
        headers["Cookie"] = site.cookie
    if site.user_agent:
        headers["User-Agent"] = site.user_agent
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        http2=True,
        proxy=proxy_url,
    ) as client:
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


async def _record_submitted_torrent_items(
    state: AppState,
    task_id: int | None,
    torrent_data: bytes | None,
    *,
    playlist_track_id: int | None = None,
) -> list[int]:
    if task_id is None or not torrent_data:
        return []
    task = await state.repository.get_download_task(task_id)
    if task is None:
        return []
    try:
        parsed_items = _torrent_audio_items(torrent_data)
        if not parsed_items:
            return []
        media_metadata = task.media_metadata or {}
        artist = _optional_string(media_metadata.get("artist"))
        rows = await state.repository.replace_download_task_items(
            task_id,
            [
                {
                    "file_name": item["file_name"],
                    "file_path": item["file_path"],
                    "artist": artist,
                    "parsed_title": item["parsed_title"],
                    "playlist_track_id": playlist_track_id,
                    "status": "pending",
                    "raw_payload": {"size": item.get("size")},
                }
                for item in parsed_items
            ],
        )
    except Exception as exc:  # noqa: BLE001
        state.add_log("download", f"Torrent item parse failed for task={task_id}: {exc}", "WARNING")
        return []
    return [row.id for row in rows]


async def _schedule_download_task_item_scraping(
    state: AppState,
    task_id: int | None,
    item_ids: list[int],
) -> None:
    if task_id is None or not item_ids:
        return
    pending_ids = set(item_ids)
    items = await state.repository.list_download_task_items(task_id)
    eligible_ids = {
        item.id
        for item in items
        if item.id in pending_ids and item.status in DOWNLOAD_ITEM_SCRAPE_INCOMPLETE_STATUSES
    }
    for item_id in item_ids:
        if item_id not in eligible_ids:
            continue
        await _enqueue_download_item_scrape(state, task_id, item_id)


async def _restore_pending_download_item_scrapes(state: AppState) -> None:
    restored = 0
    for task in await state.repository.list_unfinished_download_tasks():
        scheduled, _incomplete = await _schedule_pending_download_task_item_scrapes(
            state,
            task.id,
        )
        restored += scheduled
    if restored:
        state.add_log(
            "metadata",
            f"Restored pending download item metadata scrape tasks: count={restored}",
        )


async def _schedule_pending_download_task_item_scrapes(
    state: AppState,
    task_id: int,
) -> tuple[int, int]:
    scheduled = 0
    incomplete = 0
    for item in await state.repository.list_download_task_items(task_id):
        if item.status in DOWNLOAD_ITEM_SCRAPE_INCOMPLETE_STATUSES:
            incomplete += 1
        if item.status not in DOWNLOAD_ITEM_SCRAPE_INCOMPLETE_STATUSES:
            continue
        scrape_task_id = await _enqueue_download_item_scrape(state, task_id, item.id)
        if scrape_task_id is not None:
            scheduled += 1
    return scheduled, incomplete


async def _schedule_download_item_processing_for_files(
    state: AppState,
    task: TorrentRecord,
    source_files: tuple[Path, ...],
) -> tuple[int, int, int]:
    items = await state.repository.list_download_task_items(task.id)
    matched = _download_items_by_source_file(source_files, items)
    matched_item_ids = sorted({item.id for item in matched.values()})
    payload = dict(task.payload or {})
    if payload.get("organize_item_ids") != matched_item_ids:
        payload["organize_item_ids"] = matched_item_ids
        await state.repository.update_download_task(task.id, payload=payload)
    scheduled = 0
    pending = 0
    terminal = 0
    for source_file in source_files:
        item = matched.get(source_file)
        if item is None:
            continue
        if item.status in DOWNLOAD_ITEM_ORGANIZE_TERMINAL_STATUSES:
            terminal += 1
            continue
        if item.status in DOWNLOAD_ITEM_ORGANIZE_ACTIVE_STATUSES:
            organize_task_id = await _enqueue_download_item_organize(
                state,
                task,
                item,
                source_file,
            )
            if organize_task_id is not None:
                scheduled += 1
            pending += 1
            continue
        if item.status in DOWNLOAD_ITEM_SCRAPE_DONE_STATUSES:
            organize_task_id = await _enqueue_download_item_organize(
                state,
                task,
                item,
                source_file,
            )
            if organize_task_id is not None:
                scheduled += 1
            pending += 1
            continue
        scrape_task_id = await _enqueue_download_item_scrape(
            state,
            task.id,
            item.id,
            organize_after_scrape=True,
            source_file=source_file,
            task_name=task.name,
        )
        if scrape_task_id is not None:
            scheduled += 1
        pending += 1
    return scheduled, pending, terminal


async def _wait_for_download_item_scrapes(
    state: AppState,
    task_id: int,
    task_name: str,
) -> None:
    logged = False
    while True:
        scheduled, incomplete = await _schedule_pending_download_task_item_scrapes(
            state,
            task_id,
        )
        if incomplete <= 0:
            return
        if scheduled or not logged:
            state.add_log(
                "metadata",
                "Download refresh waiting for item metadata scraping: "
                f"task={task_id}, name={task_name}, incomplete={incomplete}, "
                f"scheduled={scheduled}",
            )
            logged = True
        await asyncio.sleep(2)


async def _enqueue_download_item_scrape(
    state: AppState,
    task_id: int,
    item_id: int,
    *,
    organize_after_scrape: bool = False,
    source_file: Path | None = None,
    task_name: str | None = None,
) -> int | None:
    item = await state.repository.get_download_task_item(item_id)
    if item is None or item.torrent_record_id != task_id:
        return None
    idempotency_key = _download_item_scrape_idempotency_key(item)
    payload = {
        "torrent_record_id": task_id,
        "item_id": item_id,
        "organize_after_scrape": organize_after_scrape,
        "source_file": str(source_file) if source_file is not None else None,
        "task_name": task_name,
    }
    existing = await state.repository.get_system_task_by_idempotency_key(idempotency_key)
    if existing is not None:
        if existing.status in {"WAIT", "RUNNING"}:
            await _upgrade_waiting_system_task(
                state,
                existing,
                payload=payload,
                priority=DOWNLOAD_ITEM_TASK_PRIORITY,
            )
            return None
        if item.status in DOWNLOAD_ITEM_SCRAPE_INCOMPLETE_STATUSES:
            idempotency_key = f"{idempotency_key}:recover:{_download_item_generation(item)}"
            recovery = await state.repository.get_system_task_by_idempotency_key(idempotency_key)
            if recovery is not None and recovery.status in {"WAIT", "RUNNING"}:
                await _upgrade_waiting_system_task(
                    state,
                    recovery,
                    payload=payload,
                    priority=DOWNLOAD_ITEM_TASK_PRIORITY,
                )
                return None
        else:
            return None
    return await state.task_manager.enqueue(
        TaskCreate(
            task_type="DOWNLOAD_ITEM_SCRAPE",
            payload=payload,
            resource_keys=[f"download-item:{item_id}"],
            priority=DOWNLOAD_ITEM_TASK_PRIORITY,
            max_attempts=3,
            idempotency_key=idempotency_key,
        )
    )


async def _enqueue_download_item_organize(
    state: AppState,
    task: TorrentRecord,
    item: TorrentRecordItem,
    source_file: Path,
) -> int | None:
    idempotency_key = _download_item_organize_idempotency_key(item, source_file)
    task_create = _download_item_organize_task_create(
        torrent_record_id=task.id,
        item_id=item.id,
        source_file=source_file,
        task_name=task.name,
        idempotency_key=idempotency_key,
    )
    existing = await state.repository.get_system_task_by_idempotency_key(idempotency_key)
    if existing is not None:
        if existing.status in {"WAIT", "RUNNING"}:
            await _upgrade_waiting_system_task(
                state,
                existing,
                payload=task_create.payload,
                priority=DOWNLOAD_ITEM_TASK_PRIORITY,
            )
            return None
        if (
            existing.status == "SUCCEEDED"
            and item.status in DOWNLOAD_ITEM_ORGANIZE_TERMINAL_STATUSES
        ):
            return None
        idempotency_key = (
            f"{idempotency_key}:recover:"
            f"{_download_item_generation(item)}:{_file_identity_digest(source_file)}"
        )
        recovery = await state.repository.get_system_task_by_idempotency_key(idempotency_key)
        if recovery is not None and recovery.status in {"WAIT", "RUNNING"}:
            await _upgrade_waiting_system_task(
                state,
                recovery,
                payload=task_create.payload,
                priority=DOWNLOAD_ITEM_TASK_PRIORITY,
            )
            return None
        task_create = _download_item_organize_task_create(
            torrent_record_id=task.id,
            item_id=item.id,
            source_file=source_file,
            task_name=task.name,
            idempotency_key=idempotency_key,
        )
    return await state.task_manager.enqueue(task_create)


def _download_item_organize_task_create(
    *,
    torrent_record_id: int,
    item_id: int,
    source_file: Path,
    task_name: str,
    idempotency_key: str | None = None,
) -> TaskCreate:
    return TaskCreate(
        task_type="FILE_ORGANIZE",
        payload={
            "torrent_record_id": torrent_record_id,
            "item_id": item_id,
            "source_file": str(source_file),
            "task_name": task_name,
        },
        resource_keys=[_scraping_file_resource_key(source_file)],
        priority=DOWNLOAD_ITEM_TASK_PRIORITY,
        max_attempts=3,
        idempotency_key=idempotency_key,
    )


async def _upgrade_waiting_system_task(
    state: AppState,
    task: object,
    *,
    payload: dict[str, Any],
    priority: int,
) -> None:
    task_id = _optional_int(getattr(task, "id", None))
    if task_id is None or getattr(task, "status", None) != "WAIT":
        return
    current_payload = getattr(task, "payload", None)
    merged_payload = dict(current_payload if isinstance(current_payload, dict) else {})
    merged_payload.update(payload)
    updated = await state.repository.update_waiting_system_task(
        task_id,
        payload=merged_payload,
        priority=priority,
        available_at=datetime.now(UTC),
    )
    if updated is not None:
        await state.task_manager.wake()


def _file_identity_digest(path: Path) -> str:
    try:
        identity = str(path.expanduser().resolve(strict=False))
    except OSError:
        identity = str(path.expanduser())
    return hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _download_item_scrape_idempotency_key(item: TorrentRecordItem) -> str:
    raw_payload = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    identity = "|".join(
        (
            str(item.torrent_record_id),
            item.file_path,
            item.file_name,
            str(raw_payload.get("size") or ""),
        )
    )
    digest = hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return (
        "download-item-scrape:"
        f"{item.torrent_record_id}:{item.id}:{_download_item_generation(item)}:{digest}"
    )


def _download_item_generation(item: TorrentRecordItem) -> str:
    created_at = item.created_at
    if isinstance(created_at, datetime):
        return created_at.astimezone(UTC).strftime("%Y%m%d%H%M%S%f")
    return "unknown"


def _download_item_organize_idempotency_key(
    item: TorrentRecordItem,
    source_file: Path,
) -> str:
    identity = "|".join(
        (
            str(item.torrent_record_id),
            str(item.id),
            item.file_path,
            str(source_file),
            _download_item_generation(item),
        )
    )
    digest = hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"download-item-organize:{item.torrent_record_id}:{item.id}:{digest}"


async def _scrape_download_task_item(state: AppState, item_id: int) -> TorrentRecordItem | None:
    item = await state.repository.get_download_task_item(item_id)
    if item is None:
        return None
    reference = _download_task_item_reference_metadata(item)
    title = reference.title.strip()
    if not title:
        await state.repository.update_download_task_item(
            item_id,
            status="metadata_not_found",
            last_error="No title parsed from torrent file.",
        )
        return await state.repository.get_download_task_item(item_id)
    await state.repository.update_download_task_item(
        item_id,
        status="metadata_searching",
        last_error=None,
    )
    try:
        state.add_log(
            "metadata",
            f"Download item metadata scraping input: item_id={item_id}, "
            f"file={item.file_path}, reference={_track_metadata_log_text(reference)}",
        )
        candidates = await state.scraper.search_metadata_candidates(reference, reference)
        metadata = await state.scraper.select_metadata_candidate(reference, candidates)
        failure_message = await state.scraper.metadata_candidate_failure_message(
            reference,
            candidates,
        )
    except Exception as exc:  # noqa: BLE001
        error_message = f"{exc.__class__.__name__}: {exc}"
        await state.repository.update_download_task_item(
            item_id,
            status="failed",
            last_error=error_message,
        )
        state.add_log(
            "metadata",
            f"Download item metadata scraping failed: item_id={item_id}, "
            f"reference={_track_metadata_log_text(reference)}, error={error_message}",
            "WARNING",
        )
        return await state.repository.get_download_task_item(item_id)
    if metadata is None:
        await state.repository.update_download_task_item(
            item_id,
            status="metadata_not_found",
            last_error=failure_message,
        )
        state.add_log(
            "metadata",
            f"Download item metadata scraping result: item_id={item_id}, "
            f"status=metadata_not_found, reference={_track_metadata_log_text(reference)}, "
            f"candidates={len(candidates)}, error={failure_message}",
            "WARNING",
        )
        return await state.repository.get_download_task_item(item_id)
    await _ensure_artist_from_metadata(
        state,
        metadata,
        context=f"download item {item_id}",
    )
    await state.repository.update_download_task_item(
        item_id,
        status="metadata_found",
        metadata_title=metadata.title,
        metadata_artist=metadata.artist,
        metadata_album=metadata.album,
        metadata_payload=_track_metadata_payload(metadata),
        last_error=None,
    )
    state.add_log(
        "metadata",
        f"Download item metadata scraping result: item_id={item_id}, status=metadata_found, "
        f"reference={_track_metadata_log_text(reference)}, "
        f"metadata={_track_metadata_log_text(metadata)}, "
        f"candidates={len(candidates)}",
    )
    return await state.repository.get_download_task_item(item_id)


def _track_metadata_payload(metadata: TrackMetadata) -> dict[str, object]:
    return dataclasses.asdict(metadata)


def _track_metadata_response(metadata: TrackMetadata) -> TrackMetadataResponse:
    extra = dict(metadata.extra or {})
    return TrackMetadataResponse(
        title=metadata.title,
        artist=metadata.artist,
        album=metadata.album,
        year=metadata.year,
        track_number=metadata.track_number,
        lyrics=metadata.lyrics,
        cover_url=metadata.cover_url,
        source=extra.get("source"),
        source_id=extra.get("source_id"),
        extra=extra,
    )


def _track_metadata_from_manual_payload(payload: MediaManualOrganizeRequest) -> TrackMetadata:
    return TrackMetadata(
        title=payload.title.strip(),
        artist=_optional_string(payload.artist),
        album=_optional_string(payload.album),
        year=payload.year,
        track_number=payload.track_number,
        lyrics=_optional_string(payload.lyrics),
        cover_url=_optional_string(payload.cover_url),
        extra=dict(payload.extra or {}),
    )


async def _search_manual_metadata_candidates(
    state: AppState,
    *,
    query: str,
    source: str,
    limit: int,
) -> tuple[TrackMetadata, ...]:
    if source not in {"qmusic", "netease", "migu", "kuwo"}:
        raise ValueError("不支持的元数据源。")
    for provider in state.scraping_metadata.providers:
        search = getattr(provider, "search_metadata_from_source", None)
        if search is not None:
            return await search(source, title=query, artist=None, limit=limit)
    return await state.scraping_metadata.search_metadata(title=query, limit=limit)


def _manual_metadata_by_source_file(value: object) -> dict[Path, tuple[TrackMetadata, ...]]:
    if not isinstance(value, dict):
        return {}
    result: dict[Path, tuple[TrackMetadata, ...]] = {}
    for raw_path, raw_items in value.items():
        if not isinstance(raw_path, str):
            continue
        items = raw_items if isinstance(raw_items, list) else [raw_items]
        metadata_items = tuple(
            metadata
            for item in items
            if isinstance(item, dict)
            and (metadata := _track_metadata_from_payload(item)) is not None
        )
        if metadata_items:
            result[Path(raw_path)] = metadata_items
    return result


def _contextual_metadata_by_source_file(value: object) -> dict[Path, ContextualMetadata]:
    if not isinstance(value, dict):
        return {}
    result: dict[Path, ContextualMetadata] = {}
    for raw_path, raw_item in value.items():
        if not isinstance(raw_path, str) or not isinstance(raw_item, dict):
            continue
        metadata = _track_metadata_from_payload(raw_item)
        if metadata is None:
            continue
        result[Path(raw_path)] = ContextualMetadata(
            metadata=metadata,
            verify_identity=True,
            preserve_artist_album=True,
        )
    return result


def _paths_from_payload(value: object) -> tuple[Path, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(Path(item) for item in value if isinstance(item, str) and item)


async def _auto_build_artist_library(state: AppState) -> None:
    """Build artist library in background with a timeout."""
    if state.artist_build_lock.locked():
        state.add_log("artist", "自动构建歌手库跳过：已有构建任务进行中", "INFO")
        return
    async with state.artist_build_lock:
        _mark_artist_build_started(state)
        try:
            created = await asyncio.wait_for(
                state.artist_service.build_library_from_media_files(),
                timeout=300,
            )
            if created:
                state.add_log(
                    "artist",
                    f"启动时自动构建歌手库：已创建 {created} 个歌手组。",
                    "INFO",
                )
            _mark_artist_build_finished(state)
        except TimeoutError:
            _mark_artist_build_finished(state, "自动构建歌手库超时（可稍后手动构建）")
            state.add_log("artist", "自动构建歌手库超时（可稍后手动构建）", "WARNING")
        except Exception as exc:  # noqa: BLE001
            _mark_artist_build_finished(state, str(exc))
            state.add_log("artist", f"自动构建歌手库失败（可稍后手动构建）：{exc}", "WARNING")


async def _run_artist_build(state: AppState) -> None:
    """Run artist library build in background."""
    async with state.artist_build_lock:
        _mark_artist_build_started(state)
        try:
            created = await state.artist_service.build_library_from_media_files()
            message = (
                f"歌手库构建完成：共 {created} 个歌手组。"
                if created
                else "歌手库构建完成：没有新增歌手组。"
            )
            state.add_log(
                "artist",
                message,
                "INFO",
            )
            _mark_artist_build_finished(state)
        except asyncio.CancelledError:
            _mark_artist_build_finished(state, "歌手库构建已被取消")
            state.add_log("artist", "歌手库构建已被取消", "WARNING")
        except Exception as exc:  # noqa: BLE001
            _mark_artist_build_finished(state, str(exc))
            state.add_log("artist", f"歌手库构建失败：{exc}", "ERROR")


def _mark_artist_build_started(state: AppState) -> None:
    state.artist_build_started_at = datetime.now(UTC)
    state.artist_build_finished_at = None
    state.artist_build_last_error = None


def _mark_artist_build_finished(state: AppState, error: str | None = None) -> None:
    state.artist_build_finished_at = datetime.now(UTC)
    state.artist_build_last_error = error


async def _ensure_artist_from_metadata(
    state: AppState,
    metadata: TrackMetadata,
    *,
    context: str,
) -> None:
    artists = split_artist_credit(metadata.artist)
    if not artists:
        return
    for artist in artists:
        try:
            await state.artist_service.ensure_artist(artist, source="scraping")
        except Exception as exc:  # noqa: BLE001
            state.add_log(
                "artist",
                f"Artist library update skipped for {context}: artist={artist}, error={exc}",
                "WARNING",
            )


def _track_metadata_log_text(metadata: TrackMetadata | None) -> str:
    if metadata is None:
        return "None"
    return (
        "{"
        f"title={metadata.title!r}, artist={metadata.artist!r}, album={metadata.album!r}, "
        f"year={metadata.year!r}, track_number={metadata.track_number!r}, "
        f"lyrics={bool(metadata.lyrics)}, cover_url={metadata.cover_url!r}, "
        f"extra_keys={sorted(metadata.extra.keys()) if metadata.extra else []}"
        "}"
    )


def _download_task_item_reference_metadata(item: TorrentRecordItem) -> TrackMetadata:
    virtual_path = Path(item.file_path.replace("\\", "/"))
    inferred = infer_metadata_from_paths([virtual_path]).get(virtual_path)
    title = item.parsed_title or (inferred.title if inferred else None) or Path(item.file_name).stem
    artist = item.artist or (inferred.artist if inferred else None)
    return TrackMetadata(
        title=title,
        artist=artist,
        album=inferred.album if inferred else None,
        year=inferred.year if inferred else None,
    )


def _torrent_audio_items(torrent_data: bytes) -> list[dict[str, object]]:
    payload = _bdecode(torrent_data)
    if not isinstance(payload, dict):
        return []
    info = payload.get(b"info")
    if not isinstance(info, dict):
        return []
    items: list[dict[str, object]] = []
    root_name = _decode_torrent_text(info.get(b"name.utf-8") or info.get(b"name") or b"")
    files = info.get(b"files")
    if isinstance(files, list):
        for file_info in files:
            if not isinstance(file_info, dict):
                continue
            path_value = file_info.get(b"path.utf-8") or file_info.get(b"path")
            if not isinstance(path_value, list):
                continue
            parts = [_decode_torrent_text(part) for part in path_value]
            file_path = "/".join(part for part in [root_name, *parts] if part)
            _append_torrent_audio_item(items, file_path, file_info.get(b"length"))
        return items

    single_name = root_name
    _append_torrent_audio_item(items, single_name, info.get(b"length"))
    return items


def _append_torrent_audio_item(
    items: list[dict[str, object]],
    file_path: str,
    size: object,
) -> None:
    if not file_path:
        return
    file_name = Path(file_path).name
    if Path(file_name).suffix.lower() not in _TORRENT_AUDIO_EXTENSIONS:
        return
    items.append(
        {
            "file_name": file_name,
            "file_path": file_path,
            "parsed_title": _title_from_audio_filename(file_name),
            "size": size if isinstance(size, int) else None,
        }
    )


def _title_from_audio_filename(file_name: str) -> str:
    title = Path(file_name).stem
    title = re.sub(r"^\s*(?:cd\s*\d+\s*[-_. ]*)?\d{1,3}\s*[-_. ]+", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title.replace("_", " ")).strip()
    return title or Path(file_name).stem


def _decode_torrent_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, bytes):
        return ""
    for encoding in ("utf-8", "gb18030", "big5"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def _bdecode(data: bytes) -> object:
    value, offset = _bdecode_at(data, 0)
    if offset != len(data):
        raise ValueError("Invalid trailing data in torrent file.")
    return value


def _bdecode_at(data: bytes, offset: int) -> tuple[object, int]:
    if offset >= len(data):
        raise ValueError("Unexpected end of torrent file.")
    token = data[offset : offset + 1]
    if token == b"i":
        end = data.index(b"e", offset)
        return int(data[offset + 1 : end]), end + 1
    if token == b"l":
        values: list[object] = []
        offset += 1
        while data[offset : offset + 1] != b"e":
            value, offset = _bdecode_at(data, offset)
            values.append(value)
        return values, offset + 1
    if token == b"d":
        values: dict[bytes, object] = {}
        offset += 1
        while data[offset : offset + 1] != b"e":
            key, offset = _bdecode_at(data, offset)
            if not isinstance(key, bytes):
                raise ValueError("Invalid torrent dictionary key.")
            value, offset = _bdecode_at(data, offset)
            values[key] = value
        return values, offset + 1
    if token.isdigit():
        separator = data.index(b":", offset)
        length = int(data[offset:separator])
        start = separator + 1
        end = start + length
        return data[start:end], end
    raise ValueError("Invalid bencode token.")


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
            *(
                _run_metadata_site_search_for_indexer(state, task, indexer, limit)
                for indexer in indexers
            )
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
    state: AppState,
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

        async def publish_site_progress() -> None:
            merged = _dedupe_results(raw_results)
            filtered = await _filter_by_artist_with_aliases(state, merged, task.media.artist)
            ranked = sorted(filtered, key=lambda item: item.seeders, reverse=True)[:limit]
            await task.site_progress(
                site=site_name,
                raw_count=len(merged),
                filtered_count=len(filtered),
                results=[_search_result_response(item) for item in ranked],
                errors=errors,
            )

        async def search_keyword(keyword: str) -> None:
            async with semaphore:
                await task.keyword_started(keyword)
                try:
                    _source, results = await _search_indexer(state, indexer, keyword, limit)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{keyword}: {exc}")
                else:
                    raw_results.extend(results)
                finally:
                    try:
                        await publish_site_progress()
                    finally:
                        await task.keyword_finished(keyword)

        await asyncio.gather(*(search_keyword(keyword) for keyword in keywords))
        merged = _dedupe_results(raw_results)
        filtered = await _filter_by_artist_with_aliases(state, merged, task.media.artist)
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
        metadata=result.metadata,
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


def _scraping_summary_result(summary: ScrapingSummary) -> dict[str, int]:
    return {
        "source_files": summary.source_files,
        "mapped_files": summary.mapped_files,
        "updated_files": summary.updated_files,
        "moved_files": summary.moved_files,
        "failed_files": summary.failed_files,
        "skipped_files": sum(1 for item in summary.results if item.status == "skipped"),
    }


def _file_organize_response_from_task_result(
    result: dict[str, Any],
) -> FileOrganizeResponse:
    return FileOrganizeResponse(
        source_files=_optional_int(result.get("source_files")) or 0,
        mapped_files=_optional_int(result.get("mapped_files")) or 0,
        updated_files=_optional_int(result.get("updated_files")) or 0,
        moved_files=_optional_int(result.get("moved_files")) or 0,
        failed_files=_optional_int(result.get("failed_files")) or 0,
        skipped_files=_optional_int(result.get("skipped_files")) or 0,
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
        local_path=item.local_path,
        listen_mode=item.listen_mode,
        is_default=item.is_default,
        enabled=item.enabled,
    )


def _validate_downloader_paths(payload: DownloaderCreateRequest) -> None:
    error = _downloader_path_error(payload)
    if error is not None:
        raise HTTPException(status_code=422, detail=error)


def _downloader_path_error(payload: DownloaderCreateRequest) -> str | None:
    if not payload.download_path.strip():
        return "下载器下载目录不能为空。"
    if not payload.local_path.strip():
        return "下载器本机对应目录不能为空。"
    return None


def _downloader_payload(payload: DownloaderCreateRequest) -> dict[str, object]:
    data = payload.model_dump()
    data["download_path"] = payload.download_path.strip()
    data["local_path"] = payload.local_path.strip()
    return data


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


def _dashboard_response(summary: dict[str, Any]) -> DashboardResponse:
    library = summary["library"]
    playlists = summary["playlists"]
    downloads = summary["downloads"]
    media = summary["media"]
    tasks = summary["tasks"]
    return DashboardResponse(
        library=DashboardLibrarySummaryResponse(**library),
        playlists=DashboardPlaylistSummaryResponse(**playlists),
        downloads=DashboardDownloadSummaryResponse(
            total=downloads["total"],
            active=downloads["active"],
            completed_7d=downloads["completed_7d"],
            failed=downloads["failed"],
            status_counts=downloads["status_counts"],
            recent=[
                DashboardDownloadItemResponse(
                    id=item.id,
                    name=item.name,
                    state=item.status,
                    progress=item.progress,
                    updated_at=item.updated_at,
                )
                for item in downloads["recent"]
            ],
        ),
        media=DashboardMediaSummaryResponse(
            total=media["total"],
            success=media["success"],
            failed=media["failed"],
            recent_7d=media["recent_7d"],
            recent=[
                DashboardMediaItemResponse(
                    id=item.id,
                    title=item.title,
                    artist=item.artist,
                    source_path=item.source_path,
                    operation_type=item.operation_type,
                    status=item.status,
                    updated_at=item.updated_at,
                )
                for item in media["recent"]
            ],
        ),
        tasks=DashboardTaskSummaryResponse(**tasks),
    )


def _system_task_response(item: SystemTask) -> SystemTaskResponse:
    return SystemTaskResponse(
        id=item.id,
        task_type=item.task_type,
        status=item.status,
        chain_id=item.chain_id,
        parent_task_id=item.parent_task_id,
        priority=item.priority,
        payload=item.payload or {},
        error_message=item.error_message,
        attempts=item.attempts,
        max_attempts=item.max_attempts,
        available_at=item.available_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
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


def _download_task_item_response(item: TorrentRecordItem) -> DownloadTaskItemResponse:
    raw_payload = item.raw_payload or {}
    return DownloadTaskItemResponse(
        id=item.id,
        torrent_record_id=item.torrent_record_id,
        file_name=item.file_name,
        file_path=item.file_path,
        size_bytes=_optional_int(raw_payload.get("size")),
        artist=item.artist,
        parsed_title=item.parsed_title,
        metadata_title=item.metadata_title,
        metadata_artist=item.metadata_artist,
        metadata_album=item.metadata_album,
        playlist_track_id=item.playlist_track_id,
        status=item.status,
        last_error=item.last_error,
        metadata_payload=item.metadata_payload,
        created_at=item.created_at,
        updated_at=item.updated_at,
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
        "use_proxy": site.use_proxy,
        "enabled": site.enabled,
    }


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    by_key: dict[tuple[str, str], SearchResult] = {}
    for result in results:
        current = by_key.get(result.identity_key)
        if current is None or result.seeders > current.seeders:
            by_key[result.identity_key] = result
    return list(by_key.values())


def _filter_by_exclude_keywords(
    results: list[SearchResult],
    exclude_keywords: str,
) -> list[SearchResult]:
    if not exclude_keywords or not exclude_keywords.strip():
        return results
    keywords = [kw.strip().casefold() for kw in exclude_keywords.split("|") if kw.strip()]
    if not keywords:
        return results
    return [
        result
        for result in results
        if not any(kw in (result.title or "").casefold() for kw in keywords)
    ]


async def _get_exclude_keywords(state: AppState) -> str:
    settings = await state.repository.get_system_settings()
    search_settings = settings.get("search") or {}
    return str(search_settings.get("exclude_keywords") or "")


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
    artist_values = _artist_credit_base_match_values(artist)
    if not artist_values:
        return results
    return [item for item in results if _resource_matches_artist_values(item, artist_values)]


async def _filter_by_artist_with_aliases(
    state: AppState,
    results: list[SearchResult],
    artist: str | None,
) -> list[SearchResult]:
    if not artist:
        return results
    artist_values = await _artist_credit_match_values(state, artist)
    if not artist_values:
        return results
    return [item for item in results if _resource_matches_artist_values(item, artist_values)]


async def _artist_matches(state: AppState, value: str | None, artist: str | None) -> bool:
    if not artist:
        return True
    if not value:
        return False
    left_values = await _artist_credit_match_values(state, value)
    right_values = await _artist_credit_match_values(state, artist)
    return _artist_value_sets_match(left_values, right_values)


async def _artist_credit_match_values_cached(
    state: AppState,
    artist_credit: str | None,
    cache: dict[str, set[str]] | None,
) -> set[str]:
    if cache is None:
        return await _artist_credit_match_values(state, artist_credit)
    key = artist_credit or ""
    if key not in cache:
        cache[key] = await _artist_credit_match_values(state, artist_credit)
    return cache[key]


async def _artist_credit_match_values(state: AppState, artist_credit: str | None) -> set[str]:
    values: set[str] = set()
    for artist in split_artist_credit(artist_credit):
        candidates = [artist]
        canonical = await state.artist_service.get_canonical_name(artist)
        if canonical:
            candidates.append(canonical)
        candidates.extend(await state.artist_service.get_aliases(artist))
        for candidate in candidates:
            normalized = normalize_search_text(candidate)
            compact = _compact_search_text(normalized)
            match_normalized = normalize_metadata_match_text(candidate)
            if normalized:
                values.add(normalized)
            if compact:
                values.add(compact)
            if match_normalized:
                values.add(match_normalized)
    return values


def _artist_credit_base_match_values(artist_credit: str | None) -> set[str]:
    values: set[str] = set()
    for artist in split_artist_credit(artist_credit):
        normalized = normalize_search_text(artist)
        compact = _compact_search_text(normalized)
        match_normalized = normalize_metadata_match_text(artist)
        if normalized:
            values.add(normalized)
        if compact:
            values.add(compact)
        if match_normalized:
            values.add(match_normalized)
    return values


def _artist_value_sets_match(left_values: set[str], right_values: set[str]) -> bool:
    if not left_values or not right_values:
        return False
    if left_values & right_values:
        return True
    return any(
        _normalized_contains(left, right, _compact_search_text(right))
        or _normalized_contains(right, left, _compact_search_text(left))
        for left in left_values
        for right in right_values
    )


def _resource_matches_artist_values(result: SearchResult, artist_values: set[str]) -> bool:
    text = _resource_text(result)
    return any(
        _normalized_contains(text, value, _compact_search_text(value))
        for value in artist_values
        if value
    )


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
            await _sync_music_library_from_media_server(state)
        except Exception as exc:  # noqa: BLE001
            state.add_log("library", f"Music library sync failed: {exc}", "ERROR")
        await asyncio.sleep(MUSIC_LIBRARY_SYNC_INTERVAL_SECONDS)


async def _sync_music_library_after_refresh(state: AppState) -> None:
    await asyncio.sleep(MUSIC_LIBRARY_SYNC_AFTER_REFRESH_DELAY_SECONDS)
    try:
        await _sync_music_library_from_media_server(state)
    except Exception as exc:  # noqa: BLE001
        state.add_log("library", f"Music library sync after refresh failed: {exc}", "ERROR")


async def _sync_music_library_from_media_server(state: AppState) -> int:
    server = await state.repository.default_media_server()
    if server is None:
        state.add_log("library", "Music library sync skipped: no media server", "WARNING")
        return 0
    client = build_media_server_client(server)
    tracks = await client.list_tracks()
    count = await state.repository.sync_music_library_tracks(
        [_media_server_track_payload(track) for track in tracks]
    )
    await _refresh_playlist_library_matches(state)
    state.add_log("library", f"Music library synced: {count} track(s)")
    return count


def _media_server_track_payload(track: object) -> dict[str, Any]:
    return {
        "id": getattr(track, "id", ""),
        "title": getattr(track, "title", ""),
        "artist": getattr(track, "artist", None),
        "album": getattr(track, "album", None),
        "duration": getattr(track, "duration", None),
        "size": getattr(track, "size", None),
        "year": getattr(track, "year", None),
        "suffix": getattr(track, "suffix", None),
        "path": getattr(track, "path", None),
        "contentType": getattr(track, "content_type", None),
        "raw_payload": getattr(track, "raw_payload", {}),
    }


async def _sync_playlist_to_media_server(
    state: AppState,
    playlist: Playlist,
    *,
    media_server_id: str | None = None,
    public: bool = True,
) -> tuple[str | None, int, str]:
    server = (
        await state.repository.get_media_server(media_server_id)
        if media_server_id
        else await state.repository.default_media_server()
    )
    if server is None:
        if media_server_id:
            raise ValueError("选择的媒体服务器用户不存在。")
        raise ValueError("请先配置并启用默认媒体服务器。")
    if not server.enabled:
        raise ValueError("请选择已启用的媒体服务器用户。")
    matched_tracks = await state.repository.list_matched_playlist_library_tracks(playlist.id)
    song_ids = [
        library_track.navidrome_id
        for _, library_track in matched_tracks
        if library_track.navidrome_id
    ]
    if not song_ids:
        raise ValueError("该歌单没有已匹配到音乐库的歌曲。")
    client = build_media_server_client(server)
    result = await client.sync_playlist(name=playlist.name, song_ids=song_ids, public=public)
    state.add_log(
        "playlist",
        "Playlist synced to music library: "
        f"playlist_id={playlist.id}, name={playlist.name}, "
        f"media_server={server.name}, username={server.username or '-'}, public={public}, "
        f"library_playlist_id={result.playlist_id or '-'}, "
        f"mode={result.mode}, tracks={result.synced_count}",
    )
    return result.playlist_id, result.synced_count, result.mode


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


async def _prepare_source_file_reorganize(
    state: AppState,
    source_path: Path,
    config: ScrapingConfig,
) -> tuple[Path, ...]:
    source_roots = tuple(path for path in (config.source_directory,) if path is not None)
    source_keys = _path_match_keys(source_path, source_roots)
    exclude_paths: list[Path] = []
    seen_ids: set[int] = set()
    for media in await state.repository.list_media_files():
        if media.id in seen_ids:
            continue
        if not _path_matches_any_key(media.source_path, source_keys, source_roots):
            continue
        seen_ids.add(media.id)
        exclude_paths.extend(await _prepare_media_record_reorganize(state, media, config))
    return tuple(exclude_paths)


async def _prepare_media_record_reorganize(
    state: AppState,
    media: MediaFile,
    config: ScrapingConfig,
) -> tuple[Path, ...]:
    exclude_paths: list[Path] = []
    if media.library_path:
        library_paths = _media_library_path_candidates(media.library_path, config)
        exclude_paths.extend(library_paths)
        for library_path in library_paths:
            if media.status != "success":
                continue
            if await asyncio.to_thread(
                _paths_are_same_file,
                library_path,
                Path(media.source_path),
            ):
                continue
            await _delete_file_path(library_path)
            break
    elif media.error_message:
        legacy_paths = _media_existing_path_candidates(media.error_message, config)
        exclude_paths.extend(legacy_paths)
        for legacy_path in legacy_paths:
            await _delete_file_path(legacy_path)
            break
    await state.repository.delete_media_file(media.id)
    return tuple(exclude_paths)


def _media_existing_path_candidates(message: str, config: ScrapingConfig) -> tuple[Path, ...]:
    match = re.search(r"(?:已存在路径|原路径)=([^，]+)", message)
    if match is None:
        return ()
    return _media_library_path_candidates(match.group(1).strip(), config)


def _media_library_path_candidates(value: str, config: ScrapingConfig) -> tuple[Path, ...]:
    raw = Path(value)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        for root in (config.mapped_directory, config.source_directory):
            if root is not None:
                candidates.append(root / raw)
        candidates.append(raw)
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _normalized_path_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return tuple(deduped)


def _paths_are_same_file(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError:
        return False
    return _path_match_key(left) == _path_match_key(right)


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
    return _scraping_file_root_or_409(config, "source")


def _scraping_file_root_or_409(config: ScrapingConfig, root_type: str) -> Path:
    if root_type == "mapped":
        configured = config.mapped_directory
        label = "映射目录"
    else:
        configured = config.source_directory
        label = "源文件目录"
    if configured is None:
        raise HTTPException(status_code=409, detail=f"请先配置刮削{label}。")
    root = configured.expanduser().resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"刮削{label}不存在。")
    if not root.is_dir():
        raise HTTPException(status_code=422, detail=f"刮削{label}不是目录。")
    return root


def _resolve_source_relative_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path or "")
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="只能访问当前文件目录下的相对路径。")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=403, detail="不能访问当前文件目录之外的路径。")
    return target


def _resolve_source_delete_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path or "")
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="只能访问当前文件目录下的相对路径。")
    if not relative.parts:
        raise HTTPException(status_code=400, detail="不能删除当前文件目录。")
    parent = (root / relative).parent.resolve()
    if not parent.is_relative_to(root):
        raise HTTPException(status_code=403, detail="不能访问当前文件目录之外的路径。")
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
    return _audio_files_for_target(target, root=root)


def _audio_files_for_target(target: Path, *, root: Path | None = None) -> tuple[Path, ...]:
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
            or (root is not None and not resolved.is_relative_to(root))
            or not resolved.is_file()
            or not _is_audio_file(resolved)
        ):
            continue
        seen.add(resolved)
        files.append(resolved)
    return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))


def _source_audio_files_for_targets(root: Path, targets: list[Path]) -> tuple[Path, ...]:
    files: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        for source_file in _source_audio_files(root, target):
            if source_file in seen:
                continue
            seen.add(source_file)
            files.append(source_file)
    return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))


def _path_match_key(path: str | Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).expanduser().resolve(strict=False))
    except OSError:
        return str(Path(path).expanduser())


def _path_match_keys(path: str | Path | None, roots: tuple[Path, ...] = ()) -> set[str]:
    if path is None:
        return set()
    raw_path = Path(path).expanduser()
    keys = {_normalized_path_key(raw_path)}
    resolved = raw_path.resolve(strict=False)
    keys.add(_normalized_path_key(resolved))
    for root in roots:
        root_resolved = root.expanduser().resolve(strict=False)
        with contextlib.suppress(ValueError):
            keys.add(_normalized_path_key(resolved.relative_to(root_resolved)))
    return {key for key in keys if key}


def _normalized_path_key(path: Path) -> str:
    return path.as_posix().lstrip("./")


def _scraping_file_resource_key(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError:
        resolved = path.expanduser().absolute()
    digest = hashlib.sha1(str(resolved).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"scraping-file:{digest}"


def _scraping_batch_resource_key(prefix: str, source_files: Iterable[Path]) -> str:
    identity = "|".join(
        sorted(str(path.expanduser()) for path in source_files)
    )
    digest = hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _scraping_file_transfer_runner(
    state: AppState,
) -> Callable[[Path, Callable[[], Awaitable[ScrapingFileOutcome]]], Awaitable[ScrapingFileOutcome]]:
    async def run(
        source_file: Path,
        runner: Callable[[], Awaitable[ScrapingFileOutcome]],
    ) -> ScrapingFileOutcome:
        return await state.task_manager.run_exclusive(
            task_type="FILE_ORGANIZE",
            resource_keys=[_scraping_file_resource_key(source_file)],
            payload={"source_file": str(source_file)},
            wait_log_message=f"File organization waiting for file resource: {source_file.name}",
            runner=runner,
        )

    return run


def _path_matches_any_key(
    path: str | Path | None,
    excluded_keys: set[str],
    roots: tuple[Path, ...],
) -> bool:
    for key in _path_match_keys(path, roots):
        if key in excluded_keys:
            return True
        if any(_path_key_suffix_matches(key, excluded) for excluded in excluded_keys):
            return True
    return False


def _path_key_suffix_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return "/" in shorter and longer.endswith(f"/{shorter}")


async def _scrape_manual_source_files(
    state: AppState,
    config: ScrapingConfig,
    task_name: str,
    source_files: tuple[Path, ...],
    *,
    manual_metadata: dict[Path, tuple[TrackMetadata, ...]] | None = None,
    contextual_metadata: dict[Path, ContextualMetadata] | None = None,
    exclude_library_paths: tuple[Path, ...] = (),
    use_task_manager: bool = True,
) -> ScrapingSummary:
    try:
        await _sync_music_library_from_media_server(state)
    except Exception as exc:  # noqa: BLE001
        state.add_log(
            "library",
            f"Music library sync before manual scraping failed: {exc}",
            "WARNING",
        )
    library_roots = tuple(
        path
        for path in (config.mapped_directory, config.source_directory)
        if path is not None
    )
    excluded_library_keys = {
        key
        for path in exclude_library_paths
        for key in _path_match_keys(path, library_roots)
    }
    library_tracks = tuple(
        LibraryTrackSnapshot(
            title=item.title,
            artist=item.artist,
            album=item.album,
            size=item.size,
            path=item.path,
        )
        for item in await state.repository.list_music_library_tracks()
        if not _path_matches_any_key(item.path, excluded_library_keys, library_roots)
    )
    media_history = tuple(
        LibraryTrackSnapshot(
            title=item.title or "",
            artist=item.artist,
            album=item.album,
            size=media_file_size,
            path=item.library_path,
        )
        for item in await state.repository.list_media_files()
        if item.title
        and item.status == "success"
        and item.library_path
        and not _path_matches_any_key(
            item.library_path,
            excluded_library_keys,
            library_roots,
        )
        and (media_file_size := _file_size_or_none(item.library_path)) is not None
    )
    async def record_file_result(item: ScrapingFileResult) -> None:
        if item.status in {"success", "skipped"}:
            await _ensure_artist_from_metadata(
                state,
                item.metadata,
                context=f"manual scraping {item.source_path}",
            )
        await state.repository.record_scraping_result(
            torrent_hash=None,
            source_path=item.source_path,
            library_path=item.library_path,
            operation_type=item.operation_type,
            metadata=item.metadata,
            status=item.status,
            error_message=item.error_message,
        )
        state.add_log(
            "metadata",
            _scraping_file_log_message(task_name, item),
            "WARNING" if item.status == "failed" else "INFO",
        )

    async def run_scrape() -> ScrapingSummary:
        forced_metadata = {
            source_file: candidates[0]
            for source_file, candidates in (manual_metadata or {}).items()
            if candidates
        }
        return await state.scraper.process_download(
            task_name=task_name,
            save_path=None,
            config=config,
            source_files=source_files,
            library_tracks=library_tracks,
            media_history=media_history,
            forced_metadata=forced_metadata,
            contextual_metadata=contextual_metadata,
            on_file_result=record_file_result,
            transfer_runner=_scraping_file_transfer_runner(state),
        )

    if use_task_manager:
        summary = await state.task_manager.run_exclusive(
            task_type="SCRAPE",
            resource_keys=[_scraping_batch_resource_key("manual-scrape", source_files)],
            payload={
                "mode": "manual",
                "task_name": task_name,
                "source_file_count": len(source_files),
            },
            wait_log_message=f"Manual scraping is waiting for scraper resource: {task_name}",
            runner=run_scrape,
        )
    else:
        summary = await run_scrape()
    state.add_log(
        "metadata",
        "Manual scraping completed for "
        f"{task_name}: files={summary.source_files}, mapped={summary.mapped_files}, "
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
            await _schedule_download_refresh_library(state, task)
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
                resolved = await state.repository.update_download_task(
                    task.id,
                    torrent_hash=status.torrent_hash,
                )
                if resolved is not None:
                    await _sync_playlist_tracks_for_download_task(state, resolved)
        if status is None:
            if has_real_hash:
                deleted = await state.repository.update_download_task(
                    task.id,
                    status="deleted",
                    last_error="qBittorrent 中未找到该任务，可能已被删除。",
                )
                if deleted is not None:
                    await _sync_playlist_tracks_for_download_task(state, deleted)
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
        updated = await state.repository.update_download_task(task.id, **changes)
        if updated is not None:
            await _sync_playlist_tracks_for_download_task(state, updated)


async def _schedule_download_refresh_library(
    state: AppState,
    task: TorrentRecord,
) -> None:
    refresh_task = task
    if task.status != "refreshing_library":
        updated = await state.repository.update_download_task(
            task.id,
            status="refreshing_library",
        )
        if updated is not None:
            refresh_task = updated
            await _sync_playlist_tracks_for_download_task(state, updated)
    try:
        source_files = await _scraping_source_files_for_task(state, refresh_task)
    except ScrapingSourceDirectoryNotFound as exc:
        failed = await state.repository.update_download_task(
            task.id,
            status="source_directory_not_found",
            last_error=str(exc),
        )
        if failed is not None:
            await _sync_playlist_tracks_for_download_task(state, failed)
        state.add_log(
            "metadata",
            f"Scraping source directory not found for {task.name}: {exc}",
            "WARNING",
        )
        return
    if source_files is None:
        return
    scheduled, pending, terminal = await _schedule_download_item_processing_for_files(
        state,
        refresh_task,
        source_files,
    )
    if scheduled or pending:
        state.add_log(
            "metadata",
            "Download file processing scheduled: "
            f"task={task.id}, name={task.name}, files={len(source_files)}, "
            f"pending={pending}, terminal={terminal}, scheduled={scheduled}",
        )
        return
    if terminal >= len(source_files):
        await _finalize_download_refresh_if_ready(state, task.id)
        return
    idempotency_key = f"download-refresh-library:{task.id}"
    existing = await state.repository.get_system_task_by_idempotency_key(idempotency_key)
    if existing is not None:
        if existing.status in {"WAIT", "RUNNING"}:
            return
        if existing.status == "FAILED":
            failed = await state.repository.update_download_task(
                task.id,
                status="failed",
                last_error=existing.error_message or "Download refresh task failed.",
            )
            if failed is not None:
                await _sync_playlist_tracks_for_download_task(state, failed)
            state.add_log(
                "library",
                f"Download refresh task failed for {task.name}: {existing.error_message}",
                "ERROR",
            )
        return
    await state.task_manager.enqueue(
        TaskCreate(
            task_type="DOWNLOAD_REFRESH_LIBRARY",
            payload={
                "torrent_record_id": task.id,
                "task_name": refresh_task.name,
            },
            resource_keys=[f"download-refresh:{task.id}"],
            priority=DOWNLOAD_REFRESH_TASK_PRIORITY,
            max_attempts=3,
            idempotency_key=idempotency_key,
        )
    )


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


async def _refresh_library_for_task(
    state: AppState,
    task: TorrentRecord,
    *,
    use_scrape_task_manager: bool = True,
) -> None:
    await _wait_for_download_item_scrapes(state, task.id, task.name)
    if task.status != "refreshing_library":
        refreshing = await state.repository.update_download_task(
            task.id,
            status="refreshing_library",
        )
        if refreshing is not None:
            await _sync_playlist_tracks_for_download_task(state, refreshing)
    try:
        summary = await _scrape_download_for_task(
            state,
            task,
            use_task_manager=use_scrape_task_manager,
        )
    except ScrapingSourceDirectoryNotFound as exc:
        failed = await state.repository.update_download_task(
            task.id,
            status="source_directory_not_found",
            last_error=str(exc),
        )
        if failed is not None:
            await _sync_playlist_tracks_for_download_task(state, failed)
        state.add_log(
            "metadata",
            f"Scraping source directory not found for {task.name}: {exc}",
            "WARNING",
        )
        return
    if (
        summary is not None
        and not summary.mapped_files
        and not summary.updated_files
        and not summary.moved_files
    ):
        state.add_log(
            "library",
            f"Library refresh skipped for {task.name}: no files transferred.",
        )
        refreshed = await state.repository.update_download_task(
            task.id,
            status="library_refreshed",
            library_refreshed_at=datetime.now(UTC),
        )
        if refreshed is not None:
            await _sync_playlist_tracks_for_download_task(state, refreshed)
        await _send_event_notifications(state, "library", refreshed or task)
        return
    server = await state.repository.default_media_server()
    if server is None:
        failed = await state.repository.update_download_task(
            task.id,
            status="failed",
            last_error="No enabled default media server is configured.",
        )
        if failed is not None:
            await _sync_playlist_tracks_for_download_task(state, failed)
        state.add_log(
            "library",
            f"Library refresh failed for {task.name}: no media server",
            "ERROR",
        )
        return
    try:
        state.add_log("library", f"Refreshing media library via {server.name}: {task.name}")
        client = build_media_server_client(server)
        await client.start_scan()
    except Exception as exc:  # noqa: BLE001
        failed = await state.repository.update_download_task(
            task.id,
            status="failed",
            last_error=str(exc),
        )
        if failed is not None:
            await _sync_playlist_tracks_for_download_task(state, failed)
        state.add_log("library", f"Library refresh failed for {task.name}: {exc}", "ERROR")
        return
    refreshed = await state.repository.update_download_task(
        task.id,
        status="library_refreshed",
        library_refreshed_at=datetime.now(UTC),
    )
    if refreshed is not None:
        await _sync_playlist_tracks_for_download_task(state, refreshed)
    state.add_log("library", f"Media library refresh requested: {task.name}")
    _fire_sync = asyncio.create_task(
        _sync_music_library_after_refresh(state),
        name="musicpilot-music-library-sync-after-refresh",
    )
    state._background_tasks.add(_fire_sync)
    _fire_sync.add_done_callback(state._background_tasks.discard)
    await _send_event_notifications(state, "library", refreshed or task)


async def _scrape_download_for_task(
    state: AppState,
    task: TorrentRecord,
    *,
    use_task_manager: bool = True,
) -> ScrapingSummary | None:
    settings_payload = await state.repository.get_system_settings()
    config = scraping_config_from_payload(settings_payload)
    if not config.enabled:
        return
    if (task.payload or {}).get("scraping_completed"):
        return
    try:
        try:
            await _sync_music_library_from_media_server(state)
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
                size=media_file_size,
                path=item.library_path,
            )
            for item in await state.repository.list_media_files()
            if item.title
            and item.status == "success"
            and item.library_path
            and (media_file_size := _file_size_or_none(item.library_path)) is not None
        )
        source_files = await _scraping_source_files_for_task(state, task)
        if source_files is None:
            return
        cached_metadata = await _cached_metadata_for_task_source_files(
            state,
            task,
            source_files,
        )
        async def run_scrape() -> ScrapingSummary:
            return await state.scraper.process_download(
                task_name=task.name,
                save_path=task.save_path,
                config=config,
                source_files=source_files,
                library_tracks=library_tracks,
                media_history=media_history,
                cached_metadata=cached_metadata,
                transfer_runner=_scraping_file_transfer_runner(state),
            )

        if use_task_manager:
            summary = await state.task_manager.run_exclusive(
                task_type="SCRAPE",
                resource_keys=[_scraping_batch_resource_key("download-scrape", source_files)],
                payload={
                    "mode": "download",
                    "torrent_record_id": task.id,
                    "task_name": task.name,
                    "source_file_count": len(source_files),
                },
                priority=DOWNLOAD_REFRESH_TASK_PRIORITY,
                wait_log_message=f"Download scraping is waiting for scraper resource: {task.name}",
                runner=run_scrape,
            )
        else:
            summary = await run_scrape()
    except ScrapingSourceDirectoryNotFound:
        raise
    except Exception as exc:  # noqa: BLE001
        state.add_log("metadata", f"Scraping failed for {task.name}: {exc}", "WARNING")
        return
    payload = dict(task.payload or {})
    payload["scraping_completed"] = True
    await state.repository.update_download_task(task.id, payload=payload)
    for item in summary.results:
        if item.status in {"success", "skipped"}:
            await _ensure_artist_from_metadata(
                state,
                item.metadata,
                context=f"download scraping {task.name}",
            )
        await state.repository.record_scraping_result(
            torrent_hash=task.torrent_hash,
            source_path=item.source_path,
            library_path=item.library_path,
            operation_type=item.operation_type,
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
    return summary


async def _organize_download_task_item(
    state: AppState,
    task_id: int,
    item_id: int,
    source_file: Path,
    task_name: str,
) -> TorrentRecordItem | None:
    task = await state.repository.get_download_task(task_id)
    item = await state.repository.get_download_task_item(item_id)
    if task is None or item is None:
        return item
    await state.repository.update_download_task_item(
        item_id,
        status="organizing",
        last_error=None,
    )
    settings_payload = await state.repository.get_system_settings()
    config = scraping_config_from_payload(settings_payload)
    if not config.enabled:
        return await state.repository.update_download_task_item(
            item_id,
            status="organize_failed",
            last_error="Scraping is disabled.",
        )
    source_exists = await asyncio.to_thread(
        lambda: source_file.exists() and source_file.is_file()
    )
    if not source_exists:
        return await state.repository.update_download_task_item(
            item_id,
            status="organize_failed",
            last_error="Source file is missing.",
        )
    library_tracks, media_history = await _scraping_library_snapshots(state)
    metadata = _track_metadata_from_payload(item.metadata_payload)
    cached_metadata = {source_file: (metadata,)} if metadata is not None else {}

    async def record_file_result(result: ScrapingFileResult) -> None:
        if result.status in {"success", "skipped"}:
            await _ensure_artist_from_metadata(
                state,
                result.metadata,
                context=f"download file organize {task_name}",
            )
        await state.repository.record_scraping_result(
            torrent_hash=task.torrent_hash,
            source_path=result.source_path,
            library_path=result.library_path,
            operation_type=result.operation_type,
            metadata=result.metadata,
            status=result.status,
            error_message=result.error_message,
        )
        state.add_log(
            "metadata",
            _scraping_file_log_message(task_name, result),
            "WARNING" if result.status == "failed" else "INFO",
        )

    try:
        summary = await state.scraper.process_download(
            task_name=task_name,
            save_path=task.save_path,
            config=config,
            source_files=(source_file,),
            library_tracks=library_tracks,
            media_history=media_history,
            cached_metadata=cached_metadata,
            on_file_result=record_file_result,
            preload_metadata=False,
            metadata_lookup_completed_files={source_file},
        )
    except Exception as exc:  # noqa: BLE001
        state.add_log(
            "metadata",
            "Download file organization failed: "
            f"item_id={item_id}, file={source_file}, error={exc}",
            "ERROR",
        )
        return await state.repository.update_download_task_item(
            item_id,
            status="organize_failed",
            last_error=str(exc) or exc.__class__.__name__,
        )
    result = summary.results[0] if summary.results else None
    if result is None:
        return await state.repository.update_download_task_item(
            item_id,
            status="organize_failed",
            last_error="No scraping result was produced.",
        )
    status = {
        "success": "organized",
        "skipped": "organize_skipped",
        "failed": "organize_failed",
    }.get(result.status, "organize_failed")
    return await state.repository.update_download_task_item(
        item_id,
        status=status,
        metadata_title=result.metadata.title,
        metadata_artist=result.metadata.artist,
        metadata_album=result.metadata.album,
        metadata_payload=_track_metadata_payload(result.metadata),
        last_error=result.error_message if result.status != "success" else None,
    )


async def _scraping_library_snapshots(
    state: AppState,
) -> tuple[tuple[LibraryTrackSnapshot, ...], tuple[LibraryTrackSnapshot, ...]]:
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
            size=media_file_size,
            path=item.library_path,
        )
        for item in await state.repository.list_media_files()
        if item.title
        and item.status == "success"
        and item.library_path
        and (media_file_size := _file_size_or_none(item.library_path)) is not None
    )
    return library_tracks, media_history


async def _finalize_download_refresh_if_ready(state: AppState, task_id: int) -> None:
    await state.task_manager.run_exclusive(
        task_type="DOWNLOAD_FINALIZE_LIBRARY",
        resource_keys=[f"download-finalize:{task_id}"],
        payload={"torrent_record_id": task_id},
        runner=lambda: _finalize_download_refresh_if_ready_direct(state, task_id),
    )


async def _finalize_download_refresh_if_ready_direct(state: AppState, task_id: int) -> None:
    task = await state.repository.get_download_task(task_id)
    if task is None or task.status == "library_refreshed":
        return
    items = await state.repository.list_download_task_items(task_id)
    payload = task.payload if isinstance(task.payload, dict) else {}
    organize_item_ids = {
        int(item)
        for item in payload.get("organize_item_ids", [])
        if isinstance(item, int)
    }
    if organize_item_ids:
        items = [item for item in items if item.id in organize_item_ids]
    if not items:
        return
    if any(item.status not in DOWNLOAD_ITEM_ORGANIZE_TERMINAL_STATUSES for item in items):
        return
    organized_count = sum(1 for item in items if item.status == "organized")
    if organized_count <= 0:
        state.add_log(
            "library",
            f"Library refresh skipped for {task.name}: no files transferred.",
        )
        refreshed = await state.repository.update_download_task(
            task.id,
            status="library_refreshed",
            library_refreshed_at=datetime.now(UTC),
        )
        if refreshed is not None:
            await _sync_playlist_tracks_for_download_task(state, refreshed)
        await _send_event_notifications(state, "library", refreshed or task)
        return
    server = await state.repository.default_media_server()
    if server is None:
        failed = await state.repository.update_download_task(
            task.id,
            status="failed",
            last_error="No enabled default media server is configured.",
        )
        if failed is not None:
            await _sync_playlist_tracks_for_download_task(state, failed)
        state.add_log(
            "library",
            f"Library refresh failed for {task.name}: no media server",
            "ERROR",
        )
        return
    try:
        state.add_log("library", f"Refreshing media library via {server.name}: {task.name}")
        client = build_media_server_client(server)
        await client.start_scan()
    except Exception as exc:  # noqa: BLE001
        failed = await state.repository.update_download_task(
            task.id,
            status="failed",
            last_error=str(exc),
        )
        if failed is not None:
            await _sync_playlist_tracks_for_download_task(state, failed)
        state.add_log("library", f"Library refresh failed for {task.name}: {exc}", "ERROR")
        return
    refreshed = await state.repository.update_download_task(
        task.id,
        status="library_refreshed",
        library_refreshed_at=datetime.now(UTC),
    )
    if refreshed is not None:
        await _sync_playlist_tracks_for_download_task(state, refreshed)
    state.add_log("library", f"Media library refresh requested: {task.name}")
    _fire_sync = asyncio.create_task(
        _sync_music_library_after_refresh(state),
        name="musicpilot-music-library-sync-after-refresh",
    )
    state._background_tasks.add(_fire_sync)
    _fire_sync.add_done_callback(state._background_tasks.discard)
    await _send_event_notifications(state, "library", refreshed or task)


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
    except Exception as exc:  # noqa: BLE001
        state.add_log(
            "metadata",
            f"Scraping skipped for {task.name}: qBittorrent status failed: {exc}",
            "WARNING",
        )
        return None
    downloader_config = await state.repository.default_downloader()
    source_files = await asyncio.to_thread(
        _mapped_torrent_audio_files,
        task,
        status,
        downloader_config,
    )
    if source_files:
        state.add_log(
            "metadata",
            "Scraping source files resolved from mapped download path for "
            f"{task.name}: files={len(source_files)}",
        )
        return source_files
    state.add_log(
        "metadata",
        f"Scraping source files not found from mapped download path for {task.name}.",
        "WARNING",
    )
    raise ScrapingSourceDirectoryNotFound(
        _scraping_source_directory_not_found_message(task, status, downloader_config)
    )


async def _cached_metadata_for_task_source_files(
    state: AppState,
    task: TorrentRecord,
    source_files: tuple[Path, ...],
) -> dict[Path, tuple[TrackMetadata, ...]]:
    items = await state.repository.list_download_task_items(task.id)
    candidates_by_item = [
        (item, metadata)
        for item in items
        if (metadata := _track_metadata_from_payload(item.metadata_payload)) is not None
    ]
    if not candidates_by_item:
        return {}

    result: dict[Path, tuple[TrackMetadata, ...]] = {}
    used_item_ids: set[int] = set()
    for source_file in source_files:
        matched: list[TrackMetadata] = []
        for item, metadata in candidates_by_item:
            if item.id in used_item_ids:
                continue
            if _source_file_matches_torrent_item(source_file, item):
                matched.append(metadata)
                used_item_ids.add(item.id)
        if matched:
            result[source_file] = tuple(matched)

    for source_file in source_files:
        if source_file in result:
            continue
        same_name = [
            (item, metadata)
            for item, metadata in candidates_by_item
            if item.id not in used_item_ids
            and item.file_name.casefold() == source_file.name.casefold()
        ]
        if len(same_name) == 1:
            item, metadata = same_name[0]
            used_item_ids.add(item.id)
            result[source_file] = (metadata,)
    return result


def _download_items_by_source_file(
    source_files: tuple[Path, ...],
    items: list[TorrentRecordItem],
) -> dict[Path, TorrentRecordItem]:
    result: dict[Path, TorrentRecordItem] = {}
    used_item_ids: set[int] = set()
    for source_file in source_files:
        for item in items:
            if item.id in used_item_ids:
                continue
            if _source_file_matches_torrent_item(source_file, item):
                result[source_file] = item
                used_item_ids.add(item.id)
                break
    for source_file in source_files:
        if source_file in result:
            continue
        same_name = [
            item
            for item in items
            if item.id not in used_item_ids
            and item.file_name.casefold() == source_file.name.casefold()
        ]
        if len(same_name) == 1:
            item = same_name[0]
            result[source_file] = item
            used_item_ids.add(item.id)
    return result


def _scraping_source_directory_not_found_message(
    task: TorrentRecord,
    status: DownloadStatus,
    downloader: DownloaderConfig | None,
) -> str:
    remote_roots = _download_remote_roots(task, status, downloader)
    content_roots = _torrent_content_roots(task, status)
    local_root = (downloader.local_path if downloader is not None else "").strip()
    remote_paths = content_roots or tuple(Path(item) for item in remote_roots)
    remote_text = _join_log_values(str(item) for item in remote_paths)
    if local_root:
        return (
            "下载已完成，但映射后的本机目录中没有找到可刮削的音频文件。"
            f"请检查下载器下载目录和本机映射目录。qBittorrent路径={remote_text or '-'}，"
            f"本机映射目录={local_root}"
        )
    return (
        "下载已完成，但 MusicPilot 无法访问 qBittorrent 返回的下载目录，"
        "且下载器未配置本机映射目录。"
        f"请在下载器设置中配置映射目录。qBittorrent路径={remote_text or '-'}"
    )


def _join_log_values(values: Iterable[object]) -> str:
    items = [str(item) for item in values if str(item).strip()]
    if len(items) <= 3:
        return ", ".join(items)
    return ", ".join(items[:3]) + f", ...(+{len(items) - 3})"


def _track_metadata_from_payload(payload: dict[str, Any] | None) -> TrackMetadata | None:
    if not isinstance(payload, dict):
        return None
    title = _optional_string(payload.get("title"))
    if title is None:
        return None
    extra = payload.get("extra")
    return TrackMetadata(
        title=title,
        artist=_optional_string(payload.get("artist")),
        album=_optional_string(payload.get("album")),
        year=_optional_int(payload.get("year")),
        track_number=_optional_int(payload.get("track_number")),
        lyrics=_optional_string(payload.get("lyrics")),
        cover_url=_optional_string(payload.get("cover_url")),
        extra=dict(extra) if isinstance(extra, dict) else {},
    )


def _source_file_matches_torrent_item(source_file: Path, item: TorrentRecordItem) -> bool:
    item_parts = _normalized_torrent_path_parts(item.file_path)
    if not item_parts:
        return False
    source_parts = tuple(part.casefold() for part in source_file.parts)
    return len(source_parts) >= len(item_parts) and source_parts[-len(item_parts) :] == item_parts


def _normalized_torrent_path_parts(value: str) -> tuple[str, ...]:
    return tuple(
        part.casefold()
        for part in Path(value.replace("\\", "/")).parts
        if part not in {"", ".", "/"}
    )


def _mapped_torrent_audio_files(
    task: TorrentRecord,
    status: DownloadStatus,
    downloader: DownloaderConfig | None,
) -> tuple[Path, ...]:
    targets = _mapped_torrent_targets(task, status, downloader)
    files: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        for source_file in _audio_files_for_target(target):
            if source_file in seen:
                continue
            seen.add(source_file)
            files.append(source_file)
    return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))


def _mapped_torrent_targets(
    task: TorrentRecord,
    status: DownloadStatus,
    downloader: DownloaderConfig | None,
) -> tuple[Path, ...]:
    remote_roots = _download_remote_roots(task, status, downloader)
    local_root = (downloader.local_path if downloader is not None else "").strip()
    candidates = _torrent_content_roots(task, status)
    mapped: list[Path] = []
    for candidate in candidates:
        for remote_root in remote_roots:
            local = _map_downloader_path(candidate, remote_root, local_root)
            if local is not None:
                mapped.append(local)
    return tuple(_dedupe_paths(mapped))


def _download_remote_roots(
    task: TorrentRecord,
    status: DownloadStatus,
    downloader: DownloaderConfig | None,
) -> tuple[str, ...]:
    roots: list[str] = []
    if downloader is not None and downloader.download_path.strip():
        roots.append(downloader.download_path)
    if task.save_path:
        roots.append(task.save_path)
    if status.save_path is not None:
        roots.append(str(status.save_path))
    seen: set[str] = set()
    deduped: list[str] = []
    for root in roots:
        key = _normalized_path_text(root).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return tuple(deduped)


def _torrent_content_roots(task: TorrentRecord, status: DownloadStatus) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if status.content_path is not None:
        candidates.append(status.content_path)
    if status.save_path is not None and task.name:
        candidates.append(status.save_path / task.name)
    if task.save_path and task.name:
        candidates.append(Path(task.save_path) / task.name)
    return tuple(_dedupe_paths(candidates))


def _map_downloader_path(
    path: Path,
    remote_root: str,
    local_root: str,
) -> Path | None:
    if not remote_root.strip() or not local_root.strip():
        return None
    path_text = _normalized_path_text(str(path))
    root_text = _normalized_path_text(remote_root).rstrip("/")
    if not path_text or not root_text:
        return None
    path_key = path_text.casefold()
    root_key = root_text.casefold()
    if path_key == root_key:
        suffix = ""
    elif path_key.startswith(f"{root_key}/"):
        suffix = path_text[len(root_text) :].lstrip("/")
    else:
        return None
    local = Path(local_root).expanduser()
    if not suffix:
        return local
    return local.joinpath(*[part for part in suffix.split("/") if part])


def _normalized_path_text(value: str) -> str:
    return value.replace("\\", "/").rstrip("/")


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
        "local_path": str(item.get("local_path") or ""),
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
        filter={
            name: {
                "include": list(rule.include),
                "exclude": list(rule.exclude),
            }
            for name, rule in parser.result_filter.items()
        },
        search_query_param=parser.search_query_param,
        search_params=parser.search_params,
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


async def _stream_temporary_file(path: Path) -> AsyncIterator[bytes]:
    try:
        with path.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                yield chunk
                await asyncio.sleep(0)
    finally:
        with contextlib.suppress(FileNotFoundError):
            await asyncio.to_thread(path.unlink)


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


def _current_app_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as file:
            project = tomllib.load(file).get("project", {})
    except OSError:
        project = {}
    version = project.get("version")
    if version:
        return str(version)
    try:
        return importlib.metadata.version("musicpilot")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


async def _resolve_proxy_for_site(
    state: AppState,
    site: IndexerSite | None,
) -> str | None:
    if site is None or not site.use_proxy:
        return None
    system_settings = await state.repository.get_system_settings()
    return _proxy_url(system_settings)


def _category_from_logger(name: str) -> str:
    if name.startswith("musicpilot.metadata.scraping"):
        return "metadata"
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
