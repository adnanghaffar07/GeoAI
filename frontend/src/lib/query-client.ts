import { MutationCache, QueryCache, QueryClient, type Mutation, type Query } from '@tanstack/react-query'

import { authQueryKeys } from '@/api/auth'
import { isApiError } from '@/lib/api-client'
import { logger } from '@/lib/logger'
import { notify } from '@/lib/notify'

const MAX_RETRIES = 2

/**
 * Optional text for a save (`useMutation({ meta: { success: 'Photo location saved' } })`):
 * shown as a short notice when it works. Failures are shown on the page itself, next to the form.
 */
declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: { success?: string }
  }
}

/** Retry network and server errors a couple of times, but never 4xx errors (they will fail again). */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (isApiError(error) && error.isClientError) return false
  return failureCount < MAX_RETRIES
}

/** Short summary of an error for the console: code, status and the reference to look up in the server log. */
function describe(error: unknown): Record<string, unknown> {
  if (isApiError(error)) return { status: error.status, code: error.code, message: error.message, ref: error.requestId }
  return { error }
}

export function createQueryClient(): QueryClient {
  // Created first so the error handlers below can reach it.
  // eslint-disable-next-line prefer-const -- assigned once, right below
  let client: QueryClient

  /** The session ended (expired, or signed out in another tab): go back to sign-in instead of showing errors everywhere. */
  function handleSessionEnded(error: unknown): boolean {
    if (!isApiError(error) || error.status !== 401 || !client.getQueryData(authQueryKeys.me)) return false
    logger.warn('Session ended; going back to the sign-in page')
    notify.info('Your session has ended. Please sign in again.')
    void client.invalidateQueries({ queryKey: authQueryKeys.me })
    return true
  }

  client = new QueryClient({
    queryCache: new QueryCache({
      onError: (error: unknown, query: Query<unknown, unknown, unknown>) => {
        if (handleSessionEnded(error)) return
        logger.error(`Could not load ${JSON.stringify(query.queryKey)}`, describe(error))
      },
    }),
    mutationCache: new MutationCache({
      onSuccess: (_data, _variables, _context, mutation: Mutation<unknown, unknown, unknown>) => {
        if (mutation.meta?.success) notify.success(mutation.meta.success)
      },
      onError: (error: unknown, _variables, _context, mutation: Mutation<unknown, unknown, unknown>) => {
        if (handleSessionEnded(error)) return
        logger.error(`Could not save (${mutation.options.mutationKey ? JSON.stringify(mutation.options.mutationKey) : 'change'})`, describe(error))
      },
    }),
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30_000, refetchOnWindowFocus: false },
      mutations: { retry: false }, // never repeat a write automatically
    },
  })
  return client
}
