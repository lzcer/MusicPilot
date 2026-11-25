import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'

export function createPollingActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    logTimer,
    downloadTimer,
    artistBuildTimer,
    directoryMonitorStatusTimer,
    activePage,
    settingsTab
  } = state

  function startLogPolling() {
    window.clearInterval(logTimer.value)
    logTimer.value = window.setInterval(() => {
      void actions.loadLogs().catch(() => undefined)
    }, 5000)
  }

  function startDownloadPolling() {
    window.clearInterval(downloadTimer.value)
    downloadTimer.value = window.setInterval(() => {
      void actions.loadDownloads().catch(() => {
        // Keep polling quiet; visible errors are handled by manual refresh and page load.
      })
    }, 5000)
  }

  function startArtistBuildPolling() {
    window.clearInterval(artistBuildTimer.value)
    artistBuildTimer.value = window.setInterval(() => {
      void actions.loadArtistBuildStatus()
    }, 5000)
  }

  function startDirectoryMonitorStatusPolling() {
    window.clearInterval(directoryMonitorStatusTimer.value)
    void actions.loadDirectoryMonitorStatus().catch(() => undefined)
    directoryMonitorStatusTimer.value = window.setInterval(() => {
      void actions.loadDirectoryMonitorStatus().catch(() => undefined)
    }, 30000)
  }

  function syncPagePolling() {
    if (document.hidden) {
      window.clearInterval(logTimer.value)
      window.clearInterval(downloadTimer.value)
      window.clearInterval(artistBuildTimer.value)
      window.clearInterval(directoryMonitorStatusTimer.value)
      return
    }
    if (activePage.value === 'logs') {
      startLogPolling()
    } else {
      window.clearInterval(logTimer.value)
    }

    if (activePage.value === 'downloads') {
      startDownloadPolling()
    } else {
      window.clearInterval(downloadTimer.value)
    }

    if (activePage.value === 'artists') {
      startArtistBuildPolling()
    } else {
      window.clearInterval(artistBuildTimer.value)
    }

    if (activePage.value === 'settings' && settingsTab.value === 'system') {
      startDirectoryMonitorStatusPolling()
    } else {
      window.clearInterval(directoryMonitorStatusTimer.value)
    }
  }

  return {
    startLogPolling,
    startDownloadPolling,
    startArtistBuildPolling,
    startDirectoryMonitorStatusPolling,
    syncPagePolling
  }
}
