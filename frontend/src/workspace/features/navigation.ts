import router from '../../router'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'

export function createNavigationActions(state: WorkspaceState, actions: WorkspaceActions) {
  const { snackbar } = state

  function notify(text: string, color = 'success') {
    snackbar.value = { show: true, color, text }
  }

  function switchPage(page: string) {
    void router.push({ name: page })
  }

  return { notify, switchPage }
}
