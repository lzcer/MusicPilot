import { api, apiNoContent } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type {
  SearchResult,
  DownloadTask,
  DownloadResponse,
  DownloadTaskItem,
  DownloadDeleteMode
} from '../../types/musicpilot'

export function createDownloadsActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    pendingDownload,
    downloadSubmitting,
    selectedMedia,
    selectedSiteIds,
    downloads,
    downloadableTaskIds,
    selectedDownloadIds,
    selectedDownloadTask,
    downloadItemsDialog,
    downloadItemsLoading,
    downloadTaskItems,
    pendingDownloadDeleteIds,
    pendingDownloadDeleteLabel,
    downloadDeleteDialog,
    downloadDeleting,
    activeDownloadDeleteMode
  } = state

  async function confirmDownload() {
    if (!pendingDownload.value || downloadSubmitting.value) return
    downloadSubmitting.value = true
    try {
      await addDownload(pendingDownload.value)
      pendingDownload.value = null
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '下载失败', 'error')
      await loadDownloads().catch(() => undefined)
    } finally {
      downloadSubmitting.value = false
    }
  }

  async function addDownload(result: SearchResult) {
    const response = await api<DownloadResponse>('/api/downloads', {
      method: 'POST',
      body: JSON.stringify({
        ...result,
        resource: result,
        media_metadata: selectedMedia.value,
        selected_site_ids: selectedSiteIds.value
      })
    })
    actions.notify(response.status === 'existing' ? '下载任务已存在' : '已发送到默认下载器')
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
      actions.notify(error instanceof Error ? error.message : '下载明细加载失败', 'error')
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
      actions.notify('下载任务已删除')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '下载任务删除失败', 'error')
      await loadDownloads()
    } finally {
      downloadDeleting.value = false
      activeDownloadDeleteMode.value = null
    }
  }

  return {
    confirmDownload,
    addDownload,
    loadDownloads,
    syncSelectedDownloadIds,
    viewDownloadItems,
    deleteDownloadTask,
    deleteSelectedDownloads,
    confirmDeleteDownloads
  }
}
