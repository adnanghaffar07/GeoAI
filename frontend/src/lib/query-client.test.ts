import { describe, expect, it, vi } from 'vitest'

import { authQueryKeys } from '@/api/auth'
import { ApiError } from '@/lib/api-client'
import { getNotices } from '@/lib/notify'
import { createQueryClient } from '@/lib/query-client'

const signedIn = { user: { id: 'u1' }, memberships: [] }

describe('createQueryClient', () => {
  it('shows the success message of a save', async () => {
    const client = createQueryClient()
    await client.getMutationCache().build(client, { mutationFn: async () => 'ok', meta: { success: 'Photo location saved' } }).execute(undefined)
    expect(getNotices().map((notice) => notice.message)).toContain('Photo location saved')
  })

  it('when the session has ended, re-checks the sign-in instead of failing quietly', async () => {
    const client = createQueryClient()
    client.setQueryData(authQueryKeys.me, signedIn)
    const recheck = vi.spyOn(client, 'invalidateQueries')
    const ended = new ApiError({ status: 401, code: 'not_authenticated', message: 'Your session has ended.' })

    await expect(client.fetchQuery({ queryKey: ['projects'], queryFn: () => Promise.reject(ended) })).rejects.toBe(ended)

    expect(recheck).toHaveBeenCalledWith({ queryKey: authQueryKeys.me })
    expect(getNotices().map((notice) => notice.message)).toContain('Your session has ended. Please sign in again.')
  })

  it('a wrong password on the sign-in page (nobody signed in yet) does not trigger that', async () => {
    const client = createQueryClient()
    const recheck = vi.spyOn(client, 'invalidateQueries')
    const wrong = new ApiError({ status: 401, code: 'not_authenticated', message: 'Email or password is incorrect.' })
    await expect(client.getMutationCache().build(client, { mutationFn: () => Promise.reject(wrong) }).execute(undefined)).rejects.toBe(wrong)
    expect(recheck).not.toHaveBeenCalled()
  })
})
