import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect, type RefObject } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { AreaGeometry } from '@/api/projects'
import { NewProjectPage } from '@/pages/project-form-page'
import { ADMIN_WITH_PROJECTS, AREA, json, page } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

// The real map needs WebGL, which the test browser does not have. This stand-in
// offers one button that "draws" the test area.
vi.mock('@/components/map/area-draw-map', () => ({
  AreaDrawMap: ({
    onAreaDrawn,
    onRoadDrawn,
    onRoute,
    viewRef,
  }: {
    onAreaDrawn: (area: AreaGeometry) => void
    onRoadDrawn?: (shape: unknown) => void
    onRoute?: (from: [number, number], to: [number, number]) => void
    viewRef?: RefObject<(() => [number, number, number, number] | null) | null>
  }) => {
    // The real map tells the page which part of it is on screen.
    useEffect(() => {
      if (viewRef) viewRef.current = () => MAP_VIEW
    }, [viewRef])
    return (
    <>
      <button type="button" onClick={() => onAreaDrawn(AREA)}>
        Draw test area
      </button>
      <button type="button" onClick={() => onRoadDrawn?.(DRAWN_ROAD)}>
        Draw test road
      </button>
      <button type="button" onClick={() => onRoute?.([-88.15, 41.77], [-88.14, 41.78])}>
        Pick two test points
      </button>
    </>
    )
  },
}))

const MAP_VIEW: [number, number, number, number] = [-88.2, 41.7, -88.1, 41.8]

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

