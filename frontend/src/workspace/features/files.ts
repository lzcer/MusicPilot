import { api } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type {
  FileEntry,
  FileListResponse,
  FileAudioDetail,
  FileOrganizeEnqueueResponse,
  FileBulkDeleteResponse
} from '../../types/musicpilot'

export function createFilesActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    filePath,
    fileLoading,
    fileError,
    fileSearchQuery,
    fileRootType,
    fileEntries,
    fileParent,
    fileRoot,
    fileEntryPaths,
    selectedFilePaths,
    AUDIO_FILE_EXTENSIONS,
    fileDetailRequestId,
    fileDetail,
    fileDetailError,
    fileDetailLoading,
    fileDetailDialog,
    pendingFileOrganize,
    pendingFileOrganizePaths,
    pendingFileOrganizeLabel,
    pendingFileOrganizeHasDirectory,
    fileOrganizeDialog,
    pendingFileDeleteRootType,
    pendingFileDeletePaths,
    pendingFileDeleteLabel,
    pendingFileDeleteHasDirectory,
    fileDeleteDialog,
    fileDeleting,
    fileOrganizing
  } = state

  let listRequestId = 0

  async function loadFiles(path = filePath.value) {
    const requestId = ++listRequestId
    fileLoading.value = true
    fileError.value = ''
    try {
      const search = actions.trimmedInput(fileSearchQuery.value)
      const params = new URLSearchParams()
      params.set('root_type', fileRootType.value)
      if (path) params.set('path', path)
      if (search) {
        params.set('query', search)
        params.set('limit', '500')
      }
      const query = params.toString()
      const response = await api<FileListResponse>(`/api/files${query ? `?${query}` : ''}`)
      if (requestId !== listRequestId) return
      fileEntries.value = response.entries
      filePath.value = response.path
      fileParent.value = response.parent ?? null
      fileRoot.value = response.root
      const existingPaths = new Set(fileEntryPaths.value)
      selectedFilePaths.value = selectedFilePaths.value.filter((item) => existingPaths.has(item))
    } catch (error) {
      if (requestId !== listRequestId) return
      fileEntries.value = []
      selectedFilePaths.value = []
      fileError.value = error instanceof Error ? error.message : '文件列表加载失败'
    } finally {
      if (requestId === listRequestId) fileLoading.value = false
    }
  }

  function openFileEntry(entry: FileEntry) {
    if (entry.type !== 'directory') return
    void loadFiles(entry.path)
  }

  function isAudioFile(entry: FileEntry) {
    if (entry.type !== 'file') return false
    const extensionIndex = entry.name.lastIndexOf('.')
    if (extensionIndex < 0) return false
    return AUDIO_FILE_EXTENSIONS.has(entry.name.slice(extensionIndex).toLowerCase())
  }

  async function openFileDetail(entry: FileEntry) {
    if (!isAudioFile(entry)) return
    const requestId = ++fileDetailRequestId.value
    fileDetail.value = null
    fileDetailError.value = ''
    fileDetailLoading.value = true
    fileDetailDialog.value = true
    const params = new URLSearchParams({
      path: entry.path,
      root_type: fileRootType.value
    })
    try {
      const detail = await api<FileAudioDetail>(`/api/files/detail?${params.toString()}`)
      if (requestId !== fileDetailRequestId.value) return
      fileDetail.value = detail
    } catch (error) {
      if (requestId !== fileDetailRequestId.value) return
      const message = error instanceof Error ? error.message : '音频详情加载失败'
      fileDetailError.value = message
      actions.notify(message, 'error')
    } finally {
      if (requestId === fileDetailRequestId.value) {
        fileDetailLoading.value = false
      }
    }
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
        actions.notify(
          `已删除 ${result.deleted_paths.length} 个，失败 ${result.failures.length} 个`,
          'warning'
        )
      } else if (result.not_found_paths.length) {
        actions.notify(
          `已删除 ${result.deleted_paths.length} 个，${result.not_found_paths.length} 个不存在`,
          'warning'
        )
      } else {
        actions.notify(`已删除 ${result.deleted_paths.length} 个项目`)
      }
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '文件删除失败', 'error')
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
    try {
      const result = await api<FileOrganizeEnqueueResponse>('/api/files/organize', {
        method: 'POST',
        body: JSON.stringify({ paths })
      })
      fileOrganizeDialog.value = false
      pendingFileOrganize.value = null
      pendingFileOrganizePaths.value = []
      pendingFileOrganizeLabel.value = ''
      pendingFileOrganizeHasDirectory.value = false
      selectedFilePaths.value = selectedFilePaths.value.filter((item) => !paths.includes(item))
      const existingText = result.existing_tasks
        ? `，${result.existing_tasks} 条已有任务正在处理`
        : ''
      actions.notify(`已创建 ${result.created_tasks} 条刮削任务${existingText}`)
      void actions.loadDashboard(true)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '创建刮削任务失败', 'error')
    } finally {
      fileOrganizing.value = false
    }
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

  return {
    loadFiles,
    openFileEntry,
    isAudioFile,
    openFileDetail,
    runFileSearch,
    clearFileSearch,
    openFileOrganize,
    organizeSelectedFiles,
    openFileDelete,
    deleteSelectedFiles,
    confirmFileDelete,
    confirmFileOrganize,
    changeFileRootType
  }
}
