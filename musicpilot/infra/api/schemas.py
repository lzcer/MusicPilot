from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from musicpilot.core.defaults import DEFAULT_SEARCH_EXCLUDE_KEYWORDS


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str


class AboutResponse(BaseModel):
    app: str
    version: str
    latest_version: str | None
    latest_release_url: str | None
    repository_name: str
    repository_url: str
    description: str
    license: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    status: str
    username: str


class TestResponse(BaseModel):
    ok: bool
    message: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class SearchResultResponse(BaseModel):
    title: str
    download_url: str
    source: str
    seeders: int
    leechers: int = 0
    size_bytes: int | None = None
    details_url: str | None = None
    subtitle: str | None = None
    published_at: str | None = None
    promotion: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]


class MediaCandidateResponse(BaseModel):
    title: str
    artist: str | None = None
    album: str | None = None
    albums: list[str] = Field(default_factory=list)
    release_date: str | None = None
    cover_url: str | None = None
    source: str
    external_id: str
    group_key: str | None = None


class MetadataSearchResponse(BaseModel):
    query: str
    artist: str | None = None
    candidates: list[MediaCandidateResponse]
    next_offset: int | None = None
    has_more: bool = False


class MetadataSiteSearchRequest(BaseModel):
    media: MediaCandidateResponse
    site_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=200)


class MetadataSiteSearchResponse(BaseModel):
    raw_count: int
    filtered_count: int
    results: list[SearchResultResponse]


class DownloadRequest(BaseModel):
    title: str = Field(min_length=1)
    download_url: str = Field(min_length=1)
    source: str = Field(min_length=1)
    seeders: int = 0
    leechers: int = 0
    size_bytes: int | None = None
    details_url: str | None = None
    subtitle: str | None = None
    published_at: str | None = None
    promotion: str | None = None
    category: str = "MusicPilot"
    media_metadata: MediaCandidateResponse | None = None
    resource: SearchResultResponse | None = None
    selected_site_ids: list[str] = Field(default_factory=list)


class DownloadResponse(BaseModel):
    status: str
    task_id: int | None = None
    torrent_hash: str | None = None


DownloadDeleteMode = Literal["record_only", "all"]
MediaDeleteMode = Literal["record_only", "media_file", "all"]
FileEntryType = Literal["file", "directory"]
FileRootType = Literal["source", "mapped"]


class DownloadTaskResponse(BaseModel):
    id: int | None = None
    torrent_hash: str | None = None
    name: str
    creation_type: str = "task_created"
    size_bytes: int | None = None
    state: str
    progress: float
    save_path: str | None = None
    source: str = ""
    last_error: str | None = None


class DownloadTaskItemResponse(BaseModel):
    id: int
    torrent_record_id: int
    file_name: str
    file_path: str
    size_bytes: int | None = None
    artist: str | None = None
    parsed_title: str | None = None
    metadata_title: str | None = None
    metadata_artist: str | None = None
    metadata_album: str | None = None
    playlist_track_id: int | None = None
    status: str
    last_error: str | None = None
    metadata_payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DashboardLibrarySummaryResponse(BaseModel):
    songs: int
    albums: int
    artists: int
    recent_7d_songs: int
    last_synced_at: datetime | None = None


class DashboardPlaylistSummaryResponse(BaseModel):
    playlists: int
    tracks: int
    existing_tracks: int
    pending_tracks: int
    failed_tracks: int


class DashboardDownloadItemResponse(BaseModel):
    id: int | None = None
    name: str
    state: str
    progress: float
    updated_at: datetime


class DashboardDownloadSummaryResponse(BaseModel):
    total: int
    active: int
    completed_7d: int
    failed: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    recent: list[DashboardDownloadItemResponse] = Field(default_factory=list)


class DashboardMediaItemResponse(BaseModel):
    id: int
    title: str | None = None
    artist: str | None = None
    source_path: str
    operation_type: str
    status: str
    updated_at: datetime


class DashboardMediaSummaryResponse(BaseModel):
    total: int
    success: int
    failed: int
    recent_7d: int
    recent: list[DashboardMediaItemResponse] = Field(default_factory=list)


class DashboardTaskSummaryResponse(BaseModel):
    waiting: int
    running: int
    failed: int
    slow: int


class DashboardStorageSummaryResponse(BaseModel):
    status: Literal["ready", "waiting", "error"]
    source_size_bytes: int | None = None
    expansion_size_bytes: int | None = None
    total_size_bytes: int | None = None
    calculated_at: datetime | None = None
    error: str | None = None