function mockApi(onCreate: (body: unknown) => Response, extra?: (url: string, init?: RequestInit) => Response | undefined) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    const special = extra?.(url, init)
    if (special) return Promise.resolve(special)
    if (url.endsWith('/finding-types')) return Promise.resolve(json(FINDING_TYPES))
    if (url.endsWith('/members')) return Promise.resolve(json(MEMBERS))
    if (url.endsWith('/projects') && init?.method === 'POST') return Promise.resolve(onCreate(JSON.parse(String(init.body))))
    if (url.startsWith('https://nominatim.openstreetmap.org/search'))
      return Promise.resolve(json([{ place_id: 7, display_name: 'Washington Street, Naperville, Illinois', geojson: ROAD_LINE }]))
    if (url.endsWith('/v1/geo/whole-road') && init?.method === 'POST')
      return Promise.resolve(json({ shape: { type: 'MultiLineString', coordinates: [ROAD_LINE.coordinates] }, pieces: 3, length_km: 4.2, source: 'overpass' }))
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
    // Each road is its own place; the server joins them into one area for saving.
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Save project' })).toBeEnabled())
    const calls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/v1/geo/area-from-place'))
    expect(JSON.parse(String(calls[1]?.[1]?.body)).add_to).toBeNull()
    expect(JSON.parse(String(calls[2]?.[1]?.body))).toEqual({ shape: STRIP, road_width_m: 50, add_to: STRIP })
    expect(screen.getAllByRole('button', { name: /^Remove Washington Street/ })).toHaveLength(2)

    await userEvent.click(screen.getByRole('button', { name: 'Save project' }))
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith('/projects') && init?.method === 'POST')).toBe(true))
    const createCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/projects') && init?.method === 'POST')
    expect(JSON.parse(String(createCall?.[1]?.body)).boundary).toEqual(TWO_STRIPS)
  })

  it('a road drawn on the map becomes its own place and is joined to the area already selected', async () => {
    const fetchMock = mockApi(() => json({ id: 'p9' }, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.click(screen.getByRole('button', { name: 'Draw test area' })) // an area first
    await userEvent.selectOptions(screen.getByLabelText('Road width (searched and drawn roads)'), '20')
    await userEvent.click(screen.getByRole('button', { name: 'Draw test road' })) // then a road

    await vi.waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/v1/geo/area-from-place'))).toHaveLength(2))
    const calls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/v1/geo/area-from-place'))
    expect(JSON.parse(String(calls[0]?.[1]?.body))).toEqual({ shape: DRAWN_ROAD, road_width_m: 20, add_to: null })
    expect(JSON.parse(String(calls[1]?.[1]?.body))).toEqual({ shape: STRIP, road_width_m: 20, add_to: AREA })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    const list = screen.getByRole('list', { name: 'Selected places' })
    expect(list).toHaveTextContent('Drawn area 1')
    expect(list).toHaveTextContent('Drawn road 1')
  })

  it('removes one selected place after asking, and keeps the others', async () => {
    const fetchMock = mockApi(() => json({ id: 'p9' }, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.click(screen.getByRole('button', { name: 'Draw test area' }))
    await userEvent.click(screen.getByRole('button', { name: 'Draw test area' }))
    expect(screen.getByRole('list', { name: 'Selected places' }).children).toHaveLength(2)

    await userEvent.click(screen.getByRole('button', { name: 'Remove Drawn area 1' }))
    const ask = screen.getByRole('alertdialog', { name: 'Remove a place' })
    expect(ask).toHaveTextContent('Remove Drawn area 1 from the survey area?')
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }))
    expect(screen.getByRole('list', { name: 'Selected places' }).children).toHaveLength(2)

    await userEvent.click(screen.getByRole('button', { name: 'Remove Drawn area 1' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    const list = screen.getByRole('list', { name: 'Selected places' })
    expect(list.children).toHaveLength(1)
    expect(list).toHaveTextContent('Drawn area 2')
    expect(list).not.toHaveTextContent('Drawn area 1')
    expect(screen.getByRole('button', { name: 'Save project' })).toBeEnabled()
    expect(fetchMock).toBeDefined()
  })

  it('selects the whole road: every part with the same name nearby', async () => {
    const fetchMock = mockApi(() => json({ id: 'p9' }, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.type(screen.getByLabelText('Find a road, address or area'), 'Washington Street, Naperville{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: 'Whole road: Washington Street (Naperville)' }))
    expect(await screen.findByText(/Whole road “Washington Street” selected: 3 parts, about 4.2 km/)).toBeInTheDocument()
    const ask = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/v1/geo/whole-road'))
    expect(JSON.parse(String(ask?.[1]?.body))).toEqual({ name: 'Washington Street', by_ref: false, latitude: 41.78, longitude: -88.15, radius_m: 5000, extent: 'radius', sources: ['overpass'] })
    expect(screen.getByRole('list', { name: 'Selected places' })).toHaveTextContent('Washington Street, Naperville (whole road)')
    expect(screen.getByText(/Source: OpenStreetMap fast search/)).toBeInTheDocument()
  })

  it('uses the backup sources when the map servers time out, and says which one worked', async () => {
    const unavailable = json({ error: { code: 'service_unavailable', message: 'The fast map search did not answer in time.', details: null, request_id: 'r1' } }, 503)
    const part = (id: number, line: unknown) => ({ place_id: id, osm_type: 'way', osm_id: id, name: 'Washington Street', display_name: 'Washington Street, Naperville', geojson: line })
    const fetchMock = mockApi(
      () => json({ id: 'p9' }, 201),
      (url) => {
        if (url.endsWith('/v1/geo/whole-road')) return unavailable
        if (url.includes('dedupe=0')) return json([part(11, ROAD_LINE), part(12, { type: 'LineString', coordinates: [[-88.15, 41.78], [-88.15, 41.79]] })])
        return undefined
      },
    )
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.type(screen.getByLabelText('Find a road, address or area'), 'Washington Street, Naperville{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: 'Whole road: Washington Street (Naperville)' }))

    expect(await screen.findByText(/Whole road “Washington Street” selected: 2 parts/)).toBeInTheDocument()
    expect(screen.getByText(/Source: OpenStreetMap place search \(backup\)/)).toBeInTheDocument()
    const backup = new URL(String(fetchMock.mock.calls.find(([url]) => String(url).includes('dedupe=0'))?.[0]))
    expect(Object.fromEntries(backup.searchParams)).toMatchObject({ dedupe: '0', limit: '40', bounded: '1', polygon_geojson: '1' })
  })

  it('falls back to our own database, and explains when every source fails', async () => {
    let databaseWorks = true
    const down = (message: string) => json({ error: { code: 'service_unavailable', message, details: null, request_id: 'r1' } }, 503)
    mockApi(
      () => json({ id: 'p9' }, 201),
      (url, init) => {
        if (url.endsWith('/v1/geo/whole-road')) {
          const { sources } = JSON.parse(String(init?.body)) as { sources: string[] }
          if (sources[0] === 'overpass') return down('The fast map search did not answer in time.')
          return databaseWorks
            ? json({ shape: { type: 'MultiLineString', coordinates: [ROAD_LINE.coordinates] }, pieces: 5, length_km: 3.1, source: 'database' })
            : down('Our road database has no such road.')
        }
        if (url.includes('dedupe=0')) return json([])
        return undefined
      },
    )
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')
    await userEvent.type(screen.getByLabelText('Find a road, address or area'), 'Washington Street, Naperville{Enter}')

    await userEvent.click(await screen.findByRole('button', { name: 'Whole road: Washington Street (Naperville)' }))
    expect(await screen.findByText(/selected: 5 parts, about 3.1 km/)).toBeInTheDocument()
    expect(screen.getByText(/Source: our own road database \(backup\)/)).toBeInTheDocument()

    databaseWorks = false
    await userEvent.type(screen.getByLabelText('Find a road, address or area'), '{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: 'Whole road: Washington Street (Naperville)' }))
    const problem = await screen.findByRole('alert')
    expect(problem).toHaveTextContent(/OpenStreetMap fast search/)
    expect(problem).toHaveTextContent(/OpenStreetMap place search \(backup\)/)
    expect(problem).toHaveTextContent(/our own road database \(backup\)/)
    expect(problem).toHaveTextContent(/Road between two points/)
  })

  it('finds all parts of a road by name inside the town limits, the map view, or within 10 km', async () => {
    const fetchMock = mockApi(() => json({ id: 'p9' }, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')
    const asked = () =>
      fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/v1/geo/whole-road')).map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>)

    // Nothing searched yet: the middle of the map is used, so only the town is asked for.
    await userEvent.type(screen.getByLabelText('Road name or route number'), 'Washington Street')
    await userEvent.click(screen.getByRole('button', { name: 'Find all parts by name' }))
    expect(asked()).toHaveLength(0)
    expect(await screen.findByText('Type the town name.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Town'), 'Naperville')
    await userEvent.click(screen.getByRole('button', { name: 'Find all parts by name' }))
    expect(await screen.findByText(/Whole road “Washington Street” selected: 3 parts, about 4.2 km, inside the limits of Naperville/)).toBeInTheDocument()
    expect(asked()[0]).toEqual({ name: 'Washington Street', by_ref: false, latitude: expect.closeTo(41.75, 5), longitude: expect.closeTo(-88.15, 5), radius_m: 5000, extent: 'town', town: 'Naperville', sources: ['overpass'] })

    await userEvent.selectOptions(screen.getByLabelText('Where to look'), 'The map I see now')
    await userEvent.click(screen.getByRole('button', { name: 'Find all parts by name' }))
    expect(await screen.findByText(/in the map view/)).toBeInTheDocument()
    expect(asked()[1]).toMatchObject({ extent: 'box', box: MAP_VIEW, latitude: expect.closeTo(41.75, 5), longitude: expect.closeTo(-88.15, 5) })

    await userEvent.selectOptions(screen.getByLabelText('Where to look'), 'Within 10 km')
    await userEvent.clear(screen.getByLabelText('Road name or route number'))
    await userEvent.type(screen.getByLabelText('Road name or route number'), 'IL 59')
    await userEvent.click(screen.getByRole('button', { name: 'Find all parts by name' }))
    expect(await screen.findByText(/within 10 km of the place/)).toBeInTheDocument()
    expect(asked()[2]).toMatchObject({ name: 'IL 59', by_ref: true, extent: 'radius', radius_m: 10_000 })
  })

  it('adds the streets between two clicked points as a road, with the source named', async () => {
    const fetchMock = mockApi(
      () => json({ id: 'p9' }, 201),
      (url) =>
        url.startsWith('https://router.project-osrm.org/route/v1/driving/')
          ? json({ code: 'Ok', routes: [{ distance: 1500, geometry: { type: 'LineString', coordinates: [[-88.15, 41.77], [-88.145, 41.775], [-88.14, 41.78]] } }] })
          : undefined,
    )
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.click(screen.getByRole('button', { name: 'Pick two test points' }))

    expect(await screen.findByText(/Road between two points added: about 1.5 km, 30 m wide. Source: OpenStreetMap route finder/)).toBeInTheDocument()
    expect(String(fetchMock.mock.calls.find(([url]) => String(url).includes('osrm'))?.[0])).toContain('/-88.15,41.77;-88.14,41.78?overview=full&geometries=geojson')
    const strip = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/v1/geo/area-from-place'))
    expect((JSON.parse(String(strip?.[1]?.body)) as { shape: { type: string } }).shape.type).toBe('LineString')
    expect(within(screen.getByRole('list', { name: 'Selected places' })).getByText(/Road between two points 1/)).toBeInTheDocument()
  })

  it('shows a plain message when no street route is found', async () => {
    mockApi(
      () => json({ id: 'p9' }, 201),
      (url) => (url.includes('osrm') ? json({ code: 'NoRoute', routes: [] }) : undefined),
    )
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.click(screen.getByRole('button', { name: 'Pick two test points' }))

    expect(await screen.findByText(/No street route was found between these two points/)).toBeInTheDocument()
  })
})
