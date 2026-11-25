import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type { MediaFile, SystemTask, MusicPlatform } from '../../types/musicpilot'

export function createFormattingActions(state: WorkspaceState, actions: WorkspaceActions) {
  const { metadataSourceOptions, systemForm } = state

  function metadataSourceLabel(source?: string | null) {
    return (
      metadataSourceOptions.find((option) => option.value === source)?.title || source || 'QQ音乐'
    )
  }

  function downloadCreationTypeText(value: string) {
    return value === 'monitor_created' ? '监听创建' : '任务创建'
  }

  function trimmedInput(value: string | null | undefined) {
    return typeof value === 'string' ? value.trim() : ''
  }

  function databaseExportFilename(disposition: string) {
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    if (encoded) {
      try {
        return decodeURIComponent(encoded)
      } catch {
        return encoded
      }
    }
    return 'musicpilot-database.zip'
  }

  function clampInteger(value: number, min: number, max: number, fallback: number) {
    const normalized = Number.isFinite(value) ? Math.trunc(value) : fallback
    return Math.min(Math.max(normalized, min), max)
  }

  function progressPercent(value: number) {
    return Math.round(value * 100)
  }

  function formatSize(value?: number | null) {
    if (value == null) return '-'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let size = value
    let unitIndex = 0
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex += 1
    }
    return `${size.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`
  }

  function formatDuration(value?: number | null) {
    if (!value) return '-'
    const minutes = Math.floor(value / 60)
    const seconds = value % 60
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  function formatAudioDuration(value?: number | null) {
    return formatDuration(value ? Math.round(value) : value)
  }

  function formatAudioBitrate(value?: number | null) {
    return value ? `${Math.round(value / 1000)} kbps` : '-'
  }

  function formatAudioSampleRate(value?: number | null) {
    if (!value) return '-'
    const kilohertz = value / 1000
    return `${Number.isInteger(kilohertz) ? kilohertz : kilohertz.toFixed(1)} kHz`
  }

  function formatAudioChannels(value?: number | null) {
    if (!value) return '-'
    if (value === 1) return '1（单声道）'
    if (value === 2) return '2（立体声）'
    return `${value}`
  }

  function formatTime(value: string) {
    return new Date(value).toLocaleString()
  }

  function formatOptionalTime(value?: string | null) {
    return value ? formatTime(value) : '-'
  }

  function systemTaskElapsedText(task: SystemTask) {
    if (!task.started_at) return '-'
    const startedAt = Date.parse(task.started_at)
    if (Number.isNaN(startedAt)) return '-'
    const finishedAt = task.finished_at ? Date.parse(task.finished_at) : Date.now()
    const endedAt = Number.isNaN(finishedAt) ? Date.now() : finishedAt
    const seconds = Math.max(0, Math.floor((endedAt - startedAt) / 1000))
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const remainingSeconds = seconds % 60
    if (hours > 0) {
      return `${hours}小时${minutes.toString().padStart(2, '0')}分`
    }
    return `${minutes}分${remainingSeconds.toString().padStart(2, '0')}秒`
  }

  function musicPlatformLabel(platform: MusicPlatform) {
    return `${platform.platform === 'spotify' ? 'Spotify' : platform.platform}${platform.display_name ? ` - ${platform.display_name}` : ''}`
  }

  function playlistPlatformLabel(platform: string) {
    return (
      {
        spotify: 'Spotify',
        spotify_public: 'Spotify',
        qq: 'QQ音乐',
        netease: '网易云音乐',
        kuwo: '酷我音乐',
        kugou: '酷狗音乐',
        apple_music: 'Apple Music'
      }[platform] ?? platform
    )
  }

  function musicPlatformStatusText(status: string) {
    return (
      {
        pending: '待授权',
        connected: '已关联',
        reauthorization_required: '需要重新登录',
        failed: '关联失败'
      }[status] ?? status
    )
  }

  function musicPlatformStatusColor(status: string) {
    return (
      {
        pending: 'warning',
        connected: 'success',
        reauthorization_required: 'error',
        failed: 'error'
      }[status] ?? 'secondary'
    )
  }

  function playlistStatusText(status: string) {
    return (
      {
        synced: '已同步',
        downloading: '下载中',
        failed: '失败'
      }[status] ?? status
    )
  }

  function playlistStatusColor(status: string) {
    return (
      {
        synced: 'success',
        downloading: 'info',
        failed: 'error'
      }[status] ?? 'secondary'
    )
  }

  function downloadStatusText(status: string) {
    return (
      {
        queued: '队列中',
        pre_scraping: '预刮削中',
        candidate_matched: '已匹配，准备提交',
        candidate_cleaning: '未匹配，清理中',
        candidate_cleanup_failed: '候选清理失败',
        submitted: '已提交',
        downloading: '下载中',
        completed: '下载完成',
        refreshing_library: '整理中',
        library_refreshed: '曲库已刷新',
        library_refresh_skipped: '跳过刷新',
        source_directory_not_found: '目录未找到',
        failed: '失败',
        deleted: '已删除',
        interrupted: '已中断'
      }[status] ?? status
    )
  }

  function downloadStatusColor(status: string) {
    return (
      {
        queued: 'warning',
        pre_scraping: 'info',
        candidate_matched: 'primary',
        candidate_cleaning: 'warning',
        candidate_cleanup_failed: 'error',
        submitted: 'primary',
        downloading: 'info',
        completed: 'success',
        refreshing_library: 'info',
        library_refreshed: 'success',
        library_refresh_skipped: 'success',
        source_directory_not_found: 'error',
        failed: 'error',
        deleted: 'error',
        interrupted: 'warning'
      }[status] ?? 'secondary'
    )
  }

  function systemTaskStatusText(status: string) {
    return (
      {
        WAIT: '等待中',
        RUNNING: '运行中',
        SLOW: '耗时异常',
        SUCCEEDED: '已完成',
        FAILED: '失败',
        INTERRUPTED: '已中断'
      }[status] ?? status
    )
  }

  function systemTaskStatusColor(status: string) {
    return (
      {
        WAIT: 'warning',
        RUNNING: 'info',
        SLOW: 'warning',
        SUCCEEDED: 'success',
        FAILED: 'error',
        INTERRUPTED: 'warning'
      }[status] ?? 'secondary'
    )
  }

  function systemTaskTypeText(type: string) {
    return (
      {
        PLAYLIST_TRACK_DOWNLOAD: '歌单单曲下载',
        DOWNLOAD_ITEM_SCRAPE: '下载明细匹配',
        MANUAL_FILE_SCRAPE: '文件元数据刮削',
        FILE_ORGANIZE: '文件整理',
        DOWNLOAD_REFRESH_LIBRARY: '曲库刷新',
        DOWNLOAD_FINALIZE_LIBRARY: '曲库收尾',
        SEARCH_SITE: '站点搜索',
        SEARCH_MEDIA: '媒体搜索',
        SEARCH_SITE_CANDIDATES: '候选站点搜索'
      }[type] ?? type
    )
  }

  function playlistTrackStatusText(status: string) {
    return (
      {
        pending: '待处理',
        existing: '已存在',
        waiting: '等待',
        searching: '搜索中',
        submitted: '已提交',
        queue: '排队中',
        downloading: '下载中',
        completed: '下载完成',
        refreshing_library: '刷新曲库',
        library_refreshed: '曲库已刷新',
        not_found: '未找到',
        source_directory_not_found: '目录未找到',
        failed: '失败',
        deleted: '已删除',
        interrupted: '已中断'
      }[status] ?? status
    )
  }

  function playlistTrackStatusColor(status: string) {
    return (
      {
        existing: 'success',
        waiting: 'warning',
        searching: 'info',
        submitted: 'primary',
        queue: 'warning',
        downloading: 'info',
        completed: 'success',
        refreshing_library: 'info',
        library_refreshed: 'success',
        not_found: 'error',
        source_directory_not_found: 'error',
        failed: 'error',
        deleted: 'error',
        interrupted: 'warning'
      }[status] ?? 'secondary'
    )
  }

  function downloadTaskItemStatusText(status: string) {
    return (
      {
        pending: '待查询',
        metadata_searching: '查询中',
        metadata_found: '已匹配',
        metadata_not_found: '未匹配',
        organizing: '整理中',
        organized: '已整理',
        organize_failed: '整理失败',
        organize_skipped: '已跳过',
        failed: '失败',
        interrupted: '已中断'
      }[status] ?? status
    )
  }

  function downloadTaskItemStatusColor(status: string) {
    return (
      {
        pending: 'secondary',
        metadata_searching: 'info',
        metadata_found: 'success',
        metadata_not_found: 'warning',
        organizing: 'info',
        organized: 'success',
        organize_failed: 'error',
        organize_skipped: 'warning',
        failed: 'error',
        interrupted: 'warning'
      }[status] ?? 'secondary'
    )
  }

  function mediaStatusColor(status: string) {
    if (status === 'failed') return 'error'
    if (status === 'skipped') return 'warning'
    return 'success'
  }

  function mediaStatusText(status: string) {
    if (status === 'failed') return '失败'
    if (status === 'skipped') return '跳过'
    return '成功'
  }

  function mediaOperationTypeText(type: string | undefined) {
    return (
      {
        copy: '复制',
        mapped: '映射',
        source: '源目录'
      }[type || 'mapped'] ??
      (type || '映射')
    )
  }

  function mediaOperationReason(row: MediaFile) {
    return row.operation_reason?.trim() || '历史数据未记录'
  }

  function mediaRemark(row: MediaFile) {
    return row.remark || row.error_message || '-'
  }

  function mediaTableRow(item: MediaFile | { raw: MediaFile }) {
    return 'raw' in item ? item.raw : item
  }

  function mediaDisplayPath(row: MediaFile) {
    const sourcePath = displayRelativePath(
      row.source_path,
      systemForm.value.scraping.source_directory
    )
    if (
      row.status === 'success' &&
      row.library_path &&
      pathIsUnderRoot(row.library_path, systemForm.value.scraping.mapped_directory)
    ) {
      const mappedPath = displayRelativePath(
        row.library_path,
        systemForm.value.scraping.mapped_directory
      )
      return `${sourcePath}\n=>\n${mappedPath}`
    }
    return sourcePath || '-'
  }

  function displayRelativePath(path: string | null | undefined, root: string) {
    const normalized = normalizeDisplayPath(path)
    if (!normalized) return ''
    const normalizedRoot = normalizeDisplayPath(root)
    if (!normalizedRoot) return normalized
    const lowerPath = normalized.toLowerCase()
    const lowerRoot = normalizedRoot.toLowerCase()
    if (lowerPath === lowerRoot) {
      const segments = normalized.split('/').filter(Boolean)
      return segments[segments.length - 1] || normalized
    }
    if (lowerPath.startsWith(`${lowerRoot}/`)) return normalized.slice(normalizedRoot.length + 1)
    return normalized
  }

  function pathIsUnderRoot(path: string | null | undefined, root: string) {
    const normalized = normalizeDisplayPath(path)
    const normalizedRoot = normalizeDisplayPath(root)
    if (!normalized || !normalizedRoot) return false
    const lowerPath = normalized.toLowerCase()
    const lowerRoot = normalizedRoot.toLowerCase()
    return lowerPath === lowerRoot || lowerPath.startsWith(`${lowerRoot}/`)
  }

  function normalizeDisplayPath(path: string | null | undefined) {
    return (path || '').replace(/\\/g, '/').replace(/\/+$/g, '').trim()
  }

  function logColor(level: string) {
    if (level === 'ERROR') return 'error'
    if (level === 'WARNING') return 'warning'
    if (level === 'INFO') return 'info'
    return 'secondary'
  }

  return {
    metadataSourceLabel,
    downloadCreationTypeText,
    trimmedInput,
    databaseExportFilename,
    clampInteger,
    progressPercent,
    formatSize,
    formatDuration,
    formatAudioDuration,
    formatAudioBitrate,
    formatAudioSampleRate,
    formatAudioChannels,
    formatTime,
    formatOptionalTime,
    systemTaskElapsedText,
    musicPlatformLabel,
    playlistPlatformLabel,
    musicPlatformStatusText,
    musicPlatformStatusColor,
    playlistStatusText,
    playlistStatusColor,
    downloadStatusText,
    downloadStatusColor,
    systemTaskStatusText,
    systemTaskStatusColor,
    systemTaskTypeText,
    playlistTrackStatusText,
    playlistTrackStatusColor,
    downloadTaskItemStatusText,
    downloadTaskItemStatusColor,
    mediaStatusColor,
    mediaStatusText,
    mediaOperationTypeText,
    mediaOperationReason,
    mediaRemark,
    mediaTableRow,
    mediaDisplayPath,
    displayRelativePath,
    pathIsUnderRoot,
    normalizeDisplayPath,
    logColor
  }
}
