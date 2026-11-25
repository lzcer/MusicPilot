import { watch, onUnmounted } from 'vue'
import type { WorkspaceState } from './state'
import type { WorkspaceActions } from './actions'

export function installWorkspaceEffects(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    pendingDownload,
    torrentFilesController,
    torrentFiles,
    torrentFilesExpanded,
    torrentFilesLoading,
    torrentFilesError,
    collapsedTorrentDirectories,
    fileDetailDialog,
    fileDetailRequestId,
    fileDetailLoading,
    fileDetailError,
    fileDetail,
    activePage,
    settingsTab,
    downloadableTaskIds,
    systemTasksDialog,
    selectedSystemTaskIds,
    searchSiteFilter,
    searchPage,
    searchResultView,
    displayedSearchResults,
    logTimer,
    downloadTimer,
    artistBuildTimer,
    directoryMonitorStatusTimer,
    metadataSearchStream
  } = state
  watch(
    pendingDownload,
    () => {
      torrentFilesController.value?.abort()
      torrentFilesController.value = null
      torrentFiles.value = null
      torrentFilesExpanded.value = false
      torrentFilesLoading.value = false
      torrentFilesError.value = ''
      collapsedTorrentDirectories.value.clear()
    },
    { flush: 'sync' }
  )

  watch(fileDetailDialog, (open) => {
    if (open) return
    fileDetailRequestId.value += 1
    fileDetailLoading.value = false
    fileDetailError.value = ''
    fileDetail.value = null
  })

  watch(activePage, () => {
    actions.syncPagePolling()
  })

  watch(settingsTab, () => {
    actions.syncPagePolling()
  })

  watch(downloadableTaskIds, () => {
    actions.syncSelectedDownloadIds()
  })

  watch(systemTasksDialog, (open) => {
    if (open) {
      actions.startSystemTaskPolling()
      return
    }
    actions.stopSystemTaskPolling()
    selectedSystemTaskIds.value = []
  })

  watch(searchSiteFilter, () => {
    searchPage.value = 1
  })

  watch(searchResultView, () => {
    searchPage.value = 1
    if (
      searchSiteFilter.value &&
      !displayedSearchResults.value.some((item) => item.source === searchSiteFilter.value)
    ) {
      searchSiteFilter.value = ''
    }
  })

  onUnmounted(() => {
    window.clearInterval(logTimer.value)
    window.clearInterval(downloadTimer.value)
    window.clearInterval(artistBuildTimer.value)
    window.clearInterval(directoryMonitorStatusTimer.value)
    actions.stopSystemTaskPolling()
    metadataSearchStream.value?.close()
    torrentFilesController.value?.abort()
  })
}
