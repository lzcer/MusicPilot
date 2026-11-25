import { api, apiNoContent } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type {
  MediaDeleteMode,
  MediaClearMode,
  MediaFile,
  TrackMetadata,
  MetadataSearchResponse,
  FileEntry,
  FileOrganizeResponse,
  MediaBulkDeleteResponse,
  MediaRetryResponse,
  PageResponse
} from '../../types/musicpilot'

export function createMediaActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    mediaPage,
    mediaPageSize,
    mediaQuery,
    mediaStatusFilter,
    mediaFiles,
    mediaTotal,
    mediaFileIds,
    selectedMediaIds,
    pendingMediaDelete,
    pendingMediaDeleteIds,
    pendingMediaDeleteLabel,
    mediaDeleteDialog,
    pendingMediaClearMode,
    mediaClearDialog,
    mediaClearConfirmDialog,
    mediaClearing,
    mediaDeleteAllConfirmDialog,
    mediaDeleting,
    activeMediaDeleteMode,
    pendingMediaRetryIds,
    pendingMediaRetryLabel,
    mediaRetryDialog,
    manualOrganizeTarget,
    manualMetadataForm,
    manualMetadataSearchQuery,
    manualMetadataSource,
    manualMetadataResults,
    mediaManualDialog,
    fileRootType,
    mediaMetadataSearching,
    mediaMetadataSearchDialog,
    manualOrganizeIsDirectory,
    mediaManualSubmitting,
    filePath,
    mediaRetrying
  } = state

  let listRequestId = 0

  async function loadMedia() {
    const requestId = ++listRequestId
    const params = new URLSearchParams({
      page: String(mediaPage.value),
      page_size: String(mediaPageSize.value)
    })
    const query = actions.trimmedInput(mediaQuery.value)
    if (query) params.set('q', query)
    if (mediaStatusFilter.value) params.set('status', mediaStatusFilter.value)
    const response = await api<PageResponse<MediaFile>>(`/api/media?${params.toString()}`)
    if (requestId !== listRequestId) return
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

  function requestClearMedia(mode: MediaClearMode) {
    pendingMediaClearMode.value = mode
    mediaClearDialog.value = false
    mediaClearConfirmDialog.value = true
  }

  function closeMediaClearConfirm() {
    mediaClearConfirmDialog.value = false
    pendingMediaClearMode.value = null
  }

  async function confirmClearMedia() {
    const mode = pendingMediaClearMode.value
    if (!mode) return
    mediaClearing.value = true
    try {
      const result = await api<MediaBulkDeleteResponse>(`/api/media/clear?mode=${mode}`, {
        method: 'DELETE'
      })
      selectedMediaIds.value = []
      mediaPage.value = 1
      mediaClearDialog.value = false
      mediaClearConfirmDialog.value = false
      pendingMediaClearMode.value = null
      await loadMedia()
      if (result.failures.length) {
        actions.notify(
          `已清空 ${result.deleted_ids.length} 条，失败 ${result.failures.length} 条`,
          'warning'
        )
      } else if (result.not_found_ids.length) {
        actions.notify(
          `已清空 ${result.deleted_ids.length} 条，${result.not_found_ids.length} 条记录已不存在`,
          'warning'
        )
      } else {
        actions.notify(`已清空 ${result.deleted_ids.length} 条整理记录`)
      }
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '整理记录清空失败', 'error')
      await loadMedia()
    } finally {
      mediaClearing.value = false
    }
  }

  function requestDeleteMedia(mode: MediaDeleteMode) {
    if (mode === 'all') {
      mediaDeleteAllConfirmDialog.value = true
      return
    }
    void confirmDeleteMedia(mode)
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
          actions.notify(
            `已删除 ${result.deleted_ids.length} 条，失败 ${result.failures.length} 条`,
            'warning'
          )
        } else if (result.not_found_ids.length) {
          actions.notify(
            `已删除 ${result.deleted_ids.length} 条，${result.not_found_ids.length} 条记录不存在`,
            'warning'
          )
        } else {
          actions.notify(`已删除 ${result.deleted_ids.length} 条整理记录`)
        }
      }
      selectedMediaIds.value = selectedMediaIds.value.filter((id) => !ids.includes(id))
      pendingMediaDelete.value = null
      pendingMediaDeleteIds.value = []
      pendingMediaDeleteLabel.value = ''
      mediaDeleteDialog.value = false
      mediaDeleteAllConfirmDialog.value = false
      await loadMedia()
      if (deletingSingle) {
        actions.notify('整理记录已删除')
      }
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '整理记录删除失败', 'error')
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
    manualMetadataSearchQuery.value =
      [row.title, row.artist].filter(Boolean).join(' ') || row.source_path
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
    const query = actions.trimmedInput(manualMetadataSearchQuery.value)
    if (!query) {
      actions.notify('请输入搜索关键词', 'warning')
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
      const response = await api<MetadataSearchResponse>(
        `/api/media/metadata-search?${params.toString()}`
      )
      manualMetadataResults.value = response.results
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '元数据搜索失败', 'error')
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
    const title = actions.trimmedInput(manualMetadataForm.value.title)
    const artist = actions.trimmedInput(manualMetadataForm.value.artist)
    const album = actions.trimmedInput(manualMetadataForm.value.album)
    if (!manualOrganizeIsDirectory.value && !title) {
      actions.notify('标题不能为空', 'warning')
      return
    }
    if (manualOrganizeIsDirectory.value && (!artist || !album)) {
      actions.notify('歌手和专辑不能为空', 'warning')
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
        lyrics: actions.trimmedInput(form.lyrics) || null,
        cover_url: actions.trimmedInput(form.cover_url) || null,
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
          ? actions.loadFiles(filePath.value)
          : Promise.resolve()
      ])
      actions.notify(`手动整理完成：文件 ${result.source_files}，失败 ${result.failed_files}`)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '手动整理失败', 'error')
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
      actions.notify(`重试完成：${result.source_files} 个文件已处理，${result.failed_files} 个失败`)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '重试失败', 'error')
      await loadMedia()
    } finally {
      mediaRetrying.value = false
    }
  }

  return {
    loadMedia,
    applyMediaFilters,
    deleteMediaFile,
    deleteSelectedMediaFiles,
    requestClearMedia,
    closeMediaClearConfirm,
    confirmClearMedia,
    requestDeleteMedia,
    confirmDeleteMedia,
    retrySingleMedia,
    openManualOrganize,
    openFileManualOrganize,
    searchManualMetadata,
    selectManualMetadata,
    confirmManualOrganize,
    retrySelectedMedia,
    confirmRetryMedia
  }
}
