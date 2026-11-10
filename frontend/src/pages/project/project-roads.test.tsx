import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectDetail } from '@/api/projects'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectRoadsPage } from '@/pages/project/project-roads-page'
import { json, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

vi.mock('@/components/map/roads-map', () => ({
  RoadsMap: ({ onBox }: { onBox: (box: [number, number, number, number]) => void }) => (
    <button type="button" onClick={() => onBox([-88.2, 41.7, -88.1, 41.8])}>
      Pick box
    </button>
  ),
}))

const PROJ: ProjectDetail = { ...PROJECT, road_risk_enabled: true, my_permissions: [...PROJECT.my_permissions, 'risk.view'] }

const road = (id: string, name: string, speed: number | null, level: string) => ({
  type: 'Feature',
  geometry: { type: 'LineString', coordinates: [[-88.15, 41.77], [-88.149, 41.77]] },
  properties: { section_id: id, name, road_type: 'secondary', length_m: 100, level, speed_limit_mph: speed, lanes: 2, surface: 'Asphalt', oneway: false, climate_level: 'high', traffic_level: 'missing', roughness_level: 'missing' },
})

describe('Roads-only view (item 11)', () => {
  it('lists roads with speed limits, recolours by speed, and narrows to a chosen area', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/roads.geojson?box=')) return Promise.resolve(json({ type: 'FeatureCollection', box: [-88.2, 41.7, -88.1, 41.8], features: [road('s1', 'Washington Street', 35, 'high')] }))
      if (url.includes('/roads.geojson')) return Promise.resolve(json({ type: 'FeatureCollection', box: null, features: [road('s1', 'Washington Street', 35, 'high'), road('s2', 'Ogden Avenue', null, 'low')] }))
      if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(PROJ))
      return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
    })
    renderWithProviders(
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectLayout />}>
          <Route path="roads" element={<ProjectRoadsPage />} />
        </Route>
      </Routes>,
      { route: '/projects/p1/roads' },
    )
    const list = await screen.findByRole('list', { name: 'Roads' })
    expect(await within(list).findByText('Washington Street')).toBeInTheDocument()
    expect(within(list).getByText(/speed limit not on the map/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Roads' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Colour roads by'), 'speed')
    const key = screen.getByRole('list', { name: 'Key: Speed limit' })
    expect(within(key).getByText('30–35 mph')).toBeInTheDocument()
    expect(within(key).getByText('Not on the map')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Pick box' }))
    expect(await screen.findByRole('heading', { name: 'Roads in the chosen area' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('box=-88.200000,41.700000,-88.100000,41.800000'))).toBe(true)
  })
})
