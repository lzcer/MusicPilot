import { api } from '../../api'
import type { WorkspaceState } from '../state'
import type { WorkspaceActions } from '../actions'
import type { Site, TestResponse } from '../../types/musicpilot'

export function createSitesActions(state: WorkspaceState, actions: WorkspaceActions) {
  const {
    sites,
    editingSiteId,
    siteForm,
    siteDialog,
    sitePrioritySaving,
    draggedSiteId,
    siteTesting
  } = state

  async function loadSites() {
    sites.value = await api<Site[]>('/api/sites')
  }

  function openNewSiteDialog() {
    editingSiteId.value = null
    siteForm.value = {
      name: '',
      base_url: '',
      cookie: '',
      auth_type: 'cookie',
      api_key: '',
      user_agent: '',
      priority: 100,
      max_concurrency: 2,
      use_proxy: false,
      enabled: true
    }
    siteDialog.value = true
  }

  function editSite(site: Site) {
    editingSiteId.value = site.id ?? null
    siteForm.value = {
      name: site.name,
      base_url: site.base_url,
      cookie: site.cookie ?? '',
      auth_type: site.auth_type ?? 'cookie',
      api_key: site.api_key ?? '',
      user_agent: site.user_agent ?? '',
      priority: site.priority,
      max_concurrency: site.max_concurrency,
      use_proxy: site.use_proxy,
      enabled: site.enabled
    }
    siteDialog.value = true
  }

  function sitePayload() {
    return { ...siteForm.value }
  }

  async function saveSite() {
    try {
      const editing = Boolean(editingSiteId.value)
      const site = await api<Site>(editing ? `/api/sites/${editingSiteId.value}` : '/api/sites', {
        method: editing ? 'PUT' : 'POST',
        body: JSON.stringify(sitePayload())
      })
      if (editing) {
        sites.value = sites.value.map((item) => (item.id === site.id ? site : item))
      } else {
        sites.value.push(site)
      }
      siteDialog.value = false
      actions.notify('站点已保存')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '站点保存失败', 'error')
    }
  }

  function startSiteDrag(site: Site) {
    if (!site.id || sitePrioritySaving.value) return
    draggedSiteId.value = site.id
  }

  function finishSiteDrag() {
    draggedSiteId.value = null
  }

  async function dropSite(site: Site) {
    const sourceId = draggedSiteId.value
    const targetId = site.id
    finishSiteDrag()
    if (!sourceId || !targetId || sourceId === targetId || sitePrioritySaving.value) return

    const original = [...sites.value]
    const sourceIndex = original.findIndex((item) => item.id === sourceId)
    const targetIndex = original.findIndex((item) => item.id === targetId)
    if (sourceIndex < 0 || targetIndex < 0) return

    const reordered = [...original]
    const [moved] = reordered.splice(sourceIndex, 1)
    if (!moved) return
    reordered.splice(targetIndex, 0, moved)
    const siteIds = reordered.map((item) => item.id).filter((id): id is string => Boolean(id))
    if (siteIds.length !== reordered.length) return

    sites.value = reordered.map((item, index) => ({ ...item, priority: index + 1 }))
    sitePrioritySaving.value = true
    try {
      sites.value = await api<Site[]>('/api/sites/priorities', {
        method: 'PUT',
        body: JSON.stringify({ site_ids: siteIds })
      })
      actions.notify('站点优先级已更新')
    } catch (error) {
      sites.value = original
      actions.notify(error instanceof Error ? error.message : '站点优先级保存失败', 'error')
    } finally {
      sitePrioritySaving.value = false
    }
  }

  function openDeleteSite(site: Site) {
    if (!site.id) return
    actions.openDeleteDialog({ kind: 'site', id: site.id, name: site.name })
  }

  async function testSite() {
    siteTesting.value = true
    try {
      const result = await api<TestResponse>('/api/sites/test', {
        method: 'POST',
        body: JSON.stringify(sitePayload())
      })
      actions.notify(result.message, result.ok ? 'success' : 'error')
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : '站点测试失败', 'error')
    } finally {
      siteTesting.value = false
    }
  }

  return {
    loadSites,
    openNewSiteDialog,
    editSite,
    sitePayload,
    saveSite,
    startSiteDrag,
    finishSiteDrag,
    dropSite,
    openDeleteSite,
    testSite
  }
}
