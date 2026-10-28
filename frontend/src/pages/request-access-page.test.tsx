import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { RequestAccessPage } from '@/pages/request-access-page'
import { SignInPage } from '@/pages/sign-in-page'
import { json } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

async function fillForm() {
  await userEvent.type(screen.getByLabelText('Organization name'), 'Naperville Public Works')
  await userEvent.type(screen.getByLabelText('City or agency'), 'City of Naperville')
  await userEvent.type(screen.getByLabelText('Your name'), 'Pat Rivera')
  await userEvent.type(screen.getByLabelText('Work email'), 'pat@naperville.test')
}

describe('Request access (CR-004)', () => {
  it('is linked from the sign-in page', () => {
    renderWithProviders(<SignInPage />, { me: null, route: '/sign-in' })

    expect(screen.getByRole('link', { name: 'Request access' })).toHaveAttribute('href', '/request-access')
  })

  it('explains missing fields without calling the server', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<RequestAccessPage />, { me: null, route: '/request-access' })

    await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

    expect(await screen.findByText('Enter your organization’s name.')).toBeInTheDocument()
    expect(screen.getByText('Enter your work email.')).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('sends the request and says what happens next (no password asked)', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(json({ message: 'Thank you. Your request has been sent.' }, 202))
    renderWithProviders(<RequestAccessPage />, { me: null, route: '/request-access' })
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()

    await fillForm()
    await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

    expect(await screen.findByText('Thank you. Your request has been sent.')).toBeInTheDocument()
    expect(screen.getByText(/You cannot sign in yet/)).toBeInTheDocument()
    const [url, init] = fetchMock.mock.calls[0]!
    expect(String(url)).toContain('/api/v1/organization-requests')
    expect(JSON.parse(String(init?.body))).toMatchObject({ contact_email: 'pat@naperville.test', website: '' })
  })

  it('shows the server message when a request is already waiting', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ error: { code: 'conflict', message: 'A request for this email is already waiting for review.', details: null, request_id: 'r1' } }, 409),
    )
    renderWithProviders(<RequestAccessPage />, { me: null, route: '/request-access' })

    await fillForm()
    await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already waiting for review')
  })
})
