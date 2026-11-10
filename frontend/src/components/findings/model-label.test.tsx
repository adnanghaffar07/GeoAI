import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ModelLabel } from '@/components/findings/model-label'

describe('ModelLabel', () => {
  it('marks test-detector results as not real', () => {
    render(<ModelLabel testDetector />)
    expect(screen.getByText('TEST DETECTOR: not a real detection')).toBeInTheDocument()
  })

  it('shows no warning on trial-model results (decision TL-D2)', () => {
    const { container } = render(<ModelLabel trialModel />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows nothing for an approved model', () => {
    const { container } = render(<ModelLabel />)
    expect(container).toBeEmptyDOMElement()
  })
})
