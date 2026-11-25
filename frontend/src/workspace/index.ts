import { inject, provide, type InjectionKey } from 'vue'
import { createWorkspaceState } from './state'
import { installWorkspaceEffects } from './effects'
import type { WorkspaceActions } from './actions'
import { invalidateQueries } from '../api'
import { createSettingsActions } from './features/settings'
import { createFormattingActions } from './features/formatting'
import { createSearchActions } from './features/search'
import { createNavigationActions } from './features/navigation'
import { createDashboardActions } from './features/dashboard'
import { createDownloadsActions } from './features/downloads'
import { createMediaActions } from './features/media'
import { createFilesActions } from './features/files'
import { createLibraryActions } from './features/library'
import { createArtistsActions } from './features/artists'
import { createSitesActions } from './features/sites'
import { createPlaylistsActions } from './features/playlists'
import { createLogsActions } from './features/logs'
import { createPollingActions } from './features/polling'

function createWorkspace() {
  const actions = {} as WorkspaceActions
  const state = createWorkspaceState(actions)
  Object.assign(actions, createSettingsActions(state, actions))
  Object.assign(actions, createFormattingActions(state, actions))
  Object.assign(actions, createSearchActions(state, actions))
  Object.assign(actions, createNavigationActions(state, actions))
  Object.assign(actions, createDashboardActions(state, actions))
  Object.assign(actions, createDownloadsActions(state, actions))
  Object.assign(actions, createMediaActions(state, actions))
  Object.assign(actions, createFilesActions(state, actions))
  Object.assign(actions, createLibraryActions(state, actions))
  Object.assign(actions, createArtistsActions(state, actions))
  Object.assign(actions, createSitesActions(state, actions))
  Object.assign(actions, createPlaylistsActions(state, actions))
  Object.assign(actions, createLogsActions(state, actions))
  Object.assign(actions, createPollingActions(state, actions))
  installWorkspaceEffects(state, actions)
  async function refreshData(load: () => Promise<unknown>) {
    invalidateQueries()
    try {
      await load()
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '刷新失败', 'error')
    }
  }
  return { ...state, ...actions, refreshData }
}

export type Workspace = ReturnType<typeof createWorkspace>
const workspaceKey: InjectionKey<Workspace> = Symbol('musicpilot-workspace')

export function provideWorkspace() {
  const workspace = createWorkspace()
  provide(workspaceKey, workspace)
  return workspace
}

export function useWorkspace() {
  const workspace = inject(workspaceKey)
  if (!workspace) throw new Error('Workspace is unavailable')
  return workspace
}
