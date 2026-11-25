export type ParserField = {
  selector: string
  attribute?: string
  regex?: string | null
  index?: number | null
  remove?: string[]
  filters?: string[]
}

export type ParserConfig = {
  list_selector: string
  fields: Record<string, ParserField>
  filter?: Record<string, unknown>
  search_path?: string
  search_query_param?: string
  search_params?: Record<string, string>
}

export type SearchResult = {
  title: string
  download_url: string
  source: string
  seeders: number
  leechers?: number
  size_bytes?: number | null
  details_url?: string | null
  subtitle?: string | null
  published_at?: string | null
  promotion?: string | null
  metadata?: Record<string, unknown>
}

export type TorrentFile = {
  path: string
  size_bytes: number | null
}

export type TorrentFileTreeNode = {
  id: string
  name: string
  path: string
  depth: number
} & ({ kind: 'directory'; children: TorrentFileTreeNode[] } | { kind: 'file'; size: number | null })

export type SearchSortField = 'size' | 'seeders' | 'publishedAt'

export type SearchSortDirection = 'asc' | 'desc'

export type SearchResultView = 'raw' | 'filtered'

export type MediaCandidate = {
  title: string
  artist?: string | null
  album?: string | null
  albums?: string[]
  release_date?: string | null
  cover_url?: string | null
  source: string
  external_id: string
  group_key?: string | null
  exists_in_library?: boolean
}

export type DiscoverySongAction = {
  name: string
  artist_name?: string | null
}

export type DiscoveryAlbumAction = DiscoverySongAction & {
  id: string
  album_name: string
  artwork_url?: string | null
  release_date?: string | null
}

export type DiscoveryPlaylistAction = {
  id: string
  name: string
  external_url: string
}

export type MetadataCandidatePageResponse = {
  query: string
  artist?: string | null
  candidates: MediaCandidate[]
  next_offset?: number | null
  has_more: boolean
}

export type MetadataSiteSearchResponse = {
  raw_count: number
  filtered_count: number
  results: SearchResult[]
}

export type MetadataSiteSearchStreamPayload = {
  media?: MediaCandidate
  keywords?: string[]
  total_sites?: number
  completed_sites?: number
  active_keywords?: string[]
  raw_count?: number
  filtered_count?: number
  done?: boolean
  raw_results?: SearchResult[]
  results?: SearchResult[]
}

export type MetadataSiteDonePayload = {
  site: string
  raw_count: number
  filtered_count: number
  results: SearchResult[]
  errors?: string[]
}

export type DownloadTask = {
  id?: number | null
  torrent_hash?: string | null
  name: string
  creation_type: string
  size_bytes?: number | null
  state: string
  progress: number
  save_path?: string | null
  source?: string
  last_error?: string | null
  auto_organize_mode?: 'downloader' | 'directory' | null
}

export type DownloadResponse = {
  status: string
  task_id?: number | null
  torrent_hash?: string | null
}

