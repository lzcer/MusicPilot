import { api } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type {
  DiscoveryPlaylistAction,
  PlaylistTrackSource,
  PlaylistAddCandidate,
  MusicPlatform,
  MusicPlatformConnectResponse,
  Playlist,
  PlaylistAvailable,
  PlaylistTrack,
  PlaylistLibrarySyncResponse,
  PlaylistLibrarySyncBinding,
  PageResponse
} from '../../types/musicpilot'

export function createPlaylistsActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    musicPlatforms,
    playlistLoading,
    playlists,
    musicPlatformForm,
    musicPlatformDialog,
    musicPlatformConnecting,
    selectedPlaylistConnectionId,
    playlistImportUrl,
    availablePlaylists,
    selectedAvailablePlaylistIds,
    playlistImportDialog,
    availablePlaylistLoading,
    selectedPlaylist,
    playlistTracks,
    playlistTrackTitleQuery,
    playlistTrackArtistQuery,
    playlistTrackDownloadStatus,
    playlistTrackLibraryStatus,
    playlistTrackPage,
    playlistTrackTotal,
    locatedPlaylistTrackId,
    playlistTracksDialog,
    playlistTrackRequestId,
    playlistTrackLoading,
    playlistTrackPageSize,
    libraryPlaylistDialog,
    playlistAddDialog,
    playlistAddSearchGeneration,
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
    playlistAddedKeys,
    playlistAddDuplicates,
    playlistAddDuplicate,
    playlistAddPageSize,
    playlistAddSavingKey,
    playlistTrackEditForm,
    playlistTrackEditDialog,
    playlistTrackEditSaving,
    playlistLibrarySyncingIds,
    mediaServers,
    playlistLibrarySyncBindings,
    playlistLibrarySyncForm,
    playlistLibrarySyncDialog,
    playlistDownloading,
    playlistTrackDownloadingIds,
    playlistTrackRetryableStatuses,
    playlistPageDownloading,
    downloadablePlaylistTracks,
    discoveryPlaylistAddingId
  } = state

  async function loadMusicPlatforms() {
    musicPlatforms.value = await api<MusicPlatform[]>('/api/music-platforms')
  }

  async function loadPlaylists() {
    playlistLoading.value = true
    try {
      playlists.value = await api<Playlist[]>('/api/playlists')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '歌单加载失败', 'error')
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
      actions.notify('已打开 Spotify 授权页面，完成后请刷新音乐平台列表')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '音乐平台关联失败', 'error')
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
      actions.notify('已打开重新登录页面，完成后请刷新音乐平台列表')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '重新登录失败', 'error')
    }
  }

  function openDeleteMusicPlatform(platform: MusicPlatform) {
    actions.openDeleteDialog({
      kind: 'musicPlatform',
      id: platform.id,
      name: actions.musicPlatformLabel(platform)
    })
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
      actions.notify('请填写歌单链接', 'warning')
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
      actions.notify('歌单解析完成')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '歌单解析失败', 'error')
    } finally {
      availablePlaylistLoading.value = false
    }
  }

  async function loadAvailablePlaylists() {
    if (!selectedPlaylistConnectionId.value) {
      actions.notify('请先选择已关联平台', 'warning')
      return
    }
    availablePlaylistLoading.value = true
    try {
      const params = new URLSearchParams({ connection_id: selectedPlaylistConnectionId.value })
      availablePlaylists.value = await api<PlaylistAvailable[]>(
        `/api/playlists/available?${params}`
      )
      selectedAvailablePlaylistIds.value = []
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '读取平台歌单失败', 'error')
    } finally {
      availablePlaylistLoading.value = false
    }
  }

  async function importSelectedPlaylists() {
    const selectedPreviewTokens = availablePlaylists.value
      .filter(
        (item) =>
          item.import_token && selectedAvailablePlaylistIds.value.includes(item.import_token)
      )
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
        actions.notify('歌单已同步')
      } catch (error) {
        actions.notify(error instanceof Error ? error.message : '歌单同步失败', 'error')
      } finally {
        availablePlaylistLoading.value = false
      }
      return
    }
    const selectedPlatformPlaylistIds = availablePlaylists.value
      .filter(
        (item) =>
          !item.import_token && selectedAvailablePlaylistIds.value.includes(item.external_id)
      )
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
      actions.notify('歌单已同步')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '歌单同步失败', 'error')
    } finally {
      availablePlaylistLoading.value = false
    }
  }

  async function viewPlaylist(playlist: Playlist, trackId: number | null = null) {
    selectedPlaylist.value = playlist
    playlistTracks.value = []
    playlistTrackTitleQuery.value = ''
    playlistTrackArtistQuery.value = ''
    playlistTrackDownloadStatus.value = ''
    playlistTrackLibraryStatus.value = 'all'
    playlistTrackPage.value = 1
    playlistTrackTotal.value = 0
    locatedPlaylistTrackId.value = trackId
    playlistTracksDialog.value = true
    await loadPlaylistTracks(playlist)
  }

  async function loadPlaylistTracks(playlist: Playlist) {
    const requestId = ++playlistTrackRequestId.value
    playlistTrackLoading.value = true
    try {
      const params = new URLSearchParams({
        page: String(playlistTrackPage.value),
        page_size: String(playlistTrackPageSize.value)
      })
      if (locatedPlaylistTrackId.value !== null) {
        params.set('track_id', String(locatedPlaylistTrackId.value))
      } else {
        const titleQuery = actions.trimmedInput(playlistTrackTitleQuery.value)
        const artistQuery = actions.trimmedInput(playlistTrackArtistQuery.value)
        if (titleQuery) params.set('title', titleQuery)
        if (artistQuery) params.set('artist', artistQuery)
        if (playlistTrackDownloadStatus.value) {
          params.set('download_status', playlistTrackDownloadStatus.value)
        }
        if (playlistTrackLibraryStatus.value !== 'all') {
          params.set(
            'exists_in_library',
            playlistTrackLibraryStatus.value === 'yes' ? 'true' : 'false'
          )
        }
      }
      const response = await api<PageResponse<PlaylistTrack>>(
        `/api/playlists/${playlist.id}/tracks?${params.toString()}`
      )
      if (requestId !== playlistTrackRequestId.value) return
      playlistTracks.value = response.items
      playlistTrackTotal.value = response.total
      playlistTrackPage.value = response.page
      playlistTrackPageSize.value = response.page_size
    } catch (error) {
      if (requestId === playlistTrackRequestId.value) {
        actions.notify(error instanceof Error ? error.message : '歌单明细加载失败', 'error')
      }
    } finally {
      if (requestId === playlistTrackRequestId.value) playlistTrackLoading.value = false
    }
  }

  function applyPlaylistTrackFilters() {
    locatedPlaylistTrackId.value = null
    playlistTrackPage.value = 1
    if (selectedPlaylist.value) {
      void loadPlaylistTracks(selectedPlaylist.value)
    }
  }

  async function appendTrackToPlaylist(playlistId: number, payload: PlaylistTrackSource) {
    const result = await api<{ added: boolean; track: PlaylistTrack }>(
      `/api/playlists/${playlistId}/tracks`,
      {
        method: 'POST',
        body: JSON.stringify(payload)
      }
    )
    if (result.added) {
      actions.notify('已加入歌单')
      void loadPlaylists()
      if (playlistTracksDialog.value && selectedPlaylist.value?.id === playlistId) {
        void loadPlaylistTracks(selectedPlaylist.value)
      }
    }
    return result
  }

  function playlistTrackLabel(track: PlaylistTrack) {
    return [track.title, track.artist, track.album].filter(Boolean).join(' · ')
  }

  function locatePlaylistTrack(track: PlaylistTrack) {
    const playlist =
      selectedPlaylist.value?.id === track.playlist_id
        ? selectedPlaylist.value
        : playlists.value.find((item) => item.id === track.playlist_id)
    if (!playlist) {
      actions.notify('找不到该歌单，请刷新后重试', 'warning')
      return
    }
    libraryPlaylistDialog.value = false
    playlistAddDialog.value = false
    void viewPlaylist(playlist, track.id)
  }

  function openPlaylistAddDialog(source: PlaylistTrackSource['source']) {
    ++playlistAddSearchGeneration.value
    playlistAddSource.value = source
    playlistAddQuery.value = ''
    playlistAddArtist.value = ''
    playlistAddSearch.value = { query: '', artist: '' }
    playlistAddCandidates.value = []
    playlistAddPage.value = 1
    playlistAddTotal.value = 0
    playlistAddNextOffset.value = null
    playlistAddLoading.value = false
    playlistAddSearched.value = false
    playlistAddedKeys.value.clear()
    playlistAddDuplicates.value.clear()
    playlistAddDuplicate.value = null
    playlistAddDialog.value = true
    if (source === 'library') searchPlaylistAddCandidates()
  }

  function searchPlaylistAddCandidates() {
    const query = actions.trimmedInput(playlistAddQuery.value)
    const artist = actions.trimmedInput(playlistAddArtist.value)
    if (playlistAddSource.value === 'network' && !query && !artist) return
    playlistAddSearch.value = { query, artist }
    playlistAddCandidates.value = []
    playlistAddNextOffset.value = null
    playlistAddTotal.value = 0
    playlistAddPage.value = 1
    void loadPlaylistAddCandidates()
  }

  async function loadPlaylistAddCandidates(offset = 0) {
    const generation = ++playlistAddSearchGeneration.value
    const { query, artist } = playlistAddSearch.value
    playlistAddLoading.value = true
    playlistAddSearched.value = true
    try {
      if (playlistAddSource.value === 'library') {
        const response = await actions.fetchMusicLibraryPage(
          playlistAddPage.value,
          playlistAddPageSize,
          query
        )
        if (generation !== playlistAddSearchGeneration.value) return
        playlistAddTotal.value = response.total
        playlistAddCandidates.value = response.items.map((track) => ({
          key: track.id,
          title: track.title,
          artist: track.artist,
          album: track.album,
          payload: { source: 'library', library_track_id: track.id }
        }))
      } else {
        const response = await actions.fetchMetadataCandidatePage(query, artist, offset)
        if (generation !== playlistAddSearchGeneration.value) return
        const knownKeys = new Set(playlistAddCandidates.value.map((candidate) => candidate.key))
        for (const track of response.candidates) {
          const key = actions.metadataCandidateGroupKey(track)
          if (knownKeys.has(key)) continue
          knownKeys.add(key)
          playlistAddCandidates.value.push({
            key,
            title: track.title,
            artist: track.artist,
            album: track.album,
            payload: {
              source: 'network',
              provider: track.source,
              external_id: track.external_id,
              title: track.title,
              artist: track.artist,
              album: track.album,
              cover_url: track.cover_url
            }
          })
        }
        playlistAddNextOffset.value = response.has_more ? (response.next_offset ?? null) : null
      }
    } catch (error) {
      if (generation === playlistAddSearchGeneration.value) {
        actions.notify(error instanceof Error ? error.message : '歌曲搜索失败', 'error')
      }
    } finally {
      if (generation === playlistAddSearchGeneration.value) playlistAddLoading.value = false
    }
  }

  async function addPlaylistCandidate(candidate: PlaylistAddCandidate) {
    const playlist = selectedPlaylist.value
    if (!playlist || playlistAddSavingKey.value || playlistAddedKeys.value.has(candidate.key))
      return
    const duplicate = playlistAddDuplicates.value.get(candidate.key)
    if (duplicate) {
      playlistAddDuplicate.value = duplicate
      return
    }
    playlistAddDuplicate.value = null
    playlistAddSavingKey.value = candidate.key
    try {
      const result = await appendTrackToPlaylist(playlist.id, candidate.payload)
      if (result.added) {
        playlistAddedKeys.value.add(candidate.key)
      } else {
        playlistAddDuplicates.value.set(candidate.key, result.track)
        playlistAddDuplicate.value = result.track
      }
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '添加歌曲失败', 'error')
    } finally {
      playlistAddSavingKey.value = null
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
    const title = actions.trimmedInput(form.title)
    if (!playlist || !form.id) return
    if (!title) {
      actions.notify('歌名不能为空', 'warning')
      return
    }
    playlistTrackEditSaving.value = true
    try {
      await api<PlaylistTrack>(`/api/playlists/${playlist.id}/tracks/${form.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title,
          artist: actions.trimmedInput(form.artist) || null,
          album: actions.trimmedInput(form.album) || null
        })
      })
      playlistTrackEditDialog.value = false
      await loadPlaylistTracks(playlist)
      actions.notify('歌单条目已更新')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '歌单条目更新失败', 'error')
    } finally {
      playlistTrackEditSaving.value = false
    }
  }

  async function syncPlaylist(playlist: Playlist) {
    playlistLoading.value = true
    try {
      await api<Playlist>(`/api/playlists/${playlist.id}/sync`, { method: 'POST' })
      await loadPlaylists()
      actions.notify('歌单已同步')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '歌单同步失败', 'error')
    } finally {
      playlistLoading.value = false
    }
  }

  function isPlaylistSyncingToLibrary(playlistId: number) {
    return playlistLibrarySyncingIds.value.includes(playlistId)
  }

  async function openPlaylistLibrarySyncDialog(playlist: Playlist) {
    if (!mediaServers.value.length) {
      await actions.loadMediaServers()
    }
    try {
      playlistLibrarySyncBindings.value = await api<PlaylistLibrarySyncBinding[]>(
        `/api/playlists/${playlist.id}/library-sync-bindings`
      )
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '自动同步配置加载失败', 'error')
      return
    }
    const defaultServer = mediaServers.value.find(
      (item) => item.enabled && item.is_default && item.id
    )
    const firstEnabled = mediaServers.value.find((item) => item.enabled && item.id)
    const mediaServerId = defaultServer?.id || firstEnabled?.id || ''
    const binding = playlistLibrarySyncBindings.value.find(
      (item) => item.media_server_id === mediaServerId
    )
    playlistLibrarySyncForm.value = {
      playlist,
      media_server_id: mediaServerId,
      public: binding?.public ?? false,
      auto_sync: Boolean(binding)
    }
    playlistLibrarySyncDialog.value = true
  }

  function applyPlaylistLibrarySyncBinding(mediaServerId: string) {
    const binding = playlistLibrarySyncBindings.value.find(
      (item) => item.media_server_id === mediaServerId
    )
    playlistLibrarySyncForm.value.public = binding?.public ?? false
    playlistLibrarySyncForm.value.auto_sync = Boolean(binding)
  }

  async function syncPlaylistToLibrary() {
    const playlist = playlistLibrarySyncForm.value.playlist
    if (!playlist) return
    if (isPlaylistSyncingToLibrary(playlist.id)) return
    if (!playlistLibrarySyncForm.value.media_server_id) {
      actions.notify('请选择同步账号', 'warning')
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
            public: playlistLibrarySyncForm.value.public,
            auto_sync: playlistLibrarySyncForm.value.auto_sync
          })
        }
      )
      const actionText = response.mode === 'created' ? '创建' : '更新'
      playlistLibrarySyncDialog.value = false
      playlistLibrarySyncForm.value.playlist = null
      actions.notify(`已${actionText}音乐库歌单：${response.synced_count} 首`)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '同步到音乐库失败', 'error')
    } finally {
      playlistLibrarySyncingIds.value = playlistLibrarySyncingIds.value.filter(
        (id) => id !== playlist.id
      )
    }
  }

  async function downloadPlaylist(playlist: Playlist) {
    playlistDownloading.value = true
    try {
      await api(`/api/playlists/${playlist.id}/download`, { method: 'POST' })
      await Promise.all([loadPlaylists(), actions.loadDownloads()])
      actions.notify('歌单下载任务已开始')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '歌单下载失败', 'error')
    } finally {
      playlistDownloading.value = false
    }
  }

  function isPlaylistTrackDownloading(trackId: number) {
    return playlistTrackDownloadingIds.value.includes(trackId)
  }

  function canStartPlaylistTrackDownload(track: PlaylistTrack) {
    if (track.exists_in_library || isPlaylistTrackDownloading(track.id)) return false
    return (
      track.download_status === 'pending' ||
      playlistTrackRetryableStatuses.has(track.download_status)
    )
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

  async function requestPlaylistTrackDownload(playlist: Playlist, track: PlaylistTrack) {
    await api(`/api/playlists/${playlist.id}/tracks/${track.id}/download`, {
      method: 'POST'
    })
  }

  function markPlaylistTracksQueued(trackIds: number[]) {
    const idSet = new Set(trackIds)
    playlistTracks.value = playlistTracks.value.map((item) =>
      idSet.has(item.id) ? { ...item, download_status: 'queue', last_error: null } : item
    )
  }

  async function downloadPlaylistTrack(track: PlaylistTrack) {
    const playlist = selectedPlaylist.value
    if (!playlist || !canStartPlaylistTrackDownload(track)) return
    playlistTrackDownloadingIds.value = [...playlistTrackDownloadingIds.value, track.id]
    try {
      await requestPlaylistTrackDownload(playlist, track)
      markPlaylistTracksQueued([track.id])
      await Promise.all([loadPlaylistTracks(playlist), actions.loadDownloads()])
      actions.notify('单曲下载任务已开始')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '单曲下载失败', 'error')
    } finally {
      playlistTrackDownloadingIds.value = playlistTrackDownloadingIds.value.filter(
        (id) => id !== track.id
      )
    }
  }

  async function downloadPlaylistTrackPage() {
    const playlist = selectedPlaylist.value
    if (!playlist || playlistPageDownloading.value) return
    const tracks = [...downloadablePlaylistTracks.value]
    if (!tracks.length) {
      actions.notify('当前页没有可下载的单曲', 'warning')
      return
    }
    const trackIds = tracks.map((track) => track.id)
    playlistPageDownloading.value = true
    playlistTrackDownloadingIds.value = Array.from(
      new Set([...playlistTrackDownloadingIds.value, ...trackIds])
    )
    try {
      const results = await Promise.allSettled(
        tracks.map((track) => requestPlaylistTrackDownload(playlist, track))
      )
      const succeededIds = tracks
        .filter((_, index) => results[index].status === 'fulfilled')
        .map((track) => track.id)
      const failedCount = results.length - succeededIds.length
      if (succeededIds.length) {
        markPlaylistTracksQueued(succeededIds)
      }
      await Promise.all([loadPlaylistTracks(playlist), actions.loadDownloads()])
      if (failedCount) {
        actions.notify(
          `本页下载已触发：成功 ${succeededIds.length} 首，失败 ${failedCount} 首`,
          'warning'
        )
      } else {
        actions.notify(`本页下载任务已开始：${succeededIds.length} 首`)
      }
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '本页下载失败', 'error')
    } finally {
      playlistPageDownloading.value = false
      playlistTrackDownloadingIds.value = playlistTrackDownloadingIds.value.filter(
        (id) => !trackIds.includes(id)
      )
    }
  }

  function openDeletePlaylist(playlist: Playlist) {
    actions.openDeleteDialog({ kind: 'playlist', id: playlist.id, name: playlist.name })
  }

  async function addDiscoveryPlaylist(item: DiscoveryPlaylistAction) {
    if (discoveryPlaylistAddingId.value) return
    discoveryPlaylistAddingId.value = item.id
    try {
      const previews = await api<PlaylistAvailable[]>('/api/playlists/parse-url', {
        method: 'POST',
        body: JSON.stringify({ url: item.external_url })
      })
      const importToken = previews[0]?.import_token
      if (!importToken) throw new Error('未读取到可导入的歌单')
      await api('/api/playlists/import-url', {
        method: 'POST',
        body: JSON.stringify({ import_token: importToken })
      })
      await loadPlaylists()
      actions.notify(`已加入歌单：${item.name}`)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '加入歌单失败', 'error')
    } finally {
      discoveryPlaylistAddingId.value = null
    }
  }

  return {
    loadMusicPlatforms,
    loadPlaylists,
    openMusicPlatformDialog,
    connectMusicPlatform,
    reauthorizeMusicPlatform,
    openDeleteMusicPlatform,
    openPlaylistImportDialog,
    importPlaylistUrl,
    loadAvailablePlaylists,
    importSelectedPlaylists,
    viewPlaylist,
    loadPlaylistTracks,
    applyPlaylistTrackFilters,
    appendTrackToPlaylist,
    playlistTrackLabel,
    locatePlaylistTrack,
    openPlaylistAddDialog,
    searchPlaylistAddCandidates,
    loadPlaylistAddCandidates,
    addPlaylistCandidate,
    openPlaylistTrackEditDialog,
    savePlaylistTrackEdit,
    syncPlaylist,
    isPlaylistSyncingToLibrary,
    openPlaylistLibrarySyncDialog,
    applyPlaylistLibrarySyncBinding,
    syncPlaylistToLibrary,
    downloadPlaylist,
    isPlaylistTrackDownloading,
    canStartPlaylistTrackDownload,
    isPlaylistTrackRetry,
    playlistTrackActionIcon,
    playlistTrackActionTitle,
    requestPlaylistTrackDownload,
    markPlaylistTracksQueued,
    downloadPlaylistTrack,
    downloadPlaylistTrackPage,
    openDeletePlaylist,
    addDiscoveryPlaylist
  }
}
