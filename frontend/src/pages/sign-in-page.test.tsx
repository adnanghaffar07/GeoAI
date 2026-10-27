import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { safeNextPath } from '@/lib/safe-redirect'
import { SignInPage } from '@/pages/sign-in-page'
import { renderWithProviders } from '@/test/render'

describe('SignInPage', () => {
  it('shows field errors without calling the server', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<SignInPage />, { me: null, route: '/sign-in' })

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Enter your email.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('shows the server message for wrong credentials and keeps the email', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: 'not_authenticated', message: 'Email or password is incorrect.', details: null, request_id: 'r1' },
        }),
        { status: 401 },
      ),
    )
    renderWithProviders(<SignInPage />, { me: null, route: '/sign-in' })

    await userEvent.type(screen.getByLabelText('Email'), 'ada@city.test')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.')
    expect(screen.getByLabelText('Email')).toHaveValue('ada@city.test')
  })
})

describe('safeNextPath', () => {
  it('only allows paths inside this app', () => {
    expect(safeNextPath('/settings/team')).toBe('/settings/team')
    expect(safeNextPath('https://evil.example')).toBe('/')
    expect(safeNextPath('//evil.example')).toBe('/')
    expect(safeNextPath(null)).toBe('/')
  })
})
