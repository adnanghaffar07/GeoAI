import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { RequireAuth } from '@/auth/require-auth'
import { expectNoAccessibilityProblems } from '@/test/a11y'
import { ADMIN_WITH_PROJECTS, json } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const NEEDS = { ...ADMIN_WITH_PROJECTS, agreement_required: true, agreement_version: '2026-11-10' }

describe('Terms after sign-in (team lead plan, Phase 1)', () => {
  it('shows the disclaimer before any page and opens the page after "I agree"', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...NEEDS, agreement_required: false }))
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/" element={<RequireAuth><h1>Overview</h1></RequireAuth>} />
      </Routes>,
      { me: NEEDS },
    )
    expect(screen.getByRole('dialog', { name: 'GeoInfraLens AI disclaimer' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Overview' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    await expectNoAccessibilityProblems(container)

    await userEvent.click(screen.getByRole('button', { name: 'I agree' }))

    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/auth/agreement')
    expect(JSON.parse(String(init.body))).toEqual({ version: '2026-11-10', remember: false })
  })
})
