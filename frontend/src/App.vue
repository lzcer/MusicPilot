<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

type ParserField = {
  selector: string
  attribute?: string
  regex?: string | null
  index?: number | null
  remove?: string[]
  filters?: string[]
}

type ParserConfig = {
  list_selector: string
  fields: Record<string, ParserField>
}

type SearchResult = {
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
}

type MediaCandidate = {
  title: string
  artist?: string | null
  album?: string | null
  albums?: string[]
  release_date?: string | null
  cover_url?: string | null
  source: string
  external_id: string
}

type MetadataSiteSearchResponse = {
  raw_count: number
  filtered_count: number
  results: SearchResult[]
}

type MetadataSiteSearchStreamPayload = {
  media?: MediaCandidate
  keywords?: string[]
  total_sites?: number
  completed_sites?: number
  active_keywords?: string[]
  raw_count?: number
  filtered_count?: number
  done?: boolean
  results?: SearchResult[]
}

type MetadataSiteDonePayload = {
  site: string
  raw_count: number
  filtered_count: number
  results: SearchResult[]
  errors?: string[]
}

type DownloadTask = {
  id?: number | null
  torrent_hash?: string | null
  name: string
  state: string
  progress: number
  save_path?: string | null
  source?: string
  last_error?: string | null
}

type DownloadTaskItem = {
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

type DownloadDeleteMode = 'record_only' | 'all'
type MediaDeleteMode = 'record_only' | 'media_file' | 'all'

type MediaFile = {
  id: number
  torrent_hash?: string | null
  source_path: string
  library_path?: string | null
  operation_type?: string
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

type ManualOrganizeTarget = {
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

type TrackMetadata = {
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

type MetadataSearchResponse = {
  query: string
  source: string
  results: TrackMetadata[]
}

type FileEntry = {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number | null
  modified_at?: string | null
}

type FileRootType = 'source' | 'mapped'

type FileListResponse = {
  root: string
  path: string
  parent?: string | null
  entries: FileEntry[]
}

type FileOrganizeResponse = {
  source_files: number
  mapped_files: number
  updated_files: number
  moved_files: number
  failed_files: number
  skipped_files: number
}

type MediaBulkDeleteResponse = {
  deleted_ids: number[]
  not_found_ids: number[]
  failures: Array<{ id: number; message: string }>
}

type MediaRetryResponse = {
  total: number
  source_files: number
  failed_files: number
}

type FileBulkDeleteResponse = {
  deleted_paths: string[]
  not_found_paths: string[]
  failures: Array<{ path: string; message: string }>
}

type BuildArtistLibraryResponse = {
  created: number
}

type MusicLibraryTrack = {
  id: string
  title: string
  artist?: string | null
  album?: string | null
  duration?: number | null
  size?: number | null
  year?: number | null
}

type MusicLibraryStats = {
  songs: number
  albums: number
  artists: number
}

type MusicLibraryTrackPageResponse = PageResponse<MusicLibraryTrack> & {
  stats: MusicLibraryStats
}

type DashboardDownloadItem = {
  id?: number | null
  name: string
  state: string
  progress: number
  updated_at: string
}

type DashboardMediaItem = {
  id: number
  title?: string | null
  artist?: string | null
  source_path: string
  operation_type: string
  status: string
  updated_at: string
}

type DashboardSummary = {
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
  }
}

type DashboardMetric = {
  title: string
  value: number
  subtitle: string
  icon: string
  color: string
}

type Site = {
  id?: string | null
  name: string
  base_url: string
  cookie?: string | null
  user_agent?: string | null
  parser?: ParserConfig
  max_concurrency: number
  use_proxy: boolean
}

type DownloaderConfig = {
  id?: string | null
  name: string
  type: string
  base_url: string
  username: string
  download_path: string
  local_path: string
  listen_mode: string
  is_default: boolean
  enabled: boolean
}

type MediaServerConfig = {
  id?: string | null
  name: string
  type: string
  base_url: string
  api_key: string
  username: string
  is_default: boolean
  enabled: boolean
}

type NotifierConfig = {
  id?: string | null
  name: string
  type: string
  webhook_url: string
  chat_ids: string
  use_proxy: boolean
  enable_download_notify: boolean
  enable_library_notify: boolean
  enabled: boolean
}

type MusicPlatform = {
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

type MusicPlatformConnectResponse = {
  connection_id: string
  authorization_url: string
}

type Playlist = {
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

type PlaylistAvailable = {
  import_token?: string
  platform?: string
  external_id: string
  name: string
  owner_name?: string | null
  description?: string | null
  cover_url?: string | null
  track_count: number
}

type PlaylistTrack = {
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

type PlaylistLibrarySyncResponse = {
  status: string
  playlist_id: number
  library_playlist_id?: string | null
  synced_count: number
  mode?: string
}

type PlaylistLibrarySyncForm = {
  playlist: Playlist | null
  media_server_id: string
  public: boolean
}

type PageResponse<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
}

type SystemSettings = {
  proxy: {
    host: string
    port: number
    username: string
    password: string
  }
  scraping: {
    enabled: boolean
    mode: 'source' | 'mapped' | 'copy'
    source_directory: string
    mapped_directory: string
    scrape_when_missing: Array<'album' | 'artist' | 'lyrics'>
    required_metadata: Array<'album' | 'artist' | 'lyrics'>
    auto_rename: boolean
    auto_classify: boolean
    classify_by: 'artist' | 'album'
    duplicate_handling: 'ignore' | 'overwrite' | 'keep_largest'
  }
  search: {
    exclude_keywords: string
    metadata_concurrency: number
  }
}

type LogEntry = {
  timestamp: string
  level: string
  message: string
  category: string
}

type TestResponse = {
  ok: boolean
  message: string
}

type ArtistAlias = {
  alias: string
  source: string
}

type Artist = {
  id: number
  name: string
  normalized_name: string
  aliases: ArtistAlias[]
}

type DeleteTarget = {
  kind: 'site' | 'downloader' | 'mediaServer' | 'notifier' | 'musicPlatform' | 'playlist'
  id: string | number
  name: string
}

type ConfigMenuKind = DeleteTarget['kind']

const loggedIn = ref(false)
const loginLoading = ref(false)
const loginForm = ref({ username: 'admin', password: 'musicpilot' })
const activePage = ref('dashboard')
const settingsTab = ref('downloaders')
const drawer = ref(true)
const dashboard = ref<DashboardSummary | null>(null)
const dashboardLoading = ref(false)

const searchDialog = ref(false)
const metadataSearchLoading = ref(false)
const torrentSearchLoading = ref(false)
const searchText = ref('')
const searchResults = ref<SearchResult[]>([])
const metadataCandidates = ref<MediaCandidate[]>([])
const selectedMedia = ref<MediaCandidate | null>(null)
const siteConfirmDialog = ref(false)
const noMetadataDialog = ref(false)
const selectedSiteIds = ref<string[]>([])
const searchStats = ref({ raw_count: 0, filtered_count: 0 })
const searchProgress = ref({ completed_sites: 0, total_sites: 0, active_keywords: [] as string[] })
const hasSearchedTorrents = ref(false)
const searchPage = ref(1)
const searchPageSize = ref(20)
const pendingDownload = ref<SearchResult | null>(null)
const downloadSubmitting = ref(false)

const logs = ref<LogEntry[]>([])
const logsLoading = ref(false)
const logPaused = ref(false)
const logLevel = ref('ALL')
const logQuery = ref('')
const musicLibraryQuery = ref('')
const musicLibraryPage = ref(1)
const musicLibraryPageSize = ref(20)
const musicLibraryTotal = ref(0)
const musicLibraryStats = ref<MusicLibraryStats>({ songs: 0, albums: 0, artists: 0 })
const musicLibraryLoading = ref(false)
let logTimer: number | undefined
let downloadTimer: number | undefined
let artistBuildTimer: number | undefined
let mediaRefreshTimer: number | undefined
let metadataSearchStream: EventSource | undefined

const downloads = ref<DownloadTask[]>([])
const downloadTaskItems = ref<DownloadTaskItem[]>([])
const selectedDownloadTask = ref<DownloadTask | null>(null)
const selectedDownloadIds = ref<number[]>([])
const downloadActiveOnly = ref(true)
const mediaFiles = ref<MediaFile[]>([])
const mediaQuery = ref('')
const mediaPage = ref(1)
const mediaPageSize = ref(20)
const mediaTotal = ref(0)
const selectedMediaIds = ref<number[]>([])
const mediaStatusFilter = ref('')
const mediaRetrying = ref(false)
const mediaRetryDialog = ref(false)
const pendingMediaRetryIds = ref<number[]>([])
const pendingMediaRetryLabel = ref('')
const mediaManualDialog = ref(false)
const mediaMetadataSearchDialog = ref(false)
const mediaManualSubmitting = ref(false)
const mediaMetadataSearching = ref(false)
const manualOrganizeTarget = ref<ManualOrganizeTarget | null>(null)
const manualMetadataSearchQuery = ref('')
const manualMetadataSource = ref('qmusic')
const manualMetadataResults = ref<TrackMetadata[]>([])
const manualOrganizeIsDirectory = computed(
  () => manualOrganizeTarget.value?.kind === 'directory'
)
const manualMetadataForm = ref({
  title: '',
  artist: '',
  album: '',
  year: null as number | null,
  track_number: null as number | null,
  lyrics: '',
  cover_url: '',
  extra: {} as Record<string, string>
})
const mediaTableHeaders = [
  { title: '', key: 'select', sortable: false, width: 48 },
  { title: '标题', key: 'title', sortable: false, width: 160 },
  { title: '艺人', key: 'artist', sortable: false, width: 150 },
  { title: '专辑', key: 'album', sortable: false, width: 320 },
  { title: '操作时间', key: 'operation_time', sortable: false, width: 180 },
  { title: '类型', key: 'operation_type', sortable: false, width: 90 },
  { title: '状态', key: 'status', sortable: false, width: 90 },
  { title: '文件路径', key: 'path', sortable: false, width: 520 },
  { title: '备注', key: 'remark', sortable: false, width: 180 },
  { title: '操作', key: 'actions', sortable: false, width: 120 },
]
const fileRootType = ref<FileRootType>('source')
const fileEntries = ref<FileEntry[]>([])
const selectedFilePaths = ref<string[]>([])
const filePath = ref('')
const fileParent = ref<string | null>(null)
const fileRoot = ref('')
const fileLoading = ref(false)
const fileError = ref('')
const fileSearchQuery = ref('')
const musicLibraryTracks = ref<MusicLibraryTrack[]>([])
const sites = ref<Site[]>([])
const downloaders = ref<DownloaderConfig[]>([])
const mediaServers = ref<MediaServerConfig[]>([])
const notifiers = ref<NotifierConfig[]>([])
const musicPlatforms = ref<MusicPlatform[]>([])
const playlists = ref<Playlist[]>([])
const availablePlaylists = ref<PlaylistAvailable[]>([])
const selectedAvailablePlaylistIds = ref<string[]>([])
const selectedPlaylistConnectionId = ref<string | null>(null)
const playlistImportUrl = ref('')
const selectedPlaylist = ref<Playlist | null>(null)
const playlistTracks = ref<PlaylistTrack[]>([])
const playlistTrackTitleQuery = ref('')
const playlistTrackArtistQuery = ref('')
const playlistTrackDownloadStatus = ref('')
const playlistTrackLibraryStatus = ref<'all' | 'yes' | 'no'>('all')
const playlistTrackPage = ref(1)
const playlistTrackPageSize = ref(20)
const playlistTrackTotal = ref(0)

const siteDialog = ref(false)
const downloaderDialog = ref(false)
const mediaServerDialog = ref(false)
const notifierDialog = ref(false)
const musicPlatformDialog = ref(false)
const playlistImportDialog = ref(false)
const playlistTracksDialog = ref(false)
const playlistTrackEditDialog = ref(false)
const deleteDialog = ref(false)
const downloadItemsDialog = ref(false)
const downloadDeleteDialog = ref(false)
const mediaDeleteDialog = ref(false)
const fileOrganizeDialog = ref(false)
const fileDeleteDialog = ref(false)
const siteTesting = ref(false)
const downloaderTesting = ref(false)
const mediaServerTesting = ref(false)
const notifierTesting = ref(false)
const musicPlatformConnecting = ref(false)
const playlistLoading = ref(false)
const availablePlaylistLoading = ref(false)
const playlistTrackLoading = ref(false)
const playlistTrackEditSaving = ref(false)
const downloadItemsLoading = ref(false)
const playlistDownloading = ref(false)
const playlistLibrarySyncDialog = ref(false)
const playlistLibrarySyncingIds = ref<number[]>([])
const playlistLibrarySyncForm = ref<PlaylistLibrarySyncForm>({
  playlist: null,
  media_server_id: '',
  public: true
})
const playlistTrackEditForm = ref({
  id: 0,
  title: '',
  artist: '',
  album: ''
})
const playlistTrackDownloadingIds = ref<number[]>([])
const deleting = ref(false)
const downloadDeleting = ref(false)
const mediaDeleting = ref(false)
const fileOrganizing = ref(false)
const fileDeleting = ref(false)
const activeDownloadDeleteMode = ref<DownloadDeleteMode | null>(null)
const activeMediaDeleteMode = ref<MediaDeleteMode | null>(null)
const systemSaving = ref(false)
const artists = ref<Artist[]>([])
const artistQuery = ref('')
const artistPage = ref(1)
const artistPageSize = ref(20)
const artistTotal = ref(0)
const artistLoading = ref(false)
const artistBuilding = ref(false)
const artistEditDialog = ref(false)
const artistEditSaving = ref(false)
const artistEditForm = ref({ id: 0, name: '', aliases: '' })
const artistAliasDialog = ref(false)
const artistAliasForm = ref({ artist_id: 0, alias: '', source: 'user' })
const artistMergeDialog = ref(false)
const artistMergeForm = ref({ target_id: 0, source_id: 0, target_name: '', source_name: '' })
const clearArtistDialog = ref(false)
const editingSiteId = ref<string | null>(null)
const editingDownloaderId = ref<string | null>(null)
const editingMediaServerId = ref<string | null>(null)
const editingNotifierId = ref<string | null>(null)

const snackbar = ref({ show: false, color: 'success', text: '' })
const deleteTarget = ref<DeleteTarget | null>(null)
const pendingDownloadDeleteIds = ref<number[]>([])
const pendingDownloadDeleteLabel = ref('')
const pendingMediaDelete = ref<MediaFile | null>(null)
const pendingMediaDeleteIds = ref<number[]>([])
const pendingMediaDeleteLabel = ref('')
const pendingFileOrganize = ref<FileEntry | null>(null)
const pendingFileOrganizePaths = ref<string[]>([])
const pendingFileOrganizeLabel = ref('')
const pendingFileOrganizeHasDirectory = ref(false)
const pendingFileDeleteRootType = ref<FileRootType>('source')
const pendingFileDeletePaths = ref<string[]>([])
const pendingFileDeleteLabel = ref('')
const pendingFileDeleteHasDirectory = ref(false)
const activeConfigMenu = ref<string | null>(null)

const siteForm = ref({
  name: '',
  base_url: '',
  cookie: '',
  user_agent: '',
  max_concurrency: 2,
  use_proxy: false
})

const downloaderForm = ref({
  id: null as string | null,
  name: 'qBittorrent',
  type: 'qbittorrent',
  base_url: '',
  username: '',
  password: '',
  download_path: '',
  local_path: '',
  listen_mode: 'polling',
  is_default: true,
  enabled: true
})

const mediaServerForm = ref({
  id: null as string | null,
  name: 'Navidrome',
  type: 'navidrome',
  base_url: '',
  api_key: '',
  username: '',
  password: '',
  is_default: true,
  enabled: true
})

const mediaServerUserForm = ref({
  id: null as string | null,
  username: '',
  password: '',
  enabled: true
})

const notifierForm = ref({
  id: null as string | null,
  name: 'Telegram Bot',
  type: 'telegram',
  bot_token: '',
  webhook_url: '',
  chat_ids: '',
  use_proxy: false,
  enable_download_notify: true,
  enable_library_notify: true,
  enabled: true
})

const musicPlatformForm = ref({
  platform: 'spotify',
  client_id: '',
  client_secret: '',
  redirect_uri: 'http://127.0.0.1:8000/api/integrations/spotify/callback'
})

const systemForm = ref<SystemSettings>({
  proxy: {
    host: '',
    port: 0,
    username: '',
    password: ''
  },
  scraping: {
    enabled: false,
    mode: 'mapped',
    source_directory: '',
    mapped_directory: '',
    scrape_when_missing: [],
    required_metadata: [],
    auto_rename: false,
    auto_classify: false,
    classify_by: 'artist',
    duplicate_handling: 'ignore'
  },
  search: {
    exclude_keywords: '整轨|整軌|WAV|wav',
    metadata_concurrency: 3
  }
})

const scrapingModeOptions = [
  { title: '源文件', value: 'source' },
  { title: '映射文件', value: 'mapped' },
  { title: '复制文件', value: 'copy' }
]

const scrapingRequiredMetadataOptions = [
  { title: '专辑', value: 'album' },
  { title: '艺术家', value: 'artist' },
  { title: '歌词', value: 'lyrics' }
]

const scrapingClassifyOptions = [
  { title: '艺术家', value: 'artist' },
  { title: '专辑', value: 'album' }
]

const duplicateHandlingOptions = [
  { title: '不处理', value: 'ignore' },
  { title: '总是覆盖', value: 'overwrite' },
  { title: '保留最大文件', value: 'keep_largest' }
]

const fileRootTypeOptions = [
  { title: '源文件', value: 'source' },
  { title: '映射目录', value: 'mapped' }
]

const metadataSourceOptions = [
  { title: 'QQ音乐', value: 'qmusic' },
  { title: '网易云音乐', value: 'netease' },
  { title: '咪咕音乐', value: 'migu' },
  { title: '酷我音乐', value: 'kuwo' }
]

function metadataSourceLabel(source?: string | null) {
  return metadataSourceOptions.find((option) => option.value === source)?.title || source || 'QQ音乐'
}

const playlistTrackDownloadStatusOptions = [
  { title: '全部下载状态', value: '' },
  { title: '等待', value: 'waiting' },
  { title: '队列中', value: 'queue' },
  { title: '搜索中', value: 'searching' },
  { title: '已提交', value: 'submitted' },
  { title: '下载中', value: 'downloading' },
  { title: '已完成', value: 'completed' },
  { title: '刷新中', value: 'refreshing_library' },
  { title: '已入库', value: 'library_refreshed' },
  { title: '已存在', value: 'existing' },
  { title: '未找到', value: 'not_found' },
  { title: '目录未找到', value: 'source_directory_not_found' },
  { title: '失败', value: 'failed' },
  { title: '已删除', value: 'deleted' }
]

const playlistTrackLibraryStatusOptions = [
  { title: '全部在库状态', value: 'all' },
  { title: '已在库', value: 'yes' },
  { title: '未在库', value: 'no' }
]

const navItems = [
  { title: '仪表盘', value: 'dashboard', icon: 'mdi-view-dashboard-outline' },
  { title: '搜索', value: 'search', icon: 'mdi-magnify' },
  { title: '下载', value: 'downloads', icon: 'mdi-download' },
  { title: '歌单', value: 'playlists', icon: 'mdi-playlist-music-outline' },
  { title: '整理', value: 'media', icon: 'mdi-music-box-multiple' },
  { title: '文件管理', value: 'files', icon: 'mdi-folder-music-outline' },
  { title: '音乐库', value: 'musicLibrary', icon: 'mdi-music-circle-outline' },
  { title: '歌手库', value: 'artists', icon: 'mdi-account-music-outline' },
  { title: '站点', value: 'sites', icon: 'mdi-server-network' },
  { title: '日志', value: 'logs', icon: 'mdi-text-box-search-outline' },
  { title: '设置', value: 'settings', icon: 'mdi-cog-outline' }
]

const navGroups = [
  {
    title: '任务',
    items: navItems.filter((item) => ['search', 'downloads', 'media'].includes(item.value))
  },
  {
    title: '曲库',
    items: navItems.filter((item) => ['playlists', 'musicLibrary', 'artists'].includes(item.value))
  },
  {
    title: '管理',
    items: navItems.filter((item) => ['files', 'sites', 'logs', 'settings'].includes(item.value))
  }
]

const pageTitle = computed(() => navItems.find((item) => item.value === activePage.value)?.title ?? 'MusicPilot')

const searchLoading = computed(() => metadataSearchLoading.value || torrentSearchLoading.value)

const enabledMediaServerOptions = computed(() =>
  mediaServers.value
    .filter((item) => item.enabled && item.id)
    .map((item) => ({
      title: `${item.username || item.name}${item.is_default ? '（默认）' : ''}`,
      subtitle: item.name,
      value: item.id || ''
    }))
)

const defaultMediaServer = computed(() =>
  mediaServers.value.find((item) => item.is_default) ?? mediaServers.value[0] ?? null
)

const mediaServerUserAccounts = computed(() =>
  [...mediaServers.value].sort((left, right) => {
    if (left.is_default !== right.is_default) return left.is_default ? -1 : 1
    return (left.username || left.name).localeCompare(right.username || right.name)
  })
)

const dashboardMetricCards = computed<DashboardMetric[]>(() => {
  const data = dashboard.value
  if (!data) return []
  return [
    {
      title: '歌曲库',
      value: data.library.songs,
      subtitle: `专辑 ${data.library.albums} / 歌手 ${data.library.artists}`,
      icon: 'mdi-music-circle-outline',
      color: 'primary'
    },
    {
      title: '近 7 天新增',
      value: data.library.recent_7d_songs,
      subtitle: `最近同步 ${formatOptionalTime(data.library.last_synced_at)}`,
      icon: 'mdi-calendar-plus',
      color: 'success'
    },
    {
      title: '歌单',
      value: data.playlists.playlists,
      subtitle: `歌曲 ${data.playlists.tracks} / 已在库 ${data.playlists.existing_tracks}`,
      icon: 'mdi-playlist-music-outline',
      color: 'info'
    },
    {
      title: '活跃下载',
      value: data.downloads.active,
      subtitle: `总任务 ${data.downloads.total} / 近 7 天完成 ${data.downloads.completed_7d}`,
      icon: 'mdi-download',
      color: 'warning'
    },
    {
      title: '整理记录',
      value: data.media.total,
      subtitle: `成功 ${data.media.success} / 失败 ${data.media.failed}`,
      icon: 'mdi-music-box-multiple',
      color: 'secondary'
    },
    {
      title: '任务队列',
      value: data.tasks.waiting + data.tasks.running,
      subtitle: `运行 ${data.tasks.running} / 等待 ${data.tasks.waiting} / 失败 ${data.tasks.failed}`,
      icon: 'mdi-timeline-clock-outline',
      color: data.tasks.failed ? 'error' : 'primary'
    }
  ]
})

const torrentSearchProgressText = computed(() => {
  const siteText = `站点 ${searchProgress.value.completed_sites}/${searchProgress.value.total_sites}`
  const active = searchProgress.value.active_keywords.length
    ? searchProgress.value.active_keywords.join(' / ')
    : '等待结果'
  return `${siteText} 搜索中：${active} 结果：${searchStats.value.raw_count} 过滤：${searchStats.value.filtered_count}`
})

const pagedSearchResults = computed(() => {
  const start = (searchPage.value - 1) * searchPageSize.value
  return searchResults.value.slice(start, start + searchPageSize.value)
})

const filteredLogs = computed(() => {
  const keyword = logQuery.value.trim().toLowerCase()
  return logs.value.filter((entry) => {
    const levelMatches = logLevel.value === 'ALL' || entry.level === logLevel.value
    const text = `${entry.timestamp} ${entry.category} ${entry.level} ${entry.message}`.toLowerCase()
    return levelMatches && (!keyword || text.includes(keyword))
  })
})

const connectedMusicPlatforms = computed(() =>
  musicPlatforms.value.filter((item) => item.status === 'connected')
)

const musicPlatformOptions = computed(() =>
  connectedMusicPlatforms.value.map((item) => ({
    title: musicPlatformLabel(item),
    value: item.id
  }))
)

const fileBreadcrumbs = computed(() => {
  const segments = filePath.value.split('/').filter(Boolean)
  const rootTitle = fileRootType.value === 'mapped' ? '映射目录' : '源目录'
  const items = [{ title: rootTitle, path: '' }]
  let current = ''
  for (const segment of segments) {
    current = current ? `${current}/${segment}` : segment
    items.push({ title: segment, path: current })
  }
  return items
})

const filteredDownloads = computed(() =>
  downloadActiveOnly.value
    ? downloads.value.filter((item) => item.state !== 'library_refreshed')
    : downloads.value
)

const downloadEmptyText = computed(() =>
  downloadActiveOnly.value ? '暂无活跃下载任务' : '暂无下载任务'
)

const downloadableTaskIds = computed(() =>
  filteredDownloads.value.map((item) => item.id).filter((id): id is number => typeof id === 'number')
)

const allDownloadsSelected = computed({
  get: () =>
    downloadableTaskIds.value.length > 0 &&
    downloadableTaskIds.value.every((id) => selectedDownloadIds.value.includes(id)),
  set: (selected: boolean) => {
    selectedDownloadIds.value = selected ? [...downloadableTaskIds.value] : []
  }
})

const someDownloadsSelected = computed(
  () =>
    selectedDownloadIds.value.length > 0 &&
    !downloadableTaskIds.value.every((id) => selectedDownloadIds.value.includes(id))
)

const mediaFileIds = computed(() => mediaFiles.value.map((item) => item.id))
const mediaPageLength = computed(() =>
  Math.max(1, Math.ceil(mediaTotal.value / mediaPageSize.value))
)

const musicLibraryPageLength = computed(() =>
  Math.max(1, Math.ceil(musicLibraryTotal.value / musicLibraryPageSize.value))
)

const allMediaSelected = computed({
  get: () =>
    mediaFileIds.value.length > 0 &&
    mediaFileIds.value.every((id) => selectedMediaIds.value.includes(id)),
  set: (selected: boolean) => {
    selectedMediaIds.value = selected ? [...mediaFileIds.value] : []
  }
})

const someMediaSelected = computed(
  () =>
    selectedMediaIds.value.length > 0 &&
    !mediaFileIds.value.every((id) => selectedMediaIds.value.includes(id))
)

const artistPageLength = computed(() =>
  Math.max(1, Math.ceil(artistTotal.value / artistPageSize.value))
)

const playlistTrackPageLength = computed(() =>
  Math.max(1, Math.ceil(playlistTrackTotal.value / playlistTrackPageSize.value))
)

const fileEntryPaths = computed(() => fileEntries.value.map((item) => item.path))

const allFilesSelected = computed({
  get: () =>
    fileEntryPaths.value.length > 0 &&
    fileEntryPaths.value.every((path) => selectedFilePaths.value.includes(path)),
  set: (selected: boolean) => {
    selectedFilePaths.value = selected ? [...fileEntryPaths.value] : []
  }
})

const someFilesSelected = computed(
  () =>
    selectedFilePaths.value.length > 0 &&
    !fileEntryPaths.value.every((path) => selectedFilePaths.value.includes(path))
)

async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {})
    }
  })
  if (!response.ok) {
    throw new Error(await readError(response))
  }
  return response.json() as Promise<T>
}