export type DownloadTaskItem = {
  id: number
  torrent_record_id: number
  file_name: string
  file_path: string
  size_bytes?: number | null
  artist?: string | null
  parsed_title?: string | null
  metadata_title?: string | null
  metadata_artist?: string | null
  metadata_album?: string | null
  playlist_track_id?: number | null
  status: string
  last_error?: string | null
  metadata_payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type DownloadDeleteMode = 'record_only' | 'all'

export type MediaDeleteMode = 'record_only' | 'media_file' | 'all'

export type MediaClearMode = 'record_only' | 'media_file'

export type MediaFile = {
  id: number
  torrent_hash?: string | null
  source_path: string
  library_path?: string | null
  operation_type?: string
  operation_reason?: string | null
  status: string
  operation_time: string
  remark?: string | null
  error_message?: string | null
  title?: string | null
  artist?: string | null
  album?: string | null
  year?: number | null
  track_number?: number | null
}

export type ManualOrganizeTarget = {
  kind: 'media' | 'file' | 'directory'
  mediaId?: number
  filePath?: string
  source_path: string
  title?: string | null
  artist?: string | null
  album?: string | null
  year?: number | null
  track_number?: number | null
}

export type TrackMetadata = {
  title: string
  artist?: string | null
  album?: string | null
  year?: number | null
  track_number?: number | null
  lyrics?: string | null
  cover_url?: string | null
  source?: string | null
  source_id?: string | null
  extra: Record<string, string>
}

export type MetadataSearchResponse = {
  query: string
  source: string
  results: TrackMetadata[]
}

export type FileEntry = {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number | null
  modified_at?: string | null
}

export type FileRootType = 'source' | 'mapped'

export type FileListResponse = {
  root: string
  path: string
  parent?: string | null
  entries: FileEntry[]
}

export type FileAudioCover = {
  mime_type: string
  data: string
}

export type FileAudioDetail = {
  name: string
  path: string
  extension: string
  format: string
  size: number
  modified_at: string
  title: string
  artist?: string | null
  album?: string | null
  album_artist?: string | null
  year?: number | null
  track_number?: number | null
  lyrics?: string | null
  duration?: number | null
  bitrate?: number | null
  sample_rate?: number | null
  channels?: number | null
  cover?: FileAudioCover | null
}

export type FileOrganizeResponse = {
  source_files: number
  mapped_files: number
  updated_files: number
  moved_files: number
  failed_files: number
  skipped_files: number
}

export type FileOrganizeEnqueueResponse = {
  source_files: number
  created_tasks: number
  existing_tasks: number
}

export type MediaBulkDeleteResponse = {
  deleted_ids: number[]
  not_found_ids: number[]
  failures: Array<{ id: number; message: string }>
}

export type MediaRetryResponse = {
  total: number
  source_files: number
  failed_files: number
}

export type FileBulkDeleteResponse = {
  deleted_paths: string[]
  not_found_paths: string[]
  failures: Array<{ path: string; message: string }>
}

export type BuildArtistLibraryResponse = {
  created: number
}

export type MusicLibraryTrack = {
  id: string
  title: string
  artist?: string | null
  album?: string | null
  duration?: number | null
  size?: number | null
  year?: number | null
}

export type MusicLibraryStats = {
  songs: number
  albums: number
  artists: number
}

export type MusicLibraryTrackPageResponse = PageResponse<MusicLibraryTrack> & {
  stats: MusicLibraryStats
}

export type PlaylistTrackSource =
  | { source: 'library'; library_track_id: string }
  | {
      source: 'network'
      provider: string
      external_id: string
      title: string
      artist?: string | null
      album?: string | null
      cover_url?: string | null
    }

export type PlaylistAddCandidate = {
  key: string
  title: string
  artist?: string | null
  album?: string | null
  payload: PlaylistTrackSource
}

export type DashboardDownloadItem = {
  id?: number | null
  name: string
  state: string
  progress: number
  updated_at: string
}

export type DashboardMediaItem = {
  id: number
  title?: string | null
  artist?: string | null
  source_path: string
  operation_type: string
  status: string
  updated_at: string
}

export type DashboardSummary = {
  library: {
    songs: number
    albums: number
    artists: number
    recent_7d_songs: number
    last_synced_at?: string | null
  }
  playlists: {
    playlists: number
    tracks: number
    existing_tracks: number
    pending_tracks: number
    failed_tracks: number
  }
  downloads: {
    total: number
    active: number
    completed_7d: number
    failed: number
    status_counts: Record<string, number>
    recent: DashboardDownloadItem[]
  }
  media: {
    total: number
    success: number
    failed: number
    recent_7d: number
    recent: DashboardMediaItem[]
  }
  tasks: {
    waiting: number
    running: number
    failed: number
    slow: number
  }
  storage: {
    status: 'ready' | 'waiting' | 'error'
    source_size_bytes?: number | null
    expansion_size_bytes?: number | null
    total_size_bytes?: number | null
    calculated_at?: string | null
    error?: string | null
  }
}

export type SystemTaskStatus = 'RUNNING' | 'WAIT' | 'FAILED' | 'SLOW'

export type SystemTask = {
  id: number
  task_type: string
  status: string
  chain_id: string
  parent_task_id?: number | null
  priority: number
  payload: Record<string, unknown>
  error_message?: string | null
  attempts: number
  max_attempts: number
  available_at: string
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
}

export type SystemTaskInterruptResponse = {
  interrupted_ids: number[]
  skipped_ids: number[]
  not_found_ids: number[]
}

export type DashboardMetric = {
  title: string
  value: number | string
  subtitle: string
  subtitleLines?: string[]
  icon: string
  color: string
  help?: string
  error?: string
}

export type Site = {
  id?: string | null
  name: string
  base_url: string
  cookie?: string | null
  auth_type: 'cookie' | 'api_key'
  api_key?: string | null
  user_agent?: string | null
  adapter?: string
  parser?: ParserConfig
  priority: number
  max_concurrency: number
  use_proxy: boolean
  enabled: boolean
}

export type DownloaderConfig = {
  id?: string | null
  name: string
  type: string
  base_url: string
  username: string
  password_configured: boolean
  download_path: string
  local_path: string
  listen_mode: string
  monitor_tag: string
  is_default: boolean
  enabled: boolean
}

export type MediaServerConfig = {
  id?: string | null
  name: string
  type: string
  base_url: string
  api_key: string
  username: string
  password_configured: boolean
  is_default: boolean
  enabled: boolean
}

export type NotifierConfig = {
  id?: string | null
  name: string
  type: string
  bot_token_configured: boolean
  webhook_url: string
  chat_ids: string
  use_proxy: boolean
  enable_download_notify: boolean
  enable_library_notify: boolean
  enabled: boolean
}

export type MusicPlatform = {
  id: string
  platform: string
  display_name: string
  external_user_id?: string | null
  status: string
  redirect_uri: string
  scopes: string[]
  access_token_expires_at?: string | null
  refresh_token_expires_at?: string | null
  last_synced_at?: string | null
  last_error?: string | null
  created_at: string
  updated_at: string
}

export type MusicPlatformConnectResponse = {
  connection_id: string
  authorization_url: string
}

export type Playlist = {
  id: number
  platform_connection_id: string
  platform: string
  external_id: string
  name: string
  owner_name?: string | null
  description?: string | null
  cover_url?: string | null
  track_count: number
  existing_count: number
  waiting_count: number
  submitted_count: number
  failed_count: number
  status: string
  last_synced_at?: string | null
  last_download_started_at?: string | null
  last_error?: string | null
  created_at: string
  updated_at: string
}

export type PlaylistAvailable = {
  import_token?: string
  platform?: string
  external_id: string
  name: string
  owner_name?: string | null
  description?: string | null
  cover_url?: string | null
  track_count: number
}

export type PlaylistTrack = {
  id: number
  playlist_id: number
  platform: string
  external_id: string
  source_key: string
  position: number
  original_title: string
  title: string
  artist?: string | null
  album?: string | null
  duration?: number | null
  isrc?: string | null
  cover_url?: string | null
  exists_in_library: boolean
  matched_library_track_id?: number | null
  download_status: string
  torrent_record_id?: number | null
  last_checked_at?: string | null
  last_download_attempt_at?: string | null
  last_error?: string | null
}

export type PlaylistLibrarySyncResponse = {
  status: string
  playlist_id: number
  library_playlist_id?: string | null
  synced_count: number
  mode?: string
}

export type PlaylistLibrarySyncBinding = {
  playlist_id: number
  media_server_id: string
  public: boolean
  last_synced_existing_count: number
}

export type PlaylistLibrarySyncForm = {
  playlist: Playlist | null
  media_server_id: string
  public: boolean
  auto_sync: boolean
}

export type PageResponse<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type SystemSettings = {
  proxy: {
    host: string
    port: number
    username: string
    password: string
  }
  scraping: {
    enabled: boolean
    auto_organize: 'downloader' | 'directory'
    directory_monitor_mode: 'native' | 'polling'
    directory_monitor_poll_interval_seconds: number
    directory_monitor_notification_delay_seconds: number
    mode: 'source' | 'mapped' | 'copy'
    source_directory: string
    mapped_directory: string
    scrape_when_missing: Array<'album' | 'artist' | 'lyrics' | 'cover'>
    max_scrape_attempt: boolean
    required_metadata: Array<'album' | 'artist' | 'lyrics' | 'cover'>
    auto_rename: boolean
    auto_classify: boolean
    classify_by: 'artist' | 'album' | 'artist_album'
    duplicate_handling: 'ignore' | 'overwrite' | 'keep_largest'
    track_version_control: boolean
  }
  search: {
    exclude_keywords: string
    minimum_seeders: number
    metadata_concurrency: number
  }
}

export type DirectoryMonitorStatus = {
  state: 'disabled' | 'probing' | 'running_native' | 'running_polling' | 'failed'
  mode: 'native' | 'polling'
  source_directory: string
  poll_interval_seconds: number
  failed_at?: string | null
  message: string
  detail: string
}

export type DirectoryMonitorErrorDetail = {
  code?: string
  message?: string
  source_directory?: string
  polling_available?: boolean
}

export type AboutInfo = {
  app: string
  version: string
  latest_version: string | null
  latest_release_url: string | null
  repository_name: string
  repository_url: string
  description: string
  license: string
}

export type LogEntry = {
  timestamp: string
  level: string
  message: string
  category: string
}

export type DebugLoggingState = {
  enabled: boolean
}

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

export type TestResponse = {
  ok: boolean
  message: string
}

export type ArtistAlias = {
  alias: string
  source: string
}

export type Artist = {
  id: number
  name: string
  normalized_name: string
  aliases: ArtistAlias[]
}

export type DeleteTarget = {
  kind: 'site' | 'downloader' | 'mediaServer' | 'notifier' | 'musicPlatform' | 'playlist'
  id: string | number
  name: string
}

export type ConfigMenuKind = DeleteTarget['kind']
