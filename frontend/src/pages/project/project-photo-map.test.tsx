import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectPhotoMapPage } from '@/pages/project/project-photo-map-page'
import { json, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

vi.mock('@/components/map/photos-map', () => ({
  PhotosMap: ({ data, onSelect }: { data?: { features: { id: string }[] }; onSelect: (id: string) => void }) => (
    <div aria-label="Map of photos">
      {data?.features.map((f) => (
        <button key={f.id} type="button" onClick={() => onSelect(f.id)}>
          Pin {f.id}
        </button>
      ))}
    </div>
  ),
}))

const DATA = {
  type: 'FeatureCollection',
  truncated: false,
  features: [
    {
      type: 'Feature',
      id: 'img1',
      geometry: { type: 'Point', coordinates: [-122.42, 37.775] },
      properties: {
        id: 'img1',
        original_filename: 'street.jpg',
        width_px: 1000,
        height_px: 500,
        taken_at: '2026-11-01T10:00:00Z',
        defect_count: 2,
        worst: 3,
        defects: [
          { id: 'f1', type_key: 'pothole', severity_key: 'high', review_status: 'verified', bbox: [10, 10, 200, 100] },
          { id: 'f2', type_key: 'surface_cracking', severity_key: null, review_status: 'ai_generated', bbox: [300, 200, 500, 400] },
        ],
      },
    },
  ],
}

describe('Photo map', () => {
  it('shows a photo with all its problem boxes when a pin is clicked', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/photos.geojson')) return Promise.resolve(json(DATA))
      if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(PROJECT))
      return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
    })
    renderWithProviders(
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectLayout />}>
          <Route path="photo-map" element={<ProjectPhotoMapPage />} />
        </Route>
      </Routes>,
      { route: '/projects/p1/photo-map' },
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Pin img1' }))
    const panel = screen.getByRole('complementary', { name: 'Selected photo' })
    expect(within(panel).getByAltText('Photo street.jpg')).toBeInTheDocument()
    expect(within(panel).getAllByTestId('photo-box')).toHaveLength(2)
    expect(within(panel).getByRole('link', { name: 'Pothole' })).toHaveAttribute('href', '/projects/p1/findings?selected=f1')
    expect(screen.getByRole('link', { name: 'Photo map' })).toBeInTheDocument()
  })
})