async function apiNoContent(url: string, options: RequestInit = {}) {
  const response = await fetch(url, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {})
    }
  })
  if (!response.ok) {
    throw new Error(await readError(response))
  }
}

async function readError(response: Response) {
  const text = await response.text()
  if (!text) return response.statusText
  try {
    const data = JSON.parse(text) as { detail?: unknown; message?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (typeof data.message === 'string') return data.message
    return text
  } catch {
    return text
  }
}

function notify(text: string, color = 'success') {
  snackbar.value = { show: true, color, text }
}

function trimmedInput(value: string | null | undefined) {
  return typeof value === 'string' ? value.trim() : ''
}

async function login() {
  loginLoading.value = true
  try {
    await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(loginForm.value)
    })
  } catch {
    notify('用户名或密码错误', 'error')
    loginLoading.value = false
    return
  }

  loggedIn.value = true
  try {
    await loadInitialData()
  } catch (error) {
    notify(error instanceof Error ? `数据加载失败：${error.message}` : '数据加载失败', 'error')
  } finally {
    loginLoading.value = false
  }
}

async function loadInitialData() {
  await Promise.all([
    loadDashboard(),
    loadSites(),
    loadDownloaders(),
    loadMediaServers(),
    loadNotifiers(),
    loadSystemSettings()
  ])
  syncPagePolling()
  subscribeMetadataSiteSearch()
}

async function loadDashboard() {
  dashboardLoading.value = true
  try {
    dashboard.value = await api<DashboardSummary>('/api/dashboard')
  } catch (error) {
    notify(error instanceof Error ? error.message : '仪表盘加载失败', 'error')
  } finally {
    dashboardLoading.value = false
  }
}

async function runSearch() {
  if (!searchText.value.trim()) return
  searchDialog.value = false
  metadataSearchLoading.value = true
  selectedMedia.value = null
  searchResults.value = []
  metadataCandidates.value = []
  hasSearchedTorrents.value = false
  searchStats.value = { raw_count: 0, filtered_count: 0 }
  searchPage.value = 1
  try {
    const params = new URLSearchParams({ query: searchText.value.trim(), limit: '12' })
    const response = await api<{ candidates: MediaCandidate[] }>(`/api/metadata/search?${params.toString()}`)
    metadataCandidates.value = response.candidates
    if (!metadataCandidates.value.length) {
      noMetadataDialog.value = true
    }
  } catch (error) {
    notify(error instanceof Error ? error.message : '媒体信息搜索失败', 'error')
  } finally {
    metadataSearchLoading.value = false
  }
}

function runDirectSearch() {
  if (!searchText.value.trim()) return
  noMetadataDialog.value = false
  metadataCandidates.value = []
  selectedMedia.value = null
  searchResults.value = []
  hasSearchedTorrents.value = true
  searchPage.value = 1
  torrentSearchLoading.value = true
  const params = new URLSearchParams({ query: searchText.value.trim(), limit: '100' })
  const stream = new EventSource(`/api/search/stream?${params.toString()}`, {
    withCredentials: true
  })

  stream.addEventListener('result', (event) => {
    const result = JSON.parse((event as MessageEvent).data) as SearchResult
    searchResults.value.push(result)
  })

  stream.addEventListener('error', () => {
    stream.close()
    torrentSearchLoading.value = false
  })

  stream.addEventListener('done', () => {
    stream.close()
    torrentSearchLoading.value = false
  })
}

function openSiteConfirm(candidate: MediaCandidate) {
  selectedMedia.value = rawMediaCandidate(candidate)
  selectedSiteIds.value = sites.value.map((site) => site.id).filter(Boolean) as string[]
  siteConfirmDialog.value = true
}

async function runMetadataSiteSearch() {
  if (!selectedMedia.value) return
  siteConfirmDialog.value = false
  torrentSearchLoading.value = true
  metadataCandidates.value = []
  searchResults.value = []
  hasSearchedTorrents.value = true
  searchPage.value = 1
  searchStats.value = { raw_count: 0, filtered_count: 0 }
  searchProgress.value = { completed_sites: 0, total_sites: selectedSiteIds.value.length, active_keywords: [] }
  try {
    const snapshot = await api<MetadataSiteSearchStreamPayload>('/api/search/by-metadata/stream/start', {
      method: 'POST',
      body: JSON.stringify({
        media: rawMediaCandidate(selectedMedia.value),
        site_ids: selectedSiteIds.value,
        limit: 100
      })
    })
    applyMetadataSearchSnapshot(snapshot)
    subscribeMetadataSiteSearch()
  } catch (error) {
    notify(error instanceof Error ? error.message : '站点搜索失败', 'error')
    torrentSearchLoading.value = false
  }
}

function subscribeMetadataSiteSearch() {
  metadataSearchStream?.close()
  metadataSearchStream = new EventSource('/api/search/by-metadata/stream/current', {
    withCredentials: true
  })

  metadataSearchStream.addEventListener('snapshot', (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteSearchStreamPayload
    applyMetadataSearchSnapshot(payload)
  })

  metadataSearchStream.addEventListener('progress', (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteSearchStreamPayload
    applyMetadataSearchSnapshot(payload)
  })

  metadataSearchStream.addEventListener('site_done', (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteDonePayload
    mergeSearchResults(payload.results)
    searchStats.value = {
      raw_count: searchStats.value.raw_count + payload.raw_count,
      filtered_count: searchStats.value.filtered_count + payload.filtered_count
    }
  })

  metadataSearchStream.addEventListener('site_error', (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as { site: string; message: string }
    notify(`${payload.site} 搜索失败：${payload.message}`, 'warning')
  })

  metadataSearchStream.addEventListener('done', (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteSearchStreamPayload
    applyMetadataSearchSnapshot(payload)
    torrentSearchLoading.value = false
    metadataSearchStream?.close()
    metadataSearchStream = undefined
    if (!searchResults.value.length && (payload.raw_count ?? 0) > 0) {
      notify('艺人过滤后没有匹配资源', 'warning')
    }
  })

  metadataSearchStream.addEventListener('error', () => {
    torrentSearchLoading.value = false
    metadataSearchStream?.close()
    metadataSearchStream = undefined
  })
}

function applyMetadataSearchSnapshot(payload: MetadataSiteSearchStreamPayload) {
  searchStats.value = {
    raw_count: payload.raw_count ?? 0,
    filtered_count: payload.filtered_count ?? 0
  }
  searchProgress.value = {
    completed_sites: payload.completed_sites ?? 0,
    total_sites: payload.total_sites ?? 0,
    active_keywords: payload.active_keywords ?? []
  }
  if (payload.media) {
    selectedMedia.value = payload.media
  }
  if (payload.results) {
    searchResults.value = payload.results
  }
  hasSearchedTorrents.value =
    hasSearchedTorrents.value ||
    Boolean(payload.results?.length) ||
    Boolean(payload.total_sites)
  torrentSearchLoading.value = !(payload.done ?? false)
}

function mergeSearchResults(results: SearchResult[]) {
  const byUrl = new Map(searchResults.value.map((item) => [item.download_url, item]))
  for (const result of results) {
    byUrl.set(result.download_url, result)
  }
  searchResults.value = Array.from(byUrl.values()).sort((a, b) => b.seeders - a.seeders)
}

function rawMediaCandidate(candidate: MediaCandidate) {
  return {
    title: candidate.title,
    artist: candidate.artist ?? null,
    album: candidate.album ?? null,
    albums: candidate.albums ?? albumList(candidate),
    release_date: candidate.release_date ?? null,
    cover_url: candidate.cover_url ?? null,
    source: candidate.source,
    external_id: candidate.external_id
  }
}

function mediaSummary(candidate: MediaCandidate) {
  const count = albumList(candidate).length
  return `${candidate.artist || '-'} - ${candidate.title}${count ? ` / ${count} 个专辑` : ''}`
}

function albumList(candidate: MediaCandidate | null) {
  if (!candidate) return []
  const values = candidate.albums?.length ? candidate.albums : candidate.album ? [candidate.album] : []
  return Array.from(new Set(values.filter(Boolean)))
}

function viewResult(row: SearchResult) {
  if (!row.details_url) {
    notify('没有详情页地址', 'warning')
    return
  }
  window.open(row.details_url, '_blank', 'noopener,noreferrer')
}

function openDownloadConfirm(result: SearchResult) {
  pendingDownload.value = result
}

function switchPage(page: string) {
  activePage.value = page
  if (page === 'dashboard') {
    void loadDashboard()
  }
  if (page === 'musicLibrary' && !musicLibraryTracks.value.length) {
    void loadMusicLibrary()
  }
  if (page === 'files' && !fileEntries.value.length && !fileLoading.value) {
    void loadFiles('')
  }
  if (page === 'media' && !mediaFiles.value.length) {
    void loadMedia()
  }
  if (page === 'playlists' && !playlists.value.length && !playlistLoading.value) {
    void loadPlaylists()
  }
  if (page === 'downloads') {
    void loadDownloads().catch(() => undefined)
  }
  if (page === 'logs') {
    void loadLogs()
  }
  if (page === 'artists') {
    void loadArtists()
    void loadArtistBuildStatus()
  }
}

async function confirmDownload() {
  if (!pendingDownload.value || downloadSubmitting.value) return
  downloadSubmitting.value = true
  try {
    await addDownload(pendingDownload.value)
    pendingDownload.value = null
  } catch (error) {
    notify(error instanceof Error ? error.message : '下载失败', 'error')
    await loadDownloads().catch(() => undefined)
  } finally {
    downloadSubmitting.value = false
  }
}

async function addDownload(result: SearchResult) {
  await api('/api/downloads', {
    method: 'POST',
    body: JSON.stringify({
      ...result,
      resource: result,
      media_metadata: selectedMedia.value,
      selected_site_ids: selectedSiteIds.value
    })
  })
  notify('已发送到默认下载器')
  await loadDownloads()
}

async function loadDownloads() {
  downloads.value = await api<DownloadTask[]>('/api/downloads')
  syncSelectedDownloadIds()
}

function syncSelectedDownloadIds() {
  const existingIds = new Set(downloadableTaskIds.value)
  selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => existingIds.has(id))
}

async function viewDownloadItems(task: DownloadTask) {
  if (typeof task.id !== 'number') return
  selectedDownloadTask.value = task
  downloadItemsDialog.value = true
  downloadItemsLoading.value = true
  try {
    downloadTaskItems.value = await api<DownloadTaskItem[]>(`/api/downloads/${task.id}/items`)
  } catch (error) {
    notify(error instanceof Error ? error.message : '下载明细加载失败', 'error')
    downloadTaskItems.value = []
  } finally {
    downloadItemsLoading.value = false
  }
}

function deleteDownloadTask(task: DownloadTask) {
  if (typeof task.id !== 'number') return
  pendingDownloadDeleteIds.value = [task.id]
  pendingDownloadDeleteLabel.value = `下载任务“${task.name}”`
  downloadDeleteDialog.value = true
}

function deleteSelectedDownloads() {
  const ids = [...selectedDownloadIds.value]
  if (!ids.length) return
  pendingDownloadDeleteIds.value = ids
  pendingDownloadDeleteLabel.value = `选中的 ${ids.length} 个下载任务`
  downloadDeleteDialog.value = true
}

async function confirmDeleteDownloads(mode: DownloadDeleteMode) {
  const ids = [...pendingDownloadDeleteIds.value]
  if (!ids.length) return
  downloadDeleting.value = true
  activeDownloadDeleteMode.value = mode
  try {
    await Promise.all(
      ids.map((id) => apiNoContent(`/api/downloads/${id}?mode=${mode}`, { method: 'DELETE' }))
    )
    selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => !ids.includes(id))
    pendingDownloadDeleteIds.value = []
    pendingDownloadDeleteLabel.value = ''
    downloadDeleteDialog.value = false
    await loadDownloads()
    notify('下载任务已删除')
  } catch (error) {
    notify(error instanceof Error ? error.message : '下载任务删除失败', 'error')
    await loadDownloads()
  } finally {
    downloadDeleting.value = false
    activeDownloadDeleteMode.value = null
  }
}

async function loadMedia() {
  const params = new URLSearchParams({
    page: String(mediaPage.value),
    page_size: String(mediaPageSize.value)
  })
  const query = trimmedInput(mediaQuery.value)
  if (query) params.set('q', query)
  if (mediaStatusFilter.value) params.set('status', mediaStatusFilter.value)
  const response = await api<PageResponse<MediaFile>>(`/api/media?${params.toString()}`)
  mediaFiles.value = response.items
  mediaTotal.value = response.total
  mediaPage.value = response.page
  mediaPageSize.value = response.page_size
  const existingIds = new Set(mediaFileIds.value)
  selectedMediaIds.value = selectedMediaIds.value.filter((id) => existingIds.has(id))
}

function applyMediaFilters() {
  mediaPage.value = 1
  void loadMedia()
}

function deleteMediaFile(row: MediaFile) {
  pendingMediaDelete.value = row
  pendingMediaDeleteIds.value = [row.id]
  pendingMediaDeleteLabel.value = `整理记录“${row.title || row.source_path || '-'}”`
  mediaDeleteDialog.value = true
}

function deleteSelectedMediaFiles() {
  const ids = [...selectedMediaIds.value]
  if (!ids.length) return
  pendingMediaDelete.value = null
  pendingMediaDeleteIds.value = ids
  pendingMediaDeleteLabel.value = `选中的 ${ids.length} 条整理记录`
  mediaDeleteDialog.value = true
}

async function confirmDeleteMedia(mode: MediaDeleteMode) {
  const ids = [...pendingMediaDeleteIds.value]
  if (!ids.length) return
  const deletingSingle = ids.length === 1 && Boolean(pendingMediaDelete.value)
  mediaDeleting.value = true
  activeMediaDeleteMode.value = mode
  try {
    if (deletingSingle) {
      await apiNoContent(`/api/media/${ids[0]}?mode=${mode}`, { method: 'DELETE' })
    } else {
      const result = await api<MediaBulkDeleteResponse>('/api/media', {
        method: 'DELETE',
        body: JSON.stringify({ ids, mode })
      })
      if (result.failures.length) {
        notify(
          `已删除 ${result.deleted_ids.length} 条，失败 ${result.failures.length} 条`,
          'warning'
        )
      } else if (result.not_found_ids.length) {
        notify(
          `已删除 ${result.deleted_ids.length} 条，${result.not_found_ids.length} 条记录不存在`,
          'warning'
        )
      } else {
        notify(`已删除 ${result.deleted_ids.length} 条整理记录`)
      }
    }
    selectedMediaIds.value = selectedMediaIds.value.filter((id) => !ids.includes(id))
    pendingMediaDelete.value = null
    pendingMediaDeleteIds.value = []
    pendingMediaDeleteLabel.value = ''
    mediaDeleteDialog.value = false
    await loadMedia()
    if (deletingSingle) {
      notify('整理记录已删除')
    }
  } catch (error) {
    notify(error instanceof Error ? error.message : '整理记录删除失败', 'error')
    await loadMedia()
  } finally {
    mediaDeleting.value = false
    activeMediaDeleteMode.value = null
  }
}

function retrySingleMedia(row: MediaFile) {
  pendingMediaRetryIds.value = [row.id]
  pendingMediaRetryLabel.value = `整理记录"${row.title || row.source_path || '-'}"`
  mediaRetryDialog.value = true
}

function openManualOrganize(row: MediaFile) {
  manualOrganizeTarget.value = {
    kind: 'media',
    mediaId: row.id,
    source_path: row.source_path,
    title: row.title,
    artist: row.artist,
    album: row.album,
    year: row.year,
    track_number: row.track_number
  }
  manualMetadataForm.value = {
    title: row.title || '',
    artist: row.artist || '',
    album: row.album || '',
    year: row.year ?? null,
    track_number: row.track_number ?? null,
    lyrics: '',
    cover_url: '',
    extra: {}
  }
  manualMetadataSearchQuery.value = [row.title, row.artist].filter(Boolean).join(' ') || row.source_path
  manualMetadataSource.value = 'qmusic'
  manualMetadataResults.value = []
  mediaManualDialog.value = true
}

function openFileManualOrganize(entry: FileEntry) {
  if (fileRootType.value !== 'source') return
  const isDirectory = entry.type === 'directory'
  const title = isDirectory ? '' : entry.name.replace(/\.[^/.]+$/, '')
  manualOrganizeTarget.value = {
    kind: isDirectory ? 'directory' : 'file',
    filePath: entry.path,
    source_path: entry.path || entry.name,
    title
  }
  manualMetadataForm.value = {
    title,
    artist: '',
    album: '',
    year: null,
    track_number: null,
    lyrics: '',
    cover_url: '',
    extra: {}
  }
  manualMetadataSearchQuery.value = isDirectory ? entry.name : title
  manualMetadataSource.value = 'qmusic'
  manualMetadataResults.value = []
  mediaManualDialog.value = true
}

async function searchManualMetadata() {
  const query = trimmedInput(manualMetadataSearchQuery.value)
  if (!query) {
    notify('请输入搜索关键词', 'warning')
    return
  }
  mediaMetadataSearching.value = true
  mediaMetadataSearchDialog.value = true
  try {
    const params = new URLSearchParams({
      q: query,
      source: manualMetadataSource.value,
      limit: '12'
    })
    const response = await api<MetadataSearchResponse>(`/api/media/metadata-search?${params.toString()}`)
    manualMetadataResults.value = response.results
  } catch (error) {
    notify(error instanceof Error ? error.message : '元数据搜索失败', 'error')
    manualMetadataResults.value = []
  } finally {
    mediaMetadataSearching.value = false
  }
}

function selectManualMetadata(metadata: TrackMetadata) {
  if (manualOrganizeIsDirectory.value) {
    manualMetadataForm.value = {
      ...manualMetadataForm.value,
      artist: metadata.artist || '',
      album: metadata.album || ''
    }
    mediaMetadataSearchDialog.value = false
    return
  }
  manualMetadataForm.value = {
    title: metadata.title || manualMetadataForm.value.title,
    artist: metadata.artist || '',
    album: metadata.album || '',
    year: metadata.year ?? null,
    track_number: metadata.track_number ?? null,
    lyrics: metadata.lyrics || '',
    cover_url: metadata.cover_url || '',
    extra: metadata.extra || {}
  }
  mediaMetadataSearchDialog.value = false
}

