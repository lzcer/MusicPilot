export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const queries = new Map<string, { value: unknown; expiresAt: number }>()
const pending = new Map<string, Promise<unknown>>()
const controllers = new Set<AbortController>()
const unauthorizedListeners = new Set<() => void>()
let generation = 0

export function onUnauthorized(listener: () => void) {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

export function invalidateQueries(prefixes?: string[]) {
  generation += 1
  for (const key of queries.keys()) {
    if (!prefixes || prefixes.some((prefix) => key.startsWith(prefix))) queries.delete(key)
  }
  for (const key of pending.keys()) {
    if (!prefixes || prefixes.some((prefix) => key.startsWith(prefix))) pending.delete(key)
  }
}

function invalidateMutation(url: string) {
  const resource = url.split('/')[2]?.split('?')[0]
  const affected: Record<string, string[]> = {
    sites: ['sites'],
    settings: ['settings', 'files', 'media', 'dashboard', 'about'],
    playlists: ['playlists', 'music-library', 'downloads', 'dashboard'],
    'music-platforms': ['music-platforms', 'playlists'],
    'music-library': ['music-library', 'artists', 'playlists', 'dashboard'],
    artists: ['artists', 'music-library'],
    downloads: ['downloads', 'media', 'playlists', 'dashboard'],
    media: ['media', 'files', 'music-library', 'playlists', 'dashboard'],
    files: ['files', 'media', 'music-library', 'playlists', 'dashboard']
  }
  const resources = affected[resource]
  if (resources) invalidateQueries(resources.map((name) => `/api/${name}`))
}

export function resetApiSession() {
  invalidateQueries()
  for (const controller of controllers) controller.abort()
  controllers.clear()
}

function queryLifetime(url: string) {
  const path = url.split('?')[0]
  if (path.startsWith('/api/discovery/')) return 5 * 60_000
  if (path === '/api/about') return 5 * 60_000
  if (
    [
      '/api/sites',
      '/api/settings/downloaders',
      '/api/settings/media-servers',
      '/api/settings/notifiers'
    ].includes(path)
  )
    return 60_000
  if (['/api/music-library', '/api/playlists', '/api/artists', '/api/media'].includes(path))
    return 30_000
  return 0
}

async function request(url: string, options: RequestInit, parseBody = true) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  if (options.signal?.aborted) controller.abort()
  controllers.add(controller)
  try {
    const response = await fetch(url, {
      credentials: 'include',
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...options.headers }
    })
    if (!response.ok) {
      const error = await responseError(response)
      if (response.status === 401 && !url.startsWith('/api/auth/')) {
        for (const listener of unauthorizedListeners) listener()
      }
      throw new ApiError(error.message, response.status, error.detail)
    }
    return response.status === 204 || !parseBody ? undefined : await response.json()
  } finally {
    controllers.delete(controller)
    options.signal?.removeEventListener('abort', abort)
  }
}

export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const read = !options.method || options.method.toUpperCase() === 'GET'
  if (!read) {
    const value = await request(url, options)
    invalidateMutation(url)
    return value as T
  }
  const cacheable = !options.signal && !options.headers && options.cache !== 'no-store'
  const entry = cacheable ? queries.get(url) : undefined
  if (entry && entry.expiresAt > Date.now()) return structuredClone(entry.value) as T
  if (cacheable && pending.has(url)) return structuredClone(await pending.get(url)) as T
  const requestGeneration = generation
  const task = request(url, options).then((value) => {
    const lifetime = cacheable ? queryLifetime(url) : 0
    if (lifetime && generation === requestGeneration) {
      if (queries.size >= 100) queries.delete(queries.keys().next().value!)
      queries.set(url, { value: structuredClone(value), expiresAt: Date.now() + lifetime })
    }
    return value
  })
  if (cacheable) pending.set(url, task)
  try {
    return structuredClone(await task) as T
  } finally {
    if (pending.get(url) === task) pending.delete(url)
  }
}

export async function apiNoContent(url: string, options: RequestInit = {}) {
  await request(url, options, false)
  invalidateMutation(url)
}

export async function readError(response: Response) {
  return (await responseError(response)).message
}

async function responseError(response: Response) {
  const text = await response.text()
  if (!text) return { message: response.statusText, detail: null }
  try {
    const data = JSON.parse(text) as { detail?: unknown; message?: unknown }
    if (typeof data.detail === 'string') return { message: data.detail, detail: data.detail }
    if (typeof data.message === 'string') return { message: data.message, detail: data.detail }
    if (data.detail && typeof data.detail === 'object') {
      const detail = data.detail as { message?: unknown }
      if (typeof detail.message === 'string')
        return { message: detail.message, detail: data.detail }
    }
    return { message: text, detail: data.detail }
  } catch {
    return { message: text, detail: text }
  }
}