class DashboardResponse(BaseModel):
    library: DashboardLibrarySummaryResponse
    playlists: DashboardPlaylistSummaryResponse
    downloads: DashboardDownloadSummaryResponse
    media: DashboardMediaSummaryResponse
    tasks: DashboardTaskSummaryResponse
    storage: DashboardStorageSummaryResponse


class SystemTaskResponse(BaseModel):
    id: int
    task_type: str
    status: str
    chain_id: str
    parent_task_id: int | None = None
    priority: int
    payload: dict[str, object] = Field(default_factory=dict)
    error_message: str | None = None
    attempts: int
    max_attempts: int
    available_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SystemTaskInterruptRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class SystemTaskInterruptResponse(BaseModel):
    interrupted_ids: list[int] = Field(default_factory=list)
    skipped_ids: list[int] = Field(default_factory=list)
    not_found_ids: list[int] = Field(default_factory=list)


class FileEntryResponse(BaseModel):
    name: str
    path: str
    type: FileEntryType
    size: int | None = None
    modified_at: datetime | None = None


class FileListResponse(BaseModel):
    root: str
    path: str = ""
    parent: str | None = None
    entries: list[FileEntryResponse] = Field(default_factory=list)


class FileAudioCoverResponse(BaseModel):
    mime_type: str
    data: str


class FileAudioDetailResponse(BaseModel):
    name: str
    path: str
    extension: str
    format: str
    size: int
    modified_at: datetime
    title: str
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    year: int | None = None
    track_number: int | None = None
    lyrics: str | None = None
    duration: float | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    cover: FileAudioCoverResponse | None = None


class FileOrganizeRequest(BaseModel):
    path: str = ""
    paths: list[str] = Field(default_factory=list)


class FileOrganizeEnqueueResponse(BaseModel):
    source_files: int
    created_tasks: int
    existing_tasks: int


class FileManualOrganizeRequest(BaseModel):
    path: str = Field(min_length=1)
    title: str = Field(min_length=1)
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    year: int | None = None
    track_number: int | None = None
    lyrics: str | None = None
    cover_url: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class FileDirectoryManualOrganizeRequest(BaseModel):
    path: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    album: str = Field(min_length=1)


class FileOrganizeResponse(BaseModel):
    source_files: int
    mapped_files: int
    updated_files: int
    moved_files: int
    failed_files: int
    skipped_files: int


class FileBulkDeleteRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    root_type: FileRootType = "source"


class FileBulkDeleteFailure(BaseModel):
    path: str
    message: str


class FileBulkDeleteResponse(BaseModel):
    deleted_paths: list[str] = Field(default_factory=list)
    not_found_paths: list[str] = Field(default_factory=list)
    failures: list[FileBulkDeleteFailure] = Field(default_factory=list)


class MediaBulkDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    mode: MediaDeleteMode = "record_only"


class MediaBulkDeleteFailure(BaseModel):
    id: int
    message: str


class MediaBulkDeleteResponse(BaseModel):
    deleted_ids: list[int] = Field(default_factory=list)
    not_found_ids: list[int] = Field(default_factory=list)
    failures: list[MediaBulkDeleteFailure] = Field(default_factory=list)


class MediaRetryRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class MediaRetryResponse(BaseModel):
    total: int
    source_files: int
    failed_files: int


class TrackMetadataResponse(BaseModel):
    title: str
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    year: int | None = None
    track_number: int | None = None
    lyrics: str | None = None
    cover_url: str | None = None
    source: str | None = None
    source_id: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class MediaMetadataSearchResponse(BaseModel):
    query: str
    source: str
    results: list[TrackMetadataResponse]


class MediaManualOrganizeRequest(BaseModel):
    title: str = Field(min_length=1)
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    year: int | None = None
    track_number: int | None = None
    lyrics: str | None = None
    cover_url: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class IndexerResponse(BaseModel):
    name: str


class ParserFieldRequest(BaseModel):
    selector: str = Field(min_length=1)
    attribute: str = "text"
    regex: str | None = None
    index: int | None = None
    remove: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)


class NexusPHPParserRequest(BaseModel):
    list_selector: str = Field(
        default="table.torrents tr:has(a[href*='details.php']):has(a[href*='download.php'])",
        min_length=1,
    )
    fields: dict[str, ParserFieldRequest] = Field(default_factory=dict)
    filter: dict[str, object] = Field(default_factory=dict)
    search_path: str = "torrents.php"
    search_query_param: str = "search"
    search_params: dict[str, str] = Field(default_factory=dict)


class SiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1)
    cookie: str | None = None
    user_agent: str | None = None
    priority: int = Field(default=100, ge=0)
    max_concurrency: int = Field(default=2, ge=1, le=10)
    use_proxy: bool = False
    enabled: bool = True