async function confirmManualOrganize() {
  const target = manualOrganizeTarget.value
  if (!target || mediaManualSubmitting.value) return
  const title = trimmedInput(manualMetadataForm.value.title)
  const artist = trimmedInput(manualMetadataForm.value.artist)
  const album = trimmedInput(manualMetadataForm.value.album)
  if (!manualOrganizeIsDirectory.value && !title) {
    notify('标题不能为空', 'warning')
    return
  }
  if (manualOrganizeIsDirectory.value && (!artist || !album)) {
    notify('歌手和专辑不能为空', 'warning')
    return
  }
  mediaManualSubmitting.value = true
  try {
    const form = manualMetadataForm.value
    const payload = {
      title,
      artist: artist || null,
      album: album || null,
      year: form.year,
      track_number: form.track_number,
      lyrics: trimmedInput(form.lyrics) || null,
      cover_url: trimmedInput(form.cover_url) || null,
      extra: form.extra || {}
    }
    let result: FileOrganizeResponse
    if (target.kind === 'media') {
      result = await api<FileOrganizeResponse>(`/api/media/${target.mediaId}/manual-organize`, {
        method: 'POST',
        body: JSON.stringify(payload)
      })
    } else if (target.kind === 'directory') {
      result = await api<FileOrganizeResponse>('/api/files/manual-organize-directory', {
        method: 'POST',
        body: JSON.stringify({
          path: target.filePath,
          artist,
          album
        })
      })
    } else {
      result = await api<FileOrganizeResponse>('/api/files/manual-organize', {
        method: 'POST',
        body: JSON.stringify({
          path: target.filePath,
          ...payload
        })
      })
    }
    mediaManualDialog.value = false
    manualOrganizeTarget.value = null
    await Promise.all([
      loadMedia(),
      target.kind === 'file' || target.kind === 'directory'
        ? loadFiles(filePath.value)
        : Promise.resolve()
    ])
    notify(`手动整理完成：文件 ${result.source_files}，失败 ${result.failed_files}`)
  } catch (error) {
    notify(error instanceof Error ? error.message : '手动整理失败', 'error')
    await loadMedia()
  } finally {
    mediaManualSubmitting.value = false
  }
}

function retrySelectedMedia() {
  const ids = [...selectedMediaIds.value]
  if (!ids.length) return
  pendingMediaRetryIds.value = ids
  pendingMediaRetryLabel.value = `选中的 ${ids.length} 条整理记录`
  mediaRetryDialog.value = true
}

async function confirmRetryMedia() {
  const ids = [...pendingMediaRetryIds.value]
  if (!ids.length) return
  mediaRetrying.value = true
  try {
    const result = await api<MediaRetryResponse>('/api/media/retry', {
      method: 'POST',
      body: JSON.stringify({ ids })
    })
    pendingMediaRetryIds.value = []
    mediaRetryDialog.value = false
    await loadMedia()
    notify(`重试完成：${result.source_files} 个文件已处理，${result.failed_files} 个失败`)
  } catch (error) {
    notify(error instanceof Error ? error.message : '重试失败', 'error')
    await loadMedia()
  } finally {
    mediaRetrying.value = false
  }
}

async function loadFiles(path = filePath.value) {
  fileLoading.value = true
  fileError.value = ''
  try {
    const search = trimmedInput(fileSearchQuery.value)
    const params = new URLSearchParams()
    params.set('root_type', fileRootType.value)
    if (path) params.set('path', path)
    if (search) {
      params.set('query', search)
      params.set('limit', '500')
    }
    const query = params.toString()
    const response = await api<FileListResponse>(`/api/files${query ? `?${query}` : ''}`)
    fileEntries.value = response.entries
    filePath.value = response.path
    fileParent.value = response.parent ?? null
    fileRoot.value = response.root
    const existingPaths = new Set(fileEntryPaths.value)
    selectedFilePaths.value = selectedFilePaths.value.filter((item) => existingPaths.has(item))
  } catch (error) {
    fileEntries.value = []
    selectedFilePaths.value = []
    fileError.value = error instanceof Error ? error.message : '文件列表加载失败'
  } finally {
    fileLoading.value = false
  }
}

function openFileEntry(entry: FileEntry) {
  if (entry.type !== 'directory') return
  void loadFiles(entry.path)
}

function runFileSearch() {
  void loadFiles(filePath.value)
}

function clearFileSearch() {
  fileSearchQuery.value = ''
  void loadFiles(filePath.value)
}

function openFileOrganize(entry: FileEntry) {
  if (fileRootType.value !== 'source') return
  pendingFileOrganize.value = entry
  pendingFileOrganizePaths.value = [entry.path]
  pendingFileOrganizeLabel.value = `“${entry.name}”`
  pendingFileOrganizeHasDirectory.value = entry.type === 'directory'
  fileOrganizeDialog.value = true
}

function organizeSelectedFiles() {
  if (fileRootType.value !== 'source') return
  const paths = [...selectedFilePaths.value]
  if (!paths.length) return
  const selected = new Set(paths)
  pendingFileOrganize.value = null
  pendingFileOrganizePaths.value = paths
  pendingFileOrganizeLabel.value = `选中的 ${paths.length} 个项目`
  pendingFileOrganizeHasDirectory.value = fileEntries.value.some(
    (item) => selected.has(item.path) && item.type === 'directory'
  )
  fileOrganizeDialog.value = true
}

function openFileDelete(entry: FileEntry) {
  pendingFileDeleteRootType.value = fileRootType.value
  pendingFileDeletePaths.value = [entry.path]
  pendingFileDeleteLabel.value = `“${entry.name}”`
  pendingFileDeleteHasDirectory.value = entry.type === 'directory'
  fileDeleteDialog.value = true
}

function deleteSelectedFiles() {
  const paths = [...selectedFilePaths.value]
  if (!paths.length) return
  const selected = new Set(paths)
  pendingFileDeleteRootType.value = fileRootType.value
  pendingFileDeletePaths.value = paths
  pendingFileDeleteLabel.value = `选中的 ${paths.length} 个项目`
  pendingFileDeleteHasDirectory.value = fileEntries.value.some(
    (item) => selected.has(item.path) && item.type === 'directory'
  )
  fileDeleteDialog.value = true
}

async function confirmFileDelete() {
  const paths = [...pendingFileDeletePaths.value]
  if (!paths.length) return
  fileDeleting.value = true
  try {
    const result = await api<FileBulkDeleteResponse>('/api/files', {
      method: 'DELETE',
      body: JSON.stringify({ paths, root_type: pendingFileDeleteRootType.value })
    })
    selectedFilePaths.value = selectedFilePaths.value.filter((item) => !paths.includes(item))
    pendingFileDeletePaths.value = []
    pendingFileDeleteLabel.value = ''
    pendingFileDeleteHasDirectory.value = false
    fileDeleteDialog.value = false
    await loadFiles(filePath.value)
    if (result.failures.length) {
      notify(
        `已删除 ${result.deleted_paths.length} 个，失败 ${result.failures.length} 个`,
        'warning'
      )
    } else if (result.not_found_paths.length) {
      notify(
        `已删除 ${result.deleted_paths.length} 个，${result.not_found_paths.length} 个不存在`,
        'warning'
      )
    } else {
      notify(`已删除 ${result.deleted_paths.length} 个项目`)
    }
  } catch (error) {
    notify(error instanceof Error ? error.message : '文件删除失败', 'error')
    await loadFiles(filePath.value)
  } finally {
    fileDeleting.value = false
  }
}

async function confirmFileOrganize() {
  const paths = [...pendingFileOrganizePaths.value]
  if (!paths.length) return
  if (fileRootType.value !== 'source') {
    fileOrganizeDialog.value = false
    pendingFileOrganize.value = null
    pendingFileOrganizePaths.value = []
    pendingFileOrganizeLabel.value = ''
    pendingFileOrganizeHasDirectory.value = false
    return
  }
  fileOrganizing.value = true
  startMediaRefreshPolling()
  try {
    const summary = await api<FileOrganizeResponse>('/api/files/organize', {
      method: 'POST',
      body: JSON.stringify({ paths })
    })
    fileOrganizeDialog.value = false
    pendingFileOrganize.value = null
    pendingFileOrganizePaths.value = []
    pendingFileOrganizeLabel.value = ''
    pendingFileOrganizeHasDirectory.value = false
    selectedFilePaths.value = selectedFilePaths.value.filter((item) => !paths.includes(item))
    await Promise.all([loadFiles(filePath.value), loadMedia()])
    notify(
      `整理完成：文件 ${summary.source_files}，成功 ${summary.source_files - summary.failed_files - summary.skipped_files}，失败 ${summary.failed_files}，跳过 ${summary.skipped_files}`
    )
  } catch (error) {
    notify(error instanceof Error ? error.message : '整理失败', 'error')
  } finally {
    fileOrganizing.value = false
    stopMediaRefreshPolling()
  }
}

function startMediaRefreshPolling() {
  if (mediaRefreshTimer !== undefined) return
  void loadMedia()
  mediaRefreshTimer = window.setInterval(() => {
    void loadMedia()
  }, 2000)
}

function stopMediaRefreshPolling() {
  if (mediaRefreshTimer === undefined) return
  window.clearInterval(mediaRefreshTimer)
  mediaRefreshTimer = undefined
}

function changeFileRootType(value: unknown) {
  if (value !== 'source' && value !== 'mapped') return
  fileRootType.value = value
  filePath.value = ''
  fileParent.value = null
  fileRoot.value = ''
  fileEntries.value = []
  selectedFilePaths.value = []
  fileSearchQuery.value = ''
  void loadFiles('')
}

async function loadMusicLibrary() {
  musicLibraryLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(musicLibraryPage.value),
      page_size: String(musicLibraryPageSize.value)
    })
    const query = trimmedInput(musicLibraryQuery.value)
    if (query) params.set('q', query)
    const response = await api<MusicLibraryTrackPageResponse>(
      `/api/music-library?${params.toString()}`
    )
    applyMusicLibraryResponse(response)
  } catch (error) {
    notify(error instanceof Error ? error.message : '音乐库加载失败', 'error')
  } finally {
    musicLibraryLoading.value = false
  }
}

function applyMusicLibraryResponse(response: MusicLibraryTrackPageResponse) {
  musicLibraryTracks.value = response.items
  musicLibraryTotal.value = response.total
  musicLibraryPage.value = response.page
  musicLibraryPageSize.value = response.page_size
  musicLibraryStats.value = response.stats
}

function applyMusicLibraryFilters() {
  musicLibraryPage.value = 1
  void loadMusicLibrary()
}

async function syncMusicLibrary() {
  musicLibraryLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(musicLibraryPage.value),
      page_size: String(musicLibraryPageSize.value)
    })
    const query = trimmedInput(musicLibraryQuery.value)
    if (query) params.set('q', query)
    const response = await api<MusicLibraryTrackPageResponse>(
      `/api/music-library/sync?${params.toString()}`,
      {
        method: 'POST'
      }
    )
    applyMusicLibraryResponse(response)
    notify('音乐库已同步')
  } catch (error) {
    notify(error instanceof Error ? error.message : '音乐库同步失败', 'error')
  } finally {
    musicLibraryLoading.value = false
  }
}

async function loadArtists() {
  artistLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(artistPage.value),
      page_size: String(artistPageSize.value)
    })
    const query = trimmedInput(artistQuery.value)
    if (query) params.set('q', query)
    const response = await api<PageResponse<Artist>>(`/api/artists?${params.toString()}`)
    artists.value = response.items
    artistTotal.value = response.total
    artistPage.value = response.page
    artistPageSize.value = response.page_size
  } finally {
    artistLoading.value = false
  }
}

function applyArtistFilters() {
  artistPage.value = 1
  void loadArtists()
}

async function loadArtistBuildStatus() {
  try {
    const status = await api<{ running: boolean }>('/api/artists/build-status')
    artistBuilding.value = status.running
  } catch {
    // Silently ignore — visible errors handled by manual actions
  }
}

async function buildArtistLibrary() {
  artistBuilding.value = true
  try {
    await api('/api/artists/build-library', {
      method: 'POST'
    })
    notify('歌手库构建已开始，完成后将通过日志通知')
  } catch (error) {
    notify(error instanceof Error ? error.message : '构建歌手库失败', 'error')
    artistBuilding.value = false
  }
}

async function clearAndRebuildArtistLibrary() {
  clearArtistDialog.value = true
}

async function confirmClearAndRebuildArtistLibrary() {
  clearArtistDialog.value = false
  artistBuilding.value = true
  try {
    await api('/api/artists', { method: 'DELETE' })
    await api('/api/artists/build-library', { method: 'POST' })
    notify('歌手库已清空，后台重建中…')
  } catch (error) {
    notify(error instanceof Error ? error.message : '清空重建失败', 'error')
    artistBuilding.value = false
  }
}

function openArtistEditDialog(artist: Artist) {
  artistEditForm.value = {
    id: artist.id,
    name: artist.name,
    aliases: artist.aliases.map((item) => item.alias).join('\n')
  }
  artistEditDialog.value = true
}

function artistEditAliases() {
  const seen = new Set<string>()
  const aliases: string[] = []
  for (const line of artistEditForm.value.aliases.split(/\r?\n/)) {
    const alias = trimmedInput(line)
    if (!alias || alias === trimmedInput(artistEditForm.value.name) || seen.has(alias)) continue
    seen.add(alias)
    aliases.push(alias)
  }
  return aliases
}

async function saveArtistEdit() {
  const id = artistEditForm.value.id
  const name = trimmedInput(artistEditForm.value.name)
  if (!id || !name) {
    notify('歌手名不能为空', 'warning')
    return
  }
  artistEditSaving.value = true
  try {
    await api<Artist>(`/api/artists/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name,
        aliases: artistEditAliases()
      })
    })
    await loadArtists()
    artistEditDialog.value = false
    notify('歌手已更新')
  } catch (error) {
    notify(error instanceof Error ? error.message : '更新歌手失败', 'error')
  } finally {
    artistEditSaving.value = false
  }
}

async function openArtistAliasDialog(artist: Artist) {
  artistAliasForm.value = { artist_id: artist.id, alias: '', source: 'user' }
  artistAliasDialog.value = true
}

async function saveArtistAlias() {
  try {
    await api('/api/artists/alias', {
      method: 'POST',
      body: JSON.stringify(artistAliasForm.value)
    })
    await loadArtists()
    artistAliasDialog.value = false
    notify('别名已添加')
  } catch (error) {
    notify(error instanceof Error ? error.message : '添加别名失败', 'error')
  }
}

function openArtistMergeDialog(source: Artist) {
  artistMergeForm.value = {
    target_id: source.id,
    source_id: 0,
    target_name: source.name,
    source_name: ''
  }
  artistMergeDialog.value = true
}

async function confirmMergeArtists() {
  try {
    const result = await api<Artist>('/api/artists/merge', {
      method: 'POST',
      body: JSON.stringify({
        target_id: artistMergeForm.value.target_id,
        source_id: artistMergeForm.value.source_id
      })
    })
    await loadArtists()
    artistMergeDialog.value = false
    notify(`已合并：${result.name}`)
  } catch (error) {
    notify(error instanceof Error ? error.message : '合并失败', 'error')
  }
}

async function loadSites() {
  sites.value = await api<Site[]>('/api/sites')
}

async function loadMusicPlatforms() {
  musicPlatforms.value = await api<MusicPlatform[]>('/api/music-platforms')
}

async function loadPlaylists() {
  playlistLoading.value = true
  try {
    playlists.value = await api<Playlist[]>('/api/playlists')
  } catch (error) {
    notify(error instanceof Error ? error.message : '歌单加载失败', 'error')
  } finally {
    playlistLoading.value = false
  }
}

function openMusicPlatformDialog() {
  musicPlatformForm.value = {
    platform: 'spotify',
    client_id: '',
    client_secret: '',
    redirect_uri: 'http://127.0.0.1:8000/api/integrations/spotify/callback'
  }
  musicPlatformDialog.value = true
}

async function connectMusicPlatform() {
  musicPlatformConnecting.value = true
  try {
    const result = await api<MusicPlatformConnectResponse>('/api/music-platforms/connect/start', {
      method: 'POST',
      body: JSON.stringify(musicPlatformForm.value)
    })
    musicPlatformDialog.value = false
    await loadMusicPlatforms()
    window.open(result.authorization_url, '_blank', 'noopener,noreferrer')
    notify('已打开 Spotify 授权页面，完成后请刷新音乐平台列表')
  } catch (error) {
    notify(error instanceof Error ? error.message : '音乐平台关联失败', 'error')
  } finally {
    musicPlatformConnecting.value = false
  }
}

async function reauthorizeMusicPlatform(platform: MusicPlatform) {
  try {
    const result = await api<MusicPlatformConnectResponse>(
      `/api/music-platforms/${platform.id}/reauthorize/start`,
      { method: 'POST' }
    )
    window.open(result.authorization_url, '_blank', 'noopener,noreferrer')
    notify('已打开重新登录页面，完成后请刷新音乐平台列表')
  } catch (error) {
    notify(error instanceof Error ? error.message : '重新登录失败', 'error')
  }
}

function openDeleteMusicPlatform(platform: MusicPlatform) {
  openDeleteDialog({ kind: 'musicPlatform', id: platform.id, name: musicPlatformLabel(platform) })
}

function openPlaylistImportDialog() {
  selectedPlaylistConnectionId.value = null
  playlistImportUrl.value = ''
  availablePlaylists.value = []
  selectedAvailablePlaylistIds.value = []
  playlistImportDialog.value = true
}

async function importPlaylistUrl() {
  const url = playlistImportUrl.value.trim()
  if (!url) {
    notify('请填写歌单链接', 'warning')
    return
  }
  availablePlaylistLoading.value = true
  try {
    availablePlaylists.value = await api<PlaylistAvailable[]>('/api/playlists/parse-url', {
      method: 'POST',
      body: JSON.stringify({ url })
    })
    selectedAvailablePlaylistIds.value = availablePlaylists.value
      .map((item) => item.import_token || item.external_id)
      .filter(Boolean)
    notify('歌单解析完成')
  } catch (error) {
    notify(error instanceof Error ? error.message : '歌单解析失败', 'error')
  } finally {
    availablePlaylistLoading.value = false
  }
}

async function loadAvailablePlaylists() {
  if (!selectedPlaylistConnectionId.value) {
    notify('请先选择已关联平台', 'warning')
    return
  }
  availablePlaylistLoading.value = true
  try {
    const params = new URLSearchParams({ connection_id: selectedPlaylistConnectionId.value })
    availablePlaylists.value = await api<PlaylistAvailable[]>(`/api/playlists/available?${params}`)
    selectedAvailablePlaylistIds.value = []
  } catch (error) {
    notify(error instanceof Error ? error.message : '读取平台歌单失败', 'error')
  } finally {
    availablePlaylistLoading.value = false
  }
}

async function importSelectedPlaylists() {
  const selectedPreviewTokens = availablePlaylists.value
    .filter((item) => item.import_token && selectedAvailablePlaylistIds.value.includes(item.import_token))
    .map((item) => item.import_token as string)
  if (selectedPreviewTokens.length) {
    availablePlaylistLoading.value = true
    try {
      for (const importToken of selectedPreviewTokens) {
        await api('/api/playlists/import-url', {
          method: 'POST',
          body: JSON.stringify({ import_token: importToken })
        })
      }
      playlistImportDialog.value = false
      playlistImportUrl.value = ''
      availablePlaylists.value = []
      selectedAvailablePlaylistIds.value = []
      await loadPlaylists()
      notify('歌单已同步')
    } catch (error) {
      notify(error instanceof Error ? error.message : '歌单同步失败', 'error')
    } finally {
      availablePlaylistLoading.value = false
    }
    return
  }
  const selectedPlatformPlaylistIds = availablePlaylists.value
    .filter((item) => !item.import_token && selectedAvailablePlaylistIds.value.includes(item.external_id))
    .map((item) => item.external_id)
  if (!selectedPlaylistConnectionId.value || !selectedPlatformPlaylistIds.length) return
  availablePlaylistLoading.value = true
  try {
    await api('/api/playlists/import', {
      method: 'POST',
      body: JSON.stringify({
        connection_id: selectedPlaylistConnectionId.value,
        external_ids: selectedPlatformPlaylistIds
      })
    })
    playlistImportDialog.value = false
    await loadPlaylists()
    notify('歌单已同步')
  } catch (error) {
    notify(error instanceof Error ? error.message : '歌单同步失败', 'error')
  } finally {
    availablePlaylistLoading.value = false
  }
}

async function viewPlaylist(playlist: Playlist) {
  selectedPlaylist.value = playlist
  playlistTracks.value = []
  playlistTrackTitleQuery.value = ''
  playlistTrackArtistQuery.value = ''
  playlistTrackDownloadStatus.value = ''
  playlistTrackLibraryStatus.value = 'all'
  playlistTrackPage.value = 1
  playlistTrackTotal.value = 0
  playlistTracksDialog.value = true
  await loadPlaylistTracks(playlist)
}

async function loadPlaylistTracks(playlist: Playlist) {
  playlistTrackLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(playlistTrackPage.value),
      page_size: String(playlistTrackPageSize.value)
    })
    const titleQuery = trimmedInput(playlistTrackTitleQuery.value)
    const artistQuery = trimmedInput(playlistTrackArtistQuery.value)
    if (titleQuery) {
      params.set('title', titleQuery)
    }
    if (artistQuery) {
      params.set('artist', artistQuery)
    }
    if (playlistTrackDownloadStatus.value) {
      params.set('download_status', playlistTrackDownloadStatus.value)
    }
    if (playlistTrackLibraryStatus.value !== 'all') {
      params.set('exists_in_library', playlistTrackLibraryStatus.value === 'yes' ? 'true' : 'false')
    }
    const response = await api<PageResponse<PlaylistTrack>>(
      `/api/playlists/${playlist.id}/tracks?${params.toString()}`
    )
    playlistTracks.value = response.items
    playlistTrackTotal.value = response.total
    playlistTrackPage.value = response.page
    playlistTrackPageSize.value = response.page_size
  } catch (error) {
    notify(error instanceof Error ? error.message : '歌单明细加载失败', 'error')
  } finally {
    playlistTrackLoading.value = false
  }
}

function applyPlaylistTrackFilters() {
  playlistTrackPage.value = 1
  if (selectedPlaylist.value) {
    void loadPlaylistTracks(selectedPlaylist.value)
  }
}

function openPlaylistTrackEditDialog(track: PlaylistTrack) {
  playlistTrackEditForm.value = {
    id: track.id,
    title: track.title || '',
    artist: track.artist || '',
    album: track.album || ''
  }
  playlistTrackEditDialog.value = true
}

async function savePlaylistTrackEdit() {
  const playlist = selectedPlaylist.value
  const form = playlistTrackEditForm.value
  const title = trimmedInput(form.title)
  if (!playlist || !form.id) return
  if (!title) {
    notify('歌名不能为空', 'warning')
    return
  }
  playlistTrackEditSaving.value = true
  try {
    await api<PlaylistTrack>(`/api/playlists/${playlist.id}/tracks/${form.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        title,
        artist: trimmedInput(form.artist) || null,
        album: trimmedInput(form.album) || null
      })
    })
    playlistTrackEditDialog.value = false
    await loadPlaylistTracks(playlist)
    notify('歌单条目已更新')
  } catch (error) {
    notify(error instanceof Error ? error.message : '歌单条目更新失败', 'error')
  } finally {
    playlistTrackEditSaving.value = false
  }
}

async function syncPlaylist(playlist: Playlist) {
  playlistLoading.value = true
  try {
    await api<Playlist>(`/api/playlists/${playlist.id}/sync`, { method: 'POST' })
    await loadPlaylists()
    notify('歌单已同步')
  } catch (error) {
    notify(error instanceof Error ? error.message : '歌单同步失败', 'error')
  } finally {
    playlistLoading.value = false
  }
}

