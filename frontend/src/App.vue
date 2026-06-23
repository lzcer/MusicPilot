<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

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

type DownloadDeleteMode = 'record_only' | 'all'
type MediaDeleteMode = 'record_only' | 'media_file' | 'all'

type MediaFile = {
  id: number
  torrent_hash?: string | null
  source_path: string
  library_path?: string | null
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

type MusicLibraryTrack = {
  id: string
  title: string
  artist?: string | null
  album?: string | null
  duration?: number | null
  size?: number | null
  year?: number | null
}

type Site = {
  id?: string | null
  name: string
  base_url: string
  cookie?: string | null
  user_agent?: string | null
  parser?: ParserConfig
  max_concurrency: number
}

type DownloaderConfig = {
  id?: string | null
  name: string
  type: string
  base_url: string
  username: string
  download_path: string
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
    required_metadata: Array<'album' | 'artist' | 'lyrics'>
    auto_rename: boolean
    auto_classify: boolean
    classify_by: 'artist' | 'album'
    duplicate_handling: 'ignore' | 'overwrite' | 'keep_largest'
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

type DeleteTarget = {
  kind: 'site' | 'downloader' | 'mediaServer' | 'notifier'
  id: string
  name: string
}

type ConfigMenuKind = DeleteTarget['kind']

const loggedIn = ref(false)
const loginLoading = ref(false)
const loginForm = ref({ username: 'admin', password: 'musicpilot' })
const activePage = ref('search')
const settingsTab = ref('downloaders')
const drawer = ref(true)

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
const musicLibraryLoading = ref(false)
let logTimer: number | undefined
let downloadTimer: number | undefined
let metadataSearchStream: EventSource | undefined

const downloads = ref<DownloadTask[]>([])
const selectedDownloadIds = ref<number[]>([])
const mediaFiles = ref<MediaFile[]>([])
const musicLibraryTracks = ref<MusicLibraryTrack[]>([])
const sites = ref<Site[]>([])
const downloaders = ref<DownloaderConfig[]>([])
const mediaServers = ref<MediaServerConfig[]>([])
const notifiers = ref<NotifierConfig[]>([])

const siteDialog = ref(false)
const downloaderDialog = ref(false)
const mediaServerDialog = ref(false)
const notifierDialog = ref(false)
const deleteDialog = ref(false)
const downloadDeleteDialog = ref(false)
const mediaDeleteDialog = ref(false)
const siteTesting = ref(false)
const downloaderTesting = ref(false)
const mediaServerTesting = ref(false)
const notifierTesting = ref(false)
const deleting = ref(false)
const downloadDeleting = ref(false)
const mediaDeleting = ref(false)
const activeDownloadDeleteMode = ref<DownloadDeleteMode | null>(null)
const activeMediaDeleteMode = ref<MediaDeleteMode | null>(null)
const systemSaving = ref(false)
const editingSiteId = ref<string | null>(null)
const editingDownloaderId = ref<string | null>(null)
const editingMediaServerId = ref<string | null>(null)
const editingNotifierId = ref<string | null>(null)

const snackbar = ref({ show: false, color: 'success', text: '' })
const deleteTarget = ref<DeleteTarget | null>(null)
const pendingDownloadDeleteIds = ref<number[]>([])
const pendingDownloadDeleteLabel = ref('')
const pendingMediaDelete = ref<MediaFile | null>(null)
const activeConfigMenu = ref<string | null>(null)

const siteForm = ref({
  name: '',
  base_url: '',
  cookie: '',
  user_agent: '',
  max_concurrency: 2
})

const downloaderForm = ref({
  id: null as string | null,
  name: 'qBittorrent',
  type: 'qbittorrent',
  base_url: '',
  username: '',
  password: '',
  download_path: '',
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
    required_metadata: [],
    auto_rename: false,
    auto_classify: false,
    classify_by: 'artist',
    duplicate_handling: 'ignore'
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

const navItems = [
  { title: '搜索', value: 'search', icon: 'mdi-magnify' },
  { title: '下载', value: 'downloads', icon: 'mdi-download' },
  { title: '整理', value: 'media', icon: 'mdi-music-box-multiple' },
  { title: '音乐库', value: 'musicLibrary', icon: 'mdi-music-circle-outline' },
  { title: '站点', value: 'sites', icon: 'mdi-server-network' },
  { title: '日志', value: 'logs', icon: 'mdi-text-box-search-outline' },
  { title: '设置', value: 'settings', icon: 'mdi-cog-outline' }
]

const pageTitle = computed(() => navItems.find((item) => item.value === activePage.value)?.title ?? 'MusicPilot')

const searchLoading = computed(() => metadataSearchLoading.value || torrentSearchLoading.value)

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

const filteredMusicLibraryTracks = computed(() => {
  const keyword = musicLibraryQuery.value.trim().toLowerCase()
  if (!keyword) return musicLibraryTracks.value
  return musicLibraryTracks.value.filter((track) =>
    [track.title, track.artist, track.album, track.year?.toString()]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(keyword)
  )
})

const musicLibraryStats = computed(() => {
  const albums = new Set<string>()
  const artists = new Set<string>()
  for (const track of musicLibraryTracks.value) {
    const album = track.album?.trim()
    const artist = track.artist?.trim()
    if (album) albums.add(album.toLowerCase())
    if (artist) artists.add(artist.toLowerCase())
  }
  return {
    songs: musicLibraryTracks.value.length,
    albums: albums.size,
    artists: artists.size
  }
})

const downloadableTaskIds = computed(() =>
  downloads.value.map((item) => item.id).filter((id): id is number => typeof id === 'number')
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
    loadSites(),
    loadDownloaders(),
    loadMediaServers(),
    loadNotifiers(),
    loadSystemSettings(),
    loadMedia(),
    loadDownloads(),
    loadLogs()
  ])
  startLogPolling()
  startDownloadPolling()
  subscribeMetadataSiteSearch()
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
  if (page === 'musicLibrary' && !musicLibraryTracks.value.length) {
    void loadMusicLibrary()
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
  const existingIds = new Set(downloadableTaskIds.value)
  selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => existingIds.has(id))
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
  mediaFiles.value = await api<MediaFile[]>('/api/media')
}

function deleteMediaFile(row: MediaFile) {
  pendingMediaDelete.value = row
  mediaDeleteDialog.value = true
}

async function confirmDeleteMedia(mode: MediaDeleteMode) {
  const row = pendingMediaDelete.value
  if (!row) return
  mediaDeleting.value = true
  activeMediaDeleteMode.value = mode
  try {
    await apiNoContent(`/api/media/${row.id}?mode=${mode}`, { method: 'DELETE' })
    pendingMediaDelete.value = null
    mediaDeleteDialog.value = false
    await loadMedia()
    notify('整理记录已删除')
  } catch (error) {
    notify(error instanceof Error ? error.message : '整理记录删除失败', 'error')
    await loadMedia()
  } finally {
    mediaDeleting.value = false
    activeMediaDeleteMode.value = null
  }
}

async function loadMusicLibrary() {
  musicLibraryLoading.value = true
  try {
    musicLibraryTracks.value = await api<MusicLibraryTrack[]>('/api/music-library')
  } catch (error) {
    notify(error instanceof Error ? error.message : '音乐库加载失败', 'error')
  } finally {
    musicLibraryLoading.value = false
  }
}

async function syncMusicLibrary() {
  musicLibraryLoading.value = true
  try {
    musicLibraryTracks.value = await api<MusicLibraryTrack[]>('/api/music-library/sync', {
      method: 'POST'
    })
    notify('音乐库已同步')
  } catch (error) {
    notify(error instanceof Error ? error.message : '音乐库同步失败', 'error')
  } finally {
    musicLibraryLoading.value = false
  }
}

async function loadSites() {
  sites.value = await api<Site[]>('/api/sites')
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

function openNewSiteDialog() {
  editingSiteId.value = null
  siteForm.value = {
    name: '',
    base_url: '',
    cookie: '',
    user_agent: '',
    max_concurrency: 2
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
    max_concurrency: site.max_concurrency
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
    listen_mode: downloader.listen_mode ?? 'polling',
    is_default: downloader.is_default,
    enabled: downloader.enabled
  }
  downloaderDialog.value = true
}

async function testDownloader() {
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

function openDeleteDownloader(downloader: DownloaderConfig) {
  if (!downloader.id) return
  openDeleteDialog({ kind: 'downloader', id: downloader.id, name: downloader.name })
}

async function loadMediaServers() {
  mediaServers.value = await api<MediaServerConfig[]>('/api/settings/media-servers')
}

function openNewMediaServerDialog() {
  editingMediaServerId.value = null
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
  mediaServerDialog.value = true
}

function editMediaServer(server: MediaServerConfig) {
  editingMediaServerId.value = server.id ?? null
  mediaServerForm.value = {
    id: server.id ?? null,
    name: server.name,
    type: server.type,
    base_url: server.base_url,
    api_key: server.api_key,
    username: server.username,
    password: '',
    is_default: server.is_default,
    enabled: server.enabled
  }
  mediaServerDialog.value = true
}

async function testMediaServer() {
  mediaServerTesting.value = true
  try {
    const result = await api<TestResponse>('/api/settings/media-servers/test', {
      method: 'POST',
      body: JSON.stringify(mediaServerForm.value)
    })
    notify(result.message, result.ok ? 'success' : 'error')
  } catch (error) {
    notify(error instanceof Error ? error.message : '媒体服务器测试失败', 'error')
  } finally {
    mediaServerTesting.value = false
  }
}

async function saveMediaServer() {
  const editing = Boolean(editingMediaServerId.value)
  const server = await api<MediaServerConfig>(
    editing
      ? `/api/settings/media-servers/${editingMediaServerId.value}`
      : '/api/settings/media-servers',
    {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify(mediaServerForm.value)
    }
  )
  if (editing) {
    mediaServers.value = mediaServers.value.map((item) => (item.id === server.id ? server : item))
  } else {
    mediaServers.value.push(server)
  }
  mediaServerDialog.value = false
  notify('媒体服务器已保存')
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
    notifier: '通知'
  }[target.kind]
}

function deleteTargetUrl(target: DeleteTarget) {
  return {
    site: `/api/sites/${target.id}`,
    downloader: `/api/settings/downloaders/${target.id}`,
    mediaServer: `/api/settings/media-servers/${target.id}`,
    notifier: `/api/settings/notifiers/${target.id}`
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
    }
  }
}

async function saveSystemSettings() {
  systemSaving.value = true
  try {
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

function mediaRemark(row: MediaFile) {
  return row.remark || row.error_message || '-'
}

function mediaDisplayPath(row: MediaFile) {
  if (row.status === 'failed') return row.source_path
  if (row.status === 'skipped') return '-'
  return row.library_path || '-'
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
        <v-list nav density="compact">
          <v-list-item
            v-for="item in navItems"
            :key="item.value"
            :active="activePage === item.value"
            :prepend-icon="item.icon"
            :title="item.title"
            rounded="lg"
            @click="switchPage(item.value)"
          />
        </v-list>
      </v-navigation-drawer>

      <v-app-bar height="64" flat border>
        <v-app-bar-nav-icon @click="drawer = !drawer" />
        <v-toolbar-title>{{ pageTitle }}</v-toolbar-title>
        <v-spacer />
        <v-btn prepend-icon="mdi-text-box-search-outline" variant="tonal" @click="activePage = 'logs'">
          日志
        </v-btn>
      </v-app-bar>

      <v-main>
        <div class="content">
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
            <div class="toolbar-row">
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
                  <tr v-if="!downloads.length"><td colspan="6" class="empty-cell">暂无下载任务</td></tr>
                  <tr v-for="row in downloads" :key="row.id || row.torrent_hash || row.name">
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
                    <td><v-chip size="small" variant="tonal">{{ row.state }}</v-chip></td>
                    <td><v-progress-linear :model-value="progressPercent(row.progress)" height="8" rounded /></td>
                    <td class="path-cell">{{ row.save_path || '-' }}</td>
                    <td>
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
            </div>
            <v-card>
              <v-table>
                <thead>
                  <tr>
                    <th>标题</th>
                    <th>艺人</th>
                    <th>专辑</th>
                    <th>操作时间</th>
                    <th>状态</th>
                    <th>入库路径</th>
                    <th>备注</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!mediaFiles.length"><td colspan="8" class="empty-cell">暂无整理记录</td></tr>
                  <tr v-for="row in mediaFiles" :key="row.id">
                    <td>{{ row.title || '-' }}</td>
                    <td>{{ row.artist || '-' }}</td>
                    <td>{{ row.album || '-' }}</td>
                    <td>{{ formatTime(row.operation_time) }}</td>
                    <td>
                      <v-chip
                        :color="mediaStatusColor(row.status)"
                        size="small"
                        variant="tonal"
                      >
                        {{ mediaStatusText(row.status) }}
                      </v-chip>
                    </td>
                    <td class="path-cell">{{ mediaDisplayPath(row) }}</td>
                    <td>{{ mediaRemark(row) }}</td>
                    <td>
                      <v-btn
                        icon="mdi-delete"
                        color="error"
                        variant="text"
                        size="small"
                        title="删除整理记录"
                        @click="deleteMediaFile(row)"
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
                class="music-library-search"
              />
            </div>
            <v-card>
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
                  <tr v-if="!filteredMusicLibraryTracks.length">
                    <td colspan="6" class="empty-cell">暂无音乐库记录</td>
                  </tr>
                  <tr v-for="track in filteredMusicLibraryTracks" :key="track.id">
                    <td>{{ track.title || '-' }}</td>
                    <td>{{ track.artist || '-' }}</td>
                    <td>{{ track.album || '-' }}</td>
                    <td>{{ formatDuration(track.duration) }}</td>
                    <td>{{ formatSize(track.size) }}</td>
                    <td>{{ track.year || '-' }}</td>
                  </tr>
                </tbody>
              </v-table>
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
                  <v-chip size="small" variant="tonal">{{ site.max_concurrency }} 并发</v-chip>
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
              <v-tab value="mediaServers">媒体服务器</v-tab>
              <v-tab value="notifiers">通知</v-tab>
              <v-tab value="system">系统设置</v-tab>
            </v-tabs>

            <v-window v-model="settingsTab">
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
                      <v-chip v-if="downloader.is_default" color="success" size="small" variant="tonal">默认</v-chip>
                      <v-chip v-if="!downloader.enabled" color="warning" size="small" variant="tonal">停用</v-chip>
                    </v-card-text>
                  </v-card>
                </div>
              </v-window-item>

              <v-window-item value="mediaServers">
                <div class="toolbar-row">
                  <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewMediaServerDialog">新增媒体服务器</v-btn>
                </div>
                <div class="card-grid">
                  <v-card
                    v-for="server in mediaServers"
                    :key="server.id || server.base_url"
                    class="config-card"
                    @click="editMediaServer(server)"
                  >
                    <v-card-title class="config-card-title d-flex align-center">
                      <span>{{ server.name }}</span>
                      <v-spacer />
                      <div v-if="server.id" class="config-card-menu" @click.stop>
                        <v-btn
                          icon="mdi-dots-vertical"
                          size="small"
                          variant="text"
                          @click.stop="toggleConfigMenu('mediaServer', server.id)"
                        />
                        <v-card
                          v-if="activeConfigMenu === configMenuKey('mediaServer', server.id)"
                          class="config-card-menu-panel"
                          elevation="0"
                          @click.stop
                        >
                          <button class="config-card-menu-item" type="button" @click="openDeleteMediaServer(server)">
                            删除
                          </button>
                        </v-card>
                      </div>
                    </v-card-title>
                    <v-card-text>
                      <div class="muted">{{ server.base_url }}</div>
                      <v-chip size="small" variant="tonal">{{ server.type }}</v-chip>
                      <v-chip v-if="server.is_default" color="success" size="small" variant="tonal">默认</v-chip>
                      <v-chip v-if="!server.enabled" color="warning" size="small" variant="tonal">停用</v-chip>
                    </v-card-text>
                  </v-card>
                </div>
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
                      <div class="settings-checks-label">刮削内容</div>
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

    <v-dialog v-model="siteDialog" max-width="820">
      <v-card :title="editingSiteId ? '编辑站点' : '新增站点'">
        <v-card-text class="dialog-stack">
          <v-text-field v-model="siteForm.name" label="站点名称" />
          <v-text-field v-model="siteForm.base_url" label="站点地址" />
          <v-textarea v-model="siteForm.cookie" label="Cookie" rows="3" />
          <v-text-field v-model="siteForm.user_agent" label="User-Agent" />
          <v-text-field v-model.number="siteForm.max_concurrency" label="最大并发" type="number" />
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
          <v-text-field v-model="downloaderForm.download_path" label="下载目录" placeholder="/downloads/music" />
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
      <v-card :title="editingMediaServerId ? '编辑媒体服务器' : '新增媒体服务器'">
        <v-card-text class="dialog-stack">
          <v-select v-model="mediaServerForm.type" :items="['navidrome']" label="类型" />
          <v-text-field v-model="mediaServerForm.name" label="名称" />
          <v-text-field v-model="mediaServerForm.base_url" label="地址" />
          <v-text-field v-model="mediaServerForm.api_key" label="API Token" />
          <v-text-field v-model="mediaServerForm.username" label="用户名" />
          <v-text-field
            v-model="mediaServerForm.password"
            label="密码"
            type="password"
            :placeholder="editingMediaServerId ? '留空则保持原密码' : ''"
          />
          <v-switch v-model="mediaServerForm.is_default" color="primary" label="设为默认" hide-details />
          <v-switch v-model="mediaServerForm.enabled" color="primary" label="启用" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="mediaServerDialog = false">取消</v-btn>
          <v-btn :loading="mediaServerTesting" variant="tonal" @click="testMediaServer">测试</v-btn>
          <v-btn color="primary" @click="saveMediaServer">保存</v-btn>
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
          请选择整理记录“{{ pendingMediaDelete?.title || pendingMediaDelete?.source_path || '-' }}”的删除方式。
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

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top right">
      {{ snackbar.text }}
    </v-snackbar>
  </v-app>
</template>

<style scoped>
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

.music-library-search {
  max-width: 360px;
  min-width: 240px;
}

.select-cell {
  width: 48px;
}

.settings-checks {
  margin: 8px 0 16px;
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
