import { api } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type {
  DashboardSummary,
  SystemTaskStatus,
  SystemTask,
  SystemTaskInterruptResponse
} from '../../types/musicpilot'

export function createDashboardActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    dashboardLoading,
    dashboard,
    systemTaskStatus,
    systemTasksDialog,
    selectedSystemTaskIds,
    systemTaskRefreshPending,
    systemTasksLoading,
    systemTasks,
    systemTaskTimer,
    interruptibleSystemTaskIds,
    systemTasksInterrupting
  } = state

  async function loadDashboard(silent = false) {
    if (!silent) {
      dashboardLoading.value = true
    }
    try {
      dashboard.value = await api<DashboardSummary>('/api/dashboard')
    } catch (error) {
      if (!silent) {
        actions.notify(error instanceof Error ? error.message : '仪表盘加载失败', 'error')
      }
    } finally {
      if (!silent) {
        dashboardLoading.value = false
      }
    }
  }

  async function openSystemTasks(status: SystemTaskStatus) {
    systemTaskStatus.value = status
    systemTasksDialog.value = true
    selectedSystemTaskIds.value = []
    await loadSystemTasks()
  }

  async function loadSystemTasks(silent = false) {
    if (systemTaskRefreshPending.value) return
    systemTaskRefreshPending.value = true
    if (!silent) {
      systemTasksLoading.value = true
    }
    try {
      const params = new URLSearchParams({
        status: systemTaskStatus.value,
        limit: '200'
      })
      systemTasks.value = await api<SystemTask[]>(`/api/system-tasks?${params.toString()}`)
      syncSelectedSystemTaskIds()
    } catch (error) {
      if (!silent) {
        actions.notify(error instanceof Error ? error.message : '队列任务加载失败', 'error')
      }
      systemTasks.value = []
    } finally {
      systemTaskRefreshPending.value = false
      if (!silent) {
        systemTasksLoading.value = false
      }
    }
  }

  function startSystemTaskPolling() {
    window.clearInterval(systemTaskTimer.value)
    if (document.hidden) return
    systemTaskTimer.value = window.setInterval(() => {
      if (!systemTasksDialog.value) {
        stopSystemTaskPolling()
        return
      }
      void Promise.all([loadSystemTasks(true), loadDashboard(true)]).catch(() => undefined)
    }, 2000)
  }

  function stopSystemTaskPolling() {
    window.clearInterval(systemTaskTimer.value)
    systemTaskTimer.value = undefined
  }

  function syncSelectedSystemTaskIds() {
    const ids = new Set(interruptibleSystemTaskIds.value)
    selectedSystemTaskIds.value = selectedSystemTaskIds.value.filter((id) => ids.has(id))
  }

  function canInterruptSystemTask(task: SystemTask) {
    return (
      task.status === 'WAIT' || (systemTaskStatus.value === 'SLOW' && task.status === 'RUNNING')
    )
  }

  async function interruptSystemTask(task: SystemTask) {
    if (!canInterruptSystemTask(task)) return
    await interruptSystemTasks([task.id])
  }

  async function interruptSelectedSystemTasks() {
    const ids = [...selectedSystemTaskIds.value]
    if (!ids.length) return
    await interruptSystemTasks(ids)
  }

  async function interruptSystemTasks(ids: number[]) {
    if (!ids.length || systemTasksInterrupting.value) return
    systemTasksInterrupting.value = true
    try {
      const result = await api<SystemTaskInterruptResponse>('/api/system-tasks/interrupt', {
        method: 'POST',
        body: JSON.stringify({ ids })
      })
      selectedSystemTaskIds.value = selectedSystemTaskIds.value.filter(
        (id) => !result.interrupted_ids.includes(id)
      )
      await Promise.all([loadSystemTasks(), loadDashboard()])
      if (result.interrupted_ids.length) {
        actions.notify(`已中断 ${result.interrupted_ids.length} 个队列任务`)
      }
      if (result.skipped_ids.length) {
        actions.notify(`${result.skipped_ids.length} 个任务当前状态不可中断`, 'warning')
      }
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '队列任务中断失败', 'error')
      await loadSystemTasks().catch(() => undefined)
    } finally {
      systemTasksInterrupting.value = false
    }
  }

  return {
    loadDashboard,
    openSystemTasks,
    loadSystemTasks,
    startSystemTaskPolling,
    stopSystemTaskPolling,
    syncSelectedSystemTaskIds,
    canInterruptSystemTask,
    interruptSystemTask,
    interruptSelectedSystemTasks,
    interruptSystemTasks
  }
}