function isPlaylistSyncingToLibrary(playlistId: number) {
  return playlistLibrarySyncingIds.value.includes(playlistId)
}

async function openPlaylistLibrarySyncDialog(playlist: Playlist) {
  if (!mediaServers.value.length) {
    await loadMediaServers()
  }
  const defaultServer = mediaServers.value.find((item) => item.enabled && item.is_default && item.id)
  const firstEnabled = mediaServers.value.find((item) => item.enabled && item.id)
  playlistLibrarySyncForm.value = {
    playlist,
    media_server_id: defaultServer?.id || firstEnabled?.id || '',
    public: true
  }
  playlistLibrarySyncDialog.value = true
}

async function syncPlaylistToLibrary() {
  const playlist = playlistLibrarySyncForm.value.playlist
  if (!playlist) return
  if (isPlaylistSyncingToLibrary(playlist.id)) return
  if (!playlistLibrarySyncForm.value.media_server_id) {
    notify('请选择同步账号', 'warning')
    return
  }
  playlistLibrarySyncingIds.value = [...playlistLibrarySyncingIds.value, playlist.id]
  try {
    const response = await api<PlaylistLibrarySyncResponse>(
      `/api/playlists/${playlist.id}/sync-to-library`,
      {
        method: 'POST',
        body: JSON.stringify({
          media_server_id: playlistLibrarySyncForm.value.media_server_id,
          public: playlistLibrarySyncForm.value.public
        })
      }
    )
    const actionText = response.mode === 'created' ? '创建' : '更新'
    playlistLibrarySyncDialog.value = false
    playlistLibrarySyncForm.value.playlist = null
    notify(`已${actionText}音乐库歌单：${response.synced_count} 首`)
  } catch (error) {
    notify(error instanceof Error ? error.message : '同步到音乐库失败', 'error')
  } finally {
    playlistLibrarySyncingIds.value = playlistLibrarySyncingIds.value.filter((id) => id !== playlist.id)
  }
}

async function downloadPlaylist(playlist: Playlist) {
  playlistDownloading.value = true
  try {
    await api(`/api/playlists/${playlist.id}/download`, { method: 'POST' })
    await Promise.all([loadPlaylists(), loadDownloads()])
    notify('歌单下载任务已开始')
  } catch (error) {
    notify(error instanceof Error ? error.message : '歌单下载失败', 'error')
  } finally {
    playlistDownloading.value = false
  }
}

function isPlaylistTrackDownloading(trackId: number) {
  return playlistTrackDownloadingIds.value.includes(trackId)
}

const playlistTrackRetryableStatuses = new Set([
  'failed',
  'not_found',
  'deleted',
  'source_directory_not_found'
])

function canStartPlaylistTrackDownload(track: PlaylistTrack) {
  if (track.exists_in_library || isPlaylistTrackDownloading(track.id)) return false
  return track.download_status === 'pending' || playlistTrackRetryableStatuses.has(track.download_status)
}

function isPlaylistTrackRetry(track: PlaylistTrack) {
  return playlistTrackRetryableStatuses.has(track.download_status)
}

function playlistTrackActionIcon(track: PlaylistTrack) {
  return isPlaylistTrackRetry(track) ? 'mdi-refresh' : 'mdi-download'
}

function playlistTrackActionTitle(track: PlaylistTrack) {
  return isPlaylistTrackRetry(track) ? '重试' : '下载'
}

async function downloadPlaylistTrack(track: PlaylistTrack) {
  const playlist = selectedPlaylist.value
  if (!playlist || !canStartPlaylistTrackDownload(track)) return
  playlistTrackDownloadingIds.value = [...playlistTrackDownloadingIds.value, track.id]
  try {
    await api(`/api/playlists/${playlist.id}/tracks/${track.id}/download`, {
      method: 'POST'
    })
    playlistTracks.value = playlistTracks.value.map((item) =>
      item.id === track.id ? { ...item, download_status: 'searching', last_error: null } : item
    )
    await Promise.all([loadPlaylistTracks(playlist), loadDownloads()])
    notify('单曲下载任务已开始')
  } catch (error) {
    notify(error instanceof Error ? error.message : '单曲下载失败', 'error')
  } finally {
    playlistTrackDownloadingIds.value = playlistTrackDownloadingIds.value.filter((id) => id !== track.id)
  }
}

function openDeletePlaylist(playlist: Playlist) {
  openDeleteDialog({ kind: 'playlist', id: playlist.id, name: playlist.name })
}

async function loadLogs() {
  if (logPaused.value) return
  logsLoading.value = true
  try {
    logs.value = await api<LogEntry[]>('/api/logs?limit=300')
  } finally {
    logsLoading.value = false
  }
}

function startLogPolling() {
  window.clearInterval(logTimer)
  logTimer = window.setInterval(() => {
    void loadLogs()
  }, 5000)
}

function startDownloadPolling() {
  window.clearInterval(downloadTimer)
  downloadTimer = window.setInterval(() => {
    void loadDownloads().catch(() => {
      // Keep polling quiet; visible errors are handled by manual refresh and page load.
    })
  }, 5000)
}

function startArtistBuildPolling() {
  window.clearInterval(artistBuildTimer)
  artistBuildTimer = window.setInterval(() => {
    void loadArtistBuildStatus()
  }, 5000)
}

function syncPagePolling() {
  if (activePage.value === 'logs') {
    startLogPolling()
  } else {
    window.clearInterval(logTimer)
  }

  if (activePage.value === 'downloads') {
    startDownloadPolling()
  } else {
    window.clearInterval(downloadTimer)
  }

  if (activePage.value === 'artists') {
    startArtistBuildPolling()
  } else {
    window.clearInterval(artistBuildTimer)
  }
}

watch(activePage, () => {
  syncPagePolling()
})

watch(downloadableTaskIds, () => {
  syncSelectedDownloadIds()
})

function openNewSiteDialog() {
  editingSiteId.value = null
  siteForm.value = {
    name: '',
    base_url: '',
    cookie: '',
    user_agent: '',
    max_concurrency: 2,
    use_proxy: false
  }
  siteDialog.value = true
}

function editSite(site: Site) {
  editingSiteId.value = site.id ?? null
  siteForm.value = {
    name: site.name,
    base_url: site.base_url,
    cookie: site.cookie ?? '',
    user_agent: site.user_agent ?? '',
    max_concurrency: site.max_concurrency,
    use_proxy: site.use_proxy
  }
  siteDialog.value = true
}

function sitePayload() {
  return { ...siteForm.value }
}

async function saveSite() {
  try {
    const editing = Boolean(editingSiteId.value)
    const site = await api<Site>(editing ? `/api/sites/${editingSiteId.value}` : '/api/sites', {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify(sitePayload())
    })
    if (editing) {
      sites.value = sites.value.map((item) => (item.id === site.id ? site : item))
    } else {
      sites.value.push(site)
    }
    siteDialog.value = false
    notify('站点已保存')
  } catch (error) {
    notify(error instanceof Error ? error.message : '站点保存失败', 'error')
  }
}

function openDeleteSite(site: Site) {
  if (!site.id) return
  openDeleteDialog({ kind: 'site', id: site.id, name: site.name })
}

async function testSite() {
  siteTesting.value = true
  try {
    const result = await api<TestResponse>('/api/sites/test', {
      method: 'POST',
      body: JSON.stringify(sitePayload())
    })
    notify(result.message, result.ok ? 'success' : 'error')
  } catch (error) {
    notify(error instanceof Error ? error.message : '站点测试失败', 'error')
  } finally {
    siteTesting.value = false
  }
}

async function loadDownloaders() {
  downloaders.value = await api<DownloaderConfig[]>('/api/settings/downloaders')
}

function openNewDownloaderDialog() {
  editingDownloaderId.value = null
  downloaderForm.value = {
    id: null,
    name: 'qBittorrent',
    type: 'qbittorrent',
    base_url: '',
    username: '',
    password: '',
    download_path: '',
    local_path: '',
    listen_mode: 'polling',
    is_default: true,
    enabled: true
  }
  downloaderDialog.value = true
}

function editDownloader(downloader: DownloaderConfig) {
  editingDownloaderId.value = downloader.id ?? null
  downloaderForm.value = {
    id: downloader.id ?? null,
    name: downloader.name,
    type: downloader.type,
    base_url: downloader.base_url,
    username: downloader.username,
    password: '',
    download_path: downloader.download_path ?? '',
    local_path: downloader.local_path ?? '',
    listen_mode: downloader.listen_mode ?? 'polling',
    is_default: downloader.is_default,
    enabled: downloader.enabled
  }
  downloaderDialog.value = true
}

async function testDownloader() {
  const pathError = downloaderPathError()
  if (pathError) {
    notify(pathError, 'error')
    return
  }
  downloaderTesting.value = true
  try {
    const result = await api<TestResponse>('/api/settings/downloaders/test', {
      method: 'POST',
      body: JSON.stringify(downloaderForm.value)
    })
    notify(result.message, result.ok ? 'success' : 'error')
  } catch (error) {
    notify(error instanceof Error ? error.message : '下载器测试失败', 'error')
  } finally {
    downloaderTesting.value = false
  }
}

async function saveDownloader() {
  const pathError = downloaderPathError()
  if (pathError) {
    notify(pathError, 'error')
    return
  }
  const editing = Boolean(editingDownloaderId.value)
  const downloader = await api<DownloaderConfig>(
    editing
      ? `/api/settings/downloaders/${editingDownloaderId.value}`
      : '/api/settings/downloaders',
    {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify(downloaderForm.value)
    }
  )
  if (editing) {
    downloaders.value = downloaders.value.map((item) =>
      item.id === downloader.id ? downloader : item
    )
  } else {
    downloaders.value.push(downloader)
  }
  downloaderDialog.value = false
  notify('下载器已保存')
}

function downloaderPathError() {
  if (!trimmedInput(downloaderForm.value.download_path)) return '下载目录不能为空'
  if (!trimmedInput(downloaderForm.value.local_path)) return '本机对应目录不能为空'
  return ''
}

function openDeleteDownloader(downloader: DownloaderConfig) {
  if (!downloader.id) return
  openDeleteDialog({ kind: 'downloader', id: downloader.id, name: downloader.name })
}

async function loadMediaServers() {
  mediaServers.value = await api<MediaServerConfig[]>('/api/settings/media-servers')
  syncMediaServerFormFromDefault()
}

function syncMediaServerFormFromDefault() {
  const server = defaultMediaServer.value
  if (!server) {
    resetMediaServerForm()
    return
  }
  mediaServerForm.value = {
    id: server.id ?? null,
    name: server.name,
    type: server.type,
    base_url: server.base_url,
    api_key: server.api_key,
    username: server.username,
    password: '',
    is_default: true,
    enabled: server.enabled
  }
}

function resetMediaServerForm() {
  mediaServerForm.value = {
    id: null,
    name: 'Navidrome',
    type: 'navidrome',
    base_url: '',
    api_key: '',
    username: '',
    password: '',
    is_default: true,
    enabled: true
  }
}

function openNewMediaServerUserDialog() {
  if (!mediaServerForm.value.id) {
    notify('请先保存音乐库配置', 'warning')
    return
  }
  editingMediaServerId.value = null
  mediaServerUserForm.value = {
    id: null,
    username: '',
    password: '',
    enabled: true
  }
  mediaServerDialog.value = true
}

function editMediaServerUser(server: MediaServerConfig) {
  if (server.is_default) {
    syncMediaServerFormFromDefault()
    return
  }
  editingMediaServerId.value = server.id ?? null
  mediaServerUserForm.value = {
    id: server.id ?? null,
    username: server.username,
    password: '',
    enabled: server.enabled
  }
  mediaServerDialog.value = true
}

function mediaServerUserPayload() {
  const username = trimmedInput(mediaServerUserForm.value.username)
  return {
    id: mediaServerUserForm.value.id,
    name: username || 'Navidrome 用户',
    type: mediaServerForm.value.type,
    base_url: mediaServerForm.value.base_url,
    api_key: mediaServerForm.value.api_key,
    username,
    password: mediaServerUserForm.value.password,
    is_default: false,
    enabled: mediaServerUserForm.value.enabled
  }
}

