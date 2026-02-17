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

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options

  let url = `${BASE_URL}${path}`
  if (params) {
    const searchParams = new URLSearchParams(params)
    url += `?${searchParams.toString()}`
  }

  const isFormData = fetchOptions.body instanceof FormData
  const headers: Record<string, string> = isFormData
    ? {} // Let browser set Content-Type with boundary for FormData
    : { 'Content-Type': 'application/json' }

  const response = await fetch(url, {
    ...fetchOptions,
    headers: {
      ...headers,
      ...fetchOptions.headers,
    },
    credentials: 'same-origin',
  })

  if (response.status === 401) {
    window.location.href = '/login'
    throw new ApiError(401, null)
  }

  let data: unknown
  try {
    data = await response.json()
  } catch {
    if (!response.ok) {
      throw new ApiError(response.status, { error: `Server error (${response.status})` })
    }
    throw new ApiError(response.status, { error: 'Invalid response from server' })
  }

  if (!response.ok) {
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

  delete: <T>(path: string) =>
    request<T>(path, { method: 'DELETE' }),
}

export { ApiError }
