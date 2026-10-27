import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { PasswordField } from '@/components/ui/field'

describe('PasswordField', () => {
  it('hides the password until the eye button is pressed, then hides it again', async () => {
    render(<PasswordField label="Password" defaultValue="secret-123" />)
    const input = screen.getByLabelText('Password')
    expect(input).toHaveAttribute('type', 'password')

    await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(input).toHaveAttribute('type', 'text')
    expect(input).toHaveValue('secret-123')

    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(input).toHaveAttribute('type', 'password')
  })

  it('names the eye after its own field when there are two password boxes', () => {
    render(
      <>
        <PasswordField label="New password" />
        <PasswordField label="Repeat password" />
      </>,
    )
    expect(screen.getByRole('button', { name: 'Show new password' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show repeat password' })).toBeInTheDocument()
  })
})