class SiteResponse(SiteCreateRequest):
    id: str | None = None
    parser: NexusPHPParserRequest


class SitePriorityUpdateRequest(BaseModel):
    site_ids: list[str] = Field(min_length=1)


class DownloaderCreateRequest(BaseModel):
    id: str | None = None
    name: str = Field(default="qBittorrent", min_length=1, max_length=128)
    type: str = Field(default="qbittorrent", pattern="^(qbittorrent|transmission)$")
    base_url: str = Field(min_length=1)
    username: str = ""
    password: str = ""
    download_path: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    listen_mode: str = Field(default="polling", pattern="^(polling|qb_callback)$")
    monitor_tag: str = Field(default="MusicPilot", max_length=128)
    is_default: bool = True
    enabled: bool = True


class DownloaderResponse(BaseModel):
    id: str | None = None
    name: str
    type: str
    base_url: str
    username: str
    download_path: str = ""
    local_path: str = ""
    listen_mode: str = "polling"
    monitor_tag: str = "MusicPilot"
    is_default: bool
    enabled: bool = True


class MediaServerCreateRequest(BaseModel):
    id: str | None = None
    name: str = Field(default="Navidrome", min_length=1, max_length=128)
    type: str = Field(default="navidrome", pattern="^navidrome$")
    base_url: str = Field(min_length=1)
    api_key: str = ""
    username: str = ""
    password: str = ""
    is_default: bool = True
    enabled: bool = True


class MediaServerResponse(BaseModel):
    id: str | None = None
    name: str
    type: str
    base_url: str
    api_key: str = ""
    username: str = ""
    is_default: bool
    enabled: bool = True


class NotifierCreateRequest(BaseModel):
    id: str | None = None
    name: str = Field(default="Telegram Bot", min_length=1, max_length=128)
    type: str = Field(default="telegram", pattern="^telegram$")
    bot_token: str = ""
    webhook_url: str = ""
    chat_ids: str = ""
    use_proxy: bool = False
    enable_download_notify: bool = True
    enable_library_notify: bool = True
    enabled: bool = True


class NotifierResponse(BaseModel):
    id: str | None = None
    name: str
    type: str
    webhook_url: str = ""
    chat_ids: str = ""
    use_proxy: bool = False
    enable_download_notify: bool = True
    enable_library_notify: bool = True
    enabled: bool = True


class MusicPlatformConnectRequest(BaseModel):
    platform: Literal["spotify"] = "spotify"
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)


class MusicPlatformConnectResponse(BaseModel):
    connection_id: str
    authorization_url: str


class MusicPlatformResponse(BaseModel):
    id: str
    platform: str
    display_name: str = ""
    external_user_id: str | None = None
    status: str
    redirect_uri: str
    scopes: list[str] = Field(default_factory=list)
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class PlaylistAvailableResponse(BaseModel):
    external_id: str
    name: str
    owner_name: str | None = None
    description: str | None = None
    cover_url: str | None = None
    track_count: int = 0
    raw_payload: dict[str, object] = Field(default_factory=dict)


class PlaylistImportRequest(BaseModel):
    connection_id: str = Field(min_length=1)
    external_ids: list[str] = Field(min_length=1)


class PlaylistImportUrlRequest(BaseModel):
    import_token: str = ""
    url: str = ""


class PlaylistImportUrlPreviewRequest(BaseModel):
    url: str = Field(min_length=1)


class PlaylistImportUrlPreviewResponse(BaseModel):
    import_token: str
    platform: str
    external_id: str
    name: str
    owner_name: str | None = None
    description: str | None = None
    cover_url: str | None = None
    track_count: int = 0


class PlaylistResponse(BaseModel):
    id: int
    platform_connection_id: str
    platform: str
    external_id: str
    name: str
    owner_name: str | None = None
    description: str | None = None
    cover_url: str | None = None
    track_count: int = 0
    existing_count: int = 0
    waiting_count: int = 0
    submitted_count: int = 0
    failed_count: int = 0
    status: str
    last_synced_at: datetime | None = None
    last_download_started_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class PlaylistTrackResponse(BaseModel):
    id: int
    playlist_id: int
    platform: str
    external_id: str
    source_key: str = ""
    position: int
    original_title: str = ""
    title: str
    artist: str | None = None
    album: str | None = None
    duration: int | None = None
    isrc: str | None = None
    cover_url: str | None = None
    exists_in_library: bool = False
    matched_library_track_id: int | None = None
    download_status: str
    torrent_record_id: int | None = None
    last_checked_at: datetime | None = None
    last_download_attempt_at: datetime | None = None
    last_error: str | None = None


