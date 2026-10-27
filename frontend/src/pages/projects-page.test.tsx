import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ProjectsPage } from '@/pages/projects-page'
import { ADMIN_WITH_PROJECTS, json, MEMBER_ME, page, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

describe('ProjectsPage', () => {
  it('shows project cards with photo counts and the create button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(page([{ ...PROJECT, counts: { ...PROJECT.counts, images: 12, images_missing_location: 3, images_with_quality_flags: 1 } }])),
    )
    renderWithProviders(<ProjectsPage />, { me: ADMIN_WITH_PROJECTS })

    expect(await screen.findByText('Downtown streets')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('Your role: Field collector')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Create project' })).toHaveAttribute('href', '/projects/new')
  })

  it('tells someone without projects to ask their project manager', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page([])))
    renderWithProviders(<ProjectsPage />, { me: MEMBER_ME })

    expect(await screen.findByText(/haven't been added to a project yet/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Create project' })).not.toBeInTheDocument()
  })
})
