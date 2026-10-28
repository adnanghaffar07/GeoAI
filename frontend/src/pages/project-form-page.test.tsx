import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { AreaGeometry } from '@/api/projects'
import { NewProjectPage } from '@/pages/project-form-page'
import { ADMIN_WITH_PROJECTS, AREA, json, page } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

// The real map needs WebGL, which the test browser does not have. This stand-in
// offers one button that "draws" the test area.
vi.mock('@/components/map/area-draw-map', () => ({
  AreaDrawMap: ({
    initialArea,
    onChange,
    onShapeAdded,
  }: {
    initialArea: AreaGeometry | null
    onChange: (area: AreaGeometry | null) => void
    onShapeAdded?: (shape: unknown, rest: AreaGeometry | null) => void
  }) => (
    <>
      <button type="button" onClick={() => onChange(AREA)}>
        Draw test area
      </button>
      <button type="button" onClick={() => onShapeAdded?.(DRAWN_ROAD, initialArea)}>
        Draw test road
      </button>
    </>
  ),
}))

const DRAWN_ROAD = { type: 'LineString', coordinates: [[-122.42, 37.77], [-122.41, 37.775]] }


const ROAD_LINE = { type: 'LineString', coordinates: [[-88.15, 41.77], [-88.15, 41.78]] }
const STRIP: AreaGeometry = {
  type: 'Polygon',
  coordinates: [[[-88.1503, 41.77], [-88.1497, 41.77], [-88.1497, 41.78], [-88.1503, 41.78], [-88.1503, 41.77]]],
}
const TWO_STRIPS: AreaGeometry = { type: 'MultiPolygon', coordinates: [STRIP.coordinates, STRIP.coordinates] }

const FINDING_TYPES = page([
  { key: 'pothole', label: 'Pothole', source: 'ai', is_placeholder: true, is_active: true },
  { key: 'sidewalk_observation', label: 'Sidewalk observation', source: 'manual', is_placeholder: true, is_active: true },
])
const MEMBERS = page([
  { user_id: 'u1', email: 'admin@city.test', full_name: 'Ada Admin', org_role: 'org_admin', is_active: true, joined_at: '2026-10-01T00:00:00Z' },
])

function mockApi(onCreate: (body: unknown) => Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (url.endsWith('/finding-types')) return Promise.resolve(json(FINDING_TYPES))
    if (url.endsWith('/members')) return Promise.resolve(json(MEMBERS))
    if (url.endsWith('/projects') && init?.method === 'POST') return Promise.resolve(onCreate(JSON.parse(String(init.body))))
    if (url.startsWith('https://nominatim.openstreetmap.org/search'))
      return Promise.resolve(json([{ place_id: 7, display_name: 'Washington Street, Naperville, Illinois', geojson: ROAD_LINE }]))
    if (url.endsWith('/v1/geo/area-from-place') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as { add_to: unknown }
      return Promise.resolve(json({ area: body.add_to ? TWO_STRIPS : STRIP, area_square_meters: 30000 }))
    }
    return Promise.reject(new Error(`unexpected ${url}`))
  })
}

describe('NewProjectPage', () => {
  it('explains every missing entry next to its field', async () => {
    mockApi(() => json({}, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.click(screen.getByRole('button', { name: 'Save project' }))

    expect(await screen.findByText('Enter a project name.')).toBeInTheDocument()
    expect(screen.getByText('Choose at least one finding type.')).toBeInTheDocument()
    expect(screen.getByText('Choose at least one technical reviewer.')).toBeInTheDocument()
    expect(screen.getByText(/Draw the survey area on the map/)).toBeInTheDocument()
  })

  it('sends the project and keeps the entries when the server refuses it', async () => {
    const fetchMock = mockApi(() =>
      json(
        { error: { code: 'validation_error', message: 'The survey area shape is not valid. Check that its edges do not cross.', details: null, request_id: 'r1' } },
        422,
      ),
    )
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.type(screen.getByLabelText('Project name'), 'Downtown streets')
    await userEvent.click(screen.getByLabelText(/Pothole/))
    await userEvent.click(screen.getByLabelText(/Ada Admin/))
    await userEvent.click(screen.getByRole('button', { name: 'Draw test area' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save project' }))

    expect(await screen.findByText(/edges do not cross/)).toBeInTheDocument()
    expect(screen.getByLabelText('Project name')).toHaveValue('Downtown streets')
    const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      name: 'Downtown streets',
      finding_type_keys: ['pothole'],
      reviewer_user_ids: ['u1'],
      boundary: AREA,
      road_category: null,
    })
  })

  it('selects a road as a strip of the chosen width, and adds a second road', async () => {
    const fetchMock = mockApi(() => json({ id: 'p9' }, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.type(screen.getByLabelText('Project name'), 'Washington St survey')
    await userEvent.click(screen.getByLabelText(/Pothole/))
    await userEvent.click(screen.getByLabelText(/Ada Admin/))
    await userEvent.selectOptions(screen.getByLabelText('Road width (searched and drawn roads)'), '50')
    await userEvent.type(screen.getByLabelText('Find a road, address or area'), 'Washington Street, Naperville{Enter}')
    const result = await screen.findByRole('button', { name: /Washington Street, Naperville, Illinois/ })
    expect(result).toHaveTextContent('Road')
    expect(result).toHaveTextContent('50 m wide strip along this road')
    await userEvent.click(result)

    expect(await screen.findByText(/Road “Washington Street” \(50 m wide\) selected/)).toBeInTheDocument()
    const first = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/v1/geo/area-from-place'))
    expect(JSON.parse(String(first?.[1]?.body))).toEqual({ shape: ROAD_LINE, road_width_m: 50, add_to: null })

    // After a road, the next road is added to the area (the choice is preselected).
    expect(screen.getByLabelText('Add to the area')).toBeChecked()
    await userEvent.type(screen.getByLabelText('Find a road, address or area'), '{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: /Washington Street, Naperville, Illinois/ }))
    expect(await screen.findByText(/added to the area/)).toBeInTheDocument()
    const calls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/v1/geo/area-from-place'))
    expect(JSON.parse(String(calls[1]?.[1]?.body)).add_to).toEqual(STRIP)

    await userEvent.click(screen.getByRole('button', { name: 'Save project' }))
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith('/projects') && init?.method === 'POST')).toBe(true))
    const createCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/projects') && init?.method === 'POST')
    expect(JSON.parse(String(createCall?.[1]?.body)).boundary).toEqual(TWO_STRIPS)
  })

  it('a road drawn on the map is joined to the area already selected', async () => {
    const fetchMock = mockApi(() => json({ id: 'p9' }, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.click(screen.getByRole('button', { name: 'Draw test area' })) // an area first
    await userEvent.selectOptions(screen.getByLabelText('Road width (searched and drawn roads)'), '20')
    await userEvent.click(screen.getByRole('button', { name: 'Draw test road' })) // then a road

    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/v1/geo/area-from-place'))).toBe(true))
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/v1/geo/area-from-place'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ shape: DRAWN_ROAD, road_width_m: 20, add_to: AREA })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
