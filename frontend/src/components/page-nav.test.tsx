import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { buildCrumbs, PageNav } from '@/components/page-nav'
import { renderWithProviders } from '@/test/render'

describe('Back and breadcrumbs', () => {
  it('builds the trail with names and skips levels that are not pages', () => {
    const trail = buildCrumbs('/projects/p1/road-risk/s1', { project: 'Wicker Park', road: 'Main Street' })
    expect(trail).toEqual([
      { label: 'Home', to: '/' },
      { label: 'Projects', to: '/projects' },
      { label: 'Wicker Park', to: '/projects/p1' },
      { label: 'Road risk', to: '/projects/p1/road-risk' },
      { label: 'Main Street', to: '/projects/p1/road-risk/s1' },
    ])
    expect(buildCrumbs('/settings/team', {})[1]).toEqual({ label: 'Settings', to: null })
    expect(buildCrumbs('/projects/p1/review/f1', {}).map((c) => c.to)).toContain('/projects/p1/findings')
  })

  it('Back goes one level up, and Home has no Back', async () => {
    renderWithProviders(
      <>
        <PageNav />
        <Routes>
          <Route path="/projects/:projectId/road-risk" element={<p>Road risk page</p>} />
          <Route path="*" element={null} />
        </Routes>
      </>,
      { route: '/projects/p1/road-risk/s1' },
    )
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toHaveTextContent('HomeProjectsProjectRoad riskRoad')
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByText('Road risk page')).toBeInTheDocument()
  })
})
