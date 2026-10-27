import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Me } from '@/api/auth'
import { TeamPage } from '@/pages/team-page'
import { ADMIN_ME, renderWithProviders } from '@/test/render'

const MEMBERS = {
  items: [
    { user_id: 'u1', email: 'admin@city.test', full_name: 'Ada Admin', org_role: 'org_admin', is_active: true, joined_at: '2026-10-01T00:00:00Z' },
    { user_id: 'u2', email: 'bo@city.test', full_name: 'Bo Worker', org_role: 'org_member', is_active: true, joined_at: '2026-10-02T00:00:00Z' },
  ],
  page: 1,
  page_size: 2,
  total: 2,
}
const EMPTY = { items: [], page: 1, page_size: 0, total: 0 }

function mockApi(extra: (url: string, init?: RequestInit) => Response | undefined = () => undefined) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    const custom = extra(url, init)
    if (custom) return Promise.resolve(custom)
    if (url.endsWith('/members')) return Promise.resolve(new Response(JSON.stringify(MEMBERS)))
    if (url.endsWith('/invitations')) return Promise.resolve(new Response(JSON.stringify(EMPTY)))
    return Promise.reject(new Error(`unexpected ${url}`))
  })
}

describe('TeamPage', () => {
  it('lets an admin invite someone and shows the link once with Copy', async () => {
    mockApi((url, init) =>
      url.endsWith('/invitations') && init?.method === 'POST'
        ? new Response(
            JSON.stringify({
              id: 'i1',
              email: 'new@city.test',
              org_role: 'org_member',
              expires_at: '2026-10-21T00:00:00Z',
              created_at: '2026-10-14T00:00:00Z',
              invite_url: 'http://localhost:5173/invite/abc',
            }),
            { status: 201 },
          )
        : undefined,
    )
    renderWithProviders(<TeamPage />)

    expect(await screen.findByText('Bo Worker')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Email'), 'new@city.test')
    await userEvent.click(screen.getByRole('button', { name: 'Invite' }))

    expect(await screen.findByText('Invitation created')).toBeInTheDocument()
    expect(screen.getByLabelText('Link')).toHaveValue('http://localhost:5173/invite/abc')
    expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument()
  })

  it('asks for confirmation before removing someone', async () => {
    mockApi()
    renderWithProviders(<TeamPage />)

    const removeButtons = await screen.findAllByRole('button', { name: 'Remove' })
    await userEvent.click(removeButtons[1]!)

    expect(screen.getByRole('button', { name: 'Yes, remove' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('hides management controls from people without permission', async () => {
    const memberMe: Me = {
      ...ADMIN_ME,
      memberships: [{ ...ADMIN_ME.memberships[0]!, org_role: 'org_manager', permissions: ['org.view', 'org.members.view'] }],
    }
    mockApi()
    renderWithProviders(<TeamPage />, { me: memberMe })

    expect(await screen.findByText('Bo Worker')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invite' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByText('Pending invitations')).not.toBeInTheDocument()
  })

  it('explains that project roles are given inside each project', async () => {
    mockApi()
    renderWithProviders(<TeamPage />)

    expect(await screen.findByText('Organization roles and project roles')).toBeInTheDocument()
    expect(screen.getByText(/are given inside each project/)).toBeInTheDocument()
  })
})
