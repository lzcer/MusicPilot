import { createRouter, createWebHistory } from 'vue-router'

const positions = new Map<string, { left: number; top: number }>()
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('../pages/DashboardPage.vue')
    },
    { path: '/search', name: 'search', component: () => import('../pages/SearchPage.vue') },
    {
      path: '/downloads',
      name: 'downloads',
      component: () => import('../pages/DownloadsPage.vue')
    },
    { path: '/media', name: 'media', component: () => import('../pages/MediaPage.vue') },
    { path: '/files', name: 'files', component: () => import('../pages/FilesPage.vue') },
    {
      path: '/discovery',
      name: 'discovery',
      component: () => import('../pages/DiscoveryPage.vue')
    },
    {
      path: '/music-library',
      name: 'musicLibrary',
      component: () => import('../pages/MusicLibraryPage.vue')
    },
    {
      path: '/playlists',
      name: 'playlists',
      component: () => import('../pages/PlaylistsPage.vue')
    },
    { path: '/artists', name: 'artists', component: () => import('../pages/ArtistsPage.vue') },
    { path: '/sites', name: 'sites', component: () => import('../pages/SitesPage.vue') },
    { path: '/logs', name: 'logs', component: () => import('../pages/LogsPage.vue') },
    { path: '/settings', name: 'settings', component: () => import('../pages/SettingsPage.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
  ],
  scrollBehavior(to, _from, savedPosition) {
    return savedPosition ?? positions.get(to.path) ?? { left: 0, top: 0 }
  }
})

router.beforeEach((_to, from) => {
  positions.set(from.path, { left: window.scrollX, top: window.scrollY })
})

router.onError((error) => {
  console.error('页面加载失败', error)
  window.dispatchEvent(new CustomEvent('musicpilot:route-error'))
})

export default router
