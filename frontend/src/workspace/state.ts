import { computed, ref } from 'vue'
import type { WorkspaceActions } from './actions'
import type {
  SearchResult,
  TorrentFile,
  TorrentFileTreeNode,
  SearchSortField,
  SearchSortDirection,
  SearchResultView,
  MediaCandidate,
  DownloadTask,
  DownloadTaskItem,
  DownloadDeleteMode,
  MediaDeleteMode,
  MediaClearMode,
  MediaFile,
  ManualOrganizeTarget,
  TrackMetadata,
  FileEntry,
  FileRootType,
  FileAudioDetail,
  MusicLibraryTrack,
  MusicLibraryStats,
  PlaylistTrackSource,
  PlaylistAddCandidate,
  DashboardSummary,
  SystemTaskStatus,
  SystemTask,
  DashboardMetric,
  Site,
  DownloaderConfig,
  MediaServerConfig,
  NotifierConfig,
  MusicPlatform,
  Playlist,
  PlaylistAvailable,
  PlaylistTrack,
  PlaylistLibrarySyncBinding,
  PlaylistLibrarySyncForm,
  SystemSettings,
  DirectoryMonitorStatus,
  AboutInfo,
  LogEntry,
  LogLevel,
  Artist,
  DeleteTarget
} from '../types/musicpilot'

