import type {
  SearchResult,
  SearchSortField,
  SearchResultView,
  MediaCandidate,
  DiscoverySongAction,
  DiscoveryAlbumAction,
  DiscoveryPlaylistAction,
  MetadataCandidatePageResponse,
  MetadataSiteSearchStreamPayload,
  DownloadTask,
  DownloadDeleteMode,
  MediaDeleteMode,
  MediaClearMode,
  MediaFile,
  TrackMetadata,
  FileEntry,
  MusicLibraryTrack,
  MusicLibraryTrackPageResponse,
  PlaylistTrackSource,
  PlaylistAddCandidate,
  SystemTaskStatus,
  SystemTask,
  Site,
  DownloaderConfig,
  MediaServerConfig,
  NotifierConfig,
  MusicPlatform,
  Playlist,
  PlaylistTrack,
  SystemSettings,
  DirectoryMonitorErrorDetail,
  Artist,
  DeleteTarget,
  ConfigMenuKind
} from '../types/musicpilot'
export interface WorkspaceActions {
  maskedSecret(configured: boolean): '••••••••' | ''
  submittedSecret(secret: string): string
  updateSecret(current: string, value: string): string
  updateDownloaderPassword(value: string): void
  updateMediaServerPassword(value: string): void
  updateMediaServerUserPassword(value: string): void
  updateNotifierBotToken(value: string): void
  metadataSourceLabel(source?: string | null): string
  downloadCreationTypeText(value: string): '监听创建' | '任务创建'
  toggleSearchSort(field: SearchSortField): void
  selectSearchResultView(view: SearchResultView): void
  searchSortIcon(field: SearchSortField): '' | 'mdi-arrow-up' | 'mdi-arrow-down'
  searchSortTitle(field: SearchSortField): '点击排序' | '正序' | '倒序'
  isActiveSearchSort(field: SearchSortField): boolean
  notify(text: string, color?: string): void
  trimmedInput(value: string | null | undefined): string
  loadAboutInfo(): Promise<void>
  loadSettingsTab(tab: string): Promise<void>
  loadDashboard(silent?: boolean): Promise<void>
  openSystemTasks(status: SystemTaskStatus): Promise<void>
  loadSystemTasks(silent?: boolean): Promise<void>
  startSystemTaskPolling(): void
  stopSystemTaskPolling(): void
  syncSelectedSystemTaskIds(): void
  canInterruptSystemTask(task: SystemTask): boolean
  interruptSystemTask(task: SystemTask): Promise<void>
  interruptSelectedSystemTasks(): Promise<void>
  interruptSystemTasks(ids: number[]): Promise<void>
  runSearch(): Promise<void>
  loadMetadataCandidatePage(offset: number, generation: number): Promise<number>
  fetchMetadataCandidatePage(
    query: string,
    artist: string,
    offset: number
  ): Promise<MetadataCandidatePageResponse>
  mergeMetadataCandidates(incoming: MediaCandidate[]): number
  metadataCandidateGroupKey(candidate: MediaCandidate): string
  loadMoreMetadataCandidates(): Promise<void>
  onMetadataLoadMoreIntersect(isIntersecting: boolean): void
  stopMetadataCandidatePaging(): void
  runDirectSearch(): void
  openDirectSiteSearchConfirm(): Promise<void>
  openSiteConfirm(candidate: MediaCandidate): Promise<void>
  startDiscoverySongSearch(item: DiscoverySongAction): Promise<void>
  startDiscoveryAlbumSearch(item: DiscoveryAlbumAction): Promise<void>
  runMetadataSiteSearch(): Promise<void>
  subscribeMetadataSiteSearch(notifyCompletion: boolean): void
  applyMetadataSearchSnapshot(payload: MetadataSiteSearchStreamPayload): void
  rawMediaCandidate(candidate: MediaCandidate): {
    title: string
    artist: string | null
    album: string | null
    albums: string[]
    release_date: string | null
    cover_url: string | null
    source: string
    external_id: string
    group_key: string | null
  }
  selectedSiteSearchMedia(): {
    title: string
    artist: string | null
    album: string | null
    albums: string[]
    release_date: string | null
    cover_url: string | null
    source: string
    external_id: string
    group_key: string | null
  } | null
  selectAllAlbums(): void
  clearSelectedAlbums(): void
  toggleSelectedAlbum(album: string): void
  mediaSummary(candidate: MediaCandidate): string
  albumList(candidate: MediaCandidate | null): string[]
  viewResult(row: SearchResult): void
  searchResultType(row: SearchResult | null | undefined): string
  searchResultTime(row: SearchResult): number
  searchResultSize(row: SearchResult): number
  openDownloadConfirm(result: SearchResult): void
  toggleTorrentDirectory(id: string): void
  toggleTorrentFiles(): Promise<void>
  switchPage(page: string): void
  confirmDownload(): Promise<void>
  addDownload(result: SearchResult): Promise<void>
  loadDownloads(): Promise<void>
  syncSelectedDownloadIds(): void
  viewDownloadItems(task: DownloadTask): Promise<void>
  deleteDownloadTask(task: DownloadTask): void
  deleteSelectedDownloads(): void
  confirmDeleteDownloads(mode: DownloadDeleteMode): Promise<void>
  loadMedia(): Promise<void>
  applyMediaFilters(): void
  deleteMediaFile(row: MediaFile): void
  deleteSelectedMediaFiles(): void
  requestClearMedia(mode: MediaClearMode): void
  closeMediaClearConfirm(): void
  confirmClearMedia(): Promise<void>
  requestDeleteMedia(mode: MediaDeleteMode): void
  confirmDeleteMedia(mode: MediaDeleteMode): Promise<void>
  retrySingleMedia(row: MediaFile): void
  openManualOrganize(row: MediaFile): void
  openFileManualOrganize(entry: FileEntry): void
  searchManualMetadata(): Promise<void>
  selectManualMetadata(metadata: TrackMetadata): void
  confirmManualOrganize(): Promise<void>
  retrySelectedMedia(): void
  confirmRetryMedia(): Promise<void>
  loadFiles(path?: string): Promise<void>
  openFileEntry(entry: FileEntry): void
  isAudioFile(entry: FileEntry): boolean
  openFileDetail(entry: FileEntry): Promise<void>
  runFileSearch(): void
  clearFileSearch(): void
  openFileOrganize(entry: FileEntry): void
  organizeSelectedFiles(): void
  openFileDelete(entry: FileEntry): void
  deleteSelectedFiles(): void
  confirmFileDelete(): Promise<void>
  confirmFileOrganize(): Promise<void>
  changeFileRootType(value: unknown): void
  fetchMusicLibraryPage(
    page: number,
    pageSize: number,
    query: string
  ): Promise<MusicLibraryTrackPageResponse>
  loadMusicLibrary(): Promise<void>
  applyMusicLibraryResponse(response: MusicLibraryTrackPageResponse): void
  applyMusicLibraryFilters(): void
  openLibraryPlaylistDialog(track: MusicLibraryTrack): void
  addLibraryTrackToPlaylist(): Promise<void>
  openLibraryDeleteDialog(track: MusicLibraryTrack): void
  deleteLibraryTrack(): Promise<void>
  syncMusicLibrary(): Promise<void>
  loadArtists(): Promise<void>
  applyArtistFilters(): void
  loadArtistBuildStatus(): Promise<void>
  buildArtistLibrary(): Promise<void>
  clearAndRebuildArtistLibrary(): Promise<void>
  confirmClearAndRebuildArtistLibrary(): Promise<void>
  openArtistEditDialog(artist: Artist): void
  artistEditAliases(): string[]
  saveArtistEdit(): Promise<void>
  openArtistAliasDialog(artist: Artist): Promise<void>
  saveArtistAlias(): Promise<void>
  openArtistMergeDialog(source: Artist): void
  confirmMergeArtists(): Promise<void>
  loadSites(): Promise<void>
  loadMusicPlatforms(): Promise<void>
  loadPlaylists(): Promise<void>
  openMusicPlatformDialog(): void
  connectMusicPlatform(): Promise<void>
  reauthorizeMusicPlatform(platform: MusicPlatform): Promise<void>
  openDeleteMusicPlatform(platform: MusicPlatform): void
  openPlaylistImportDialog(): void
  importPlaylistUrl(): Promise<void>
  loadAvailablePlaylists(): Promise<void>
  importSelectedPlaylists(): Promise<void>
  viewPlaylist(playlist: Playlist, trackId?: number | null): Promise<void>
  loadPlaylistTracks(playlist: Playlist): Promise<void>
  applyPlaylistTrackFilters(): void
  appendTrackToPlaylist(
    playlistId: number,
    payload: PlaylistTrackSource
  ): Promise<{ added: boolean; track: PlaylistTrack }>
  playlistTrackLabel(track: PlaylistTrack): string
  locatePlaylistTrack(track: PlaylistTrack): void
  openPlaylistAddDialog(source: PlaylistTrackSource['source']): void
  searchPlaylistAddCandidates(): void
  loadPlaylistAddCandidates(offset?: number): Promise<void>
  addPlaylistCandidate(candidate: PlaylistAddCandidate): Promise<void>
  openPlaylistTrackEditDialog(track: PlaylistTrack): void
  savePlaylistTrackEdit(): Promise<void>
  syncPlaylist(playlist: Playlist): Promise<void>
  isPlaylistSyncingToLibrary(playlistId: number): boolean
  openPlaylistLibrarySyncDialog(playlist: Playlist): Promise<void>
  applyPlaylistLibrarySyncBinding(mediaServerId: string): void
  syncPlaylistToLibrary(): Promise<void>
  downloadPlaylist(playlist: Playlist): Promise<void>
  isPlaylistTrackDownloading(trackId: number): boolean
  canStartPlaylistTrackDownload(track: PlaylistTrack): boolean
  isPlaylistTrackRetry(track: PlaylistTrack): boolean
  playlistTrackActionIcon(track: PlaylistTrack): 'mdi-refresh' | 'mdi-download'
  playlistTrackActionTitle(track: PlaylistTrack): '重试' | '下载'
  requestPlaylistTrackDownload(playlist: Playlist, track: PlaylistTrack): Promise<void>
  markPlaylistTracksQueued(trackIds: number[]): void
  downloadPlaylistTrack(track: PlaylistTrack): Promise<void>
  downloadPlaylistTrackPage(): Promise<void>
  openDeletePlaylist(playlist: Playlist): void
  loadLogs(force?: boolean): Promise<void>
  addDiscoveryPlaylist(item: DiscoveryPlaylistAction): Promise<void>
  loadDebugLoggingState(): Promise<void>
  setDebugLoggingEnabled(enabled: boolean | null): Promise<void>
  startLogPolling(): void
  startDownloadPolling(): void
  startArtistBuildPolling(): void
  startDirectoryMonitorStatusPolling(): void
  syncPagePolling(): void
  openNewSiteDialog(): void
  editSite(site: Site): void
  sitePayload(): {
    name: string
    base_url: string
    cookie: string
    auth_type: 'cookie' | 'api_key'
    api_key: string
    user_agent: string
    priority: number
    max_concurrency: number
    use_proxy: boolean
    enabled: boolean
  }
  saveSite(): Promise<void>
  startSiteDrag(site: Site): void
  finishSiteDrag(): void
  dropSite(site: Site): Promise<void>
  openDeleteSite(site: Site): void
  testSite(): Promise<void>
  loadDownloaders(): Promise<void>
  openNewDownloaderDialog(): void
  selectDownloaderType(type: string): void
  editDownloader(downloader: DownloaderConfig): void
  testDownloader(): Promise<void>
  saveDownloader(): Promise<void>
  downloaderPathError(): '' | '下载目录不能为空' | '本机对应目录不能为空'
  openDeleteDownloader(downloader: DownloaderConfig): void
  loadMediaServers(): Promise<void>
  syncMediaServerFormFromDefault(): void
  resetMediaServerForm(): void
  openNewMediaServerUserDialog(): void
  editMediaServerUser(server: MediaServerConfig): void
  mediaServerUserPayload(): {
    id: string | null
    name: string
    type: string
    base_url: string
    api_key: string
    username: string
    password: string
    is_default: boolean
    enabled: boolean
  }
  syncMediaServerUsersToMainConfig(mainServer: MediaServerConfig): Promise<void>
  testMediaServer(): Promise<void>
  mediaServerAddressError(): '' | '音乐库地址不能为空'
  saveMediaServer(): Promise<void>
  testMediaServerUser(): Promise<void>
  saveMediaServerUser(): Promise<void>
  openDeleteMediaServer(server: MediaServerConfig): void
  loadNotifiers(): Promise<void>
  openNewNotifierDialog(): void
  editNotifier(notifier: NotifierConfig): void
  testNotifier(): Promise<void>
  saveNotifier(): Promise<void>
  openDeleteNotifier(notifier: NotifierConfig): void
  openDeleteDialog(target: DeleteTarget): void
  configMenuKey(kind: ConfigMenuKind, id: string): string
  toggleConfigMenu(kind: ConfigMenuKind, id: string): void
  deleteTargetLabel(target: DeleteTarget | null): string
  deleteTargetUrl(target: DeleteTarget): string
  confirmDelete(): Promise<void>
  applySystemSettings(settings: Partial<SystemSettings>): void
  loadSystemSettings(): Promise<void>
  loadDirectoryMonitorStatus(): Promise<void>
  directoryMonitorErrorDetail(error: unknown): DirectoryMonitorErrorDetail | null
  openDirectoryMonitorDialog(
    context: 'save' | 'failure',
    message: string,
    pollingAvailable?: boolean
  ): void
  openDirectoryMonitorFailureDialog(): void
  updateAutoOrganize(value: 'downloader' | 'directory'): void
  saveSystemSettings(): Promise<void>
  retryNativeDirectoryMonitor(): Promise<void>
  useDirectoryMonitorPolling(): Promise<void>
  switchToDownloaderMonitor(): Promise<void>
  exportDatabase(): Promise<void>
  openDatabaseImportStartDialog(): void
  confirmDatabaseImportStart(): void
  selectedDatabaseImportFile(): {
    readonly lastModified: number
    readonly name: string
    readonly webkitRelativePath: string
    readonly size: number
    readonly type: string
    arrayBuffer: () => Promise<ArrayBuffer>
    bytes: () => Promise<Uint8Array<ArrayBuffer>>
    slice: (start?: number, end?: number, contentType?: string) => Blob
    stream: () => ReadableStream<Uint8Array<ArrayBuffer>>
    text: () => Promise<string>
  } | null
  openDatabaseImportFilePicker(): void
  handleDatabaseImportFileChange(event: Event): void
  handleDatabaseImportDrop(event: DragEvent): void
  setDatabaseImportFile(file: File): void
  resetDatabaseImportSelection(): void
  closeDatabaseImportFileDialog(): void
  confirmDatabaseImport(): Promise<void>
  databaseExportFilename(disposition: string): string
  clampInteger(value: number, min: number, max: number, fallback: number): number
  progressPercent(value: number): number
  formatSize(value?: number | null): string
  formatDuration(value?: number | null): string
  formatAudioDuration(value?: number | null): string
  formatAudioBitrate(value?: number | null): string
  formatAudioSampleRate(value?: number | null): string
  formatAudioChannels(value?: number | null): string
  formatTime(value: string): string
  formatOptionalTime(value?: string | null): string
  systemTaskElapsedText(task: SystemTask): string
  musicPlatformLabel(platform: MusicPlatform): string
  playlistPlatformLabel(platform: string): string
  musicPlatformStatusText(status: string): string
  musicPlatformStatusColor(status: string): string
  playlistStatusText(status: string): string
  playlistStatusColor(status: string): string
  downloadStatusText(status: string): string
  downloadStatusColor(status: string): string
  systemTaskStatusText(status: string): string
  systemTaskStatusColor(status: string): string
  systemTaskTypeText(type: string): string
  playlistTrackStatusText(status: string): string
  playlistTrackStatusColor(status: string): string
  downloadTaskItemStatusText(status: string): string
  downloadTaskItemStatusColor(status: string): string
  mediaStatusColor(status: string): 'success' | 'warning' | 'error'
  mediaStatusText(status: string): '失败' | '跳过' | '成功'
  mediaOperationTypeText(type: string | undefined): string
  mediaOperationReason(row: MediaFile): string
  mediaRemark(row: MediaFile): string
  mediaTableRow(item: MediaFile | { raw: MediaFile }): MediaFile
  mediaDisplayPath(row: MediaFile): string
  displayRelativePath(path: string | null | undefined, root: string): string
  pathIsUnderRoot(path: string | null | undefined, root: string): boolean
  normalizeDisplayPath(path: string | null | undefined): string
  logColor(level: string): 'warning' | 'error' | 'secondary' | 'info'
}
