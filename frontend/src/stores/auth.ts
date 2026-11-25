import { ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, api, onUnauthorized, resetApiSession } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const status = ref<'checking' | 'authenticated' | 'anonymous' | 'error'>('checking')
  const error = ref('')
  let checking: Promise<void> | undefined

  onUnauthorized(() => {
    if (status.value === 'anonymous') return
    status.value = 'anonymous'
    resetApiSession()
  })

  function checkSession() {
    if (checking) return checking
    status.value = 'checking'
    error.value = ''
    checking = api('/api/auth/session', { cache: 'no-store' })
      .then(() => {
        status.value = 'authenticated'
      })
      .catch((cause: unknown) => {
        if (cause instanceof ApiError && cause.status === 401) {
          status.value = 'anonymous'
        } else {
          status.value = 'error'
          error.value = '暂时无法连接服务，请检查网络后重试。'
        }
      })
      .finally(() => {
        checking = undefined
      })
    return checking
  }

  async function login(username: string, password: string) {
    await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
    resetApiSession()
    status.value = 'authenticated'
  }

  return { status, error, checkSession, login }
})
