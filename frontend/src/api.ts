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

export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {})
    }
  })
  if (!response.ok) {
    const error = await responseError(response)
    throw new ApiError(error.message, response.status, error.detail)
  }
  return response.json() as Promise<T>
}

export async function apiNoContent(url: string, options: RequestInit = {}) {
  const response = await fetch(url, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {})
    }
  })
  if (!response.ok) {
    const error = await responseError(response)
    throw new ApiError(error.message, response.status, error.detail)
  }
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
      if (typeof detail.message === 'string') return { message: detail.message, detail: data.detail }
    }
    return { message: text, detail: data.detail }
  } catch {
    return { message: text, detail: text }
  }
}