async function syncMediaServerUsersToMainConfig(mainServer: MediaServerConfig) {
  const userServers = mediaServers.value.filter((item) => item.id && !item.is_default)
  await Promise.all(
    userServers.map((item) =>
      api<MediaServerConfig>(`/api/settings/media-servers/${item.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          ...item,
          type: mainServer.type,
          base_url: mainServer.base_url,
          api_key: mainServer.api_key,
          is_default: false,
          password: ''
        })
      })
    )
  )
}

async function testMediaServer() {
  mediaServerTesting.value = true
  try {
    const result = await api<TestResponse>('/api/settings/media-servers/test', {
      method: 'POST',
      body: JSON.stringify({
        ...mediaServerForm.value,
        is_default: true
      })
    })
    notify(result.message, result.ok ? 'success' : 'error')
  } catch (error) {
    notify(error instanceof Error ? error.message : '媒体服务器测试失败', 'error')
  } finally {
    mediaServerTesting.value = false
  }
}

async function saveMediaServer() {
  const editing = Boolean(mediaServerForm.value.id)
  const server = await api<MediaServerConfig>(
    editing
      ? `/api/settings/media-servers/${mediaServerForm.value.id}`
      : '/api/settings/media-servers',
    {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify({
        ...mediaServerForm.value,
        is_default: true
      })
    }
  )
  await syncMediaServerUsersToMainConfig(server)
  await loadMediaServers()
  notify('音乐库配置已保存')
}

async function testMediaServerUser() {
  const payload = mediaServerUserPayload()
  if (!payload.username) {
    notify('用户名不能为空', 'warning')
    return
  }
  mediaServerTesting.value = true
  try {
    const result = await api<TestResponse>('/api/settings/media-servers/test', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
    notify(result.message, result.ok ? 'success' : 'error')
  } catch (error) {
    notify(error instanceof Error ? error.message : '音乐库用户测试失败', 'error')
  } finally {
    mediaServerTesting.value = false
  }
}

async function saveMediaServerUser() {
  const payload = mediaServerUserPayload()
  if (!payload.username) {
    notify('用户名不能为空', 'warning')
    return
  }
  const editing = Boolean(editingMediaServerId.value)
  await api<MediaServerConfig>(
    editing
      ? `/api/settings/media-servers/${editingMediaServerId.value}`
      : '/api/settings/media-servers',
    {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify(payload)
    }
  )
  await loadMediaServers()
  mediaServerDialog.value = false
  notify('音乐库用户已保存')
}

function openDeleteMediaServer(server: MediaServerConfig) {
  if (!server.id) return
  openDeleteDialog({ kind: 'mediaServer', id: server.id, name: server.name })
}

async function loadNotifiers() {
  notifiers.value = await api<NotifierConfig[]>('/api/settings/notifiers')
}

function openNewNotifierDialog() {
  editingNotifierId.value = null
  notifierForm.value = {
    id: null,
    name: 'Telegram Bot',
    type: 'telegram',
    bot_token: '',
    webhook_url: '',
    chat_ids: '',
    use_proxy: false,
    enable_download_notify: true,
    enable_library_notify: true,
    enabled: true
  }
  notifierDialog.value = true
}

function editNotifier(notifier: NotifierConfig) {
  editingNotifierId.value = notifier.id ?? null
  notifierForm.value = {
    id: notifier.id ?? null,
    name: notifier.name,
    type: notifier.type,
    bot_token: '',
    webhook_url: notifier.webhook_url,
    chat_ids: notifier.chat_ids,
    use_proxy: notifier.use_proxy,
    enable_download_notify: notifier.enable_download_notify,
    enable_library_notify: notifier.enable_library_notify,
    enabled: notifier.enabled
  }
  notifierDialog.value = true
}

async function testNotifier() {
  notifierTesting.value = true
  try {
    const result = await api<TestResponse>('/api/settings/notifiers/test', {
      method: 'POST',
      body: JSON.stringify(notifierForm.value)
    })
    notify(result.message, result.ok ? 'success' : 'error')
  } catch (error) {
    notify(error instanceof Error ? error.message : '通知测试失败', 'error')
  } finally {
    notifierTesting.value = false
  }
}

async function saveNotifier() {
  const editing = Boolean(editingNotifierId.value)
  const notifier = await api<NotifierConfig>(
    editing ? `/api/settings/notifiers/${editingNotifierId.value}` : '/api/settings/notifiers',
    {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify(notifierForm.value)
    }
  )
  if (editing) {
    notifiers.value = notifiers.value.map((item) => (item.id === notifier.id ? notifier : item))
  } else {
    notifiers.value.push(notifier)
  }
  notifierDialog.value = false
  notify('通知已保存')
}

function openDeleteNotifier(notifier: NotifierConfig) {
  if (!notifier.id) return
  openDeleteDialog({ kind: 'notifier', id: notifier.id, name: notifier.name })
}

function openDeleteDialog(target: DeleteTarget) {
  activeConfigMenu.value = null
  deleteTarget.value = target
  deleteDialog.value = true
}

function configMenuKey(kind: ConfigMenuKind, id: string) {
  return `${kind}:${id}`
}

function toggleConfigMenu(kind: ConfigMenuKind, id: string) {
  const key = configMenuKey(kind, id)
  activeConfigMenu.value = activeConfigMenu.value === key ? null : key
}

function deleteTargetLabel(target: DeleteTarget | null) {
  if (!target) return ''
  return {
    site: '站点',
    downloader: '下载器',
    mediaServer: '媒体服务器',
    notifier: '通知',
    musicPlatform: '音乐平台',
    playlist: '歌单'
  }[target.kind]
}

function deleteTargetUrl(target: DeleteTarget) {
  return {
    site: `/api/sites/${target.id}`,
    downloader: `/api/settings/downloaders/${target.id}`,
    mediaServer: `/api/settings/media-servers/${target.id}`,
    notifier: `/api/settings/notifiers/${target.id}`,
    musicPlatform: `/api/music-platforms/${target.id}`,
    playlist: `/api/playlists/${target.id}`
  }[target.kind]
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  const target = deleteTarget.value
  deleting.value = true
  try {
    await apiNoContent(deleteTargetUrl(target), { method: 'DELETE' })
    if (target.kind === 'site') {
      sites.value = sites.value.filter((item) => item.id !== target.id)
    } else if (target.kind === 'downloader') {
      downloaders.value = downloaders.value.filter((item) => item.id !== target.id)
    } else if (target.kind === 'mediaServer') {
      mediaServers.value = mediaServers.value.filter((item) => item.id !== target.id)
    } else if (target.kind === 'musicPlatform') {
      musicPlatforms.value = musicPlatforms.value.filter((item) => item.id !== target.id)
    } else if (target.kind === 'playlist') {
      playlists.value = playlists.value.filter((item) => item.id !== target.id)
    } else {
      notifiers.value = notifiers.value.filter((item) => item.id !== target.id)
    }
    deleteDialog.value = false
    deleteTarget.value = null
    notify(`${deleteTargetLabel(target)}已删除`)
  } catch (error) {
    notify(error instanceof Error ? error.message : '删除失败', 'error')
  } finally {
    deleting.value = false
  }
}

async function loadSystemSettings() {
  const settings = await api<SystemSettings>('/api/settings/system')
  systemForm.value = {
    proxy: {
      ...systemForm.value.proxy,
      ...(settings.proxy ?? {})
    },
    scraping: {
      ...systemForm.value.scraping,
      ...(settings.scraping ?? {})
    },
    search: {
      ...systemForm.value.search,
      ...(settings.search ?? {})
    }
  }
}

async function saveSystemSettings() {
  systemSaving.value = true
  try {
    systemForm.value.search.metadata_concurrency = clampInteger(
      systemForm.value.search.metadata_concurrency,
      1,
      20,
      3
    )
    systemForm.value = await api<SystemSettings>('/api/settings/system', {
      method: 'POST',
      body: JSON.stringify(systemForm.value)
    })
    notify('系统设置已保存')
  } catch (error) {
    notify(error instanceof Error ? error.message : '绯荤粺设置保存澶辫触', 'error')
  } finally {
    systemSaving.value = false
  }
}

function clampInteger(value: number, min: number, max: number, fallback: number) {
  const normalized = Number.isFinite(value) ? Math.trunc(value) : fallback
  return Math.min(Math.max(normalized, min), max)
}

function progressPercent(value: number) {
  return Math.round(value * 100)
}

function formatSize(value?: number | null) {
  if (!value) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`
}

function formatDuration(value?: number | null) {
  if (!value) return '-'
  const minutes = Math.floor(value / 60)
  const seconds = value % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function formatTime(value: string) {
  return new Date(value).toLocaleString()
}

function formatOptionalTime(value?: string | null) {
  return value ? formatTime(value) : '-'
}

function musicPlatformLabel(platform: MusicPlatform) {
  return `${platform.platform === 'spotify' ? 'Spotify' : platform.platform}${platform.display_name ? ` - ${platform.display_name}` : ''}`
}

function playlistPlatformLabel(platform: string) {
  return {
    spotify: 'Spotify',
    spotify_public: 'Spotify',
    qq: 'QQ音乐',
    netease: '网易云音乐',
    kuwo: '酷我音乐',
    kugou: '酷狗音乐'
  }[platform] ?? platform
}

function musicPlatformStatusText(status: string) {
  return {
    pending: '待授权',
    connected: '已关联',
    reauthorization_required: '需要重新登录',
    failed: '关联失败'
  }[status] ?? status
}

function musicPlatformStatusColor(status: string) {
  return {
    pending: 'warning',
    connected: 'success',
    reauthorization_required: 'error',
    failed: 'error'
  }[status] ?? 'secondary'
}

function playlistStatusText(status: string) {
  return {
    synced: '已同步',
    downloading: '下载中',
    failed: '失败'
  }[status] ?? status
}

function playlistStatusColor(status: string) {
  return {
    synced: 'success',
    downloading: 'info',
    failed: 'error'
  }[status] ?? 'secondary'
}

function downloadStatusText(status: string) {
  return {
    queued: '队列中',
    submitted: '已提交',
    downloading: '下载中',
    completed: '下载完成',
    refreshing_library: '整理中',
    library_refreshed: '曲库已刷新',
    source_directory_not_found: '目录未找到',
    failed: '失败',
    deleted: '已删除'
  }[status] ?? status
}

function downloadStatusColor(status: string) {
  return {
    queued: 'warning',
    submitted: 'primary',
    downloading: 'info',
    completed: 'success',
    refreshing_library: 'info',
    library_refreshed: 'success',
    source_directory_not_found: 'error',
    failed: 'error',
    deleted: 'error'
  }[status] ?? 'secondary'
}

function playlistTrackStatusText(status: string) {
  return {
    pending: '待处理',
    existing: '已存在',
    waiting: '等待',
    searching: '搜索中',
    submitted: '已提交',
    queue: '排队中',
    downloading: '下载中',
    completed: '下载完成',
    refreshing_library: '刷新曲库',
    library_refreshed: '曲库已刷新',
    not_found: '未找到',
    source_directory_not_found: '目录未找到',
    failed: '失败',
    deleted: '已删除'
  }[status] ?? status
}

function playlistTrackStatusColor(status: string) {
  return {
    existing: 'success',
    waiting: 'warning',
    searching: 'info',
    submitted: 'primary',
    queue: 'warning',
    downloading: 'info',
    completed: 'success',
    refreshing_library: 'info',
    library_refreshed: 'success',
    not_found: 'error',
    source_directory_not_found: 'error',
    failed: 'error',
    deleted: 'error'
  }[status] ?? 'secondary'
}

function downloadTaskItemStatusText(status: string) {
  return {
    pending: '待查询',
    metadata_searching: '查询中',
    metadata_found: '已匹配',
    metadata_not_found: '未匹配',
    failed: '失败'
  }[status] ?? status
}

function downloadTaskItemStatusColor(status: string) {
  return {
    pending: 'secondary',
    metadata_searching: 'info',
    metadata_found: 'success',
    metadata_not_found: 'warning',
    failed: 'error'
  }[status] ?? 'secondary'
}

function mediaStatusColor(status: string) {
  if (status === 'failed') return 'error'
  if (status === 'skipped') return 'warning'
  return 'success'
}

function mediaStatusText(status: string) {
  if (status === 'failed') return '失败'
  if (status === 'skipped') return '跳过'
  return '成功'
}

function mediaOperationTypeText(type: string | undefined) {
  return {
    copy: '复制',
    mapped: '映射',
    source: '源目录'
  }[type || 'mapped'] ?? (type || '映射')
}

const mediaStatusFilterOptions = [
  { title: '全部', value: '' },
  { title: '成功', value: 'success' },
  { title: '失败', value: 'failed' },
  { title: '跳过', value: 'skipped' },
]

function mediaRemark(row: MediaFile) {
  return row.remark || row.error_message || '-'
}

function mediaTableRow(item: MediaFile | { raw: MediaFile }) {
  return 'raw' in item ? item.raw : item
}

function mediaDisplayPath(row: MediaFile) {
  const sourcePath = displayRelativePath(row.source_path, systemForm.value.scraping.source_directory)
  if (
    row.status === 'success' &&
    row.library_path &&
    pathIsUnderRoot(row.library_path, systemForm.value.scraping.mapped_directory)
  ) {
    const mappedPath = displayRelativePath(row.library_path, systemForm.value.scraping.mapped_directory)
    return `${sourcePath}\n=>\n${mappedPath}`
  }
  return sourcePath || '-'
}

function displayRelativePath(path: string | null | undefined, root: string) {
  const normalized = normalizeDisplayPath(path)
  if (!normalized) return ''
  const normalizedRoot = normalizeDisplayPath(root)
  if (!normalizedRoot) return normalized
  const lowerPath = normalized.toLowerCase()
  const lowerRoot = normalizedRoot.toLowerCase()
  if (lowerPath === lowerRoot) {
    const segments = normalized.split('/').filter(Boolean)
    return segments[segments.length - 1] || normalized
  }
  if (lowerPath.startsWith(`${lowerRoot}/`)) return normalized.slice(normalizedRoot.length + 1)
  return normalized
}

function pathIsUnderRoot(path: string | null | undefined, root: string) {
  const normalized = normalizeDisplayPath(path)
  const normalizedRoot = normalizeDisplayPath(root)
  if (!normalized || !normalizedRoot) return false
  const lowerPath = normalized.toLowerCase()
  const lowerRoot = normalizedRoot.toLowerCase()
  return lowerPath === lowerRoot || lowerPath.startsWith(`${lowerRoot}/`)
}

function normalizeDisplayPath(path: string | null | undefined) {
  return (path || '').replace(/\\/g, '/').replace(/\/+$/g, '').trim()
}

function logColor(level: string) {
  if (level === 'ERROR') return 'error'
  if (level === 'WARNING') return 'warning'
  if (level === 'INFO') return 'info'
  return 'secondary'
}

onMounted(async () => {
  try {
    await api('/api/sites')
  } catch {
    loggedIn.value = false
    return
  }
  loggedIn.value = true
  try {
    await loadInitialData()
  } catch (error) {
    notify(error instanceof Error ? `数据加载失败：${error.message}` : '数据加载失败', 'error')
  }
})

onUnmounted(() => {
  window.clearInterval(logTimer)
  window.clearInterval(downloadTimer)
  window.clearInterval(artistBuildTimer)
  stopMediaRefreshPolling()
  metadataSearchStream?.close()
})
</script>

<template>
  <v-app @click="activeConfigMenu = null">
    <main v-if="!loggedIn" class="login-screen">
      <v-card class="login-card">
        <v-card-title class="text-h5 font-weight-bold">MusicPilot</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="login">
            <v-text-field v-model="loginForm.username" label="用户名" autocomplete="username" />
            <v-text-field
              v-model="loginForm.password"
              label="密码"
              type="password"
              autocomplete="current-password"
              @keyup.enter="login"
            />
            <v-btn block color="primary" size="large" :loading="loginLoading" @click="login">
              登录
            </v-btn>
          </v-form>
        </v-card-text>
      </v-card>
    </main>

    <template v-else>
      <v-navigation-drawer v-model="drawer" width="244">
        <div class="brand-block">
          <div class="brand-title">MusicPilot</div>
          <div class="brand-subtitle">音乐库自动化</div>
        </div>
        <v-list nav density="compact" class="nav-list">
          <v-list-item
            :active="activePage === 'dashboard'"
            prepend-icon="mdi-view-dashboard-outline"
            title="仪表盘"
            rounded="lg"
            @click="switchPage('dashboard')"
          />
          <v-divider class="nav-group-divider" />
          <template v-for="(group, index) in navGroups" :key="group.title">
            <v-divider v-if="index > 0" class="nav-group-divider" />
            <v-list-subheader class="nav-group-title">{{ group.title }}</v-list-subheader>
            <v-list-item
              v-for="item in group.items"
              :key="item.value"
              :active="activePage === item.value"
              :prepend-icon="item.icon"
              :title="item.title"
              rounded="lg"
              @click="switchPage(item.value)"
            />
          </template>
        </v-list>
      </v-navigation-drawer>

      <v-app-bar height="64" flat border>
        <v-app-bar-nav-icon @click="drawer = !drawer" />
        <v-toolbar-title>{{ pageTitle }}</v-toolbar-title>
        <v-spacer />
      </v-app-bar>

      <v-main>
        <div class="content">
          <section v-if="activePage === 'dashboard'" class="page-stack">
            <div class="toolbar-row">
              <v-btn
                prepend-icon="mdi-refresh"
                variant="tonal"
                :loading="dashboardLoading"
                @click="loadDashboard"
              >
                刷新
              </v-btn>
              <v-chip v-if="dashboard?.library.last_synced_at" color="primary" variant="tonal">
                曲库同步 {{ formatOptionalTime(dashboard.library.last_synced_at) }}
              </v-chip>
            </div>

            <div v-if="dashboardLoading && !dashboard" class="loading-panel">
              <v-progress-circular indeterminate color="primary" size="34" width="3" />
              <span>正在加载仪表盘</span>
            </div>

            <template v-else-if="dashboard">
              <div class="dashboard-metric-grid">
                <v-card
                  v-for="metric in dashboardMetricCards"
                  :key="metric.title"
                  class="dashboard-metric-card"
                >
                  <div class="dashboard-metric-icon" :class="`text-${metric.color}`">
                    <v-icon :icon="metric.icon" size="30" />
                  </div>
                  <div>
                    <div class="dashboard-metric-title">{{ metric.title }}</div>
                    <div class="dashboard-metric-value">{{ metric.value }}</div>
                    <div class="dashboard-metric-subtitle">{{ metric.subtitle }}</div>
                  </div>
                </v-card>
              </div>

              <div class="dashboard-panel-grid">
                <v-card class="dashboard-panel">
                  <v-card-title class="dashboard-panel-title">
                    <span>最近下载</span>
                    <v-chip size="small" color="warning" variant="tonal">
                      活跃 {{ dashboard.downloads.active }}
                    </v-chip>
                  </v-card-title>
                  <v-list density="compact" lines="two">
                    <v-list-item
                      v-for="item in dashboard.downloads.recent"
                      :key="item.id || item.name"
                      :title="item.name"
                      :subtitle="formatOptionalTime(item.updated_at)"
                    >
                      <template #prepend>
                        <v-progress-circular
                          :model-value="progressPercent(item.progress)"
                          color="primary"
                          size="36"
                          width="4"
                        >
                          <span class="dashboard-progress-text">{{ progressPercent(item.progress) }}</span>
                        </v-progress-circular>
                      </template>
                      <template #append>
                        <v-chip :color="downloadStatusColor(item.state)" size="small" variant="tonal">
                          {{ downloadStatusText(item.state) }}
                        </v-chip>
                      </template>
                    </v-list-item>
                    <div v-if="!dashboard.downloads.recent.length" class="empty-cell">暂无下载任务</div>
                  </v-list>
                </v-card>

                <v-card class="dashboard-panel">
                  <v-card-title class="dashboard-panel-title">
                    <span>最近整理</span>
                    <v-chip size="small" color="error" variant="tonal">
                      失败 {{ dashboard.media.failed }}
                    </v-chip>
                  </v-card-title>
                  <v-list density="compact" lines="two">
                    <v-list-item
                      v-for="item in dashboard.media.recent"
                      :key="item.id"
                      :title="item.title || displayRelativePath(item.source_path, systemForm.scraping.source_directory)"
                      :subtitle="`${item.artist || '-'} / ${formatOptionalTime(item.updated_at)}`"
                    >
                      <template #prepend>
                        <v-icon icon="mdi-file-music-outline" size="28" />
                      </template>
                      <template #append>
                        <div class="dashboard-chip-stack">
                          <v-chip size="small" variant="tonal">
                            {{ mediaOperationTypeText(item.operation_type) }}
                          </v-chip>
                          <v-chip :color="mediaStatusColor(item.status)" size="small" variant="tonal">
                            {{ mediaStatusText(item.status) }}
                          </v-chip>
                        </div>
                      </template>
                    </v-list-item>
                    <div v-if="!dashboard.media.recent.length" class="empty-cell">暂无整理记录</div>
                  </v-list>
                </v-card>

                <v-card class="dashboard-panel">
                  <v-card-title class="dashboard-panel-title">队列健康</v-card-title>
                  <div class="dashboard-health-grid">
                    <div>
                      <div class="dashboard-health-value">{{ dashboard.tasks.running }}</div>
                      <div class="dashboard-health-label">运行中</div>
                    </div>
                    <div>
                      <div class="dashboard-health-value">{{ dashboard.tasks.waiting }}</div>
                      <div class="dashboard-health-label">等待中</div>
                    </div>
                    <div>
                      <div class="dashboard-health-value">{{ dashboard.tasks.failed }}</div>
                      <div class="dashboard-health-label">失败</div>
                    </div>
                    <div>
                      <div class="dashboard-health-value">{{ dashboard.playlists.pending_tracks }}</div>
                      <div class="dashboard-health-label">歌单待处理</div>
                    </div>
                  </div>
                  <div class="dashboard-status-row">
                    <v-chip color="success" variant="tonal">
                      已在库 {{ dashboard.playlists.existing_tracks }}
                    </v-chip>
                    <v-chip color="error" variant="tonal">
                      歌单失败 {{ dashboard.playlists.failed_tracks }}
                    </v-chip>
                    <v-chip color="warning" variant="tonal">
                      下载失败 {{ dashboard.downloads.failed }}
                    </v-chip>
                    <v-chip color="info" variant="tonal">
                      近 7 天整理 {{ dashboard.media.recent_7d }}
                    </v-chip>
                  </div>
                </v-card>
              </div>
            </template>
          </section>

          <section v-if="activePage === 'search'" class="page-stack">
            <div class="toolbar-row">
              <v-btn color="primary" prepend-icon="mdi-magnify" @click="searchDialog = true">
                搜索
              </v-btn>
              <v-chip v-if="metadataSearchLoading" class="loading-chip" color="info" variant="tonal">
                <v-progress-circular indeterminate size="16" width="2" />
                搜索媒体信息
              </v-chip>
              <v-chip v-if="torrentSearchLoading" class="loading-chip" color="info" variant="tonal">
                <v-progress-circular indeterminate size="16" width="2" />
                {{ torrentSearchProgressText }}
              </v-chip>
              <div v-if="selectedMedia" class="selected-media-summary">
                {{ mediaSummary(selectedMedia) }}
              </div>
              <v-chip v-if="searchStats.raw_count" color="secondary" variant="tonal">
                原始 {{ searchStats.raw_count }} / 过滤 {{ searchStats.filtered_count }}
              </v-chip>
            </div>

            <div v-if="metadataSearchLoading" class="loading-panel">
              <v-progress-circular indeterminate color="primary" size="34" width="3" />
              <span>正在搜索媒体信息</span>
            </div>

            <div v-if="metadataCandidates.length && !metadataSearchLoading" class="result-card-grid media-card-grid">
              <article
                v-for="candidate in metadataCandidates"
                :key="`${candidate.source}-${candidate.external_id}-${candidate.title}-${candidate.artist}`"
                class="media-card"
                @click="openSiteConfirm(candidate)"
              >
                <img
                  v-if="candidate.cover_url"
                  :src="candidate.cover_url"
                  alt=""
                  class="media-cover"
                  loading="lazy"
                />
                <div class="media-card-body">
                  <h3>{{ candidate.title }}</h3>
                  <p>{{ candidate.artist || '未知艺人' }}</p>
                  <div class="media-album-list">
                    <div
                      v-for="album in albumList(candidate)"
                      :key="album"
                      class="media-album"
                    >
                      {{ album }}
                    </div>
                    <div v-if="!albumList(candidate).length" class="media-album">未知专辑</div>
                  </div>
                  <div class="media-card-tags">
                    <v-chip size="small" variant="tonal">{{ candidate.release_date || '-' }}</v-chip>
                    <v-chip size="small" variant="tonal">{{ albumList(candidate).length }} 个专辑</v-chip>
                  </div>
                </div>
              </article>
            </div>

            <v-card class="search-panel">
              <div v-if="torrentSearchLoading && !pagedSearchResults.length" class="loading-panel">
                <v-progress-circular indeterminate color="primary" size="34" width="3" />
                <span>正在搜索种子资源</span>
              </div>
              <div v-else-if="pagedSearchResults.length" class="result-card-grid">
                <article
                  v-for="row in pagedSearchResults"
                  :key="row.download_url"
                  class="result-card"
                  @click="openDownloadConfirm(row)"
                >
                  <div class="result-card-body">
                    <div class="result-card-head">
                      <h3>{{ row.title }}</h3>
                    </div>
                    <div class="result-card-source">
                      <v-icon icon="mdi-server-network" size="22" />
                      <span>{{ row.source }}</span>
                    </div>
                    <p class="result-card-subtitle">{{ row.subtitle || row.title }}</p>
                    <div class="result-card-meta">
                      <span><v-icon icon="mdi-clock-outline" size="16" />{{ row.published_at || '-' }}</span>
                      <span class="seeders"><v-icon icon="mdi-arrow-up" size="18" />{{ row.seeders }}</span>
                      <span class="leechers"><v-icon icon="mdi-arrow-down" size="18" />{{ row.leechers || 0 }}</span>
                    </div>
                    <div class="result-card-tags">
                      <v-chip v-if="row.promotion" color="success" size="small" variant="flat">
                        {{ row.promotion }}
                      </v-chip>
                      <v-chip color="secondary" size="small" variant="tonal">{{ row.source }}</v-chip>
                    </div>
                  </div>
                  <div class="result-card-footer">
                    <v-chip color="primary" size="small" variant="flat">
                      {{ formatSize(row.size_bytes) }}
                    </v-chip>
                    <v-btn
                      icon="mdi-information-outline"
                      color="primary"
                      variant="text"
                      size="small"
                      title="查看原站点"
                      @click.stop="viewResult(row)"
                    />
                  </div>
                </article>
              </div>
              <div v-else-if="hasSearchedTorrents" class="empty-cell">暂无搜索结果</div>
              <div v-if="searchResults.length" class="pagination-row">
                <v-select
                  v-model="searchPageSize"
                  :items="[10, 20, 50, 100]"
                  label="每页"
                  hide-details
                  class="page-size"
                />
                <v-pagination
                  v-model="searchPage"
                  :length="Math.max(1, Math.ceil(searchResults.length / searchPageSize))"
                  density="comfortable"
                />
              </div>
            </v-card>
          </section>

          <section v-if="activePage === 'downloads'" class="page-stack">
            <div class="toolbar-row download-toolbar">
              <v-btn prepend-icon="mdi-refresh" variant="tonal" @click="loadDownloads">刷新</v-btn>
              <v-btn
                prepend-icon="mdi-delete"
                color="error"
                variant="tonal"
                :disabled="!selectedDownloadIds.length"
                @click="deleteSelectedDownloads"
              >
                删除
              </v-btn>
              <v-switch
                v-model="downloadActiveOnly"
                class="download-active-switch"
                color="primary"
                density="compact"
                hide-details
                inset
                label="仅看活跃"
              />
            </div>
            <v-card>
              <v-table>
                <thead>
                  <tr>
                    <th class="select-cell">
                      <v-checkbox
                        v-model="allDownloadsSelected"
                        :indeterminate="someDownloadsSelected"
                        density="compact"
                        hide-details
                      />
                    </th>
                    <th>名称</th>
                    <th>状态</th>
                    <th>进度</th>
                    <th>保存路径</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!filteredDownloads.length"><td colspan="6" class="empty-cell">{{ downloadEmptyText }}</td></tr>
                  <tr v-for="row in filteredDownloads" :key="row.id || row.torrent_hash || row.name">
                    <td class="select-cell">
                      <v-checkbox
                        v-if="typeof row.id === 'number'"
                        v-model="selectedDownloadIds"
                        :value="row.id"
                        density="compact"
                        hide-details
                      />
                    </td>
                    <td>{{ row.name }}</td>
                    <td>
                      <v-chip
                        :color="downloadStatusColor(row.state)"
                        size="small"
                        variant="tonal"
                      >
                        {{ downloadStatusText(row.state) }}
                      </v-chip>
                    </td>
                    <td><v-progress-linear :model-value="progressPercent(row.progress)" height="8" rounded /></td>
                    <td class="path-cell">{{ row.save_path || '-' }}</td>
                    <td class="table-actions">
                      <v-btn
                        icon="mdi-format-list-bulleted"
                        color="primary"
                        variant="text"
                        size="small"
                        title="查看明细"
                        :disabled="typeof row.id !== 'number'"
                        @click="viewDownloadItems(row)"
                      />
                      <v-btn
                        icon="mdi-delete"
                        color="error"
                        variant="text"
                        size="small"
                        title="删除任务"
                        :disabled="typeof row.id !== 'number'"
                        @click="deleteDownloadTask(row)"
                      />
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
          </section>

          <section v-if="activePage === 'media'" class="page-stack">
            <div class="toolbar-row">
              <v-btn prepend-icon="mdi-refresh" variant="tonal" @click="loadMedia">刷新</v-btn>
              <v-btn
                prepend-icon="mdi-refresh"
                variant="tonal"
                :disabled="!selectedMediaIds.length || mediaRetrying"
                :loading="mediaRetrying"
                @click="retrySelectedMedia"
              >
                重试
              </v-btn>
              <v-btn
                prepend-icon="mdi-delete"
                color="error"
                variant="tonal"
                :disabled="!selectedMediaIds.length"
                @click="deleteSelectedMediaFiles"
              >
                删除
              </v-btn>
              <v-text-field
                v-model="mediaQuery"
                label="搜索整理记录"
                prepend-inner-icon="mdi-magnify"
                hide-details
                clearable
                class="table-search"
                @keyup.enter="applyMediaFilters"
                @click:clear="applyMediaFilters"
              />
              <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyMediaFilters">
                搜索
              </v-btn>
              <v-select
                v-model="mediaStatusFilter"
                :items="mediaStatusFilterOptions"
                item-title="title"
                item-value="value"
                label="状态筛选"
                hide-details
                density="compact"
                class="status-filter-select"
                clearable
                @update:model-value="applyMediaFilters"
              />
            </div>
            <v-card>
              <v-data-table
                :headers="mediaTableHeaders"
                :items="mediaFiles"
                :items-per-page="-1"
                class="media-table"
                density="comfortable"
                hide-default-footer
                item-value="id"
              >
                <template #header.select>
                  <v-checkbox
                    v-model="allMediaSelected"
                    :indeterminate="someMediaSelected"
                    density="compact"
                    hide-details
                  />
                </template>
                <template #item.select="{ item }">
                  <v-checkbox
                    v-model="selectedMediaIds"
                    :value="mediaTableRow(item).id"
                    density="compact"
                    hide-details
                  />
                </template>
                <template #item.title="{ item }">
                  {{ mediaTableRow(item).title || '-' }}
                </template>
                <template #item.artist="{ item }">
                  {{ mediaTableRow(item).artist || '-' }}
                </template>
                <template #item.album="{ item }">
                  {{ mediaTableRow(item).album || '-' }}
                </template>
                <template #item.operation_time="{ item }">
                  {{ formatTime(mediaTableRow(item).operation_time) }}
                </template>
                <template #item.operation_type="{ item }">
                  <v-chip size="small" variant="tonal">
                    {{ mediaOperationTypeText(mediaTableRow(item).operation_type) }}
                  </v-chip>
                </template>
                <template #item.status="{ item }">
                  <v-chip
                    :color="mediaStatusColor(mediaTableRow(item).status)"
                    size="small"
                    variant="tonal"
                  >
                    {{ mediaStatusText(mediaTableRow(item).status) }}
                  </v-chip>
                </template>
                <template #item.path="{ item }">
                  <div class="media-cell-clip media-path-clip">
                    <v-tooltip location="top" max-width="640">
                      <template #activator="{ props }">
                        <span v-bind="props" class="media-path-text">
                          {{ mediaDisplayPath(mediaTableRow(item)) }}
                        </span>
                      </template>
                      <span class="media-tooltip-text">{{ mediaDisplayPath(mediaTableRow(item)) }}</span>
                    </v-tooltip>
                  </div>
                </template>
                <template #item.remark="{ item }">
                  <div class="media-cell-clip media-remark-clip">
                    <v-tooltip location="top" max-width="420">
                      <template #activator="{ props }">
                        <span v-bind="props" class="media-remark-text">
                          {{ mediaRemark(mediaTableRow(item)) }}
                        </span>
                      </template>
                      <span class="media-tooltip-text">{{ mediaRemark(mediaTableRow(item)) }}</span>
                    </v-tooltip>
                  </div>
                </template>
                <template #item.actions="{ item }">
                  <v-btn
                    icon="mdi-pencil-box-outline"
                    color="primary"
                    variant="text"
                    size="small"
                    title="手动整理"
                    :disabled="mediaManualSubmitting"
                    @click="openManualOrganize(mediaTableRow(item))"
                  />
                  <v-btn
                    icon="mdi-refresh"
                    color="primary"
                    variant="text"
                    size="small"
                    title="重试"
                    :disabled="mediaRetrying"
                    @click="retrySingleMedia(mediaTableRow(item))"
                  />
                  <v-btn
                    icon="mdi-delete"
                    color="error"
                    variant="text"
                    size="small"
                    title="删除整理记录"
                    @click="deleteMediaFile(mediaTableRow(item))"
                  />
                </template>
                <template #no-data>
                  <div class="empty-cell">暂无整理记录</div>
                </template>
                <template #bottom></template>
              </v-data-table>
              <div class="pagination-row">
                <v-select
                  v-model="mediaPageSize"
                  :items="[20, 50, 100]"
                  label="每页"
                  density="compact"
                  hide-details
                  class="page-size-select"
                  @update:model-value="applyMediaFilters"
                />
                <v-pagination
                  v-model="mediaPage"
                  :length="mediaPageLength"
                  density="comfortable"
                  total-visible="7"
                  @update:model-value="loadMedia"
                />
                <v-chip color="secondary" variant="tonal">共 {{ mediaTotal }} 条</v-chip>
              </div>
            </v-card>
          </section>

          <section v-if="activePage === 'files'" class="page-stack">
            <div class="toolbar-row">
              <v-select
                :model-value="fileRootType"
                :items="fileRootTypeOptions"
                item-title="title"
                item-value="value"
                label="当前目录"
                hide-details
                class="file-root-select"
                :disabled="fileLoading"
                @update:model-value="changeFileRootType"
              />
              <v-btn
                prepend-icon="mdi-refresh"
                variant="tonal"
                :loading="fileLoading"
                @click="loadFiles(filePath)"
              >
                刷新
              </v-btn>
              <v-btn
                prepend-icon="mdi-arrow-up"
                variant="tonal"
                :disabled="fileParent === null || fileLoading"
                @click="loadFiles(fileParent || '')"
              >
                上级目录
              </v-btn>
              <v-btn
                prepend-icon="mdi-playlist-check"
                color="primary"
                variant="tonal"
                :disabled="fileRootType !== 'source' || !selectedFilePaths.length || fileLoading || fileOrganizing"
                @click="organizeSelectedFiles"
              >
                批量整理
              </v-btn>
              <v-btn
                prepend-icon="mdi-delete"
                color="error"
                variant="tonal"
                :disabled="!selectedFilePaths.length || fileLoading"
                @click="deleteSelectedFiles"
              >
                删除
              </v-btn>
              <v-text-field
                v-model="fileSearchQuery"
                label="搜索文件"
                prepend-inner-icon="mdi-magnify"
                hide-details
                clearable
                class="file-search"
                @keyup.enter="runFileSearch"
                @click:clear="clearFileSearch"
              />
              <v-btn
                prepend-icon="mdi-magnify"
                variant="tonal"
                :loading="fileLoading"
                @click="runFileSearch"
              >
                搜索
              </v-btn>
              <v-chip v-if="fileRoot" color="secondary" variant="tonal">{{ fileRoot }}</v-chip>
            </div>

            <div class="file-breadcrumbs">
              <button
                v-for="(item, index) in fileBreadcrumbs"
                :key="item.path"
                class="file-breadcrumb"
                type="button"
                :disabled="item.path === filePath || fileLoading"
                @click="loadFiles(item.path)"
              >
                <span v-if="index > 0">/</span>
                {{ item.title }}
              </button>
            </div>

            <v-card>
              <v-progress-linear v-if="fileLoading" indeterminate color="primary" />
              <v-table>
                <thead>
                  <tr>
                    <th class="select-cell">
                      <v-checkbox
                        v-model="allFilesSelected"
                        :indeterminate="someFilesSelected"
                        density="compact"
                        hide-details
                      />
                    </th>
                    <th>名称</th>
                    <th>类型</th>
                    <th>大小</th>
                    <th>修改时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="fileError">
                    <td colspan="6" class="empty-cell">{{ fileError }}</td>
                  </tr>
                  <tr v-else-if="!fileEntries.length && !fileLoading">
                    <td colspan="6" class="empty-cell">
                      {{ trimmedInput(fileSearchQuery) ? '没有匹配文件' : '目录为空' }}
                    </td>
                  </tr>
                  <tr
                    v-for="entry in fileEntries"
                    :key="entry.path"
                    :class="{ 'file-row-clickable': entry.type === 'directory' }"
                    @click="openFileEntry(entry)"
                  >
                    <td class="select-cell" @click.stop>
                      <v-checkbox
                        v-model="selectedFilePaths"
                        :value="entry.path"
                        density="compact"
                        hide-details
                      />
                    </td>
                    <td>
                      <div class="file-name-cell">
                        <v-icon
                          :icon="entry.type === 'directory' ? 'mdi-folder-outline' : 'mdi-file-music-outline'"
                          size="22"
                        />
                        <button
                          class="file-name-button"
                          type="button"
                          :disabled="entry.type !== 'directory'"
                          @click.stop="openFileEntry(entry)"
                        >
                          {{ entry.name }}
                        </button>
                      </div>
                    </td>
                    <td>{{ entry.type === 'directory' ? '目录' : '文件' }}</td>
                    <td>{{ entry.type === 'directory' ? '-' : formatSize(entry.size) }}</td>
                    <td>{{ entry.modified_at ? formatTime(entry.modified_at) : '-' }}</td>
                    <td>
                      <v-btn
                        icon="mdi-playlist-check"
                        color="primary"
                        variant="text"
                        size="small"
                        :disabled="fileRootType !== 'source' || fileOrganizing"
                        :title="fileRootType === 'source' ? '整理' : '映射目录不能整理'"
                        @click.stop="openFileOrganize(entry)"
                      />
                      <v-btn
                        icon="mdi-pencil-box-outline"
                        color="primary"
                        variant="text"
                        size="small"
                        :disabled="fileRootType !== 'source' || mediaManualSubmitting"
                        :title="fileRootType === 'source' ? '手动整理' : '仅源目录可手动整理'"
                        @click.stop="openFileManualOrganize(entry)"
                      />
                      <v-btn
                        icon="mdi-delete"
                        color="error"
                        variant="text"
                        size="small"
                        title="删除"
                        @click.stop="openFileDelete(entry)"
                      />
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
          </section>

          <section v-if="activePage === 'musicLibrary'" class="page-stack">
            <div class="toolbar-row">
              <v-btn
                prepend-icon="mdi-refresh"
                variant="tonal"
                :loading="musicLibraryLoading"
                @click="syncMusicLibrary"
              >
                同步
              </v-btn>
              <v-chip color="secondary" variant="tonal">Navidrome</v-chip>
              <v-chip color="primary" variant="tonal">歌曲 {{ musicLibraryStats.songs }}</v-chip>
              <v-chip color="primary" variant="tonal">专辑 {{ musicLibraryStats.albums }}</v-chip>
              <v-chip color="primary" variant="tonal">艺术家 {{ musicLibraryStats.artists }}</v-chip>
              <v-text-field
                v-model="musicLibraryQuery"
                label="搜索音乐库"
                prepend-inner-icon="mdi-magnify"
                hide-details
                clearable
                class="table-search"
                @keydown.enter="applyMusicLibraryFilters"
                @click:clear="applyMusicLibraryFilters"
              />
              <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyMusicLibraryFilters">
                查询
              </v-btn>
            </div>
            <v-card>
              <v-progress-linear v-if="musicLibraryLoading" indeterminate color="primary" />
              <v-table>
                <thead>
                  <tr>
                    <th>标题</th>
                    <th>艺人</th>
                    <th>专辑</th>
                    <th>时长</th>
                    <th>大小</th>
                    <th>年份</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!musicLibraryTracks.length">
                    <td colspan="6" class="empty-cell">暂无音乐库记录</td>
                  </tr>
                  <tr v-for="track in musicLibraryTracks" :key="track.id">
                    <td>{{ track.title || '-' }}</td>
                    <td>{{ track.artist || '-' }}</td>
                    <td>{{ track.album || '-' }}</td>
                    <td>{{ formatDuration(track.duration) }}</td>
                    <td>{{ formatSize(track.size) }}</td>
                    <td>{{ track.year || '-' }}</td>
                  </tr>
                </tbody>
              </v-table>
              <div class="pagination-row">
                <v-select
                  v-model="musicLibraryPageSize"
                  :items="[10, 20, 50, 100]"
                  density="comfortable"
                  hide-details
                  label="每页"
                  class="page-size-select"
                  @update:model-value="applyMusicLibraryFilters"
                />
                <v-pagination
                  v-model="musicLibraryPage"
                  :length="musicLibraryPageLength"
                  density="comfortable"
                  total-visible="5"
                  @update:model-value="loadMusicLibrary"
                />
                <v-chip color="secondary" variant="tonal">共 {{ musicLibraryTotal }} 条</v-chip>
              </div>
            </v-card>
          </section>

          <section v-if="activePage === 'playlists'" class="page-stack">
            <div class="toolbar-row">
              <v-btn color="primary" prepend-icon="mdi-plus" @click="openPlaylistImportDialog">
                新增
              </v-btn>
              <v-btn
                prepend-icon="mdi-refresh"
                variant="tonal"
                :loading="playlistLoading"
                @click="loadPlaylists"
              >
                刷新
              </v-btn>
            </div>
            <v-card>
              <v-progress-linear v-if="playlistLoading" indeterminate color="primary" />
              <v-table class="playlist-table fixed-table">
                <thead>
                  <tr>
                    <th class="playlist-name-col">歌单</th>
                    <th class="playlist-platform-col">平台</th>
                    <th class="count-col">歌曲</th>
                    <th class="count-col">已存在</th>
                    <th class="count-col">等待</th>
                    <th class="count-col">已提交</th>
                    <th class="count-col">失败</th>
                    <th class="status-col">状态</th>
                    <th class="time-col">最近同步</th>
                    <th class="sticky-action-col playlist-action-col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!playlists.length">
                    <td colspan="10" class="empty-cell">暂无歌单</td>
                  </tr>
                  <tr v-for="playlist in playlists" :key="playlist.id">
                    <td>
                      <div class="playlist-title-cell">
                        <img
                          v-if="playlist.cover_url"
                          :src="playlist.cover_url"
                          alt=""
                          class="playlist-cover"
                          loading="lazy"
                        />
                        <div class="playlist-title-text">
                          <div class="truncate-text" :title="playlist.name">{{ playlist.name }}</div>
                          <div class="muted truncate-text" :title="playlist.owner_name || '-'">
                            {{ playlist.owner_name || '-' }}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td class="truncate-cell" :title="playlistPlatformLabel(playlist.platform)">
                      {{ playlistPlatformLabel(playlist.platform) }}
                    </td>
                    <td>{{ playlist.track_count }}</td>
                    <td>{{ playlist.existing_count }}</td>
                    <td>{{ playlist.waiting_count }}</td>
                    <td>{{ playlist.submitted_count }}</td>
                    <td>{{ playlist.failed_count }}</td>
                    <td>
                      <v-chip :color="playlistStatusColor(playlist.status)" size="small" variant="tonal">
                        {{ playlistStatusText(playlist.status) }}
                      </v-chip>
                    </td>
                    <td class="truncate-cell" :title="formatOptionalTime(playlist.last_synced_at)">
                      {{ formatOptionalTime(playlist.last_synced_at) }}
                    </td>
                    <td class="sticky-action-col playlist-action-col">
                      <v-btn
                        icon="mdi-eye-outline"
                        color="primary"
                        variant="text"
                        size="small"
                        title="查看"
                        @click="viewPlaylist(playlist)"
                      />
                      <v-btn
                        icon="mdi-sync"
                        color="primary"
                        variant="text"
                        size="small"
                        title="同步来源"
                        @click="syncPlaylist(playlist)"
                      />
                      <v-btn
                        icon="mdi-playlist-check"
                        color="primary"
                        variant="text"
                        size="small"
                        title="同步到音乐库"
                        :loading="isPlaylistSyncingToLibrary(playlist.id)"
                        @click="openPlaylistLibrarySyncDialog(playlist)"
                      />
                      <v-btn
                        icon="mdi-download"
                        color="primary"
                        variant="text"
                        size="small"
                        title="下载"
                        :loading="playlistDownloading"
                        @click="downloadPlaylist(playlist)"
                      />
                      <v-btn
                        icon="mdi-delete-outline"
                        color="error"
                        variant="text"
                        size="small"
                        title="删除"
                        @click="openDeletePlaylist(playlist)"
                      />
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
          </section>

<section v-if="activePage === 'artists'" class="page-stack">
            <div class="toolbar-row">
              <v-btn
                prepend-icon="mdi-refresh"
                variant="tonal"
                :loading="artistLoading"
                @click="loadArtists"
              >
                刷新
              </v-btn>
              <v-btn
                color="primary"
                prepend-icon="mdi-database-plus"
                :loading="artistBuilding"
                @click="buildArtistLibrary"
              >
                从曲库构建
              </v-btn>
              <v-btn
                color="warning"
                prepend-icon="mdi-database-refresh"
                :loading="artistBuilding"
                @click="clearAndRebuildArtistLibrary"
              >
                清空并重建
              </v-btn>
              <v-text-field
                v-model="artistQuery"
                label="搜索歌手或别名"
                prepend-inner-icon="mdi-magnify"
                hide-details
                clearable
                class="table-search"
                @keyup.enter="applyArtistFilters"
                @click:clear="applyArtistFilters"
              />
              <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyArtistFilters">
                搜索
              </v-btn>
              <v-chip v-if="artistTotal" color="primary" variant="tonal">
                共 {{ artistTotal }} 个歌手
              </v-chip>
            </div>
            <v-card>
              <v-progress-linear v-if="artistLoading" indeterminate color="primary" />
              <v-table>
                <thead>
                  <tr>
                    <th>歌手名（权威名）</th>
                    <th>归一化名</th>
                    <th>别名</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!artists.length">
                    <td colspan="4" class="empty-cell">
                      暂无歌手数据，点击「从曲库构建」按钮自动生成
                    </td>
                  </tr>
                  <tr v-for="artist in artists" :key="artist.id">
                    <td>
                      <strong>{{ artist.name }}</strong>
                    </td>
                    <td class="muted">{{ artist.normalized_name }}</td>
                    <td>
                      <div v-if="artist.aliases.length" class="alias-list">
                        <v-chip
                          v-for="alias in artist.aliases"
                          :key="alias.alias"
                          size="x-small"
                          variant="tonal"
                          class="alias-chip"
                        >
                          {{ alias.alias }}
                        </v-chip>
                      </div>
                      <span v-else class="muted">-</span>
                    </td>
                    <td>
                      <v-btn
                        icon="mdi-pencil-outline"
                        color="primary"
                        variant="text"
                        size="small"
                        title="编辑"
                        @click="openArtistEditDialog(artist)"
                      />
                      <v-btn
                        icon="mdi-book-plus"
                        color="primary"
                        variant="text"
                        size="small"
                        title="添加别名"
                        @click="openArtistAliasDialog(artist)"
                      />
                      <v-btn
                        icon="mdi-call-merge"
                        color="warning"
                        variant="text"
                        size="small"
                        title="合并到此歌手"
                        @click="openArtistMergeDialog(artist)"
                      />
                    </td>
                  </tr>
                </tbody>
              </v-table>
              <div class="pagination-row">
                <v-select
                  v-model="artistPageSize"
                  :items="[20, 50, 100]"
                  label="每页"
                  density="compact"
                  hide-details
                  class="page-size-select"
                  @update:model-value="applyArtistFilters"
                />
                <v-pagination
                  v-model="artistPage"
                  :length="artistPageLength"
                  density="comfortable"
                  total-visible="7"
                  @update:model-value="loadArtists"
                />
              </div>
            </v-card>
          </section>

          <section v-if="activePage === 'sites'" class="page-stack">
            <div class="toolbar-row">
              <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewSiteDialog">新增站点</v-btn>
            </div>
            <div class="card-grid">
              <v-card v-for="site in sites" :key="site.id || site.name" class="config-card" @click="editSite(site)">
                <v-card-title class="config-card-title d-flex align-center">
                  <span>{{ site.name }}</span>
                  <v-spacer />
                  <div v-if="site.id" class="config-card-menu" @click.stop>
                    <v-btn
                      icon="mdi-dots-vertical"
                      size="small"
                      variant="text"
                      @click.stop="toggleConfigMenu('site', site.id)"
                    />
                    <v-card
                      v-if="activeConfigMenu === configMenuKey('site', site.id)"
                      class="config-card-menu-panel"
                      elevation="0"
                      @click.stop
                    >
                      <button class="config-card-menu-item" type="button" @click="openDeleteSite(site)">
                        删除
                      </button>
                    </v-card>
                  </div>
                </v-card-title>
                <v-card-text>
                  <div class="muted">{{ site.base_url }}</div>
                  <div class="mt-1">
                    <v-chip size="small" variant="tonal">{{ site.max_concurrency }} 并发</v-chip>
                    <v-chip
                      v-if="site.use_proxy"
                      size="small"
                      color="primary"
                      variant="tonal"
                      class="ml-1"
                    >代理</v-chip>
                  </div>
                </v-card-text>
              </v-card>
            </div>
          </section>

          <section v-if="activePage === 'logs'" class="page-stack">
            <v-card>
              <v-card-text class="log-toolbar">
                <v-select
                  v-model="logLevel"
                  :items="['ALL', 'INFO', 'WARNING', 'ERROR']"
                  label="级别"
                  hide-details
                  class="log-level"
                />
                <v-text-field
                  v-model="logQuery"
                  label="搜索日志"
                  prepend-inner-icon="mdi-magnify"
                  hide-details
                />
                <v-btn
                  :prepend-icon="logPaused ? 'mdi-play' : 'mdi-pause'"
                  variant="tonal"
                  @click="logPaused = !logPaused"
                >
                  {{ logPaused ? '继续' : '暂停' }}
                </v-btn>
                <v-btn prepend-icon="mdi-refresh" :loading="logsLoading" variant="tonal" @click="loadLogs">
                  刷新
                </v-btn>
              </v-card-text>
              <div class="log-list">
                <div v-if="!filteredLogs.length" class="empty-cell">暂无日志</div>
                <div v-for="entry in filteredLogs" :key="`${entry.timestamp}-${entry.message}`" class="log-line">
                  <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
                  <v-chip :color="logColor(entry.level)" size="x-small" variant="tonal">{{ entry.level }}</v-chip>
                  <span class="log-category">{{ entry.category }}</span>
                  <span class="log-message">{{ entry.message }}</span>
                </div>
              </div>
            </v-card>
          </section>

          <section v-if="activePage === 'settings'" class="page-stack">
            <v-tabs v-model="settingsTab" color="primary">
              <v-tab value="downloaders">下载器</v-tab>
              <v-tab value="mediaServers">音乐库</v-tab>
              <v-tab value="notifiers">通知</v-tab>
              <v-tab value="system">系统设置</v-tab>
            </v-tabs>

            <v-window v-model="settingsTab" class="settings-window">
              <v-window-item value="downloaders">
                <div class="toolbar-row">
                  <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewDownloaderDialog">新增下载器</v-btn>
                </div>
                <div class="card-grid">
                  <v-card
                    v-for="downloader in downloaders"
                    :key="downloader.id || downloader.base_url"
                    class="config-card"
                    @click="editDownloader(downloader)"
                  >
                    <v-card-title class="config-card-title d-flex align-center">
                      <span>{{ downloader.name }}</span>
                      <v-spacer />
                      <div v-if="downloader.id" class="config-card-menu" @click.stop>
                        <v-btn
                          icon="mdi-dots-vertical"
                          size="small"
                          variant="text"
                          @click.stop="toggleConfigMenu('downloader', downloader.id)"
                        />
                        <v-card
                          v-if="activeConfigMenu === configMenuKey('downloader', downloader.id)"
                          class="config-card-menu-panel"
                          elevation="0"
                          @click.stop
                        >
                          <button class="config-card-menu-item" type="button" @click="openDeleteDownloader(downloader)">
                            删除
                          </button>
                        </v-card>
                      </div>
                    </v-card-title>
                    <v-card-text>
                      <div class="muted">{{ downloader.base_url }}</div>
                      <div class="muted">{{ downloader.download_path || '未设置下载目录' }}</div>
                      <div class="muted">{{ downloader.local_path || '未设置本机对应目录' }}</div>
                      <v-chip v-if="downloader.is_default" color="success" size="small" variant="tonal">默认</v-chip>
                      <v-chip v-if="!downloader.enabled" color="warning" size="small" variant="tonal">停用</v-chip>
                    </v-card-text>
                  </v-card>
                </div>
              </v-window-item>

              <v-window-item value="mediaServers">
                <v-card class="settings-card">
                  <v-card-title>音乐库配置</v-card-title>
                  <v-card-text class="settings-grid">
                    <v-select v-model="mediaServerForm.type" :items="['navidrome']" label="类型" />
                    <v-text-field v-model="mediaServerForm.name" label="名称" />
                    <v-text-field v-model="mediaServerForm.base_url" label="地址" />
                    <v-text-field v-model="mediaServerForm.api_key" label="API Token" />
                    <v-text-field v-model="mediaServerForm.username" label="默认用户名" />
                    <v-text-field
                      v-model="mediaServerForm.password"
                      label="默认用户密码"
                      type="password"
                      :placeholder="mediaServerForm.id ? '留空则保持原密码' : ''"
                    />
                    <v-switch
                      v-model="mediaServerForm.enabled"
                      class="compact-switch"
                      color="primary"
                      density="compact"
                      hide-details
                      inset
                      label="启用"
                    />
                  </v-card-text>
                  <v-card-actions>
                    <v-spacer />
                    <v-btn :loading="mediaServerTesting" variant="tonal" @click="testMediaServer">
                      测试
                    </v-btn>
                    <v-btn color="primary" @click="saveMediaServer">
                      保存
                    </v-btn>
                  </v-card-actions>
                </v-card>

                <v-card class="settings-card mt-4">
                  <v-card-title class="d-flex align-center">
                    <span>用户账号</span>
                    <v-spacer />
                    <v-btn
                      color="primary"
                      prepend-icon="mdi-account-plus"
                      variant="tonal"
                      @click="openNewMediaServerUserDialog"
                    >
                      新增用户
                    </v-btn>
                  </v-card-title>
                  <v-table>
                    <thead>
                      <tr>
                        <th>用户名</th>
                        <th>状态</th>
                        <th>类型</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="!mediaServerUserAccounts.length">
                        <td colspan="4" class="empty-cell">保存音乐库配置后会生成默认用户</td>
                      </tr>
                      <tr v-for="server in mediaServerUserAccounts" :key="server.id || server.username">
                        <td>
                          <div class="font-weight-medium">{{ server.username || '-' }}</div>
                          <div class="muted">{{ server.is_default ? '默认账号' : server.name }}</div>
                        </td>
                        <td>
                          <v-chip
                            :color="server.enabled ? 'success' : 'warning'"
                            size="small"
                            variant="tonal"
                          >
                            {{ server.enabled ? '启用' : '停用' }}
                          </v-chip>
                        </td>
                        <td>{{ server.type }}</td>
                        <td class="table-actions">
                          <v-btn
                            icon="mdi-pencil-outline"
                            color="primary"
                            variant="text"
                            size="small"
                            :title="server.is_default ? '默认账号请在上方编辑' : '编辑用户'"
                            :disabled="server.is_default"
                            @click="editMediaServerUser(server)"
                          />
                          <v-btn
                            icon="mdi-delete-outline"
                            color="error"
                            variant="text"
                            size="small"
                            title="删除用户"
                            :disabled="server.is_default"
                            @click="openDeleteMediaServer(server)"
                          />
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                </v-card>
              </v-window-item>

              <v-window-item value="notifiers">
                <div class="toolbar-row">
                  <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewNotifierDialog">新增通知</v-btn>
                </div>
                <div class="card-grid">
                  <v-card
                    v-for="notifier in notifiers"
                    :key="notifier.id || notifier.name"
                    class="config-card"
                    @click="editNotifier(notifier)"
                  >
                    <v-card-title class="config-card-title d-flex align-center">
                      <span>{{ notifier.name }}</span>
                      <v-spacer />
                      <div v-if="notifier.id" class="config-card-menu" @click.stop>
                        <v-btn
                          icon="mdi-dots-vertical"
                          size="small"
                          variant="text"
                          @click.stop="toggleConfigMenu('notifier', notifier.id)"
                        />
                        <v-card
                          v-if="activeConfigMenu === configMenuKey('notifier', notifier.id)"
                          class="config-card-menu-panel"
                          elevation="0"
                          @click.stop
                        >
                          <button class="config-card-menu-item" type="button" @click="openDeleteNotifier(notifier)">
                            删除
                          </button>
                        </v-card>
                      </div>
                    </v-card-title>
                    <v-card-text>
                      <v-chip size="small" variant="tonal">{{ notifier.type }}</v-chip>
                      <v-chip v-if="notifier.use_proxy" color="warning" size="small" variant="tonal">代理</v-chip>
                      <v-chip v-if="!notifier.enabled" color="warning" size="small" variant="tonal">停用</v-chip>
                      <div class="muted">{{ notifier.chat_ids || '未指定会话' }}</div>
                    </v-card-text>
                  </v-card>
                </div>
              </v-window-item>

              <v-window-item value="system">
                <v-card class="settings-card">
                  <v-card-title>网络设置</v-card-title>
                  <v-card-text class="settings-grid">
                    <v-text-field v-model="systemForm.proxy.host" label="代理地址" placeholder="127.0.0.1 或 http://127.0.0.1:7890" />
                    <v-text-field v-model.number="systemForm.proxy.port" label="端口" type="number" />
                    <v-text-field v-model="systemForm.proxy.username" label="用户名" />
                    <v-text-field v-model="systemForm.proxy.password" label="密码" type="password" />
                  </v-card-text>
                  <v-card-actions>
                    <v-spacer />
                    <v-btn color="primary" :loading="systemSaving" @click="saveSystemSettings">
                      保存网络设置
                    </v-btn>
                  </v-card-actions>
                </v-card>

                <v-card class="settings-card mt-4">
                  <v-card-title>刮削设置</v-card-title>
                  <v-card-text>
                    <div class="settings-grid">
                      <v-switch
                        v-model="systemForm.scraping.enabled"
                        class="compact-switch"
                        color="primary"
                        density="compact"
                        hide-details
                        inset
                        label="开启刮削"
                      />
                      <v-select
                        v-model="systemForm.scraping.mode"
                        :items="scrapingModeOptions"
                        label="刮削类型"
                      />
                      <v-text-field
                        v-model="systemForm.scraping.source_directory"
                        label="源文件目录"
                      />
                      <v-text-field
                        v-if="systemForm.scraping.mode !== 'source'"
                        v-model="systemForm.scraping.mapped_directory"
                        :label="systemForm.scraping.mode === 'copy' ? '复制目录' : '映射目录'"
                      />
                    </div>

                    <div class="settings-checks">
                      <div class="settings-checks-label">缺失时尝试刮削</div>
                      <div class="settings-checks-row">
                        <v-checkbox
                          v-for="item in scrapingRequiredMetadataOptions"
                          :key="item.value"
                          v-model="systemForm.scraping.scrape_when_missing"
                          :label="item.title"
                          :value="item.value"
                          hide-details
                        />
                      </div>
                    </div>

                    <div class="settings-checks">
                      <div class="settings-checks-label">缺失则判定失败</div>
                      <div class="settings-checks-row">
                        <v-checkbox
                          v-for="item in scrapingRequiredMetadataOptions"
                          :key="item.value"
                          v-model="systemForm.scraping.required_metadata"
                          :label="item.title"
                          :value="item.value"
                          hide-details
                        />
                      </div>
                    </div>

                    <div class="settings-grid">
                      <v-switch
                        v-model="systemForm.scraping.auto_rename"
                        class="compact-switch"
                        color="primary"
                        density="compact"
                        hide-details
                        inset
                        label="自动重命名"
                      />
                      <v-switch
                        v-model="systemForm.scraping.auto_classify"
                        class="compact-switch"
                        color="primary"
                        density="compact"
                        hide-details
                        inset
                        label="自动分类"
                      />
                      <v-select
                        v-if="systemForm.scraping.auto_classify"
                        v-model="systemForm.scraping.classify_by"
                        :items="scrapingClassifyOptions"
                        label="分类方式"
                      />
                      <v-select
                        v-model="systemForm.scraping.duplicate_handling"
                        :items="duplicateHandlingOptions"
                        label="重复文件处理"
                      />
                    </div>
                  </v-card-text>
                  <v-card-actions>
                    <v-spacer />
                    <v-btn color="primary" :loading="systemSaving" @click="saveSystemSettings">
                      保存刮削设置
                    </v-btn>
                  </v-card-actions>
                </v-card>

                <v-card class="settings-card mt-4">
                  <v-card-title>搜索设置</v-card-title>
                  <v-card-text>
                    <div class="settings-grid">
                      <v-textarea
                        v-model="systemForm.search.exclude_keywords"
                        label="排除关键词"
                        placeholder="试听|sample|preview|acoustic"
                        hint="用 | 分隔多个关键词。标题中包含任一关键词的种子会被过滤掉。"
                        persistent-hint
                        auto-grow
                        rows="2"
                      />
                      <v-text-field
                        v-model.number="systemForm.search.metadata_concurrency"
                        label="元数据搜索并发数"
                        type="number"
                        min="1"
                        max="20"
                        hint="限制同时访问元数据源的搜索任务数量。默认 3；遇到频率限制可降到 1 或 2。"
                        persistent-hint
                      />
                    </div>
                  </v-card-text>
                  <v-card-actions>
                    <v-spacer />
                    <v-btn color="primary" :loading="systemSaving" @click="saveSystemSettings">
                      保存搜索设置
                    </v-btn>
                  </v-card-actions>
                </v-card>
              </v-window-item>
            </v-window>
          </section>
        </div>
      </v-main>
    </template>

    <v-dialog v-model="searchDialog" max-width="460">
      <v-card title="搜索">
        <v-card-text>
          <v-text-field v-model="searchText" label="搜索文本" autofocus @keyup.enter="runSearch" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="searchDialog = false">取消</v-btn>
          <v-btn color="primary" :loading="searchLoading" @click="runSearch">搜索</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="noMetadataDialog" max-width="460">
      <v-card title="未找到媒体信息">
        <v-card-text>未找到媒体信息，是否直接使用站点搜索？</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="noMetadataDialog = false">取消</v-btn>
          <v-btn color="primary" @click="runDirectSearch">直接搜索</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="siteConfirmDialog" max-width="620">
      <v-card title="确认搜索站点">
        <v-card-text class="dialog-stack">
          <div v-if="selectedMedia" class="site-confirm-media">
            <div class="site-confirm-label">媒体信息</div>
            <div class="site-confirm-title">{{ selectedMedia.title }}</div>
            <div class="site-confirm-line">{{ selectedMedia.artist || '未知艺人' }}</div>
            <div class="site-confirm-label site-confirm-album-label">专辑列表</div>
            <div v-if="albumList(selectedMedia).length" class="site-confirm-albums">
              <div v-for="album in albumList(selectedMedia)" :key="album" class="site-confirm-line">
                {{ album }}
              </div>
            </div>
            <div v-else class="site-confirm-line">未知专辑</div>
          </div>
          <v-checkbox
            v-for="site in sites"
            :key="site.id || site.name"
            v-model="selectedSiteIds"
            :label="site.name"
            :value="site.id"
            density="compact"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="siteConfirmDialog = false">取消</v-btn>
          <v-btn color="primary" :disabled="!selectedSiteIds.length" @click="runMetadataSiteSearch">
            执行搜索
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog
      :model-value="Boolean(pendingDownload)"
      max-width="560"
      @update:model-value="(value: boolean) => { if (!value) pendingDownload = null }"
    >
      <v-card class="download-confirm-card">
        <v-card-title class="download-confirm-title">
          <v-icon icon="mdi-monitor-arrow-down-variant" size="36" />
          <div>
            <div>确认下载</div>
            <div class="download-confirm-subtitle">
              {{ pendingDownload?.source }} - {{ pendingDownload?.title }}
            </div>
          </div>
        </v-card-title>
        <v-card-text v-if="pendingDownload" class="download-confirm-body">
          <div class="confirm-row">
            <v-icon icon="mdi-web" size="34" />
            <div>
              <div class="confirm-main-text">{{ pendingDownload.subtitle || pendingDownload.title }}</div>
              <div class="confirm-seeders">
                <span class="seeders"><v-icon icon="mdi-arrow-up" size="18" />{{ pendingDownload.seeders }}</span>
                <span class="leechers"><v-icon icon="mdi-arrow-down" size="18" />{{ pendingDownload.leechers || 0 }}</span>
              </div>
            </div>
          </div>
          <div class="confirm-row">
            <v-icon icon="mdi-database" size="34" />
            <v-chip size="large" variant="tonal">{{ formatSize(pendingDownload.size_bytes) }}</v-chip>
          </div>
          <div class="confirm-row muted">
            <v-icon icon="mdi-clock-outline" size="28" />
            <span>{{ pendingDownload.published_at || '发布时间未知' }}</span>
          </div>
          <div v-if="pendingDownload.promotion" class="confirm-row confirm-promotion-row">
            <v-icon icon="mdi-tag-outline" size="28" />
            <v-chip color="success" size="large" variant="flat" class="confirm-promotion-chip">
              {{ pendingDownload.promotion }}
            </v-chip>
          </div>
        </v-card-text>
        <v-card-actions class="download-confirm-actions">
          <v-btn variant="text" :disabled="downloadSubmitting" @click="pendingDownload = null">取消</v-btn>
          <v-btn
            color="primary"
            prepend-icon="mdi-download"
            size="large"
            :loading="downloadSubmitting"
            :disabled="downloadSubmitting"
            @click="confirmDownload"
          >
            开始下载
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="musicPlatformDialog" max-width="620">
      <v-card title="关联音乐平台">
        <v-card-text class="dialog-stack">
          <v-select
            v-model="musicPlatformForm.platform"
            :items="[{ title: 'Spotify', value: 'spotify' }]"
            label="平台"
          />
          <v-text-field v-model="musicPlatformForm.client_id" label="Client ID" />
          <v-text-field
            v-model="musicPlatformForm.client_secret"
            label="Client Secret"
            type="password"
          />
          <v-text-field v-model="musicPlatformForm.redirect_uri" label="Redirect URI" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="musicPlatformConnecting" @click="musicPlatformDialog = false">
            取消
          </v-btn>
          <v-btn color="primary" :loading="musicPlatformConnecting" @click="connectMusicPlatform">
            下一步
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="playlistImportDialog" max-width="760">
      <v-card title="导入歌单">
        <v-card-text class="dialog-stack">
          <div class="toolbar-row">
            <v-text-field
              v-model="playlistImportUrl"
              label="歌单链接"
              hide-details
              class="platform-select"
              @keyup.enter="importPlaylistUrl"
            />
            <v-btn
              prepend-icon="mdi-link-variant-plus"
              color="primary"
              :loading="availablePlaylistLoading"
              :disabled="!playlistImportUrl.trim()"
              @click="importPlaylistUrl"
            >
              解析
            </v-btn>
          </div>
          <v-table>
            <thead>
              <tr>
                <th class="select-cell"></th>
                <th>封面</th>
                <th>歌单</th>
                <th>平台</th>
                <th>歌曲数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!availablePlaylists.length">
                <td colspan="5" class="empty-cell">请输入歌单链接并解析</td>
              </tr>
              <tr v-for="playlist in availablePlaylists" :key="playlist.import_token || playlist.external_id">
                <td class="select-cell">
                  <v-checkbox
                    v-model="selectedAvailablePlaylistIds"
                    :value="playlist.import_token || playlist.external_id"
                    density="compact"
                    hide-details
                  />
                </td>
                <td>
                  <v-img
                    v-if="playlist.cover_url"
                    :src="playlist.cover_url"
                    width="48"
                    height="48"
                    cover
                    class="playlist-cover"
                  />
                  <div v-else class="playlist-cover playlist-cover-placeholder">-</div>
                </td>
                <td>
                  <div class="font-weight-medium">{{ playlist.name }}</div>
                  <div class="muted-text">{{ playlist.owner_name || '-' }}</div>
                </td>
                <td>{{ playlist.platform || '-' }}</td>
                <td>{{ playlist.track_count }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="availablePlaylistLoading" @click="playlistImportDialog = false">
            取消
          </v-btn>
          <v-btn
            color="primary"
            :loading="availablePlaylistLoading"
            :disabled="!selectedAvailablePlaylistIds.length"
            @click="importSelectedPlaylists"
          >
            确认同步
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="playlistTracksDialog" max-width="980">
      <v-card>
        <v-card-title class="d-flex align-center ga-2">
          <span class="text-truncate">{{ selectedPlaylist ? selectedPlaylist.name : '歌单明细' }}</span>
          <v-spacer />
          <v-btn
            icon="mdi-refresh"
            variant="text"
            size="small"
            title="刷新"
            :loading="playlistTrackLoading"
            :disabled="!selectedPlaylist"
            @click="selectedPlaylist && loadPlaylistTracks(selectedPlaylist)"
          />
        </v-card-title>
        <v-card-text>
          <div class="toolbar-row dialog-filter-row">
            <v-text-field
              v-model="playlistTrackTitleQuery"
              label="歌名"
              prepend-inner-icon="mdi-magnify"
              density="compact"
              hide-details
              clearable
              @keyup.enter="applyPlaylistTrackFilters"
              @click:clear="applyPlaylistTrackFilters"
            />
            <v-text-field
              v-model="playlistTrackArtistQuery"
              label="歌手"
              prepend-inner-icon="mdi-account-music-outline"
              density="compact"
              hide-details
              clearable
              @keyup.enter="applyPlaylistTrackFilters"
              @click:clear="applyPlaylistTrackFilters"
            />
            <v-select
              v-model="playlistTrackDownloadStatus"
              :items="playlistTrackDownloadStatusOptions"
              label="下载状态"
              density="compact"
              hide-details
              @update:model-value="applyPlaylistTrackFilters"
            />
            <v-select
              v-model="playlistTrackLibraryStatus"
              :items="playlistTrackLibraryStatusOptions"
              label="在库状态"
              density="compact"
              hide-details
              @update:model-value="applyPlaylistTrackFilters"
            />
            <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyPlaylistTrackFilters">
              查询
            </v-btn>
          </div>
          <v-progress-linear v-if="playlistTrackLoading" indeterminate color="primary" />
          <v-table class="playlist-track-table fixed-table">
            <thead>
              <tr>
                <th class="track-position-col">#</th>
                <th class="track-title-col">歌曲</th>
                <th class="track-artist-col">艺人</th>
                <th class="track-album-col">专辑</th>
                <th class="track-error-col">错误</th>
                <th class="sticky-track-col sticky-track-library-col">音乐库</th>
                <th class="sticky-track-col sticky-track-status-col">下载状态</th>
                <th class="sticky-track-col sticky-track-download-col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!playlistTracks.length && !playlistTrackLoading">
                <td colspan="8" class="empty-cell">暂无歌曲</td>
              </tr>
              <tr v-for="track in playlistTracks" :key="track.id">
                <td>{{ track.position }}</td>
                <td class="truncate-cell" :title="track.title">{{ track.title }}</td>
                <td class="truncate-cell" :title="track.artist || '-'">{{ track.artist || '-' }}</td>
                <td class="truncate-cell" :title="track.album || '-'">{{ track.album || '-' }}</td>
                <td class="truncate-cell" :title="track.last_error || '-'">{{ track.last_error || '-' }}</td>
                <td class="sticky-track-col sticky-track-library-col">
                  <v-icon
                    v-if="track.exists_in_library"
                    icon="mdi-check-circle"
                    color="success"
                    size="22"
                    title="已存在"
                  />
                  <span v-else>-</span>
                </td>
                <td class="sticky-track-col sticky-track-status-col">
                  <v-chip
                    :color="playlistTrackStatusColor(track.download_status)"
                    size="small"
                    variant="tonal"
                  >
                    {{ playlistTrackStatusText(track.download_status) }}
                  </v-chip>
                </td>
                <td class="sticky-track-col sticky-track-download-col">
                  <v-btn
                    icon="mdi-pencil-outline"
                    color="primary"
                    variant="text"
                    size="small"
                    title="编辑"
                    @click="openPlaylistTrackEditDialog(track)"
                  />
                  <v-btn
                    :icon="playlistTrackActionIcon(track)"
                    color="primary"
                    variant="text"
                    size="small"
                    :title="playlistTrackActionTitle(track)"
                    :loading="isPlaylistTrackDownloading(track.id)"
                    :disabled="!canStartPlaylistTrackDownload(track)"
                    @click="downloadPlaylistTrack(track)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
          <div class="pagination-row">
            <v-select
              v-model="playlistTrackPageSize"
              :items="[20, 50, 100]"
              label="每页"
              density="compact"
              hide-details
              class="page-size-select"
              @update:model-value="applyPlaylistTrackFilters"
            />
            <v-pagination
              v-model="playlistTrackPage"
              :length="playlistTrackPageLength"
              density="comfortable"
              total-visible="7"
              @update:model-value="selectedPlaylist && loadPlaylistTracks(selectedPlaylist)"
            />
            <v-chip color="secondary" variant="tonal">共 {{ playlistTrackTotal }} 首</v-chip>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="playlistTracksDialog = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="playlistTrackEditDialog" max-width="620">
      <v-card title="编辑歌单条目">
        <v-card-text class="dialog-stack">
          <v-text-field
            v-model="playlistTrackEditForm.title"
            label="歌名"
            autofocus
            @keyup.enter="savePlaylistTrackEdit"
          />
          <v-text-field v-model="playlistTrackEditForm.artist" label="歌手" />
          <v-text-field v-model="playlistTrackEditForm.album" label="专辑" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="playlistTrackEditSaving" @click="playlistTrackEditDialog = false">
            取消
          </v-btn>
          <v-btn
            color="primary"
            :loading="playlistTrackEditSaving"
            :disabled="!playlistTrackEditForm.title.trim()"
            @click="savePlaylistTrackEdit"
          >
            保存
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="playlistLibrarySyncDialog" max-width="520">
      <v-card title="同步到音乐库">
        <v-card-text class="dialog-stack">
          <div class="muted">
            {{ playlistLibrarySyncForm.playlist?.name || '-' }}
          </div>
          <v-select
            v-model="playlistLibrarySyncForm.media_server_id"
            :items="enabledMediaServerOptions"
            item-title="title"
            item-value="value"
            label="同步账号"
            no-data-text="暂无已启用的音乐库账号"
          />
          <v-switch
            v-model="playlistLibrarySyncForm.public"
            color="primary"
            density="compact"
            hide-details
            inset
            label="公开"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="playlistLibrarySyncDialog = false">取消</v-btn>
          <v-btn
            color="primary"
            :disabled="!playlistLibrarySyncForm.media_server_id || !playlistLibrarySyncForm.playlist"
            :loading="playlistLibrarySyncForm.playlist ? isPlaylistSyncingToLibrary(playlistLibrarySyncForm.playlist.id) : false"
            @click="syncPlaylistToLibrary"
          >
            同步
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="siteDialog" max-width="820">
      <v-card :title="editingSiteId ? '编辑站点' : '新增站点'">
        <v-card-text class="dialog-stack">
          <v-text-field v-model="siteForm.name" label="站点名称" />
          <v-text-field v-model="siteForm.base_url" label="站点地址" />
          <v-textarea v-model="siteForm.cookie" label="Cookie" rows="3" />
          <v-text-field v-model="siteForm.user_agent" label="User-Agent" />
          <v-text-field v-model.number="siteForm.max_concurrency" label="最大并发" type="number" />
          <v-switch
            v-model="siteForm.use_proxy"
            color="primary"
            density="compact"
            hide-details
            inset
            label="使用系统代理"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="siteDialog = false">取消</v-btn>
          <v-btn :loading="siteTesting" variant="tonal" @click="testSite">测试</v-btn>
          <v-btn color="primary" @click="saveSite">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="downloaderDialog" max-width="560">
      <v-card :title="editingDownloaderId ? '编辑下载器' : '新增下载器'">
        <v-card-text class="dialog-stack">
          <v-select v-model="downloaderForm.type" :items="['qbittorrent']" label="类型" />
          <v-text-field v-model="downloaderForm.name" label="名称" />
          <v-text-field v-model="downloaderForm.base_url" label="地址" />
          <v-text-field v-model="downloaderForm.username" label="用户名" />
          <v-text-field
            v-model="downloaderForm.password"
            label="密码"
            type="password"
            :placeholder="editingDownloaderId ? '留空则保持原密码' : ''"
          />
          <v-text-field
            v-model="downloaderForm.download_path"
            label="下载目录"
            placeholder="/downloads/music"
            required
          />
          <v-text-field
            v-model="downloaderForm.local_path"
            label="本机对应目录"
            placeholder="/volume1/music"
            required
          />
          <v-select
            v-model="downloaderForm.listen_mode"
            :items="[
              { title: '轮询', value: 'polling' },
              { title: 'qB 回调（预留）', value: 'qb_callback' }
            ]"
            label="监听模式"
          />
          <v-switch v-model="downloaderForm.is_default" color="primary" label="设为默认" hide-details />
          <v-switch v-model="downloaderForm.enabled" color="primary" label="启用" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="downloaderDialog = false">取消</v-btn>
          <v-btn :loading="downloaderTesting" variant="tonal" @click="testDownloader">测试</v-btn>
          <v-btn color="primary" @click="saveDownloader">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="mediaServerDialog" max-width="560">
      <v-card :title="editingMediaServerId ? '编辑音乐库用户' : '新增音乐库用户'">
        <v-card-text class="dialog-stack">
          <v-text-field v-model="mediaServerUserForm.username" label="用户名" autofocus />
          <v-text-field
            v-model="mediaServerUserForm.password"
            label="密码"
            type="password"
            :placeholder="editingMediaServerId ? '留空则保持原密码' : ''"
          />
          <v-switch
            v-model="mediaServerUserForm.enabled"
            color="primary"
            label="启用"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="mediaServerDialog = false">取消</v-btn>
          <v-btn :loading="mediaServerTesting" variant="tonal" @click="testMediaServerUser">测试</v-btn>
          <v-btn color="primary" @click="saveMediaServerUser">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="notifierDialog" max-width="560">
      <v-card :title="editingNotifierId ? '编辑通知' : '新增通知'">
        <v-card-text class="dialog-stack">
          <v-select v-model="notifierForm.type" :items="['telegram']" label="类型" />
          <v-text-field v-model="notifierForm.name" label="名称" />
          <v-text-field
            v-model="notifierForm.bot_token"
            label="Bot Token"
            :placeholder="editingNotifierId ? '留空则保持原 Token' : ''"
          />
          <v-text-field v-model="notifierForm.webhook_url" label="Webhook URL" />
          <v-text-field v-model="notifierForm.chat_ids" label="Chat IDs" />
          <v-switch v-model="notifierForm.use_proxy" color="primary" label="使用系统代理" hide-details />
          <v-switch v-model="notifierForm.enable_download_notify" color="primary" label="下载通知" hide-details />
          <v-switch v-model="notifierForm.enable_library_notify" color="primary" label="媒体库刷新通知" hide-details />
          <v-switch v-model="notifierForm.enabled" color="primary" label="启用" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="notifierDialog = false">取消</v-btn>
          <v-btn :loading="notifierTesting" variant="tonal" @click="testNotifier">测试</v-btn>
          <v-btn color="primary" @click="saveNotifier">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card title="确认删除">
        <v-card-text>
          确定删除{{ deleteTargetLabel(deleteTarget) }}“{{ deleteTarget?.name }}”吗？
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="deleting" @click="deleteDialog = false">取消</v-btn>
          <v-btn color="error" :loading="deleting" @click="confirmDelete">删除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="downloadItemsDialog" max-width="1120">
      <v-card :title="`下载明细${selectedDownloadTask?.name ? ` - ${selectedDownloadTask.name}` : ''}`">
        <v-card-text>
          <v-progress-linear v-if="downloadItemsLoading" indeterminate class="mb-4" />
          <v-table class="fixed-table">
            <thead>
              <tr>
                <th class="download-item-file-col">文件名</th>
                <th class="download-item-size-col">大小</th>
                <th class="download-item-title-col">解析标题</th>
                <th class="download-item-artist-col">任务艺术家</th>
                <th class="download-item-title-col">匹配标题</th>
                <th class="download-item-artist-col">匹配艺术家</th>
                <th class="download-item-album-col">专辑</th>
                <th class="download-item-status-col">状态</th>
                <th class="download-item-error-col">错误</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!downloadTaskItems.length">
                <td colspan="9" class="empty-cell">暂无明细</td>
              </tr>
              <tr v-for="item in downloadTaskItems" :key="item.id">
                <td class="truncate-cell" :title="item.file_path">{{ item.file_name }}</td>
                <td>{{ formatSize(item.size_bytes) }}</td>
                <td class="truncate-cell" :title="item.parsed_title || '-'">{{ item.parsed_title || '-' }}</td>
                <td class="truncate-cell" :title="item.artist || '-'">{{ item.artist || '-' }}</td>
                <td class="truncate-cell" :title="item.metadata_title || '-'">{{ item.metadata_title || '-' }}</td>
                <td class="truncate-cell" :title="item.metadata_artist || '-'">{{ item.metadata_artist || '-' }}</td>
                <td class="truncate-cell" :title="item.metadata_album || '-'">{{ item.metadata_album || '-' }}</td>
                <td>
                  <v-chip
                    :color="downloadTaskItemStatusColor(item.status)"
                    size="small"
                    variant="tonal"
                  >
                    {{ downloadTaskItemStatusText(item.status) }}
                  </v-chip>
                </td>
                <td class="truncate-cell" :title="item.last_error || '-'">{{ item.last_error || '-' }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="downloadItemsDialog = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="downloadDeleteDialog" max-width="420">
      <v-card title="确认删除">
        <v-card-text>
          请选择{{ pendingDownloadDeleteLabel }}的删除方式。
        </v-card-text>
        <v-card-actions class="delete-action-buttons">
          <v-btn
            variant="text"
            :disabled="downloadDeleting"
            @click="downloadDeleteDialog = false"
          >
            取消
          </v-btn>
          <v-spacer />
          <v-btn
            variant="tonal"
            :disabled="downloadDeleting"
            :loading="activeDownloadDeleteMode === 'record_only'"
            @click="confirmDeleteDownloads('record_only')"
          >
            仅删除记录
          </v-btn>
          <v-btn
            color="error"
            :disabled="downloadDeleting"
            :loading="activeDownloadDeleteMode === 'all'"
            @click="confirmDeleteDownloads('all')"
          >
            删除全部
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="mediaDeleteDialog" max-width="520">
      <v-card title="确认删除">
        <v-card-text>
          请选择{{ pendingMediaDeleteLabel || '整理记录' }}的删除方式。
        </v-card-text>
        <v-card-actions class="delete-action-buttons">
          <v-btn
            variant="text"
            :disabled="mediaDeleting"
            @click="mediaDeleteDialog = false"
          >
            取消
          </v-btn>
          <v-spacer />
          <v-btn
            variant="tonal"
            :disabled="mediaDeleting"
            :loading="activeMediaDeleteMode === 'record_only'"
            @click="confirmDeleteMedia('record_only')"
          >
            仅删除记录
          </v-btn>
          <v-btn
            color="warning"
            variant="tonal"
            :disabled="mediaDeleting"
            :loading="activeMediaDeleteMode === 'media_file'"
            @click="confirmDeleteMedia('media_file')"
          >
            删除媒体文件
          </v-btn>
          <v-btn
            color="error"
            :disabled="mediaDeleting"
            :loading="activeMediaDeleteMode === 'all'"
            @click="confirmDeleteMedia('all')"
          >
            删除全部
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="mediaRetryDialog" max-width="400">
      <v-card title="确认重试">
        <v-card-text>确认重试 {{ pendingMediaRetryLabel }} ？</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="mediaRetrying" @click="mediaRetryDialog = false">
            取消
          </v-btn>
          <v-btn color="primary" variant="tonal" :loading="mediaRetrying" @click="confirmRetryMedia">
            确认重试
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="mediaManualDialog" max-width="760">
      <v-card title="手动整理">
        <v-card-text class="dialog-stack">
          <div class="manual-source-path">{{ manualOrganizeTarget?.source_path || '-' }}</div>
          <div class="manual-search-row">
            <v-text-field
              v-model="manualMetadataSearchQuery"
              class="manual-search-input"
              density="comfortable"
              hide-details
              :label="manualOrganizeIsDirectory ? '搜索专辑' : '搜索元数据'"
              prepend-inner-icon="mdi-magnify"
              @keyup.enter="searchManualMetadata"
            />
            <v-btn
              color="primary"
              prepend-icon="mdi-magnify"
              :loading="mediaMetadataSearching"
              @click="searchManualMetadata"
            >
              搜索
            </v-btn>
          </div>
          <div class="manual-metadata-grid">
            <v-text-field
              v-if="!manualOrganizeIsDirectory"
              v-model="manualMetadataForm.title"
              label="标题"
            />
            <v-text-field v-model="manualMetadataForm.artist" label="歌手" />
            <v-text-field v-model="manualMetadataForm.album" label="专辑" />
            <v-text-field
              v-if="!manualOrganizeIsDirectory"
              v-model.number="manualMetadataForm.year"
              label="年份"
              type="number"
            />
            <v-text-field
              v-if="!manualOrganizeIsDirectory"
              v-model.number="manualMetadataForm.track_number"
              label="曲序"
              type="number"
            />
            <v-text-field
              v-if="!manualOrganizeIsDirectory"
              v-model="manualMetadataForm.cover_url"
              label="封面地址"
            />
          </div>
          <v-textarea
            v-if="!manualOrganizeIsDirectory"
            v-model="manualMetadataForm.lyrics"
            auto-grow
            label="歌词"
            rows="5"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="mediaManualSubmitting" @click="mediaManualDialog = false">
            取消
          </v-btn>
          <v-btn color="primary" :loading="mediaManualSubmitting" @click="confirmManualOrganize">
            确认整理
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="mediaMetadataSearchDialog" max-width="920">
      <v-card :title="manualOrganizeIsDirectory ? '选择专辑' : '选择元数据'">
        <v-card-text class="dialog-stack">
          <div class="manual-search-row">
            <v-select
              v-model="manualMetadataSource"
              class="metadata-source-select"
              density="comfortable"
              hide-details
              :items="metadataSourceOptions"
              label="来源"
            />
            <v-text-field
              v-model="manualMetadataSearchQuery"
              class="manual-search-input"
              density="comfortable"
              hide-details
              label="搜索元数据"
              prepend-inner-icon="mdi-magnify"
              @keyup.enter="searchManualMetadata"
            />
            <v-btn
              color="primary"
              prepend-icon="mdi-magnify"
              :loading="mediaMetadataSearching"
              @click="searchManualMetadata"
            >
              搜索
            </v-btn>
          </div>
          <div v-if="mediaMetadataSearching" class="loading-panel">
            <v-progress-circular indeterminate color="primary" size="34" width="3" />
            <span>正在搜索元数据</span>
          </div>
          <div v-else-if="manualMetadataResults.length" class="metadata-result-grid">
            <article
              v-for="item in manualMetadataResults"
              :key="`${item.source || manualMetadataSource}:${item.source_id || item.title}:${item.album || ''}`"
              class="metadata-result-card"
              @click="selectManualMetadata(item)"
            >
              <img
                v-if="item.cover_url"
                class="metadata-result-cover"
                :src="item.cover_url"
                alt=""
              />
              <div class="metadata-result-body">
                <div class="metadata-result-title">{{ item.title || '-' }}</div>
                <div class="metadata-result-meta">{{ item.artist || '未知歌手' }}</div>
                <div class="metadata-result-meta">{{ item.album || '未知专辑' }}</div>
                <div class="metadata-result-tags">
                  <v-chip size="small" variant="tonal">{{ item.year || '-' }}</v-chip>
                  <v-chip size="small" variant="tonal">
                    {{ metadataSourceLabel(item.source || manualMetadataSource) }}
                  </v-chip>
                </div>
                <p v-if="item.lyrics" class="metadata-result-lyrics">{{ item.lyrics }}</p>
              </div>
            </article>
          </div>
          <div v-else class="empty-cell">暂无元数据结果</div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="mediaMetadataSearchDialog = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="fileOrganizeDialog" max-width="460">
      <v-card title="确认整理">
        <v-card-text>
          确定整理{{ pendingFileOrganizeLabel || '选中的项目' }}吗？
          <span v-if="pendingFileOrganizeHasDirectory">目录中的音频文件会批量刮削转移。</span>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="fileOrganizing" @click="fileOrganizeDialog = false">
            取消
          </v-btn>
          <v-btn color="primary" :loading="fileOrganizing" @click="confirmFileOrganize">
            整理
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="fileDeleteDialog" max-width="480">
      <v-card title="确认删除">
        <v-card-text>
          确定删除{{ pendingFileDeleteLabel || '选中的项目' }}吗？
          <span v-if="pendingFileDeleteHasDirectory">目录会被递归删除。</span>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="fileDeleting" @click="fileDeleteDialog = false">
            取消
          </v-btn>
          <v-btn color="error" :loading="fileDeleting" @click="confirmFileDelete">
            删除
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="artistEditDialog" max-width="560">
      <v-card title="编辑歌手">
        <v-card-text class="dialog-stack">
          <v-text-field
            v-model="artistEditForm.name"
            label="歌手名（权威名）"
            autofocus
            @keyup.enter="saveArtistEdit"
          />
          <v-textarea
            v-model="artistEditForm.aliases"
            auto-grow
            label="别名"
            placeholder="一行一个别名"
            rows="6"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="artistEditSaving" @click="artistEditDialog = false">
            取消
          </v-btn>
          <v-btn
            color="primary"
            :disabled="!artistEditForm.name.trim()"
            :loading="artistEditSaving"
            @click="saveArtistEdit"
          >
            保存
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="artistAliasDialog" max-width="460">
      <v-card title="添加别名">
        <v-card-text class="dialog-stack">
          <v-text-field
            v-model="artistAliasForm.alias"
            label="别名"
            placeholder="例如：Jay Chou / G.E.M."
            autofocus
            @keyup.enter="saveArtistAlias"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="artistAliasDialog = false">取消</v-btn>
          <v-btn color="primary" :disabled="!artistAliasForm.alias.trim()" @click="saveArtistAlias">
            保存
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="artistMergeDialog" max-width="480">
      <v-card title="合并歌手">
        <v-card-text class="dialog-stack">
          <p class="mb-2">
            将另一个歌手合并到
            <strong>{{ artistMergeForm.target_name }}</strong> 中。
            被合并歌手的全部别名会转移到目标歌手，被合并歌手删除。
          </p>
          <v-select
            v-model.number="artistMergeForm.source_id"
            :items="artists.filter(a => a.id !== artistMergeForm.target_id).map(a => ({
              title: `${a.name} (${a.aliases.length} 个别名)`,
              value: a.id
            }))"
            label="被合并的歌手"
            item-title="title"
            item-value="value"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="artistMergeDialog = false">取消</v-btn>
          <v-btn
            color="warning"
            :disabled="!artistMergeForm.source_id"
            @click="confirmMergeArtists"
          >
            合并
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="clearArtistDialog" max-width="420">
      <v-card title="清空并重建">
        <v-card-text>
          确定清空并重建歌手库吗？所有手动添加的别名和合并操作会丢失。
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="clearArtistDialog = false">取消</v-btn>
          <v-btn color="warning" :loading="artistBuilding" @click="confirmClearAndRebuildArtistLibrary">
            确定
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top right">
      {{ snackbar.text }}
    </v-snackbar>
  </v-app>
</template>

<style scoped>
.nav-list {
  padding: 4px 12px 16px;
}

.nav-group-divider {
  background: rgba(var(--v-theme-on-surface), 0.14);
  border: 0;
  display: block;
  height: 1px;
  margin: 14px 8px 10px;
  opacity: 1;
}

.nav-group-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 28px;
  min-height: 28px;
  padding-inline-start: 12px !important;
}

.download-toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.download-active-switch {
  flex: 0 0 auto;
  margin-left: auto;
}

.dashboard-metric-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.dashboard-metric-card {
  align-items: center;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  gap: 14px;
  min-height: 118px;
  padding: 18px;
}

.dashboard-metric-icon {
  align-items: center;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 8px;
  display: flex;
  flex: 0 0 48px;
  height: 48px;
  justify-content: center;
  width: 48px;
}

.dashboard-metric-title {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 13px;
  line-height: 18px;
}

.dashboard-metric-value {
  font-size: 30px;
  font-weight: 750;
  line-height: 38px;
}

.dashboard-metric-subtitle {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
  line-height: 18px;
}

.dashboard-panel-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.dashboard-panel {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  min-width: 0;
}

.dashboard-panel-title {
  align-items: center;
  display: flex;
  font-size: 16px;
  font-weight: 700;
  gap: 10px;
  justify-content: space-between;
}

.dashboard-progress-text {
  font-size: 10px;
  font-weight: 700;
}

.dashboard-chip-stack {
  align-items: flex-end;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dashboard-health-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 0 16px 12px;
}

.dashboard-health-grid > div {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 8px;
  padding: 14px;
}

.dashboard-health-value {
  font-size: 26px;
  font-weight: 750;
  line-height: 32px;
}

.dashboard-health-label {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
  line-height: 18px;
}

.dashboard-status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 16px;
}

