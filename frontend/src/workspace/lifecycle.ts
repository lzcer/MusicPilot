import { onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { Workspace } from './index'

export function installPageLifecycle(workspace: Workspace) {
  const route = useRoute()
  const { loadSettingsTab } = workspace
  let searchRestored = false

  async function activatePage() {
    const page = String(route.name ?? 'dashboard')
    workspace.activePage.value = page
    if (page === 'search' && !searchRestored) {
      searchRestored = true
      if (!workspace.searchText.value && !workspace.selectedMedia.value) {
        workspace.subscribeMetadataSiteSearch(false)
      }
    }
    const loaders: Record<string, () => Promise<unknown>> = {
      dashboard: () => workspace.loadDashboard(Boolean(workspace.dashboard.value)),
      search: workspace.loadSites,
      downloads: workspace.loadDownloads,
      media: () => Promise.all([workspace.loadMedia(), loadSettingsTab('system')]),
      files: () => Promise.all([workspace.loadFiles(), loadSettingsTab('system')]),
      musicLibrary: workspace.loadMusicLibrary,
      playlists: () => Promise.all([workspace.loadPlaylists(), workspace.loadMusicPlatforms()]),
      artists: () => Promise.all([workspace.loadArtists(), workspace.loadArtistBuildStatus()]),
      sites: workspace.loadSites,
      logs: () => Promise.all([workspace.loadLogs(), workspace.loadDebugLoggingState()]),
      settings: () => loadSettingsTab(workspace.settingsTab.value)
    }
    try {
      await loaders[page]?.()
    } catch (error) {
      workspace.notify(error instanceof Error ? error.message : '页面数据加载失败', 'error')
    }
  }

  watch(
    () => route.name,
    () => void activatePage(),
    { immediate: true }
  )
  watch(workspace.settingsTab, (tab) => {
    if (workspace.activePage.value !== 'settings') return
    void loadSettingsTab(tab).catch((error) => workspace.notify(String(error), 'error'))
  })
  watch(workspace.pendingDownload, (value) => {
    if (value)
      void workspace.loadDownloaders().catch((error) => workspace.notify(String(error), 'error'))
  })

  function visibilityChanged() {
    workspace.syncPagePolling()
    if (document.hidden) {
      workspace.stopSystemTaskPolling()
    } else if (workspace.systemTasksDialog.value) {
      workspace.startSystemTaskPolling()
    }
  }
  document.addEventListener('visibilitychange', visibilityChanged)
  onUnmounted(() => document.removeEventListener('visibilitychange', visibilityChanged))
}
