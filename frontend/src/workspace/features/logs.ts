import { api } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type { LogEntry, DebugLoggingState } from '../../types/musicpilot'

export function createLogsActions(state: WorkspaceState, actions: WorkspaceActions) {
  const { logPaused, logsLoading, logs, debugLoggingEnabled, debugLoggingLoading, logLevel } = state

  async function loadLogs(force = false) {
    if (logPaused.value && !force) return
    logsLoading.value = true
    try {
      logs.value = await api<LogEntry[]>('/api/logs?limit=300')
    } finally {
      logsLoading.value = false
    }
  }

  async function loadDebugLoggingState() {
    const state = await api<DebugLoggingState>('/api/logs/debug')
    debugLoggingEnabled.value = state.enabled
  }

  async function setDebugLoggingEnabled(enabled: boolean | null) {
    if (enabled === null || debugLoggingLoading.value) return
    debugLoggingLoading.value = true
    try {
      const state = await api<DebugLoggingState>('/api/logs/debug', {
        method: 'PUT',
        body: JSON.stringify({ enabled })
      })
      debugLoggingEnabled.value = state.enabled
      if (state.enabled) {
        logLevel.value = 'DEBUG'
      }
      await loadLogs(true)
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : 'DEBUG 日志设置失败', 'error')
    } finally {
      debugLoggingLoading.value = false
    }
  }

  return { loadLogs, loadDebugLoggingState, setDebugLoggingEnabled }
}
