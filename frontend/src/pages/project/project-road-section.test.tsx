import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectDetail } from '@/api/projects'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectRoadSectionPage } from '@/pages/project/project-road-section-page'
import { json, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

vi.mock('@/components/map/road-risk-map', () => ({
  RoadRiskMap: () => <div>map</div>,
  RoadRiskLegend: () => <div>legend</div>,
}))

const MANAGER: ProjectDetail = { ...PROJECT, road_risk_enabled: true, my_permissions: [...PROJECT.my_permissions, 'risk.view'] }

const DETAIL = {
  section: { section_id: 's1', name: 'Washington Street', road_type: 'secondary', length_m: 100, position: 1, level: 'high', rank_in_area: 3, reasons: [], missing_inputs: [], factors: [] },
  road: { speed_limit_mph: 35, lanes: 4, surface: 'Asphalt', oneway: null, road_ref: null, source: 'OpenStreetMap contributors' },
  geometry: { type: 'LineString', coordinates: [[-88.15, 41.77], [-88.149, 41.77]] },
  history: [],
  inspections: [],
  levels_run: null,
  factors_run: null,
  label: '',
  notice: '',
}

describe('Road section: road details (item 12)', () => {
  it('shows the speed limit and marks missing details as not on the map', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/road-sections/s1/risk')) return Promise.resolve(json(DETAIL))
      if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(MANAGER))
      return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
    })
    renderWithProviders(
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectLayout />}>
          <Route path="road-risk/:sectionId" element={<ProjectRoadSectionPage />} />
        </Route>
      </Routes>,
      { route: '/projects/p1/road-risk/s1' },
    )
    const box = await screen.findByRole('region', { name: 'Road details' })
    expect(within(box).getByText('35 mph')).toBeInTheDocument()
    expect(within(box).getByText('Asphalt')).toBeInTheDocument()
    expect(within(box).getAllByText('Not on the map')).toHaveLength(2)
  })
})
