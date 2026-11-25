import { api, apiNoContent } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type { MusicLibraryTrack, MusicLibraryTrackPageResponse } from '../../types/musicpilot'

export function createLibraryActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    musicLibraryLoading,
    musicLibraryPage,
    musicLibraryPageSize,
    musicLibraryQuery,
    musicLibraryTracks,
    musicLibraryTotal,
    musicLibraryStats,
    libraryPlaylistTrack,
    libraryPlaylistId,
    libraryPlaylistDuplicate,
    libraryPlaylistDialog,
    libraryPlaylistSaving,
    libraryDeleteTrack,
    libraryDeleteDialog,
    libraryDeleting
  } = state

  function fetchMusicLibraryPage(page: number, pageSize: number, query: string) {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (query) params.set('q', query)
    return api<MusicLibraryTrackPageResponse>(`/api/music-library?${params.toString()}`)
  }

  let listRequestId = 0

  async function loadMusicLibrary() {
    const requestId = ++listRequestId
    musicLibraryLoading.value = true
    try {
      const response = await fetchMusicLibraryPage(
        musicLibraryPage.value,
        musicLibraryPageSize.value,
        actions.trimmedInput(musicLibraryQuery.value)
      )
      if (requestId !== listRequestId) return
      applyMusicLibraryResponse(response)
    } catch (error) {
      if (requestId !== listRequestId) return
      actions.notify(error instanceof Error ? error.message : '音乐库加载失败', 'error')
    } finally {
      if (requestId === listRequestId) musicLibraryLoading.value = false
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

  function openLibraryPlaylistDialog(track: MusicLibraryTrack) {
    libraryPlaylistTrack.value = track
    libraryPlaylistId.value = null
    libraryPlaylistDuplicate.value = null
    libraryPlaylistDialog.value = true
    void actions.loadPlaylists()
  }

  async function addLibraryTrackToPlaylist() {
    const track = libraryPlaylistTrack.value
    const playlistId = libraryPlaylistId.value
    if (!track || playlistId === null || libraryPlaylistSaving.value) return
    libraryPlaylistSaving.value = true
    try {
      const result = await actions.appendTrackToPlaylist(playlistId, {
        source: 'library',
        library_track_id: track.id
      })
      if (result.added) {
        libraryPlaylistDialog.value = false
      } else {
        libraryPlaylistDuplicate.value = result.track
      }
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '添加歌曲失败', 'error')
    } finally {
      libraryPlaylistSaving.value = false
    }
  }

  function openLibraryDeleteDialog(track: MusicLibraryTrack) {
    libraryDeleteTrack.value = track
    libraryDeleteDialog.value = true
  }

  async function deleteLibraryTrack() {
    const track = libraryDeleteTrack.value
    if (!track || libraryDeleting.value) return
    libraryDeleting.value = true
    try {
      await apiNoContent(`/api/music-library/${encodeURIComponent(track.id)}`, { method: 'DELETE' })
      libraryDeleteDialog.value = false
      const remainingPages = Math.max(
        1,
        Math.ceil((musicLibraryTotal.value - 1) / musicLibraryPageSize.value)
      )
      musicLibraryPage.value = Math.min(musicLibraryPage.value, remainingPages)
      await loadMusicLibrary()
      actions.notify('已删除音乐库歌曲')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '删除音乐库歌曲失败', 'error')
    } finally {
      libraryDeleting.value = false
    }
  }

  async function syncMusicLibrary() {
    musicLibraryLoading.value = true
    try {
      const params = new URLSearchParams({
        page: String(musicLibraryPage.value),
        page_size: String(musicLibraryPageSize.value)
      })
      const query = actions.trimmedInput(musicLibraryQuery.value)
      if (query) params.set('q', query)
      const response = await api<MusicLibraryTrackPageResponse>(
        `/api/music-library/sync?${params.toString()}`,
        {
          method: 'POST'
        }
      )
      applyMusicLibraryResponse(response)
      actions.notify('音乐库已同步')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '音乐库同步失败', 'error')
    } finally {
      musicLibraryLoading.value = false
    }
  }

  return {
    fetchMusicLibraryPage,
    loadMusicLibrary,
    applyMusicLibraryResponse,
    applyMusicLibraryFilters,
    openLibraryPlaylistDialog,
    addLibraryTrackToPlaylist,
    openLibraryDeleteDialog,
    deleteLibraryTrack,
    syncMusicLibrary
  }
}
