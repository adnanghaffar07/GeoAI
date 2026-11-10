import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SharePhoto } from '@/components/share-photo'
import { json } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const LINK = { id: 'l1', image_id: 'img1', created_at: '2026-11-10T10:00:00Z', expires_at: '2026-11-17T10:00:00Z', revoked_at: null, state: 'active' }

describe('Share a photo', () => {
  it('makes a link, shows it once, and can cancel it', async () => {
    let listed: object[] = []
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/revoke')) {
        listed = []
        return Promise.resolve(json({ ...LINK, state: 'cancelled' }))
      }
      if (init?.method === 'POST') {
        listed = [{ ...LINK, url: null }]
        return Promise.resolve(json({ ...LINK, url: '/api/v1/shared/secret123' }, 201))
      }
      return Promise.resolve(json(listed))
    })
    renderWithProviders(<SharePhoto imageId="img1" />)
    await userEvent.click(screen.getByRole('button', { name: /Make a share link/ }))
    expect(await screen.findByLabelText('Share link')).toHaveValue(`${window.location.origin}/api/v1/shared/secret123`)
    const body = JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.body))
    expect(body).toEqual({ days: 7 })
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel link' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Cancel link' })).not.toBeInTheDocument())
  })
})