.delete-action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.config-card {
  overflow: visible !important;
  position: relative;
}

.config-card-title {
  overflow: visible;
  position: relative;
  z-index: 30;
}

.config-card-menu {
  align-items: center;
  display: inline-flex;
  position: relative;
  z-index: 40;
}

.config-card-menu-panel {
  box-shadow: none !important;
  min-width: 72px;
  padding: 2px 0;
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  z-index: 200;
}

.config-card-menu-item {
  background: transparent;
  border: 0;
  color: rgb(var(--v-theme-error));
  cursor: pointer;
  display: block;
  font: inherit;
  font-size: 14px;
  line-height: 20px;
  padding: 6px 14px;
  text-align: left;
  width: 100%;
}

.config-card-menu-item:hover {
  background: rgba(var(--v-theme-error), 0.08);
}

.table-search {
  max-width: 360px;
  min-width: 240px;
}

.status-filter-select {
  max-width: 140px;
  min-width: 110px;
}

.page-size-select {
  max-width: 120px;
  min-width: 96px;
}

.pagination-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: flex-end;
  padding: 12px 16px 16px;
}

.dialog-filter-row {
  margin-bottom: 12px;
}

.dialog-filter-row > * {
  min-width: 160px;
}

.platform-select {
  max-width: 360px;
  min-width: 260px;
}

