import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ModelLabel } from '@/components/findings/model-label'

describe('ModelLabel', () => {
  it('marks test-detector results as not real', () => {
    render(<ModelLabel testDetector />)
    expect(screen.getByText('TEST DETECTOR: not a real detection')).toBeInTheDocument()
  })

  it('marks trial-model results as not accuracy-approved', () => {
    render(<ModelLabel trialModel />)
    expect(screen.getByText('TRIAL MODEL: accuracy not approved')).toHaveAttribute('title', expect.stringContaining('a person must check every photo'))
  })

  it('shows nothing for an approved model', () => {
    const { container } = render(<ModelLabel />)
    expect(container).toBeEmptyDOMElement()
  })
})
