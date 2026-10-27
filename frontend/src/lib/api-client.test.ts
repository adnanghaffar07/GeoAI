import { describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest } from '@/lib/api-client'

function mockFetch(response: Response | Error) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(() =>
      response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
    )
}

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

describe('apiRequest', () => {
  it('returns parsed JSON on success and calls /api + path', async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: 'ok' }))

    await expect(apiRequest('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetchSpy).toHaveBeenCalledWith('/api/health', expect.objectContaining({ method: 'GET' }))
  })

  it('sends JSON bodies with a JSON content type', async () => {
    const fetchSpy = mockFetch(jsonResponse({ id: 1 }, 201))

    await apiRequest('/projects', { method: 'POST', body: { name: 'Pilot' } })

    const init = fetchSpy.mock.calls[0]?.[1]
    expect(init?.body).toBe('{"name":"Pilot"}')
    expect(init?.headers).toMatchObject({ 'Content-Type': 'application/json' })
  })

  it('turns the standard error format into an ApiError', async () => {
    mockFetch(
      jsonResponse(
        { error: { code: 'not_found', message: 'Project not found.', details: null, request_id: 'req-1' } },
        404,
      ),
    )

    const error = await apiRequest('/projects/9').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'Project not found.', requestId: 'req-1' })
    expect((error as ApiError).isClientError).toBe(true)
  })

  it('reports network failures as network_error', async () => {
    mockFetch(new TypeError('Failed to fetch'))

    await expect(apiRequest('/health')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })

  it('handles non-JSON error pages (e.g. a proxy error)', async () => {
    mockFetch(new Response('<html>Bad Gateway</html>', { status: 502, headers: { 'X-Request-ID': 'r2' } }))

    await expect(apiRequest('/health')).rejects.toMatchObject({
      status: 502,
      code: 'unexpected_response',
      requestId: 'r2',
    })
  })
})