.playlist-title-cell {
  align-items: center;
  display: flex;
  gap: 12px;
  min-width: 0;
}

.playlist-cover {
  flex: 0 0 44px;
  aspect-ratio: 1;
  border-radius: 6px;
  height: 44px;
  object-fit: cover;
  width: 44px;
}

.playlist-title-text {
  min-width: 0;
}

.playlist-cover-placeholder {
  align-items: center;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.54);
  display: flex;
  justify-content: center;
}

.muted-text {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
  line-height: 18px;
}

.fixed-table :deep(.v-table__wrapper) {
  overflow-x: auto;
}

.fixed-table :deep(table) {
  table-layout: fixed;
}

.fixed-table :deep(th),
.fixed-table :deep(td) {
  white-space: nowrap;
}

.table-actions {
  min-width: 96px;
  white-space: nowrap;
}

.download-item-file-col {
  width: 260px;
}

.download-item-size-col {
  width: 96px;
}

.download-item-title-col {
  width: 170px;
}

.download-item-artist-col,
.download-item-album-col {
  width: 150px;
}

.download-item-status-col {
  width: 100px;
}

.download-item-error-col {
  width: 220px;
}

.playlist-table :deep(table) {
  min-width: 1160px;
}

.playlist-name-col {
  width: 300px;
}

