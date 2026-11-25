import { api } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type { PageResponse, Artist } from '../../types/musicpilot'

export function createArtistsActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    artistLoading,
    artistPage,
    artistPageSize,
    artistQuery,
    artists,
    artistTotal,
    artistBuilding,
    clearArtistDialog,
    artistEditForm,
    artistEditDialog,
    artistEditSaving,
    artistAliasForm,
    artistAliasDialog,
    artistMergeForm,
    artistMergeDialog
  } = state

  let listRequestId = 0

  async function loadArtists() {
    const requestId = ++listRequestId
    artistLoading.value = true
    try {
      const params = new URLSearchParams({
        page: String(artistPage.value),
        page_size: String(artistPageSize.value)
      })
      const query = actions.trimmedInput(artistQuery.value)
      if (query) params.set('q', query)
      const response = await api<PageResponse<Artist>>(`/api/artists?${params.toString()}`)
      if (requestId !== listRequestId) return
      artists.value = response.items
      artistTotal.value = response.total
      artistPage.value = response.page
      artistPageSize.value = response.page_size
    } finally {
      if (requestId === listRequestId) artistLoading.value = false
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
      actions.notify('歌手库构建已开始，完成后将通过日志通知')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '构建歌手库失败', 'error')
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
      actions.notify('歌手库已清空，后台重建中…')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '清空重建失败', 'error')
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
      const alias = actions.trimmedInput(line)
      if (!alias || alias === actions.trimmedInput(artistEditForm.value.name) || seen.has(alias))
        continue
      seen.add(alias)
      aliases.push(alias)
    }
    return aliases
  }

  async function saveArtistEdit() {
    const id = artistEditForm.value.id
    const name = actions.trimmedInput(artistEditForm.value.name)
    if (!id || !name) {
      actions.notify('歌手名不能为空', 'warning')
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
      actions.notify('歌手已更新')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '更新歌手失败', 'error')
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
      actions.notify('别名已添加')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '添加别名失败', 'error')
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
      actions.notify(`已合并：${result.name}`)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '合并失败', 'error')
    }
  }

  return {
    loadArtists,
    applyArtistFilters,
    loadArtistBuildStatus,
    buildArtistLibrary,
    clearAndRebuildArtistLibrary,
    confirmClearAndRebuildArtistLibrary,
    openArtistEditDialog,
    artistEditAliases,
    saveArtistEdit,
    openArtistAliasDialog,
    saveArtistAlias,
    openArtistMergeDialog,
    confirmMergeArtists
  }
}
