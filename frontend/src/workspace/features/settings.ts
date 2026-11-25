import { ApiError, api, apiNoContent, readError } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type {
  DownloaderConfig,
  MediaServerConfig,
  NotifierConfig,
  SystemSettings,
  DirectoryMonitorStatus,
  DirectoryMonitorErrorDetail,
  AboutInfo,
  TestResponse,
  DeleteTarget,
  ConfigMenuKind
} from '../../types/musicpilot'

export function createSettingsActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    settingsLoading,
    settingsErrors,
    secretMask,
    downloaderForm,
    mediaServerForm,
    mediaServerUserForm,
    notifierForm,
    aboutInfo,
    downloaders,
    editingDownloaderId,
    downloaderDialog,
    downloaderTesting,
    mediaServers,
    defaultMediaServer,
    editingMediaServerId,
    mediaServerDialog,
    mediaServerTesting,
    notifiers,
    editingNotifierId,
    notifierDialog,
    notifierTesting,
    activeConfigMenu,
    deleteTarget,
    deleteDialog,
    deleting,
    sites,
    musicPlatforms,
    playlists,
    systemForm,
    directoryMonitorStatus,
    directoryMonitorDialogContext,
    directoryMonitorDialogMessage,
    directoryMonitorPollingAvailable,
    directoryMonitorDialog,
    systemSaving,
    directoryMonitorActionLoading,
    databaseExporting,
    databaseImportStartDialog,
    databaseImportFileDialog,
    databaseImportFile,
    databaseImportFileInput,
    databaseImportDragging,
    databaseImportSecondConfirm,
    databaseImporting
  } = state

  const settingsLoaded = new Set<string>()
  const settingsPending = new Map<string, Promise<void>>()

  async function loadSettingsTab(tab: string) {
    if (settingsLoaded.has(tab)) return
    const loaders: Record<string, () => Promise<void>> = {
      downloaders: loadDownloaders,
      mediaServers: loadMediaServers,
      notifiers: loadNotifiers,
      system: loadSystemSettings,
      about: loadAboutInfo
    }
    const load = loaders[tab]
    if (!load) return
    let task = settingsPending.get(tab)
    if (!task) {
      delete settingsErrors.value[tab]
      task = load().then(() => {
        settingsLoaded.add(tab)
      })
      settingsPending.set(tab, task)
    }
    settingsLoading.value = true
    try {
      await task
    } catch (error) {
      settingsErrors.value[tab] = error instanceof Error ? error.message : '设置加载失败'
      throw error
    } finally {
      settingsPending.delete(tab)
      settingsLoading.value = settingsPending.size > 0
    }
  }

  function maskedSecret(configured: boolean) {
    return configured ? secretMask : ''
  }

  function submittedSecret(secret: string) {
    return secret === secretMask ? '' : secret
  }

  function updateSecret(current: string, value: string) {
    if (current !== secretMask) return value
    if (value === secretMask) return value

    let start = 0
    while (start < current.length && start < value.length && current[start] === value[start]) {
      start += 1
    }

    let currentEnd = current.length
    let valueEnd = value.length
    while (
      currentEnd > start &&
      valueEnd > start &&
      current[currentEnd - 1] === value[valueEnd - 1]
    ) {
      currentEnd -= 1
      valueEnd -= 1
    }
    return value.slice(start, valueEnd)
  }

  function updateDownloaderPassword(value: string) {
    downloaderForm.value.password = updateSecret(downloaderForm.value.password, value)
  }

  function updateMediaServerPassword(value: string) {
    mediaServerForm.value.password = updateSecret(mediaServerForm.value.password, value)
  }

  function updateMediaServerUserPassword(value: string) {
    mediaServerUserForm.value.password = updateSecret(mediaServerUserForm.value.password, value)
  }

  function updateNotifierBotToken(value: string) {
    notifierForm.value.bot_token = updateSecret(notifierForm.value.bot_token, value)
  }

  async function loadAboutInfo() {
    aboutInfo.value = await api<AboutInfo>('/api/about')
  }

  async function loadDownloaders() {
    downloaders.value = await api<DownloaderConfig[]>('/api/settings/downloaders')
  }

  function openNewDownloaderDialog() {
    editingDownloaderId.value = null
    downloaderForm.value = {
      id: null,
      name: 'qBittorrent',
      type: 'qbittorrent',
      base_url: '',
      username: '',
      password: '',
      download_path: '',
      local_path: '',
      listen_mode: 'polling',
      monitor_tag: 'MusicPilot',
      is_default: true,
      enabled: true
    }
    downloaderDialog.value = true
  }

  function selectDownloaderType(type: string) {
    downloaderForm.value.name = type === 'transmission' ? 'Transmission' : 'qBittorrent'
    downloaderForm.value.listen_mode = 'polling'
  }

  function editDownloader(downloader: DownloaderConfig) {
    editingDownloaderId.value = downloader.id ?? null
    downloaderForm.value = {
      id: downloader.id ?? null,
      name: downloader.name,
      type: downloader.type,
      base_url: downloader.base_url,
      username: downloader.username,
      password: maskedSecret(downloader.password_configured),
      download_path: downloader.download_path ?? '',
      local_path: downloader.local_path ?? '',
      listen_mode: downloader.listen_mode ?? 'polling',
      monitor_tag: downloader.monitor_tag ?? 'MusicPilot',
      is_default: downloader.is_default,
      enabled: downloader.enabled
    }
    downloaderDialog.value = true
  }

  async function testDownloader() {
    const pathError = downloaderPathError()
    if (pathError) {
      actions.notify(pathError, 'error')
      return
    }
    downloaderTesting.value = true
    try {
      const result = await api<TestResponse>('/api/settings/downloaders/test', {
        method: 'POST',
        body: JSON.stringify({
          ...downloaderForm.value,
          password: submittedSecret(downloaderForm.value.password)
        })
      })
      actions.notify(result.message, result.ok ? 'success' : 'error')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '下载器测试失败', 'error')
    } finally {
      downloaderTesting.value = false
    }
  }

  async function saveDownloader() {
    const pathError = downloaderPathError()
    if (pathError) {
      actions.notify(pathError, 'error')
      return
    }
    const editing = Boolean(editingDownloaderId.value)
    await api<DownloaderConfig>(
      editing
        ? `/api/settings/downloaders/${editingDownloaderId.value}`
        : '/api/settings/downloaders',
      {
        method: editing ? 'PUT' : 'POST',
        body: JSON.stringify({
          ...downloaderForm.value,
          password: submittedSecret(downloaderForm.value.password)
        })
      }
    )
    await loadDownloaders()
    downloaderDialog.value = false
    actions.notify('下载器已保存')
  }

  function downloaderPathError() {
    if (!actions.trimmedInput(downloaderForm.value.download_path)) return '下载目录不能为空'
    if (!actions.trimmedInput(downloaderForm.value.local_path)) return '本机对应目录不能为空'
    return ''
  }

  function openDeleteDownloader(downloader: DownloaderConfig) {
    if (!downloader.id) return
    openDeleteDialog({ kind: 'downloader', id: downloader.id, name: downloader.name })
  }

  async function loadMediaServers() {
    mediaServers.value = await api<MediaServerConfig[]>('/api/settings/media-servers')
    syncMediaServerFormFromDefault()
  }

  function syncMediaServerFormFromDefault() {
    const server = defaultMediaServer.value
    if (!server) {
      resetMediaServerForm()
      return
    }
    mediaServerForm.value = {
      id: server.id ?? null,
      name: server.name,
      type: server.type,
      base_url: server.base_url,
      api_key: server.api_key,
      username: server.username,
      password: maskedSecret(server.password_configured),
      is_default: true,
      enabled: server.enabled
    }
  }

  function resetMediaServerForm() {
    mediaServerForm.value = {
      id: null,
      name: 'Navidrome',
      type: 'navidrome',
      base_url: '',
      api_key: '',
      username: '',
      password: '',
      is_default: true,
      enabled: true
    }
  }

  function openNewMediaServerUserDialog() {
    if (!mediaServerForm.value.id) {
      actions.notify('请先保存音乐库配置', 'warning')
      return
    }
    editingMediaServerId.value = null
    mediaServerUserForm.value = {
      id: null,
      username: '',
      password: '',
      enabled: true
    }
    mediaServerDialog.value = true
  }

  function editMediaServerUser(server: MediaServerConfig) {
    if (server.is_default) {
      syncMediaServerFormFromDefault()
      return
    }
    editingMediaServerId.value = server.id ?? null
    mediaServerUserForm.value = {
      id: server.id ?? null,
      username: server.username,
      password: maskedSecret(server.password_configured),
      enabled: server.enabled
    }
    mediaServerDialog.value = true
  }

  function mediaServerUserPayload() {
    const username = actions.trimmedInput(mediaServerUserForm.value.username)
    return {
      id: mediaServerUserForm.value.id,
      name: username || 'Navidrome 用户',
      type: mediaServerForm.value.type,
      base_url: mediaServerForm.value.base_url,
      api_key: mediaServerForm.value.api_key,
      username,
      password: submittedSecret(mediaServerUserForm.value.password),
      is_default: false,
      enabled: mediaServerUserForm.value.enabled
    }
  }

  async function syncMediaServerUsersToMainConfig(mainServer: MediaServerConfig) {
    const userServers = mediaServers.value.filter((item) => item.id && !item.is_default)
    await Promise.all(
      userServers.map((item) =>
        api<MediaServerConfig>(`/api/settings/media-servers/${item.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            ...item,
            type: mainServer.type,
            base_url: mainServer.base_url,
            api_key: mainServer.api_key,
            is_default: false,
            password: ''
          })
        })
      )
    )
  }

  async function testMediaServer() {
    const addressError = mediaServerAddressError()
    if (addressError) {
      actions.notify(addressError, 'error')
      return
    }
    mediaServerTesting.value = true
    try {
      const result = await api<TestResponse>('/api/settings/media-servers/test', {
        method: 'POST',
        body: JSON.stringify({
          ...mediaServerForm.value,
          password: submittedSecret(mediaServerForm.value.password),
          is_default: true
        })
      })
      actions.notify(result.message, result.ok ? 'success' : 'error')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '媒体服务器测试失败', 'error')
    } finally {
      mediaServerTesting.value = false
    }
  }

  function mediaServerAddressError() {
    if (mediaServerForm.value.enabled && !actions.trimmedInput(mediaServerForm.value.base_url)) {
      return '音乐库地址不能为空'
    }
    return ''
  }

  async function saveMediaServer() {
    const addressError = mediaServerAddressError()
    if (addressError) {
      actions.notify(addressError, 'error')
      return
    }
    try {
      const editing = Boolean(mediaServerForm.value.id)
      const server = await api<MediaServerConfig>(
        editing
          ? `/api/settings/media-servers/${mediaServerForm.value.id}`
          : '/api/settings/media-servers',
        {
          method: editing ? 'PUT' : 'POST',
          body: JSON.stringify({
            ...mediaServerForm.value,
            password: submittedSecret(mediaServerForm.value.password),
            is_default: true
          })
        }
      )
      await syncMediaServerUsersToMainConfig(server)
      await loadMediaServers()
      actions.notify('音乐库配置已保存')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '音乐库配置保存失败', 'error')
    }
  }

  async function testMediaServerUser() {
    const payload = mediaServerUserPayload()
    if (!payload.username) {
      actions.notify('用户名不能为空', 'warning')
      return
    }
    mediaServerTesting.value = true
    try {
      const result = await api<TestResponse>('/api/settings/media-servers/test', {
        method: 'POST',
        body: JSON.stringify(payload)
      })
      actions.notify(result.message, result.ok ? 'success' : 'error')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '音乐库用户测试失败', 'error')
    } finally {
      mediaServerTesting.value = false
    }
  }

  async function saveMediaServerUser() {
    const payload = mediaServerUserPayload()
    if (!payload.username) {
      actions.notify('用户名不能为空', 'warning')
      return
    }
    const editing = Boolean(editingMediaServerId.value)
    await api<MediaServerConfig>(
      editing
        ? `/api/settings/media-servers/${editingMediaServerId.value}`
        : '/api/settings/media-servers',
      {
        method: editing ? 'PUT' : 'POST',
        body: JSON.stringify(payload)
      }
    )
    await loadMediaServers()
    mediaServerDialog.value = false
    actions.notify('音乐库用户已保存')
  }

  function openDeleteMediaServer(server: MediaServerConfig) {
    if (!server.id) return
    openDeleteDialog({ kind: 'mediaServer', id: server.id, name: server.name })
  }

  async function loadNotifiers() {
    notifiers.value = await api<NotifierConfig[]>('/api/settings/notifiers')
  }

  function openNewNotifierDialog() {
    editingNotifierId.value = null
    notifierForm.value = {
      id: null,
      name: 'Telegram Bot',
      type: 'telegram',
      bot_token: '',
      webhook_url: '',
      chat_ids: '',
      use_proxy: false,
      enable_download_notify: true,
      enable_library_notify: true,
      enabled: true
    }
    notifierDialog.value = true
  }

  function editNotifier(notifier: NotifierConfig) {
    editingNotifierId.value = notifier.id ?? null
    notifierForm.value = {
      id: notifier.id ?? null,
      name: notifier.name,
      type: notifier.type,
      bot_token: maskedSecret(notifier.bot_token_configured),
      webhook_url: notifier.webhook_url,
      chat_ids: notifier.chat_ids,
      use_proxy: notifier.use_proxy,
      enable_download_notify: notifier.enable_download_notify,
      enable_library_notify: notifier.enable_library_notify,
      enabled: notifier.enabled
    }
    notifierDialog.value = true
  }

  async function testNotifier() {
    notifierTesting.value = true
    try {
      const result = await api<TestResponse>('/api/settings/notifiers/test', {
        method: 'POST',
        body: JSON.stringify({
          ...notifierForm.value,
          bot_token: submittedSecret(notifierForm.value.bot_token)
        })
      })
      actions.notify(result.message, result.ok ? 'success' : 'error')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '通知测试失败', 'error')
    } finally {
      notifierTesting.value = false
    }
  }

  async function saveNotifier() {
    const editing = Boolean(editingNotifierId.value)
    const notifier = await api<NotifierConfig>(
      editing ? `/api/settings/notifiers/${editingNotifierId.value}` : '/api/settings/notifiers',
      {
        method: editing ? 'PUT' : 'POST',
        body: JSON.stringify({
          ...notifierForm.value,
          bot_token: submittedSecret(notifierForm.value.bot_token)
        })
      }
    )
    if (editing) {
      notifiers.value = notifiers.value.map((item) => (item.id === notifier.id ? notifier : item))
    } else {
      notifiers.value.push(notifier)
    }
    notifierDialog.value = false
    actions.notify('通知已保存')
  }

  function openDeleteNotifier(notifier: NotifierConfig) {
    if (!notifier.id) return
    openDeleteDialog({ kind: 'notifier', id: notifier.id, name: notifier.name })
  }

  function openDeleteDialog(target: DeleteTarget) {
    activeConfigMenu.value = null
    deleteTarget.value = target
    deleteDialog.value = true
  }

  function configMenuKey(kind: ConfigMenuKind, id: string) {
    return `${kind}:${id}`
  }

  function toggleConfigMenu(kind: ConfigMenuKind, id: string) {
    const key = configMenuKey(kind, id)
    activeConfigMenu.value = activeConfigMenu.value === key ? null : key
  }

  function deleteTargetLabel(target: DeleteTarget | null) {
    if (!target) return ''
    return {
      site: '站点',
      downloader: '下载器',
      mediaServer: '媒体服务器',
      notifier: '通知',
      musicPlatform: '音乐平台',
      playlist: '歌单'
    }[target.kind]
  }

  function deleteTargetUrl(target: DeleteTarget) {
    return {
      site: `/api/sites/${target.id}`,
      downloader: `/api/settings/downloaders/${target.id}`,
      mediaServer: `/api/settings/media-servers/${target.id}`,
      notifier: `/api/settings/notifiers/${target.id}`,
      musicPlatform: `/api/music-platforms/${target.id}`,
      playlist: `/api/playlists/${target.id}`
    }[target.kind]
  }

  async function confirmDelete() {
    if (!deleteTarget.value) return
    const target = deleteTarget.value
    deleting.value = true
    try {
      await apiNoContent(deleteTargetUrl(target), { method: 'DELETE' })
      if (target.kind === 'site') {
        sites.value = sites.value.filter((item) => item.id !== target.id)
      } else if (target.kind === 'downloader') {
        downloaders.value = downloaders.value.filter((item) => item.id !== target.id)
      } else if (target.kind === 'mediaServer') {
        mediaServers.value = mediaServers.value.filter((item) => item.id !== target.id)
      } else if (target.kind === 'musicPlatform') {
        musicPlatforms.value = musicPlatforms.value.filter((item) => item.id !== target.id)
      } else if (target.kind === 'playlist') {
        playlists.value = playlists.value.filter((item) => item.id !== target.id)
      } else {
        notifiers.value = notifiers.value.filter((item) => item.id !== target.id)
      }
      deleteDialog.value = false
      deleteTarget.value = null
      actions.notify(`${deleteTargetLabel(target)}已删除`)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '删除失败', 'error')
    } finally {
      deleting.value = false
    }
  }

  function applySystemSettings(settings: Partial<SystemSettings>) {
    systemForm.value = {
      proxy: {
        ...systemForm.value.proxy,
        ...(settings.proxy ?? {})
      },
      scraping: {
        ...systemForm.value.scraping,
        ...(settings.scraping ?? {})
      },
      search: {
        ...systemForm.value.search,
        ...(settings.search ?? {})
      }
    }
  }

  async function loadSystemSettings() {
    applySystemSettings(await api<SystemSettings>('/api/settings/system'))
  }

  async function loadDirectoryMonitorStatus() {
    directoryMonitorStatus.value = await api<DirectoryMonitorStatus>(
      '/api/settings/directory-monitor/status'
    )
  }

  function directoryMonitorErrorDetail(error: unknown) {
    if (!(error instanceof ApiError) || !error.detail || typeof error.detail !== 'object') {
      return null
    }
    return error.detail as DirectoryMonitorErrorDetail
  }

  function openDirectoryMonitorDialog(
    context: 'save' | 'failure',
    message: string,
    pollingAvailable = true
  ) {
    directoryMonitorDialogContext.value = context
    directoryMonitorDialogMessage.value = message
    directoryMonitorPollingAvailable.value = pollingAvailable
    directoryMonitorDialog.value = true
  }

  function openDirectoryMonitorFailureDialog() {
    const status = directoryMonitorStatus.value
    const reason = [status.message, status.detail].filter(Boolean).join(' ')
    openDirectoryMonitorDialog('failure', reason || '目录监听已停止，请选择处理方式。')
  }

  function updateAutoOrganize(value: 'downloader' | 'directory') {
    const previous = systemForm.value.scraping.auto_organize
    systemForm.value.scraping.auto_organize = value
    if (value === 'directory' && previous !== 'directory') {
      systemForm.value.scraping.directory_monitor_mode = 'native'
    }
  }

  async function saveSystemSettings() {
    systemSaving.value = true
    try {
      systemForm.value.search.metadata_concurrency = actions.clampInteger(
        systemForm.value.search.metadata_concurrency,
        1,
        20,
        3
      )
      systemForm.value.search.minimum_seeders = actions.clampInteger(
        systemForm.value.search.minimum_seeders,
        0,
        Number.MAX_SAFE_INTEGER,
        1
      )
      systemForm.value.scraping.directory_monitor_poll_interval_seconds = actions.clampInteger(
        systemForm.value.scraping.directory_monitor_poll_interval_seconds,
        30,
        Number.MAX_SAFE_INTEGER,
        60
      )
      systemForm.value.scraping.directory_monitor_notification_delay_seconds = actions.clampInteger(
        systemForm.value.scraping.directory_monitor_notification_delay_seconds,
        1,
        Number.MAX_SAFE_INTEGER,
        10
      )
      const settings = await api<SystemSettings>('/api/settings/system', {
        method: 'POST',
        body: JSON.stringify(systemForm.value)
      })
      applySystemSettings(settings)
      await loadDirectoryMonitorStatus()
      actions.notify('系统设置已保存')
    } catch (error) {
      const detail = directoryMonitorErrorDetail(error)
      if (detail?.code === 'directory_monitor_native_unavailable') {
        openDirectoryMonitorDialog(
          'save',
          detail.message || (error instanceof Error ? error.message : '原生目录监听不可用。'),
          detail.polling_available !== false
        )
      } else if (detail?.code === 'directory_monitor_start_failed') {
        await Promise.allSettled([loadSystemSettings(), loadDirectoryMonitorStatus()])
        actions.notify(detail.message || '系统设置已保存，但目录监听启动失败。', 'error')
      } else {
        actions.notify(error instanceof Error ? error.message : '系统设置保存失败', 'error')
      }
    } finally {
      systemSaving.value = false
    }
  }

  async function retryNativeDirectoryMonitor() {
    directoryMonitorActionLoading.value = true
    try {
      if (directoryMonitorDialog.value && directoryMonitorDialogContext.value === 'save') {
        directoryMonitorDialog.value = false
        await saveSystemSettings()
        return
      }
      directoryMonitorStatus.value = await api<DirectoryMonitorStatus>(
        '/api/settings/directory-monitor/retry-native',
        { method: 'POST' }
      )
      await loadSystemSettings()
      directoryMonitorDialog.value = false
      actions.notify('原生目录监听已恢复')
    } catch (error) {
      const detail = directoryMonitorErrorDetail(error)
      directoryMonitorDialogMessage.value =
        detail?.message || (error instanceof Error ? error.message : '原生目录监听检测失败')
      directoryMonitorPollingAvailable.value = detail?.polling_available !== false
      await loadDirectoryMonitorStatus().catch(() => undefined)
    } finally {
      directoryMonitorActionLoading.value = false
    }
  }

  async function useDirectoryMonitorPolling() {
    systemForm.value.scraping.directory_monitor_mode = 'polling'
    systemForm.value.scraping.directory_monitor_poll_interval_seconds = actions.clampInteger(
      systemForm.value.scraping.directory_monitor_poll_interval_seconds,
      30,
      Number.MAX_SAFE_INTEGER,
      60
    )
    directoryMonitorDialog.value = false
    await saveSystemSettings()
  }

  async function switchToDownloaderMonitor() {
    systemForm.value.scraping.auto_organize = 'downloader'
    systemForm.value.scraping.directory_monitor_mode = 'native'
    directoryMonitorDialog.value = false
    await saveSystemSettings()
  }

  async function exportDatabase() {
    databaseExporting.value = true
    try {
      const response = await fetch('/api/settings/database/export', {
        credentials: 'include'
      })
      if (!response.ok) {
        throw new Error(await readError(response))
      }
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition') ?? ''
      const filename = actions.databaseExportFilename(disposition)
      const link = document.createElement('a')
      const url = URL.createObjectURL(blob)
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      actions.notify('数据库已导出')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '数据库导出失败', 'error')
    } finally {
      databaseExporting.value = false
    }
  }

  function openDatabaseImportStartDialog() {
    databaseImportStartDialog.value = true
  }

  function confirmDatabaseImportStart() {
    databaseImportStartDialog.value = false
    resetDatabaseImportSelection()
    databaseImportFileDialog.value = true
  }

  function selectedDatabaseImportFile() {
    return databaseImportFile.value
  }

  function openDatabaseImportFilePicker() {
    databaseImportFileInput.value?.click()
  }

  function handleDatabaseImportFileChange(event: Event) {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0] ?? null
    if (file) {
      setDatabaseImportFile(file)
    }
  }

  function handleDatabaseImportDrop(event: DragEvent) {
    databaseImportDragging.value = false
    const file = event.dataTransfer?.files?.[0] ?? null
    if (file) {
      setDatabaseImportFile(file)
    }
  }

  function setDatabaseImportFile(file: File) {
    if (!file.name.toLowerCase().endsWith('.zip')) {
      actions.notify('请选择 zip 导出包', 'warning')
      return
    }
    databaseImportFile.value = file
    databaseImportSecondConfirm.value = false
  }

  function resetDatabaseImportSelection() {
    databaseImportFile.value = null
    databaseImportSecondConfirm.value = false
    databaseImportDragging.value = false
    if (databaseImportFileInput.value) {
      databaseImportFileInput.value.value = ''
    }
  }

  function closeDatabaseImportFileDialog() {
    databaseImportFileDialog.value = false
    resetDatabaseImportSelection()
  }

  async function confirmDatabaseImport() {
    const file = selectedDatabaseImportFile()
    if (!file) {
      actions.notify('请先选择导入文件', 'warning')
      return
    }
    if (!databaseImportSecondConfirm.value) {
      databaseImportSecondConfirm.value = true
      return
    }
    databaseImporting.value = true
    try {
      const response = await fetch('/api/settings/database/import', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/zip'
        },
        body: file
      })
      if (!response.ok) {
        throw new Error(await readError(response))
      }
      databaseImportFileDialog.value = false
      resetDatabaseImportSelection()
      window.location.reload()
      actions.notify('数据库已导入')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '数据库导入失败', 'error')
    } finally {
      databaseImporting.value = false
    }
  }

  return {
    loadSettingsTab,
    maskedSecret,
    submittedSecret,
    updateSecret,
    updateDownloaderPassword,
    updateMediaServerPassword,
    updateMediaServerUserPassword,
    updateNotifierBotToken,
    loadAboutInfo,
    loadDownloaders,
    openNewDownloaderDialog,
    selectDownloaderType,
    editDownloader,
    testDownloader,
    saveDownloader,
    downloaderPathError,
    openDeleteDownloader,
    loadMediaServers,
    syncMediaServerFormFromDefault,
    resetMediaServerForm,
    openNewMediaServerUserDialog,
    editMediaServerUser,
    mediaServerUserPayload,
    syncMediaServerUsersToMainConfig,
    testMediaServer,
    mediaServerAddressError,
    saveMediaServer,
    testMediaServerUser,
    saveMediaServerUser,
    openDeleteMediaServer,
    loadNotifiers,
    openNewNotifierDialog,
    editNotifier,
    testNotifier,
    saveNotifier,
    openDeleteNotifier,
    openDeleteDialog,
    configMenuKey,
    toggleConfigMenu,
    deleteTargetLabel,
    deleteTargetUrl,
    confirmDelete,
    applySystemSettings,
    loadSystemSettings,
    loadDirectoryMonitorStatus,
    directoryMonitorErrorDetail,
    openDirectoryMonitorDialog,
    openDirectoryMonitorFailureDialog,
    updateAutoOrganize,
    saveSystemSettings,
    retryNativeDirectoryMonitor,
    useDirectoryMonitorPolling,
    switchToDownloaderMonitor,
    exportDatabase,
    openDatabaseImportStartDialog,
    confirmDatabaseImportStart,
    selectedDatabaseImportFile,
    openDatabaseImportFilePicker,
    handleDatabaseImportFileChange,
    handleDatabaseImportDrop,
    setDatabaseImportFile,
    resetDatabaseImportSelection,
    closeDatabaseImportFileDialog,
    confirmDatabaseImport
  }
}
