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
  AreaDrawMap: ({ onChange }: { onChange: (area: AreaGeometry | null) => void }) => (
    <button type="button" onClick={() => onChange(AREA)}>
      Draw test area
    </button>
  ),
}))


/** Coordinates rounded to ~1 mm, so tiny floating-point differences do not matter. */
const rounded = (area: { type: string; coordinates: unknown }) => ({
  ...area,
  coordinates: JSON.parse(JSON.stringify(area.coordinates), (_key, value: unknown) => (typeof value === 'number' ? Math.round(value * 1e8) / 1e8 : value)),
})

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
      return Promise.resolve(
        json([{ place_id: 7, display_name: 'Washington Street, Naperville, Illinois', boundingbox: ['41.77', '41.78', '-88.15', '-88.14'] }]),
      )
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

  it('selects the survey area from a searched street', async () => {
    const fetchMock = mockApi(() => json({ id: 'p9' }, 201))
    renderWithProviders(<NewProjectPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Pothole')

    await userEvent.type(screen.getByLabelText('Project name'), 'Washington St survey')
    await userEvent.click(screen.getByLabelText(/Pothole/))
    await userEvent.click(screen.getByLabelText(/Ada Admin/))
    await userEvent.type(screen.getByLabelText('Find a street, neighborhood or city'), 'Washington Street, Naperville{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: /Washington Street, Naperville, Illinois/ }))

    expect(screen.getByText(/Area set from “Washington Street, Naperville, Illinois”/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save project' }))
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
    const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(rounded(JSON.parse(String(createCall?.[1]?.body)).boundary)).toEqual({
      type: 'Polygon',
      coordinates: [[[-88.15, 41.77], [-88.14, 41.77], [-88.14, 41.78], [-88.15, 41.78], [-88.15, 41.77]]],
    })
  })
})