export function createWorkspaceState(actions: WorkspaceActions) {
  const LOG_LEVEL_OPTIONS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const

  const LOG_LEVEL_SEVERITY: Record<string, number> = {
    DEBUG: 10,
    INFO: 20,
    WARNING: 30,
    ERROR: 40,
    CRITICAL: 50
  }

  const activePage = ref('dashboard')

  const settingsTab = ref('downloaders')
  const settingsLoading = ref(false)
  const settingsErrors = ref<Record<string, string>>({})

  const drawer = ref(true)

  const dashboard = ref<DashboardSummary | null>(null)

  const dashboardLoading = ref(false)

  const searchDialog = ref(false)

  const metadataSearchLoading = ref(false)

  const torrentSearchLoading = ref(false)

  const searchText = ref('')

  const searchArtist = ref('')

  const searchResults = ref<SearchResult[]>([])

  const rawSearchResults = ref<SearchResult[]>([])

  const searchResultView = ref<SearchResultView>('filtered')

  const metadataCandidates = ref<MediaCandidate[]>([])

  const metadataSearchQuery = ref('')

  const metadataSearchArtist = ref('')

  const metadataNextOffset = ref<number | null>(null)

  const metadataHasMore = ref(false)

  const metadataPageLoading = ref(false)

  const metadataPageLoadFailed = ref(false)

  const selectedMedia = ref<MediaCandidate | null>(null)

  const siteConfirmDialog = ref(false)

  const noMetadataDialog = ref(false)

  const selectedSiteIds = ref<string[]>([])

  const selectedAlbumNames = ref<string[]>([])

  const searchStats = ref({ raw_count: 0, filtered_count: 0 })

  const searchProgress = ref({
    completed_sites: 0,
    total_sites: 0,
    active_keywords: [] as string[]
  })

  const hasSearchedTorrents = ref(false)

  const searchSiteFilter = ref('')

  const searchSortField = ref<SearchSortField | ''>('')

  const searchSortDirection = ref<SearchSortDirection>('desc')

  const searchPage = ref(1)

  const searchPageSize = ref(20)

  const pendingDownload = ref<SearchResult | null>(null)

  const downloadSubmitting = ref(false)

  const torrentFiles = ref<TorrentFile[] | null>(null)

  const torrentFilesExpanded = ref(false)

  const torrentFilesLoading = ref(false)

  const torrentFilesError = ref('')

  const collapsedTorrentDirectories = ref(new Set<string>())

  const torrentFilesController = ref<AbortController | null>(null)

  const torrentFileTree = computed(() => {
    const root: TorrentFileTreeNode[] = []
    const directories = new Map<string, Extract<TorrentFileTreeNode, { kind: 'directory' }>>()
    for (const [index, file] of (torrentFiles.value ?? []).entries()) {
      const parts = file.path.split('/').filter(Boolean)
      const name = parts.pop() ?? file.path
      let children = root
      let path = ''
      for (const [depth, part] of parts.entries()) {
        path = path ? `${path}/${part}` : part
        let directory = directories.get(path)
        if (!directory) {
          directory = {
            id: `directory:${path}`,
            kind: 'directory',
            name: part,
            path,
            depth,
            children: []
          }
          directories.set(path, directory)
          children.push(directory)
        }
        children = directory.children
      }
      children.push({
        id: `file:${index}`,
        kind: 'file',
        name,
        path: file.path,
        depth: parts.length,
        size: file.size_bytes
      })
    }
    return root
  })

  const visibleTorrentFileNodes = computed(() => {
    const rows: TorrentFileTreeNode[] = []
    const pending = [...torrentFileTree.value].reverse()
    while (pending.length) {
      const node = pending.pop()!
      rows.push(node)
      if (node.kind === 'directory' && !collapsedTorrentDirectories.value.has(node.id)) {
        for (let index = node.children.length - 1; index >= 0; index -= 1) {
          pending.push(node.children[index])
        }
      }
    }
    return rows
  })

  const logs = ref<LogEntry[]>([])

  const logsLoading = ref(false)

  const logPaused = ref(false)

  const logLevel = ref<LogLevel>('INFO')

  const logQuery = ref('')

  const debugLoggingEnabled = ref(false)

  const debugLoggingLoading = ref(false)

  const musicLibraryQuery = ref('')

  const musicLibraryPage = ref(1)

  const musicLibraryPageSize = ref(20)

  const musicLibraryTotal = ref(0)

  const musicLibraryStats = ref<MusicLibraryStats>({ songs: 0, albums: 0, artists: 0 })

  const musicLibraryLoading = ref(false)

  const logTimer = ref<number | undefined>()

  const downloadTimer = ref<number | undefined>()

  const artistBuildTimer = ref<number | undefined>()

  const directoryMonitorStatusTimer = ref<number | undefined>()

  const systemTaskTimer = ref<number | undefined>()

  const systemTaskRefreshPending = ref(false)

  const metadataSearchStream = ref<EventSource | undefined>()

  const metadataSearchGeneration = ref(0)

  const downloads = ref<DownloadTask[]>([])

  const downloadTaskItems = ref<DownloadTaskItem[]>([])

  const selectedDownloadTask = ref<DownloadTask | null>(null)

  const selectedDownloadIds = ref<number[]>([])

  const downloadActiveOnly = ref(true)

  const systemTasksDialog = ref(false)

  const systemTaskStatus = ref<SystemTaskStatus>('WAIT')

  const systemTasks = ref<SystemTask[]>([])

  const selectedSystemTaskIds = ref<number[]>([])

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

  const manualOrganizeIsDirectory = computed(() => manualOrganizeTarget.value?.kind === 'directory')

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
    { title: '专辑', key: 'album', sortable: false, width: 200 },
    { title: '类型', key: 'operation_type', sortable: false, width: 90 },
    { title: '状态', key: 'status', sortable: false, width: 90 },
    { title: '文件路径', key: 'path', sortable: false, width: 520 },
    { title: '备注', key: 'remark', sortable: false, width: 300 },
    { title: '操作时间', key: 'operation_time', sortable: false, width: 180 },
    { title: '操作', key: 'actions', sortable: false, width: 160, fixed: 'end' as const }
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

  const fileDetailDialog = ref(false)

  const fileDetailLoading = ref(false)

  const fileDetailError = ref('')

  const fileDetail = ref<FileAudioDetail | null>(null)

  const fileDetailRequestId = ref(0)

  const fileDetailCoverSource = computed(() => {
    const cover = fileDetail.value?.cover
    return cover ? `data:${cover.mime_type};base64,${cover.data}` : ''
  })

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

  const locatedPlaylistTrackId = ref<number | null>(null)

  const playlistTrackRequestId = ref(0)

  const siteDialog = ref(false)

  const downloaderDialog = ref(false)

  const mediaServerDialog = ref(false)

  const notifierDialog = ref(false)

  const musicPlatformDialog = ref(false)

  const playlistImportDialog = ref(false)

  const playlistTracksDialog = ref(false)

  const playlistTrackEditDialog = ref(false)

  const libraryPlaylistDialog = ref(false)

  const libraryPlaylistTrack = ref<MusicLibraryTrack | null>(null)

  const libraryPlaylistId = ref<number | null>(null)

  const libraryPlaylistSaving = ref(false)

  const libraryPlaylistDuplicate = ref<PlaylistTrack | null>(null)

  const libraryDeleteTrack = ref<MusicLibraryTrack | null>(null)

  const libraryDeleteDialog = ref(false)

  const libraryDeleting = ref(false)

  const playlistAddDialog = ref(false)

  const playlistAddSource = ref<PlaylistTrackSource['source']>('library')

  const playlistAddQuery = ref('')

  const playlistAddArtist = ref('')

  const playlistAddSearch = ref({ query: '', artist: '' })

  const playlistAddCandidates = ref<PlaylistAddCandidate[]>([])

  const playlistAddPage = ref(1)

  const playlistAddTotal = ref(0)

  const playlistAddNextOffset = ref<number | null>(null)

  const playlistAddLoading = ref(false)

  const playlistAddSearched = ref(false)

  const playlistAddSavingKey = ref<string | null>(null)

  const playlistAddedKeys = ref(new Set<string>())

  const playlistAddDuplicates = ref(new Map<string, PlaylistTrack>())

  const playlistAddDuplicate = ref<PlaylistTrack | null>(null)

  const playlistAddPageSize = 20

  const playlistAddSearchGeneration = ref(0)

  const deleteDialog = ref(false)

  const downloadItemsDialog = ref(false)

  const systemTasksLoading = ref(false)

  const systemTasksInterrupting = ref(false)

  const downloadDeleteDialog = ref(false)

  const mediaDeleteDialog = ref(false)

  const mediaDeleteAllConfirmDialog = ref(false)

  const mediaClearDialog = ref(false)

  const mediaClearConfirmDialog = ref(false)

  const fileOrganizeDialog = ref(false)

  const fileDeleteDialog = ref(false)

  const siteTesting = ref(false)

  const downloaderTesting = ref(false)

  const mediaServerTesting = ref(false)

  const notifierTesting = ref(false)

  const musicPlatformConnecting = ref(false)

  const playlistLoading = ref(false)

  const discoveryPlaylistAddingId = ref<string | null>(null)

  const availablePlaylistLoading = ref(false)

  const playlistTrackLoading = ref(false)

  const playlistTrackEditSaving = ref(false)

  const downloadItemsLoading = ref(false)

  const playlistDownloading = ref(false)

  const playlistLibrarySyncDialog = ref(false)

  const playlistLibrarySyncingIds = ref<number[]>([])

  const playlistLibrarySyncBindings = ref<PlaylistLibrarySyncBinding[]>([])

  const playlistLibrarySyncForm = ref<PlaylistLibrarySyncForm>({
    playlist: null,
    media_server_id: '',
    public: false,
    auto_sync: false
  })

  const playlistTrackEditForm = ref({
    id: 0,
    title: '',
    artist: '',
    album: ''
  })

  const playlistTrackDownloadingIds = ref<number[]>([])

  const playlistPageDownloading = ref(false)

  const deleting = ref(false)

  const downloadDeleting = ref(false)

  const mediaDeleting = ref(false)

  const mediaClearing = ref(false)

  const fileOrganizing = ref(false)

  const fileDeleting = ref(false)

  const activeDownloadDeleteMode = ref<DownloadDeleteMode | null>(null)

  const activeMediaDeleteMode = ref<MediaDeleteMode | null>(null)

  const systemSaving = ref(false)

  const directoryMonitorStatus = ref<DirectoryMonitorStatus>({
    state: 'disabled',
    mode: 'native',
    source_directory: '',
    poll_interval_seconds: 60,
    failed_at: null,
    message: '',
    detail: ''
  })

  const directoryMonitorDialog = ref(false)

  const directoryMonitorDialogContext = ref<'save' | 'failure'>('failure')

  const directoryMonitorDialogMessage = ref('')

  const directoryMonitorPollingAvailable = ref(true)

  const directoryMonitorActionLoading = ref(false)

  const aboutInfo = ref<AboutInfo | null>(null)

  const databaseExporting = ref(false)

  const databaseImporting = ref(false)

  const databaseImportStartDialog = ref(false)

  const databaseImportFileDialog = ref(false)

  const databaseImportSecondConfirm = ref(false)

  const databaseImportDragging = ref(false)

  const databaseImportFile = ref<File | null>(null)

  const databaseImportFileInput = ref<HTMLInputElement | null>(null)

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

  const draggedSiteId = ref<string | null>(null)

  const sitePrioritySaving = ref(false)

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

  const pendingMediaClearMode = ref<MediaClearMode | null>(null)

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
    auth_type: 'cookie' as 'cookie' | 'api_key',
    api_key: '',
    user_agent: '',
    priority: 100,
    max_concurrency: 2,
    use_proxy: false,
    enabled: true
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
    monitor_tag: 'MusicPilot',
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

  const secretMask = '••••••••'

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
      auto_organize: 'downloader',
      directory_monitor_mode: 'native',
      directory_monitor_poll_interval_seconds: 60,
      directory_monitor_notification_delay_seconds: 10,
      mode: 'mapped',
      source_directory: '',
      mapped_directory: '',
      scrape_when_missing: [],
      max_scrape_attempt: false,
      required_metadata: [],
      auto_rename: false,
      auto_classify: false,
      classify_by: 'artist',
      duplicate_handling: 'ignore',
      track_version_control: false
    },
    search: {
      exclude_keywords: '整轨|整軌|WAV|wav',
      minimum_seeders: 1,
      metadata_concurrency: 3
    }
  })

  const scrapingModeOptions = [
    { title: '源文件', value: 'source' },
    { title: '映射文件', value: 'mapped' },
    { title: '复制文件', value: 'copy' }
  ]

  const autoOrganizeOptions = [
    { title: '下载器监听', value: 'downloader' },
    { title: '目录监听', value: 'directory' }
  ]

  const autoOrganizeDescription = computed(() =>
    systemForm.value.scraping.auto_organize === 'directory'
      ? systemForm.value.scraping.directory_monitor_mode === 'polling'
        ? `当前使用轮询监听，每 ${systemForm.value.scraping.directory_monitor_poll_interval_seconds} 秒检查源文件目录，稳定后逐文件触发刮削。`
        : '下载任务到完成即结束；源文件目录的每个新增音乐文件写入稳定后，独立触发现有刮削与整理任务链。'
      : '下载稳定完成后，由下载任务继续触发目录检索、文件整理和曲库刷新。'
  )

  const directoryMonitorFailed = computed(
    () =>
      systemForm.value.scraping.auto_organize === 'directory' &&
      directoryMonitorStatus.value.state === 'failed'
  )

  const scrapingModeDescription = computed(() => {
    switch (systemForm.value.scraping.mode) {
      case 'source':
        return '直接刮削源文件；补充或写入元数据会修改原文件，可能影响做种。'
      case 'copy':
        return '先复制源文件再刮削，源文件不受影响，但会占用两份磁盘空间。'
      default:
        return '源文件满足刮削要求时创建映射；若需补充元数据等不满足映射条件，则自动降级为复制后再刮削。'
    }
  })

  const scrapingRequiredMetadataOptions = [
    { title: '专辑', value: 'album' },
    { title: '艺术家', value: 'artist' },
    { title: '歌词', value: 'lyrics' },
    { title: '封面', value: 'cover' }
  ]

  const scrapingClassifyOptions = [
    { title: '艺术家', value: 'artist' },
    { title: '专辑', value: 'album' },
    { title: '艺术家-专辑', value: 'artist_album' }
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

  const AUDIO_FILE_EXTENSIONS = new Set([
    '.aac',
    '.aiff',
    '.alac',
    '.ape',
    '.flac',
    '.m4a',
    '.mp3',
    '.ogg',
    '.opus',
    '.wav',
    '.wma'
  ])

  const playlistTrackDownloadStatusOptions = [
    { title: '全部下载状态', value: '' },
    { title: '待处理', value: 'pending' },
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
    { title: '发现', value: 'discovery', icon: 'mdi-compass-outline' },
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
      items: navItems.filter((item) =>
        ['playlists', 'musicLibrary', 'artists'].includes(item.value)
      )
    },
    {
      title: '管理',
      items: navItems.filter((item) => ['files', 'sites', 'logs', 'settings'].includes(item.value))
    }
  ]

  const pageTitle = computed(
    () => navItems.find((item) => item.value === activePage.value)?.title ?? 'MusicPilot'
  )

  const searchLoading = computed(() => metadataSearchLoading.value || torrentSearchLoading.value)

  const selectedMediaAlbums = computed(() => actions.albumList(selectedMedia.value))

  const enabledSites = computed(() => sites.value.filter((site) => site.enabled && site.id))

  const enabledSiteIds = computed(
    () => enabledSites.value.map((site) => site.id).filter(Boolean) as string[]
  )

  const selectedEnabledSiteIds = computed(() =>
    selectedSiteIds.value.filter((id) => enabledSiteIds.value.includes(id))
  )

  const canRunMetadataSiteSearch = computed(
    () =>
      selectedEnabledSiteIds.value.length > 0 &&
      (!selectedMediaAlbums.value.length || selectedAlbumNames.value.length > 0)
  )

  const enabledMediaServerOptions = computed(() =>
    mediaServers.value
      .filter((item) => item.enabled && item.id)
      .map((item) => ({
        title: `${item.username || item.name}${item.is_default ? '（默认）' : ''}`,
        subtitle: item.name,
        value: item.id || ''
      }))
  )

  const defaultMediaServer = computed(
    () => mediaServers.value.find((item) => item.is_default) ?? mediaServers.value[0] ?? null
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
    const storage = data.storage
    const hasStorageResult = storage.total_size_bytes != null
    const storageDetails = hasStorageResult
      ? [
          `源文件 ${actions.formatSize(storage.source_size_bytes)}`,
          `膨胀 ${actions.formatSize(storage.expansion_size_bytes)}`
        ]
      : []
    const storageSubtitle =
      storage.status === 'waiting'
        ? '等待后台统计'
        : storage.status === 'error'
          ? hasStorageResult
            ? ''
            : '统计失败'
          : ''
    return [
      {
        title: '歌曲库',
        value: data.library.songs,
        subtitle: `专辑 ${data.library.albums} / 歌手 ${data.library.artists}`,
        icon: 'mdi-music-circle-outline',
        color: 'primary'
      },
      {
        title: '音乐库总体积',
        value: hasStorageResult ? actions.formatSize(storage.total_size_bytes) : '--',
        subtitle: storageSubtitle,
        subtitleLines: storageDetails,
        icon: 'mdi-database-outline',
        color: 'primary',
        help: '膨胀大小是映射目录中复制文件新增的空间，硬链接不会重复计算。使用源文件刮削时为 0。',
        error: storage.status === 'error' ? storage.error || '音乐库体积统计失败' : undefined
      },
      {
        title: '近 7 天新增',
        value: data.library.recent_7d_songs,
        subtitle: `最近同步 ${actions.formatOptionalTime(data.library.last_synced_at)}`,
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

  const torrentSearchConditionText = computed(() => {
    const active = searchProgress.value.active_keywords.length
      ? searchProgress.value.active_keywords.join(' / ')
      : '等待结果'
    if (!searchProgress.value.total_sites) return `搜索中：${active}`
    const siteText = `站点 ${searchProgress.value.completed_sites}/${searchProgress.value.total_sites}`
    return `${siteText} · 搜索中：${active}`
  })

  const displayedSearchResults = computed(() =>
    searchResultView.value === 'raw' ? rawSearchResults.value : searchResults.value
  )

  const resultSiteOptions = computed(() => {
    const names = Array.from(
      new Set(displayedSearchResults.value.map((item) => item.source).filter(Boolean))
    ).sort()
    return [
      { title: '全部站点', value: '' },
      ...names.map((name) => ({ title: name, value: name }))
    ]
  })

  const filteredSearchResults = computed(() => {
    if (!searchSiteFilter.value) return displayedSearchResults.value
    return displayedSearchResults.value.filter((item) => item.source === searchSiteFilter.value)
  })

  const resultSortOptions = [
    { title: '大小', value: 'size' },
    { title: '做种人数', value: 'seeders' },
    { title: '发布时间', value: 'publishedAt' }
  ] satisfies Array<{ title: string; value: SearchSortField }>

  const sortedSearchResults = computed(() => {
    const field = searchSortField.value
    if (!field) return filteredSearchResults.value
    const multiplier = searchSortDirection.value === 'asc' ? 1 : -1
    return [...filteredSearchResults.value].sort((left, right) => {
      if (field === 'size') {
        return (actions.searchResultSize(left) - actions.searchResultSize(right)) * multiplier
      }
      if (field === 'seeders') {
        return (left.seeders - right.seeders) * multiplier
      }
      if (field === 'publishedAt') {
        return (actions.searchResultTime(left) - actions.searchResultTime(right)) * multiplier
      }
      return 0
    })
  })

  const pagedSearchResults = computed(() => {
    const start = (searchPage.value - 1) * searchPageSize.value
    return sortedSearchResults.value.slice(start, start + searchPageSize.value)
  })

  const filteredLogs = computed(() => {
    const keyword = logQuery.value.trim().toLowerCase()
    const minimumSeverity = LOG_LEVEL_SEVERITY[logLevel.value]
    return logs.value.filter((entry) => {
      const levelMatches = (LOG_LEVEL_SEVERITY[entry.level] ?? 0) >= minimumSeverity
      const text =
        `${entry.timestamp} ${entry.category} ${entry.level} ${entry.message}`.toLowerCase()
      return levelMatches && (!keyword || text.includes(keyword))
    })
  })

  const connectedMusicPlatforms = computed(() =>
    musicPlatforms.value.filter((item) => item.status === 'connected')
  )

  const musicPlatformOptions = computed(() =>
    connectedMusicPlatforms.value.map((item) => ({
      title: actions.musicPlatformLabel(item),
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
      ? downloads.value.filter(
          (item) =>
            item.state !== 'library_refreshed' &&
            item.state !== 'library_refresh_skipped' &&
            !(item.state === 'completed' && item.auto_organize_mode === 'directory')
        )
      : downloads.value
  )

  const downloadEmptyText = computed(() =>
    downloadActiveOnly.value ? '暂无活跃下载任务' : '暂无下载任务'
  )

  const downloadableTaskIds = computed(() =>
    filteredDownloads.value
      .map((item) => item.id)
      .filter((id): id is number => typeof id === 'number')
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

  const interruptibleSystemTaskIds = computed(() =>
    systemTasks.value.filter((item) => actions.canInterruptSystemTask(item)).map((item) => item.id)
  )

  const allSystemTasksSelected = computed({
    get: () =>
      interruptibleSystemTaskIds.value.length > 0 &&
      interruptibleSystemTaskIds.value.every((id) => selectedSystemTaskIds.value.includes(id)),
    set: (selected: boolean) => {
      selectedSystemTaskIds.value = selected ? [...interruptibleSystemTaskIds.value] : []
    }
  })

  const someSystemTasksSelected = computed(
    () =>
      selectedSystemTaskIds.value.length > 0 &&
      !interruptibleSystemTaskIds.value.every((id) => selectedSystemTaskIds.value.includes(id))
  )

  const systemTasksDialogTitle = computed(
    () => `队列任务 - ${actions.systemTaskStatusText(systemTaskStatus.value)}`
  )

  const systemTaskInterruptButtonText = computed(() =>
    systemTaskStatus.value === 'SLOW' ? '强制中止选中' : '中断选中'
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

  const downloadablePlaylistTracks = computed(() =>
    playlistTracks.value.filter((track) => actions.canStartPlaylistTrackDownload(track))
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

  const playlistTrackRetryableStatuses = new Set([
    'failed',
    'not_found',
    'deleted',
    'source_directory_not_found'
  ])

  const mediaStatusFilterOptions = [
    { title: '全部', value: '' },
    { title: '成功', value: 'success' },
    { title: '失败', value: 'failed' },
    { title: '跳过', value: 'skipped' }
  ]

  return {
    LOG_LEVEL_OPTIONS,
    LOG_LEVEL_SEVERITY,
    activePage,
    settingsTab,
    settingsLoading,
    settingsErrors,
    drawer,
    dashboard,
    dashboardLoading,
    searchDialog,
    metadataSearchLoading,
    torrentSearchLoading,
    searchText,
    searchArtist,
    searchResults,
    rawSearchResults,
    searchResultView,
    metadataCandidates,
    metadataSearchQuery,
    metadataSearchArtist,
    metadataNextOffset,
    metadataHasMore,
    metadataPageLoading,
    metadataPageLoadFailed,
    selectedMedia,
    siteConfirmDialog,
    noMetadataDialog,
    selectedSiteIds,
    selectedAlbumNames,
    searchStats,
    searchProgress,
    hasSearchedTorrents,
    searchSiteFilter,
    searchSortField,
    searchSortDirection,
    searchPage,
    searchPageSize,
    pendingDownload,
    downloadSubmitting,
    torrentFiles,
    torrentFilesExpanded,
    torrentFilesLoading,
    torrentFilesError,
    collapsedTorrentDirectories,
    torrentFilesController,
    torrentFileTree,
    visibleTorrentFileNodes,
    logs,
    logsLoading,
    logPaused,
    logLevel,
    logQuery,
    debugLoggingEnabled,
    debugLoggingLoading,
    musicLibraryQuery,
    musicLibraryPage,
    musicLibraryPageSize,
    musicLibraryTotal,
    musicLibraryStats,
    musicLibraryLoading,
    logTimer,
    downloadTimer,
    artistBuildTimer,
    directoryMonitorStatusTimer,
    systemTaskTimer,
    systemTaskRefreshPending,
    metadataSearchStream,
    metadataSearchGeneration,
    downloads,
    downloadTaskItems,
    selectedDownloadTask,
    selectedDownloadIds,
    downloadActiveOnly,
    systemTasksDialog,
    systemTaskStatus,
    systemTasks,
    selectedSystemTaskIds,
    mediaFiles,
    mediaQuery,
    mediaPage,
    mediaPageSize,
    mediaTotal,
    selectedMediaIds,
    mediaStatusFilter,
    mediaRetrying,
    mediaRetryDialog,
    pendingMediaRetryIds,
    pendingMediaRetryLabel,
    mediaManualDialog,
    mediaMetadataSearchDialog,
    mediaManualSubmitting,
    mediaMetadataSearching,
    manualOrganizeTarget,
    manualMetadataSearchQuery,
    manualMetadataSource,
    manualMetadataResults,
    manualOrganizeIsDirectory,
    manualMetadataForm,
    mediaTableHeaders,
    fileRootType,
    fileEntries,
    selectedFilePaths,
    filePath,
    fileParent,
    fileRoot,
    fileLoading,
    fileError,
    fileSearchQuery,
    fileDetailDialog,
    fileDetailLoading,
    fileDetailError,
    fileDetail,
    fileDetailRequestId,
    fileDetailCoverSource,
    musicLibraryTracks,
    sites,
    downloaders,
    mediaServers,
    notifiers,
    musicPlatforms,
    playlists,
    availablePlaylists,
    selectedAvailablePlaylistIds,
    selectedPlaylistConnectionId,
    playlistImportUrl,
    selectedPlaylist,
    playlistTracks,
    playlistTrackTitleQuery,
    playlistTrackArtistQuery,
    playlistTrackDownloadStatus,
    playlistTrackLibraryStatus,
    playlistTrackPage,
    playlistTrackPageSize,
    playlistTrackTotal,
    locatedPlaylistTrackId,
    playlistTrackRequestId,
    siteDialog,
    downloaderDialog,
    mediaServerDialog,
    notifierDialog,
    musicPlatformDialog,
    playlistImportDialog,
    playlistTracksDialog,
    playlistTrackEditDialog,
    libraryPlaylistDialog,
    libraryPlaylistTrack,
    libraryPlaylistId,
    libraryPlaylistSaving,
    libraryPlaylistDuplicate,
    libraryDeleteTrack,
    libraryDeleteDialog,
    libraryDeleting,
    playlistAddDialog,
    playlistAddSource,
    playlistAddQuery,
    playlistAddArtist,
    playlistAddSearch,
    playlistAddCandidates,
    playlistAddPage,
    playlistAddTotal,
    playlistAddNextOffset,
    playlistAddLoading,
    playlistAddSearched,
    playlistAddSavingKey,
    playlistAddedKeys,
    playlistAddDuplicates,
    playlistAddDuplicate,
    playlistAddPageSize,
    playlistAddSearchGeneration,
    deleteDialog,
    downloadItemsDialog,
    systemTasksLoading,
    systemTasksInterrupting,
    downloadDeleteDialog,
    mediaDeleteDialog,
    mediaDeleteAllConfirmDialog,
    mediaClearDialog,
    mediaClearConfirmDialog,
    fileOrganizeDialog,
    fileDeleteDialog,
    siteTesting,
    downloaderTesting,
    mediaServerTesting,
    notifierTesting,
    musicPlatformConnecting,
    playlistLoading,
    discoveryPlaylistAddingId,
    availablePlaylistLoading,
    playlistTrackLoading,
    playlistTrackEditSaving,
    downloadItemsLoading,
    playlistDownloading,
    playlistLibrarySyncDialog,
    playlistLibrarySyncingIds,
    playlistLibrarySyncBindings,
    playlistLibrarySyncForm,
    playlistTrackEditForm,
    playlistTrackDownloadingIds,
    playlistPageDownloading,
    deleting,
    downloadDeleting,
    mediaDeleting,
    mediaClearing,
    fileOrganizing,
    fileDeleting,
    activeDownloadDeleteMode,
    activeMediaDeleteMode,
    systemSaving,
    directoryMonitorStatus,
    directoryMonitorDialog,
    directoryMonitorDialogContext,
    directoryMonitorDialogMessage,
    directoryMonitorPollingAvailable,
    directoryMonitorActionLoading,
    aboutInfo,
    databaseExporting,
    databaseImporting,
    databaseImportStartDialog,
    databaseImportFileDialog,
    databaseImportSecondConfirm,
    databaseImportDragging,
    databaseImportFile,
    databaseImportFileInput,
    artists,
    artistQuery,
    artistPage,
    artistPageSize,
    artistTotal,
    artistLoading,
    artistBuilding,
    artistEditDialog,
    artistEditSaving,
    artistEditForm,
    artistAliasDialog,
    artistAliasForm,
    artistMergeDialog,
    artistMergeForm,
    clearArtistDialog,
    editingSiteId,
    draggedSiteId,
    sitePrioritySaving,
    editingDownloaderId,
    editingMediaServerId,
    editingNotifierId,
    snackbar,
    deleteTarget,
    pendingDownloadDeleteIds,
    pendingDownloadDeleteLabel,
    pendingMediaDelete,
    pendingMediaDeleteIds,
    pendingMediaDeleteLabel,
    pendingMediaClearMode,
    pendingFileOrganize,
    pendingFileOrganizePaths,
    pendingFileOrganizeLabel,
    pendingFileOrganizeHasDirectory,
    pendingFileDeleteRootType,
    pendingFileDeletePaths,
    pendingFileDeleteLabel,
    pendingFileDeleteHasDirectory,
    activeConfigMenu,
    siteForm,
    downloaderForm,
    mediaServerForm,
    mediaServerUserForm,
    secretMask,
    notifierForm,
    musicPlatformForm,
    systemForm,
    scrapingModeOptions,
    autoOrganizeOptions,
    autoOrganizeDescription,
    directoryMonitorFailed,
    scrapingModeDescription,
    scrapingRequiredMetadataOptions,
    scrapingClassifyOptions,
    duplicateHandlingOptions,
    fileRootTypeOptions,
    metadataSourceOptions,
    AUDIO_FILE_EXTENSIONS,
    playlistTrackDownloadStatusOptions,
    playlistTrackLibraryStatusOptions,
    navItems,
    navGroups,
    pageTitle,
    searchLoading,
    selectedMediaAlbums,
    enabledSites,
    enabledSiteIds,
    selectedEnabledSiteIds,
    canRunMetadataSiteSearch,
    enabledMediaServerOptions,
    defaultMediaServer,
    mediaServerUserAccounts,
    dashboardMetricCards,
    torrentSearchConditionText,
    displayedSearchResults,
    resultSiteOptions,
    filteredSearchResults,
    resultSortOptions,
    sortedSearchResults,
    pagedSearchResults,
    filteredLogs,
    connectedMusicPlatforms,
    musicPlatformOptions,
    fileBreadcrumbs,
    filteredDownloads,
    downloadEmptyText,
    downloadableTaskIds,
    allDownloadsSelected,
    someDownloadsSelected,
    interruptibleSystemTaskIds,
    allSystemTasksSelected,
    someSystemTasksSelected,
    systemTasksDialogTitle,
    systemTaskInterruptButtonText,
    mediaFileIds,
    mediaPageLength,
    musicLibraryPageLength,
    allMediaSelected,
    someMediaSelected,
    artistPageLength,
    playlistTrackPageLength,
    downloadablePlaylistTracks,
    fileEntryPaths,
    allFilesSelected,
    someFilesSelected,
    playlistTrackRetryableStatuses,
    mediaStatusFilterOptions
  }
}

export type WorkspaceState = ReturnType<typeof createWorkspaceState>
