/**
 * The single way the frontend talks to the backend.
 *
 * Every failure becomes an `ApiError` with the backend's standard fields
 * (`code`, `message`, `details`, `requestId`), including failures that never
 * reach the backend (network down) or return something unexpected.
 */

import { logger } from '@/lib/logger'

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details: unknown
    request_id: string | null
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | null

  constructor(params: {
    status: number
    code: string
    message: string
    details?: unknown
    requestId?: string | null
  }) {
    super(params.message)
    this.name = 'ApiError'
    this.status = params.status
    this.code = params.code
    this.details = params.details ?? null
    this.requestId = params.requestId ?? null
  }

  /** True for 4xx errors: retrying the same request will not help. */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const error = (value as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  )
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return undefined // not JSON; caller decides what that means
  }
}

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  /** Sent as JSON. For file uploads pass a FormData instead. */
  body?: unknown
  signal?: AbortSignal
}

/**
 * Call the backend API. `path` starts after `/api`, e.g. `apiRequest('/health')`.
 *
 * @throws ApiError on network failure, non-2xx responses, or unreadable responses.
 */
export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = options
  const headers: Record<string, string> = { Accept: 'application/json' }
  let requestBody: BodyInit | undefined

  if (body instanceof FormData) {
    requestBody = body // the browser sets the multipart Content-Type itself
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }

  let response: Response
  const started = performance.now()
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: requestBody,
      signal,
      credentials: 'same-origin', // send the session cookie
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    logger.request(method, path, 0, performance.now() - started, null)
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: 'Cannot reach the server. Check your connection and try again.',
    })
  }

  const data = await readJson(response)
  const headerRequestId = response.headers.get('X-Request-ID')
  logger.request(method, path, response.status, performance.now() - started, headerRequestId)

  if (!response.ok) {
    if (isApiErrorBody(data)) {
      throw new ApiError({
        status: response.status,
        code: data.error.code,
        message: data.error.message,
        details: data.error.details,
        requestId: data.error.request_id ?? headerRequestId,
      })
    }
    throw new ApiError({
      status: response.status,
      code: 'unexpected_response',
      message:
        response.status >= 500
          ? 'The server is having a problem right now. Please try again in a minute.'
          : `The request could not be completed (error ${response.status}). Please try again.`,
      requestId: headerRequestId,
    })
  }

  if (data === undefined) {
    throw new ApiError({
      status: response.status,
      code: 'invalid_response',
      message: 'The server sent an answer the app could not read. Please reload the page and try again.',
      requestId: headerRequestId,
    })
  }
  return data as T
}