class PlaylistTrackPageResponse(BaseModel):
    items: list[PlaylistTrackResponse]
    total: int
    page: int
    page_size: int


class PlaylistTrackUpdateRequest(BaseModel):
    title: str = Field(min_length=1)
    artist: str | None = None
    album: str | None = None


class PlaylistImportResponse(BaseModel):
    playlists: list[PlaylistResponse]


class PlaylistDownloadResponse(BaseModel):
    status: str
    playlist_id: int


class PlaylistTrackDownloadResponse(BaseModel):
    status: str
    playlist_id: int
    track_id: int


class PlaylistLibrarySyncRequest(BaseModel):
    media_server_id: str | None = None
    public: bool = True


class PlaylistLibrarySyncResponse(BaseModel):
    status: str
    playlist_id: int
    library_playlist_id: str | None = None
    synced_count: int
    mode: str = "updated"


class ProxySettings(BaseModel):
    host: str = ""
    port: int = Field(default=0, ge=0, le=65535)
    username: str = ""
    password: str = ""


class ScrapingSettings(BaseModel):
    enabled: bool = False
    mode: Literal["source", "mapped", "copy"] = "mapped"
    source_directory: str = ""
    mapped_directory: str = ""
    scrape_when_missing: list[Literal["album", "artist", "lyrics"]] = Field(default_factory=list)
    required_metadata: list[Literal["album", "artist", "lyrics"]] = Field(default_factory=list)
    auto_rename: bool = False
    auto_classify: bool = False
    classify_by: Literal["artist", "album", "artist_album"] = "artist"
    duplicate_handling: Literal["ignore", "overwrite", "keep_largest"] = "ignore"


class SearchSettings(BaseModel):
    exclude_keywords: str = DEFAULT_SEARCH_EXCLUDE_KEYWORDS
    minimum_seeders: int = Field(default=1, ge=0)
    metadata_concurrency: int = Field(default=3, ge=1, le=20)


class SystemSettingsRequest(BaseModel):
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)


class SystemSettingsResponse(BaseModel):
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)


class LogEntryResponse(BaseModel):
    timestamp: str
    level: str
    message: str
    category: str = "system"


class QBittorrentWebhookRequest(BaseModel):
    download_path: str | None = None


class SubscriptionCreateRequest(BaseModel):
    kind: str = Field(pattern="^(artist|album|playlist)$")
    name: str = Field(min_length=1, max_length=512)
    external_id: str | None = None
    enabled: bool = True


class SubscriptionResponse(BaseModel):
    id: int
    kind: str
    name: str
    external_id: str | None
    enabled: bool
    last_checked_at: datetime | None = None


class MediaFileResponse(BaseModel):
    id: int
    torrent_hash: str | None
    source_path: str
    library_path: str | None = None
    operation_type: str = "mapped"
    operation_reason: str | None = None
    status: str = "success"
    operation_time: datetime
    remark: str | None = None
    error_message: str | None = None
    title: str | None
    artist: str | None
    album: str | None
    year: int | None
    track_number: int | None


class MediaFilePageResponse(BaseModel):
    items: list[MediaFileResponse]
    total: int
    page: int
    page_size: int


class MusicLibraryTrackResponse(BaseModel):
    id: str
    title: str
    artist: str | None = None
    album: str | None = None
    duration: int | None = None
    size: int | None = None
    year: int | None = None


class MusicLibraryStatsResponse(BaseModel):
    songs: int
    albums: int
    artists: int


class MusicLibraryTrackPageResponse(BaseModel):
    items: list[MusicLibraryTrackResponse]
    total: int
    page: int
    page_size: int
    stats: MusicLibraryStatsResponse


class ArtistAliasResponse(BaseModel):
    alias: str
    source: str = "manual"


class ArtistResponse(BaseModel):
    id: int
    name: str
    normalized_name: str
    aliases: list[ArtistAliasResponse] = Field(default_factory=list)


class ArtistPageResponse(BaseModel):
    items: list[ArtistResponse]
    total: int
    page: int
    page_size: int


class BuildArtistLibraryResponse(BaseModel):
    created: int


class ArtistBuildStatusResponse(BaseModel):
    running: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None


class ClearArtistLibraryResponse(BaseModel):
    deleted_artists: int
    deleted_aliases: int


class MergeArtistsRequest(BaseModel):
    target_id: int
    source_id: int


class AddArtistAliasRequest(BaseModel):
    artist_id: int
    alias: str = Field(min_length=1)
    source: str = "user"


class UpdateArtistRequest(BaseModel):
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
