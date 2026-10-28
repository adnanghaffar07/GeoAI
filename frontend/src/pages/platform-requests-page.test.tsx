import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Me } from '@/api/auth'
import type { OrganizationRequest } from '@/api/platform'
import { PlatformRequestsPage } from '@/pages/platform-requests-page'
import { json } from '@/test/fixtures'
import { ADMIN_ME, renderWithProviders } from '@/test/render'

const PLATFORM_ME: Me = { ...ADMIN_ME, user: { ...ADMIN_ME.user, is_platform_admin: true } }

const REQUEST: OrganizationRequest = {
  id: 'req1',
  organization_name: 'Naperville Public Works',
  contact_name: 'Pat Rivera',
  contact_email: 'pat@naperville.test',
  phone: null,
  city_or_agency: 'City of Naperville',
  note: 'Spring road survey',
  status: 'pending',
  created_at: '2026-10-28T10:00:00Z',
  decided_at: null,
  decided_by_name: null,
  decision_note: null,
  organization_id: null,
}

describe('Organization requests page (CR-004)', () => {
  it('is not shown to people who are not platform admins', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<PlatformRequestsPage />, { me: ADMIN_ME, route: '/platform/requests' })

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('lists waiting requests and approving shows the invitation link to send', async () => {
    let approved = false
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/approve') && init?.method === 'POST') {
        approved = true
        return Promise.resolve(
          json({
            request: { ...REQUEST, status: 'approved', organization_id: 'org9' },
            invitation_url: 'https://geo.test/invite/abc123',
            invitation_expires_at: '2026-11-04T10:00:00Z',
          }),
        )
      }
      const items = approved ? [] : [REQUEST]
      return Promise.resolve(json({ items, pending_count: items.length }))
    })
    renderWithProviders(<PlatformRequestsPage />, { me: PLATFORM_ME, route: '/platform/requests' })

    const card = await screen.findByRole('article', { name: 'Naperville Public Works' })
    expect(within(card).getByText('pat@naperville.test')).toBeInTheDocument()
    expect(within(card).getByText('Spring road survey')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Waiting/ })).toHaveTextContent('1')

    await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))
    await userEvent.type(within(card).getByLabelText(/Note for the history/), 'Known pilot')
    await userEvent.click(within(card).getByRole('button', { name: 'Approve and create organization' }))

    expect(await screen.findByDisplayValue('https://geo.test/invite/abc123')).toBeInTheDocument()
    expect(screen.getByText(/email it to pat@naperville.test/)).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ note: 'Known pilot' })
    expect(await screen.findByText('No requests are waiting')).toBeInTheDocument()
  })

  it('rejecting needs a reason', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_input, init) => {
      if (init?.method === 'POST') return Promise.resolve(json({ ...REQUEST, status: 'rejected', decision_note: 'Not a road agency' }))
      return Promise.resolve(json({ items: [REQUEST], pending_count: 1 }))
    })
    renderWithProviders(<PlatformRequestsPage />, { me: PLATFORM_ME, route: '/platform/requests' })

    const card = await screen.findByRole('article', { name: 'Naperville Public Works' })
    await userEvent.click(within(card).getByRole('button', { name: 'Reject' }))
    const confirm = within(card).getByRole('button', { name: 'Reject request' })
    expect(confirm).toBeDisabled()

    await userEvent.type(within(card).getByLabelText(/Reason/), 'Not a road agency')
    await userEvent.click(confirm)

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(String(post?.[0])).toContain('/req1/reject')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ reason: 'Not a road agency' })
  })

  it('approved requests can get a new invitation link', async () => {
    const done = { ...REQUEST, status: 'approved' as const, decided_by_name: 'Ada Admin', decided_at: '2026-10-28T11:00:00Z', organization_id: 'org9' }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/invitation-link') && init?.method === 'POST')
        return Promise.resolve(json({ request: done, invitation_url: 'https://geo.test/invite/new456', invitation_expires_at: '2026-11-05T10:00:00Z' }))
      if (url.includes('status=approved')) return Promise.resolve(json({ items: [done], pending_count: 0 }))
      return Promise.resolve(json({ items: [], pending_count: 0 }))
    })
    renderWithProviders(<PlatformRequestsPage />, { me: PLATFORM_ME, route: '/platform/requests' })

    await userEvent.click(await screen.findByRole('tab', { name: 'Approved' }))
    const card = await screen.findByRole('article', { name: 'Naperville Public Works' })
    expect(within(card).getByText(/Approved by Ada Admin/)).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Make a new invite link' }))

    expect(await screen.findByDisplayValue('https://geo.test/invite/new456')).toBeInTheDocument()
  })
})
