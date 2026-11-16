import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { ProjectCamerasPage } from '@/pages/project/project-cameras-page'
import { ProjectLayout } from '@/pages/project/project-layout'
import { json, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

vi.mock('@/components/map/cameras-map', () => ({
  CamerasMap: ({ cameras, onSelect }: { cameras: { id: number }[]; onSelect: (id: number) => void }) => (
    <div aria-label="Map of traffic cameras">
      {cameras.map((c) => (
        <button key={c.id} type="button" onClick={() => onSelect(c.id)}>
          Pin {c.id}
        </button>
      ))}
    </div>
  ),
}))

const LIST = {
  source: 'Illinois Department of Transportation (Gateway Traveler Information)',
  licence: 'CC BY-SA 2.0',
  licence_url: 'https://creativecommons.org/licenses/by-sa/2.0/',
  cameras: [
    { id: 1804, location: 'Warrenville / Mill', direction: 'N', latitude: 41.81, longitude: -88.16, image_url: 'https://cctv.travelmidwest.com/snapshots/a.jpg', page_url: null, age_minutes: 3, too_old: false },
  ],
}

describe('Traffic cameras (items 8 and 10)', () => {
  it('shows the camera picture with its credit and saves a snapshot as a photo', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (init?.method === 'POST' && url.endsWith('/cameras/1804/snapshot')) return Promise.resolve(json({ duplicate: false, image: { id: 'img9' } }, 201))
      if (url.endsWith('/v1/projects/p1/cameras')) return Promise.resolve(json(LIST))
      if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(PROJECT))
      return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
    })
    renderWithProviders(
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectLayout />}>
          <Route path="cameras" element={<ProjectCamerasPage />} />
        </Route>
      </Routes>,
      { route: '/projects/p1/cameras' },
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Pin 1804' }))
    const panel = screen.getByRole('complementary', { name: 'Selected camera' })
    const picture = within(panel).getByAltText('Traffic camera: Warrenville / Mill, facing north')
    expect(picture.getAttribute('src')).toMatch(/^https:\/\/cctv\.travelmidwest\.com\/snapshots\/a\.jpg\?t=/)
    expect(within(panel).getByRole('link', { name: 'CC BY-SA 2.0' })).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: /Take snapshot/ }))
    expect(await within(panel).findByRole('status')).toHaveTextContent('Saved as a photo.')
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith('/cameras/1804/snapshot') && init?.method === 'POST')).toBe(true))
  })

  it('lists the nearest cameras with their location when none is inside the area', async () => {
    const near = { ...LIST.cameras[0], id: 77, location: 'Diehl / Freedom', distance_km: 1.4, image_url: 'https://cctv.travelmidwest.com/snapshots/b.jpg' }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/v1/projects/p1/cameras/nearby')) return Promise.resolve(json({ ...LIST, cameras: [near], within_km: 15 }))
      if (url.endsWith('/v1/projects/p1/cameras')) return Promise.resolve(json({ ...LIST, cameras: [] }))
      if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(PROJECT))
      return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
    })
    renderWithProviders(
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectLayout />}>
          <Route path="cameras" element={<ProjectCamerasPage />} />
        </Route>
      </Routes>,
      { route: '/projects/p1/cameras' },
    )
    expect(await screen.findByText('No traffic cameras in this area')).toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Cameras near this area' })
    expect(list).toHaveTextContent('Diehl / Freedom, facing north')
    expect(list).toHaveTextContent('About 1.4 km outside the area · location 41.81000, -88.16000')
    await userEvent.click(within(list).getByRole('button', { name: 'View picture' }))
    const panel = screen.getByRole('complementary', { name: 'Nearby camera' })
    expect(within(panel).getByAltText('Traffic camera: Diehl / Freedom, facing north')).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: /Take snapshot/ })).not.toBeInTheDocument()
  })
})
