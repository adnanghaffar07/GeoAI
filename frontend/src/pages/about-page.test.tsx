import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AboutPage } from '@/pages/about-page'
import { expectNoAccessibilityProblems } from '@/test/a11y'
import { renderWithProviders } from '@/test/render'

describe('About page (team lead plan, Phase 1)', () => {
  it('can be read without signing in: FAQ, terms, accessibility and privacy', async () => {
    const { container } = renderWithProviders(<AboutPage />, { me: null, route: '/about' })
    expect(screen.getByRole('heading', { name: 'Is the AI always right?' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How to use the app, step by step' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Upload road photos' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Where your data is stored' })).toBeInTheDocument()
    expect(screen.getByText(/encrypted \(AES-256-GCM\)/)).not.toBeVisible() // answers open on click
    const question = screen.getByRole('button', { name: 'Is the AI always right?' })
    await userEvent.click(question)
    expect(question).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Every AI suggestion is checked by a person/)).toBeVisible()
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search the questions' }), 'camera')
    expect(screen.getByRole('button', { name: 'Where do the traffic camera pictures come from?' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.queryByRole('button', { name: 'Is the AI always right?' })).not.toBeInTheDocument()
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Search the questions' }))
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/sign-in')
    await expectNoAccessibilityProblems(container)
    await userEvent.click(screen.getByRole('tab', { name: 'Terms of use' }))
    expect(screen.getByText(/You use this application at your own risk/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Accessibility' }))
    expect(screen.getByText(/WCAG\) 2.1 level AA/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Privacy' }))
    expect(screen.getByRole('tab', { name: 'Privacy' })).toHaveAttribute('aria-selected', 'true')
  })
})