.playlist-platform-col {
  width: 110px;
}

.count-col {
  width: 72px;
}

.status-col {
  width: 96px;
}

.time-col {
  width: 180px;
}

.playlist-action-col {
  min-width: 260px;
  right: 0;
  text-align: center;
  width: 260px;
}

.sticky-action-col,
.sticky-track-col {
  background: rgb(var(--v-theme-surface));
  box-shadow: -1px 0 0 rgba(var(--v-border-color), var(--v-border-opacity));
  position: sticky;
  z-index: 2;
}

.fixed-table :deep(thead) .sticky-action-col,
.fixed-table :deep(thead) .sticky-track-col {
  z-index: 3;
}

.truncate-cell,
.truncate-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.media-table :deep(table) {
  min-width: 1660px;
  table-layout: fixed;
  width: 1660px;
}

.media-table :deep(.v-table__wrapper) {
  overflow-x: auto;
}

.media-table :deep(th),
.media-table :deep(td) {
  overflow: hidden;
  white-space: nowrap;
}

.media-table :deep(.v-data-table__tr) {
  height: 56px;
}

.media-cell-clip {
  max-width: 100%;
  overflow: hidden;
  width: 100%;
}

.media-path-clip {
  height: 40px;
}

.media-remark-clip {
  height: 20px;
}

.media-path-text {
  display: -webkit-box;
  height: 40px;
  line-height: 20px;
  max-height: 40px;
  overflow: hidden;
  overflow-wrap: anywhere;
  width: 100%;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  white-space: pre-line;
  word-break: break-all;
}

.media-remark-text {
  display: block;
  height: 20px;
  line-height: 20px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}

.media-tooltip-text {
  white-space: pre-line;
  word-break: break-all;
}

.manual-source-path {
  background: rgba(var(--v-theme-on-surface), 0.05);
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 13px;
  line-height: 20px;
  overflow-wrap: anywhere;
  padding: 10px 12px;
}

.manual-search-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.manual-search-input {
  flex: 1 1 280px;
  min-width: 220px;
}

.metadata-source-select {
  flex: 0 1 180px;
  min-width: 160px;
}

.manual-metadata-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.metadata-result-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

.metadata-result-card {
  align-items: flex-start;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  gap: 12px;
  min-height: 132px;
  padding: 12px;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.metadata-result-card:hover {
  background: rgba(var(--v-theme-primary), 0.06);
  border-color: rgba(var(--v-theme-primary), 0.45);
}

.metadata-result-cover {
  aspect-ratio: 1;
  border-radius: 6px;
  flex: 0 0 72px;
  object-fit: cover;
  width: 72px;
}

.metadata-result-body {
  min-width: 0;
}

.metadata-result-title {
  font-size: 15px;
  font-weight: 700;
  line-height: 22px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metadata-result-meta {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 13px;
  line-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metadata-result-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.metadata-result-lyrics {
  color: rgba(var(--v-theme-on-surface), 0.62);
  display: -webkit-box;
  font-size: 12px;
  line-height: 18px;
  margin: 8px 0 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.playlist-track-table :deep(table) {
  min-width: 1180px;
}

.track-position-col {
  width: 56px;
}

.track-title-col {
  width: 260px;
}

.track-artist-col,
.track-album-col {
  width: 180px;
}

.track-error-col {
  width: 230px;
}

.sticky-track-library-col {
  right: 214px;
  text-align: center;
  width: 72px;
}

.sticky-track-status-col {
  right: 104px;
  text-align: center;
  width: 110px;
}

.sticky-track-download-col {
  right: 0;
  text-align: center;
  width: 104px;
}

.select-cell {
  width: 48px;
}

.file-breadcrumbs {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 32px;
}

.file-breadcrumb {
  align-items: center;
  background: transparent;
  border: 0;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 14px;
  gap: 4px;
  line-height: 20px;
  padding: 2px 4px;
}

.file-breadcrumb:disabled {
  color: rgba(var(--v-theme-on-surface), 0.72);
  cursor: default;
}

.alias-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.alias-chip {
  max-width: 200px;
}

.file-search {
  max-width: 360px;
  min-width: 240px;
}

.file-root-select {
  max-width: 160px;
  min-width: 140px;
}

.file-row-clickable {
  cursor: pointer;
}

.file-name-cell {
  align-items: center;
  display: flex;
  gap: 10px;
  min-width: 280px;
}

.file-name-button {
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  display: block;
  font: inherit;
  max-width: 560px;
  overflow: hidden;
  padding: 0;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-name-button:disabled {
  cursor: default;
}

.settings-checks {
  margin: 8px 0 16px;
}

.settings-window .card-grid {
  margin-top: 20px;
}

.settings-checks-label {
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 14px;
  margin-bottom: 4px;
}

.settings-checks-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}

.compact-switch {
  --v-input-control-height: 32px;
}

.compact-switch :deep(.v-selection-control) {
  min-height: 32px;
}

.compact-switch :deep(.v-switch__track) {
  height: 18px;
  min-width: 34px;
}

.compact-switch :deep(.v-switch__thumb) {
  height: 14px;
  width: 14px;
}
</style>
