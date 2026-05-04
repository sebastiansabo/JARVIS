import { telemetry } from '@/lib/telemetry'

const BASE_URL = ''

interface ApiOptions extends RequestInit {
  params?: Record<string, string>
}

class ApiError extends Error {
  constructor(
    public status: number,
    public data: unknown,
  ) {
    super(`API Error ${status}`)
    this.name = 'ApiError'
  }
}

function extractMsg(data: unknown): string {
  if (data && typeof data === 'object' && 'error' in data) {
    return String((data as { error: unknown }).error)
  }
  return 'Unknown error'
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options
  const method = (fetchOptions.method || 'GET').toUpperCase()

  let url = `${BASE_URL}${path}`
  if (params) {
    const searchParams = new URLSearchParams(params)
    url += `?${searchParams.toString()}`
  }

  const isFormData = fetchOptions.body instanceof FormData
  const headers: Record<string, string> = isFormData
    ? {} // Let browser set Content-Type with boundary for FormData
    : { 'Content-Type': 'application/json' }

  let response: Response
  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers: {
        ...headers,
        ...fetchOptions.headers,
      },
      credentials: 'same-origin',
    })
  } catch (err) {
    // Network error (offline, DNS failure, CORS, etc.)
    telemetry.trackApiError(path, method, 0, err instanceof Error ? err.message : 'Network error')
    throw err
  }

  if (response.status === 401) {
    window.location.href = '/login'
    throw new ApiError(401, null)
  }

  let data: unknown
  try {
    data = await response.json()
  } catch {
    if (!response.ok) {
      const apiErr = new ApiError(response.status, { error: `Server error (${response.status})` })
      telemetry.trackApiError(path, method, response.status, `Server error (${response.status})`)
      throw apiErr
    }
    throw new ApiError(response.status, { error: 'Invalid response from server' })
  }

  if (!response.ok) {
    telemetry.trackApiError(path, method, response.status, extractMsg(data))
    throw new ApiError(response.status, data)
  }

  return data as T
}

export const api = {
  get: <T>(path: string, params?: Record<string, string>) =>
    request<T>(path, { method: 'GET', params }),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'DELETE',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),
}

export { ApiError }
