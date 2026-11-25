import { api } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type {
  SearchResult,
  TorrentFile,
  SearchSortField,
  SearchResultView,
  MediaCandidate,
  DiscoverySongAction,
  DiscoveryAlbumAction,
  MetadataCandidatePageResponse,
  MetadataSiteSearchStreamPayload,
  MetadataSiteDonePayload
} from '../../types/musicpilot'

export function createSearchActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    searchSortField,
    searchSortDirection,
    searchPage,
    torrentSearchLoading,
    searchResultView,
    searchText,
    searchArtist,
    metadataSearchGeneration,
    searchDialog,
    metadataSearchLoading,
    metadataPageLoading,
    metadataPageLoadFailed,
    metadataSearchQuery,
    metadataSearchArtist,
    metadataNextOffset,
    metadataHasMore,
    selectedMedia,
    selectedAlbumNames,
    searchResults,
    rawSearchResults,
    metadataCandidates,
    hasSearchedTorrents,
    searchStats,
    searchSiteFilter,
    noMetadataDialog,
    searchProgress,
    selectedSiteIds,
    enabledSiteIds,
    siteConfirmDialog,
    metadataSearchStream,
    canRunMetadataSiteSearch,
    selectedEnabledSiteIds,
    selectedMediaAlbums,
    pendingDownload,
    collapsedTorrentDirectories,
    torrentFilesLoading,
    torrentFiles,
    torrentFilesExpanded,
    torrentFilesController,
    torrentFilesError
  } = state

  function toggleSearchSort(field: SearchSortField) {
    if (searchSortField.value === field) {
      searchSortDirection.value = searchSortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      searchSortField.value = field
      searchSortDirection.value = 'desc'
    }
    searchPage.value = 1
  }

  function selectSearchResultView(view: SearchResultView) {
    if (view === 'raw' && torrentSearchLoading.value) return
    searchResultView.value = view
  }

  function searchSortIcon(field: SearchSortField) {
    if (searchSortField.value !== field) return ''
    return searchSortDirection.value === 'asc' ? 'mdi-arrow-up' : 'mdi-arrow-down'
  }

  function searchSortTitle(field: SearchSortField) {
    if (searchSortField.value !== field) return '点击排序'
    return searchSortDirection.value === 'asc' ? '正序' : '倒序'
  }

  function isActiveSearchSort(field: SearchSortField) {
    return searchSortField.value === field
  }

  async function runSearch() {
    const query = actions.trimmedInput(searchText.value)
    const artist = actions.trimmedInput(searchArtist.value)
    if (!query && !artist) return
    const generation = ++metadataSearchGeneration.value
    searchDialog.value = false
    metadataSearchLoading.value = true
    metadataPageLoading.value = false
    metadataPageLoadFailed.value = false
    metadataSearchQuery.value = query
    metadataSearchArtist.value = artist
    metadataNextOffset.value = null
    metadataHasMore.value = false
    selectedMedia.value = null
    selectedAlbumNames.value = []
    searchResults.value = []
    rawSearchResults.value = []
    searchResultView.value = 'filtered'
    metadataCandidates.value = []
    hasSearchedTorrents.value = false
    searchStats.value = { raw_count: 0, filtered_count: 0 }
    searchSiteFilter.value = ''
    searchPage.value = 1
    try {
      await loadMetadataCandidatePage(0, generation)
      if (generation !== metadataSearchGeneration.value) return
      if (!metadataCandidates.value.length) {
        if (query) {
          noMetadataDialog.value = true
        } else {
          actions.notify('未找到媒体信息', 'warning')
        }
      }
    } catch (error) {
      if (generation !== metadataSearchGeneration.value) return
      actions.notify(error instanceof Error ? error.message : '媒体信息搜索失败', 'error')
    } finally {
      if (generation === metadataSearchGeneration.value) {
        metadataSearchLoading.value = false
      }
    }
  }

  async function loadMetadataCandidatePage(offset: number, generation: number) {
    const response = await fetchMetadataCandidatePage(
      metadataSearchQuery.value,
      metadataSearchArtist.value,
      offset
    )
    if (generation !== metadataSearchGeneration.value) return 0
    const added = mergeMetadataCandidates(response.candidates)
    metadataNextOffset.value = response.next_offset ?? null
    metadataHasMore.value = response.has_more && metadataNextOffset.value !== null
    return added
  }

  function fetchMetadataCandidatePage(query: string, artist: string, offset: number) {
    const params = new URLSearchParams({
      query,
      offset: String(offset)
    })
    if (artist) params.set('artist', artist)
    return api<MetadataCandidatePageResponse>(`/api/metadata/search?${params.toString()}`)
  }

  function mergeMetadataCandidates(incoming: MediaCandidate[]) {
    const byKey = new Map(
      metadataCandidates.value.map((candidate) => [metadataCandidateGroupKey(candidate), candidate])
    )
    let added = 0
    for (const candidate of incoming) {
      const key = metadataCandidateGroupKey(candidate)
      const current = byKey.get(key)
      if (!current) {
        const next = { ...candidate, albums: albumList(candidate) }
        metadataCandidates.value.push(next)
        byKey.set(key, next)
        added += 1
        continue
      }
      const albums = Array.from(new Set([...albumList(current), ...albumList(candidate)]))
      current.albums = albums
      current.album ||= candidate.album || albums[0] || null
      current.cover_url ||= candidate.cover_url || null
      current.release_date ||= candidate.release_date || null
    }
    return added
  }

  function metadataCandidateGroupKey(candidate: MediaCandidate) {
    return candidate.group_key || `${candidate.source}:${candidate.external_id}`
  }

  async function loadMoreMetadataCandidates() {
    const offset = metadataNextOffset.value
    if (
      offset === null ||
      !metadataHasMore.value ||
      metadataSearchLoading.value ||
      metadataPageLoading.value
    ) {
      return
    }
    const generation = metadataSearchGeneration.value
    metadataPageLoading.value = true
    metadataPageLoadFailed.value = false
    let shouldContinue = false
    try {
      const added = await loadMetadataCandidatePage(offset, generation)
      shouldContinue = added === 0 && metadataHasMore.value
    } catch (error) {
      if (generation !== metadataSearchGeneration.value) return
      metadataPageLoadFailed.value = true
      actions.notify(error instanceof Error ? error.message : '更多媒体信息加载失败', 'error')
    } finally {
      if (generation === metadataSearchGeneration.value) {
        metadataPageLoading.value = false
      }
    }
    if (shouldContinue && generation === metadataSearchGeneration.value) {
      await loadMoreMetadataCandidates()
    }
  }

  function onMetadataLoadMoreIntersect(isIntersecting: boolean) {
    if (isIntersecting) {
      void loadMoreMetadataCandidates()
    }
  }

  function stopMetadataCandidatePaging() {
    metadataSearchGeneration.value += 1
    metadataNextOffset.value = null
    metadataHasMore.value = false
    metadataPageLoading.value = false
    metadataPageLoadFailed.value = false
  }

  function runDirectSearch() {
    if (!searchText.value.trim()) return
    stopMetadataCandidatePaging()
    noMetadataDialog.value = false
    metadataCandidates.value = []
    selectedMedia.value = null
    selectedAlbumNames.value = []
    searchResults.value = []
    rawSearchResults.value = []
    searchResultView.value = 'filtered'
    hasSearchedTorrents.value = true
    searchSiteFilter.value = ''
    searchPage.value = 1
    searchStats.value = { raw_count: 0, filtered_count: 0 }
    searchProgress.value = { completed_sites: 0, total_sites: 0, active_keywords: [] }
    torrentSearchLoading.value = true
    const params = new URLSearchParams({ query: searchText.value.trim(), limit: '100' })
    const stream = new EventSource(`/api/search/stream?${params.toString()}`, {
      withCredentials: true
    })

    stream.addEventListener('result', (event) => {
      const result = JSON.parse((event as MessageEvent).data) as SearchResult
      searchResults.value.push(result)
      searchStats.value = {
        raw_count: searchResults.value.length,
        filtered_count: searchResults.value.length
      }
    })

    stream.addEventListener('error', () => {
      stream.close()
      torrentSearchLoading.value = false
    })

    stream.addEventListener('done', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as {
        raw_count?: number
        raw_results?: SearchResult[]
      }
      rawSearchResults.value = payload.raw_results ?? []
      searchStats.value = {
        raw_count: payload.raw_count ?? rawSearchResults.value.length,
        filtered_count: searchResults.value.length
      }
      stream.close()
      torrentSearchLoading.value = false
    })
  }

  async function ensureSearchSites() {
    try {
      await actions.loadSites()
      return true
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '站点加载失败', 'error')
      return false
    }
  }

  async function openDirectSiteSearchConfirm() {
    if (!(await ensureSearchSites())) return
    const title = actions.trimmedInput(searchText.value)
    if (!title) return
    stopMetadataCandidatePaging()
    searchDialog.value = false
    metadataCandidates.value = []
    searchResults.value = []
    rawSearchResults.value = []
    searchResultView.value = 'filtered'
    hasSearchedTorrents.value = false
    searchSiteFilter.value = ''
    searchPage.value = 1
    searchStats.value = { raw_count: 0, filtered_count: 0 }
    searchProgress.value = { completed_sites: 0, total_sites: 0, active_keywords: [] }
    selectedMedia.value = {
      title,
      artist: null,
      album: null,
      albums: [],
      release_date: null,
      cover_url: null,
      source: 'direct',
      external_id: `direct:${title}`
    }
    selectedAlbumNames.value = []
    selectedSiteIds.value = [...enabledSiteIds.value]
    siteConfirmDialog.value = true
  }

  async function openSiteConfirm(candidate: MediaCandidate) {
    if (!(await ensureSearchSites())) return
    const media = rawMediaCandidate(candidate)
    selectedMedia.value = media
    selectedAlbumNames.value = albumList(media)
    selectedSiteIds.value = [...enabledSiteIds.value]
    siteConfirmDialog.value = true
  }

  async function startDiscoverySongSearch(item: DiscoverySongAction) {
    actions.switchPage('search')
    searchText.value = item.name
    searchArtist.value = item.artist_name || ''
    noMetadataDialog.value = false
    if (!(await ensureSearchSites())) return
    await runSearch()
  }

  async function startDiscoveryAlbumSearch(item: DiscoveryAlbumAction) {
    actions.switchPage('search')
    stopMetadataCandidatePaging()
    metadataSearchStream.value?.close()
    metadataSearchStream.value = undefined
    metadataSearchLoading.value = false
    torrentSearchLoading.value = false
    searchDialog.value = false
    noMetadataDialog.value = false
    searchText.value = item.album_name
    searchArtist.value = item.artist_name || ''
    metadataSearchQuery.value = item.album_name
    metadataSearchArtist.value = item.artist_name || ''
    metadataCandidates.value = []
    searchResults.value = []
    rawSearchResults.value = []
    searchResultView.value = 'filtered'
    hasSearchedTorrents.value = false
    searchSiteFilter.value = ''
    searchPage.value = 1
    searchStats.value = { raw_count: 0, filtered_count: 0 }
    searchProgress.value = { completed_sites: 0, total_sites: 0, active_keywords: [] }
    selectedMedia.value = {
      title: item.name,
      artist: item.artist_name || null,
      album: item.album_name,
      albums: [item.album_name],
      release_date: item.release_date || null,
      cover_url: item.artwork_url || null,
      source: 'apple_music',
      external_id: item.id
    }
    selectedAlbumNames.value = [item.album_name]
    if (!(await ensureSearchSites())) return
    selectedSiteIds.value = [...enabledSiteIds.value]
    siteConfirmDialog.value = true
  }

  async function runMetadataSiteSearch() {
    if (!selectedMedia.value || !canRunMetadataSiteSearch.value) return
    const siteIds = selectedEnabledSiteIds.value
    stopMetadataCandidatePaging()
    siteConfirmDialog.value = false
    torrentSearchLoading.value = true
    metadataCandidates.value = []
    searchResults.value = []
    rawSearchResults.value = []
    searchResultView.value = 'filtered'
    hasSearchedTorrents.value = true
    searchSiteFilter.value = ''
    searchPage.value = 1
    searchStats.value = { raw_count: 0, filtered_count: 0 }
    searchProgress.value = { completed_sites: 0, total_sites: siteIds.length, active_keywords: [] }
    try {
      const snapshot = await api<MetadataSiteSearchStreamPayload>(
        '/api/search/by-metadata/stream/start',
        {
          method: 'POST',
          body: JSON.stringify({
            media: selectedSiteSearchMedia(),
            site_ids: siteIds,
            limit: 100
          })
        }
      )
      applyMetadataSearchSnapshot(snapshot)
      subscribeMetadataSiteSearch(true)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '站点搜索失败', 'error')
      torrentSearchLoading.value = false
    }
  }

  function subscribeMetadataSiteSearch(notifyCompletion: boolean) {
    metadataSearchStream.value?.close()
    metadataSearchStream.value = new EventSource('/api/search/by-metadata/stream/current', {
      withCredentials: true
    })

    metadataSearchStream.value.addEventListener('snapshot', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteSearchStreamPayload
      applyMetadataSearchSnapshot(payload)
    })

    metadataSearchStream.value.addEventListener('progress', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteSearchStreamPayload
      applyMetadataSearchSnapshot(payload)
    })

    metadataSearchStream.value.addEventListener('site_done', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteDonePayload
      for (const message of payload.errors ?? []) {
        actions.notify(`${payload.site} 搜索提示：${message}`, 'warning')
      }
    })

    metadataSearchStream.value.addEventListener('site_error', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { site: string; message: string }
      actions.notify(`${payload.site} 搜索失败：${payload.message}`, 'warning')
    })

    metadataSearchStream.value.addEventListener('done', (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as MetadataSiteSearchStreamPayload
      applyMetadataSearchSnapshot(payload)
      torrentSearchLoading.value = false
      metadataSearchStream.value?.close()
      metadataSearchStream.value = undefined
      if (notifyCompletion && !searchResults.value.length && (payload.raw_count ?? 0) > 0) {
        actions.notify('未找到资源', 'warning')
      }
    })

    metadataSearchStream.value.addEventListener('error', () => {
      torrentSearchLoading.value = false
      metadataSearchStream.value?.close()
      metadataSearchStream.value = undefined
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
      selectedAlbumNames.value = albumList(payload.media)
    }
    if (payload.results) {
      searchResults.value = payload.results
    }
    if (payload.done && payload.raw_results) {
      rawSearchResults.value = payload.raw_results
    }
    hasSearchedTorrents.value =
      hasSearchedTorrents.value || Boolean(payload.results?.length) || Boolean(payload.total_sites)
    torrentSearchLoading.value = !(payload.done ?? false)
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
      external_id: candidate.external_id,
      group_key: candidate.group_key ?? null
    }
  }

  function selectedSiteSearchMedia() {
    if (!selectedMedia.value) return null
    const media = rawMediaCandidate(selectedMedia.value)
    const albums = albumList(selectedMedia.value)
    if (!albums.length) return media
    const selectedAlbums = selectedAlbumNames.value.filter((album) => albums.includes(album))
    return {
      ...media,
      album: selectedAlbums[0] ?? null,
      albums: selectedAlbums
    }
  }

  function selectAllAlbums() {
    selectedAlbumNames.value = [...selectedMediaAlbums.value]
  }

  function clearSelectedAlbums() {
    selectedAlbumNames.value = []
  }

  function toggleSelectedAlbum(album: string) {
    selectedAlbumNames.value = selectedAlbumNames.value.includes(album)
      ? selectedAlbumNames.value.filter((item) => item !== album)
      : [...selectedAlbumNames.value, album]
  }

  function mediaSummary(candidate: MediaCandidate) {
    const count = albumList(candidate).length
    return `${candidate.artist || '-'} - ${candidate.title}${count ? ` / ${count} 个专辑` : ''}`
  }

  function albumList(candidate: MediaCandidate | null) {
    if (!candidate) return []
    const values = candidate.albums?.length
      ? candidate.albums
      : candidate.album
        ? [candidate.album]
        : []
    return Array.from(new Set(values.filter(Boolean)))
  }

  function viewResult(row: SearchResult) {
    if (!row.details_url) {
      actions.notify('没有详情页地址', 'warning')
      return
    }
    window.open(row.details_url, '_blank', 'noopener,noreferrer')
  }

  function searchResultType(row: SearchResult | null | undefined) {
    const value = row?.metadata?.type
    if (typeof value === 'string') return value.trim()
    if (Array.isArray(value)) {
      return value
        .map((item) => String(item).trim())
        .filter(Boolean)
        .join(' / ')
    }
    return ''
  }

  function searchResultTime(row: SearchResult) {
    if (!row.published_at) return 0
    const normalized = row.published_at.replace(/^(\d{4}-\d{2}-\d{2})\s+/, '$1T')
    const timestamp = Date.parse(normalized)
    return Number.isNaN(timestamp) ? 0 : timestamp
  }

  function searchResultSize(row: SearchResult) {
    return row.size_bytes ?? 0
  }

  function openDownloadConfirm(result: SearchResult) {
    pendingDownload.value = result
  }

  function toggleTorrentDirectory(id: string) {
    const collapsed = collapsedTorrentDirectories.value
    if (collapsed.has(id)) collapsed.delete(id)
    else collapsed.add(id)
  }

  async function toggleTorrentFiles() {
    const result = pendingDownload.value
    if (!result || torrentFilesLoading.value) return
    if (torrentFiles.value !== null) {
      torrentFilesExpanded.value = !torrentFilesExpanded.value
      return
    }
    const controller = new AbortController()
    torrentFilesController.value = controller
    torrentFilesLoading.value = true
    torrentFilesError.value = ''
    try {
      const files = await api<TorrentFile[]>('/api/search/torrent-files', {
        method: 'POST',
        body: JSON.stringify({ source: result.source, download_url: result.download_url }),
        signal: controller.signal
      })
      if (!controller.signal.aborted) {
        torrentFiles.value = files
        torrentFilesExpanded.value = true
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        torrentFilesError.value =
          error instanceof Error ? error.message : '文件列表加载失败，请重试'
      }
    } finally {
      if (torrentFilesController.value === controller) {
        torrentFilesController.value = null
        torrentFilesLoading.value = false
      }
    }
  }

  return {
    toggleSearchSort,
    selectSearchResultView,
    searchSortIcon,
    searchSortTitle,
    isActiveSearchSort,
    runSearch,
    loadMetadataCandidatePage,
    fetchMetadataCandidatePage,
    mergeMetadataCandidates,
    metadataCandidateGroupKey,
    loadMoreMetadataCandidates,
    onMetadataLoadMoreIntersect,
    stopMetadataCandidatePaging,
    runDirectSearch,
    openDirectSiteSearchConfirm,
    openSiteConfirm,
    startDiscoverySongSearch,
    startDiscoveryAlbumSearch,
    runMetadataSiteSearch,
    subscribeMetadataSiteSearch,
    applyMetadataSearchSnapshot,
    rawMediaCandidate,
    selectedSiteSearchMedia,
    selectAllAlbums,
    clearSelectedAlbums,
    toggleSelectedAlbum,
    mediaSummary,
    albumList,
    viewResult,
    searchResultType,
    searchResultTime,
    searchResultSize,
    openDownloadConfirm,
    toggleTorrentDirectory,
    toggleTorrentFiles
  }
}
