import { computed, onScopeDispose, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

interface InstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export const usePwaStore = defineStore('pwa', () => {
  const online = ref(navigator.onLine)
  const installPrompt = shallowRef<InstallPromptEvent>()
  const installed = ref(
    window.matchMedia('(display-mode: standalone)').matches ||
      Boolean((navigator as Navigator & { standalone?: boolean }).standalone)
  )
  const installing = ref(false)
  const updateReady = ref(false)
  const showUpdate = ref(false)
  const updating = ref(false)
  const updateError = ref('')
  const canInstall = computed(() => Boolean(installPrompt.value) && !installed.value)
  const listeners = new AbortController()
  let initialized = false
  let registration: ServiceWorkerRegistration | undefined
  let registering = false
  const supported = import.meta.env.PROD && window.isSecureContext && 'serviceWorker' in navigator
  let controlled = Boolean(navigator.serviceWorker?.controller)
  let lastUpdateCheck = 0
  let registrationTimer: number | undefined
  let updateTimer: number | undefined
  let reloadTimer: number | undefined

  function offerUpdate() {
    updateReady.value = true
    showUpdate.value = true
  }

  async function checkForUpdate() {
    if (!supported || !online.value || document.hidden) return
    if (Date.now() - lastUpdateCheck < 60_000) return
    lastUpdateCheck = Date.now()
    if (!registration) {
      await register()
      return
    }
    try {
      await registration.update()
    } catch {
      // The active worker remains available when an update cannot be downloaded.
    }
  }

  async function register() {
    if (registering || registration) return
    registering = true
    try {
      registration = await navigator.serviceWorker.register('/sw.js', {
        scope: '/',
        updateViaCache: 'none'
      })
      if (registration.waiting) offerUpdate()
      const observeInstalling = () => {
        const worker = registration?.installing
        worker?.addEventListener(
          'statechange',
          () => {
            if (
              worker.state === 'installed' &&
              registration?.waiting &&
              navigator.serviceWorker.controller
            ) offerUpdate()
          },
          { signal: listeners.signal }
        )
      }
      registration.addEventListener('updatefound', observeInstalling, { signal: listeners.signal })
      observeInstalling()
      updateTimer = window.setInterval(() => void checkForUpdate(), 60 * 60_000)
    } catch (error) {
      console.warn('应用离线缓存暂不可用', error)
    } finally {
      registering = false
    }
  }

  function initialize() {
    if (initialized) return
    initialized = true
    const options = { signal: listeners.signal }
    window.addEventListener('online', () => {
      online.value = true
      lastUpdateCheck = 0
      void checkForUpdate()
    }, options)
    window.addEventListener('offline', () => {
      online.value = false
    }, options)
    window.addEventListener('beforeinstallprompt', (event) => {
      event.preventDefault()
      installPrompt.value = event as InstallPromptEvent
    }, options)
    window.addEventListener('appinstalled', () => {
      installed.value = true
      installPrompt.value = undefined
    }, options)
    if (!supported) return
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (updating.value) {
        window.location.reload()
      } else if (controlled) {
        offerUpdate()
      }
      controlled = true
    }, options)
    document.addEventListener('visibilitychange', () => void checkForUpdate(), options)
    const schedule = () => {
      registrationTimer = window.setTimeout(() => void register(), 2000)
    }
    if (document.readyState === 'complete') schedule()
    else window.addEventListener('load', schedule, { ...options, once: true })
  }

  async function install() {
    const prompt = installPrompt.value
    if (!prompt || installing.value) return
    installing.value = true
    try {
      await prompt.prompt()
      await prompt.userChoice
    } catch (error) {
      console.warn('无法打开应用安装提示', error)
    } finally {
      installPrompt.value = undefined
      installing.value = false
    }
  }

  function applyUpdate() {
    if (updating.value) return
    updateError.value = ''
    updating.value = true
    if (!registration?.waiting) {
      window.location.reload()
      return
    }
    registration.waiting.postMessage({ type: 'SKIP_WAITING' })
    reloadTimer = window.setTimeout(() => {
      updating.value = false
      updateError.value = '更新尚未完成，请稍后重试。'
    }, 15_000)
  }

  onScopeDispose(() => {
    listeners.abort()
    window.clearTimeout(registrationTimer)
    window.clearTimeout(reloadTimer)
    window.clearInterval(updateTimer)
  })

  return {
    online,
    canInstall,
    installing,
    installed,
    updateReady,
    showUpdate,
    updating,
    updateError,
    initialize,
    install,
    applyUpdate
  }
})
