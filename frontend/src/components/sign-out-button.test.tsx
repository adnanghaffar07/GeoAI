import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { RequireAuth } from '@/auth/require-auth'
import { SignOutButton } from '@/components/sign-out-button'
import { SignInPage } from '@/pages/sign-in-page'
import { renderWithProviders } from '@/test/render'

describe('SignOutButton', () => {
  it('ends the session and stays on the sign-in page (does not bounce back)', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    renderWithProviders(
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <h1>Overview</h1>
              <SignOutButton />
            </RequireAuth>
          }
        />
      </Routes>,
    )
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Overview' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/logout', expect.objectContaining({ method: 'POST' }))
  })
})
