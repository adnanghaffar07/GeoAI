import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectDetail } from '@/api/projects'
import { ProjectFindingsPage } from '@/pages/project/project-findings-page'
import { ProjectLayout } from '@/pages/project/project-layout'
import { json, makeFinding, page, PROJECT, REVIEW_OPTIONS, REVIEWER_PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

// The real maps need a browser with WebGL. These stand-ins keep the same props, so the
// tests can check that the map and the list stay in step.
vi.mock('@/components/map/findings-map', () => ({
  FindingsMap: ({ data, selectedId, onSelect }: { data?: { features: { id: string }[] }; selectedId: string | null; onSelect: (id: string) => void }) => (
    <div aria-label="Map of findings">
      {data?.features.map((feature) => (
        <button key={feature.id} type="button" aria-pressed={feature.id === selectedId} onClick={() => onSelect(feature.id)}>
          Pin {feature.id}
        </button>
      ))}
    </div>
  ),
}))
vi.mock('@/components/map/pick-location-map', () => ({
  PickLocationMap: ({ onPick }: { onPick: (point: { latitude: number; longitude: number }) => void }) => (
    <button type="button" onClick={() => onPick({ latitude: 37.78, longitude: -122.42 })}>
      Pick a point
    </button>
  ),
}))

const LOCATED = makeFinding({ id: 'f1' })
const NO_LOCATION = makeFinding({ id: 'f2', predicted_type_key: 'surface_cracking', location: null, original_location: null, location_quality: 'missing', location_source: 'none' })
const VERIFIED = makeFinding({ id: 'f3', review_status: 'verified', type_key: 'pothole', severity_key: 'high', severity_rubric_version: 1 })

const geojson = (ids: string[]) => ({
  type: 'FeatureCollection',
  truncated: false,
  features: ids.map((id) => ({ type: 'Feature', id, geometry: { type: 'Point', coordinates: [-122.42, 37.775] }, properties: { id, review_status: 'ai_generated' } })),
})

function renderFindings(project: ProjectDetail, items = [LOCATED, NO_LOCATION, VERIFIED], route = '/projects/p1/findings') {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (init?.method === 'POST' && url.endsWith('/v1/projects/p1/findings'))
      return Promise.resolve(json(makeFinding({ id: 'new', origin: 'manual', review_status: 'awaiting_review', type_key: 'sidewalk_observation' }), 201))
    if (url.includes('/review-options')) return Promise.resolve(json(REVIEW_OPTIONS))
    if (url.includes('/findings.geojson')) return Promise.resolve(json(geojson(items.filter((item) => item.location).map((item) => item.id))))
    if (url.includes('/findings?')) return Promise.resolve(json(page(items)))
    if (url.includes('/history')) return Promise.resolve(json([]))
    if (url.includes('/images?')) return Promise.resolve(json(page([])))
    if (url.includes('/v1/findings/new')) return Promise.resolve(json(makeFinding({ id: 'new', origin: 'manual', review_status: 'awaiting_review' })))
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(project))
    return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
  })
  renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route path="findings" element={<ProjectFindingsPage />} />
      </Route>
    </Routes>,
    { route },
  )
  return fetchMock
}

const calledWith = (fetchMock: ReturnType<typeof renderFindings>, part: string) => fetchMock.mock.calls.some(([url]) => String(url).includes(part))

describe('Findings: map and list', () => {
  it('lists every finding, flags missing locations, and keeps them off the map', async () => {
    renderFindings(REVIEWER_PROJECT)

    const list = await screen.findByRole('list', { name: 'Findings' })
    expect(within(list).getAllByRole('button')).toHaveLength(3)
    expect(within(list).getByText('No location, so not on the map')).toBeInTheDocument()
    expect(within(list).getByText('AI suggests: Pothole')).toBeInTheDocument()
    expect(within(list).getByText(/Severity: High/)).toBeInTheDocument()
    const map = screen.getByLabelText('Map of findings')
    expect(within(map).getAllByRole('button').map((pin) => pin.textContent)).toEqual(['Pin f1', 'Pin f3'])
    expect(screen.getByText(/AI suggestions are not confirmed problems/)).toBeInTheDocument()
  })

  it('selects the same finding in the map and the list, and opens its details', async () => {
    renderFindings(REVIEWER_PROJECT)
    const list = await screen.findByRole('list', { name: 'Findings' })

    await userEvent.click(screen.getByRole('button', { name: 'Pin f3' }))

    const rows = within(list).getAllByRole('button')
    expect(rows[2]).toHaveAttribute('aria-pressed', 'true')
    expect(rows[0]).toHaveAttribute('aria-pressed', 'false')
    const drawer = screen.getByRole('complementary', { name: 'Finding details' })
    expect(within(drawer).getByText('Verified')).toBeInTheDocument()
    expect(within(drawer).getByRole('link', { name: 'Review this finding' })).toHaveAttribute('href', '/projects/p1/review/f3')
    expect(await within(drawer).findByText('Nobody has reviewed this finding yet.')).toBeInTheDocument()

    await userEvent.click(rows[0]!)

    expect(screen.getByRole('button', { name: 'Pin f1' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(within(screen.getByRole('complementary', { name: 'Finding details' })).getByRole('button', { name: 'Close details' }))
    expect(screen.queryByRole('complementary', { name: 'Finding details' })).not.toBeInTheDocument()
  })

  it('sends the same filters to the list and the map', async () => {
    const fetchMock = renderFindings(REVIEWER_PROJECT)
    await screen.findByRole('list', { name: 'Findings' })

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Verified')
    await userEvent.selectOptions(screen.getByLabelText('Location'), 'No location')

    await waitFor(() => {
      expect(calledWith(fetchMock, '/findings?review_status=verified&has_location=false')).toBe(true)
      expect(calledWith(fetchMock, '/findings.geojson?review_status=verified&has_location=false')).toBe(true)
    })
    expect(screen.getAllByRole('button', { name: 'Reset filters' }).length).toBeGreaterThan(0)
  })

  it('shows viewers verified findings without AI wording or status choices', async () => {
    const viewer: ProjectDetail = { ...PROJECT, my_roles: ['viewer'], my_permissions: ['project.view', 'image.view', 'finding.view_verified'] }
    renderFindings(viewer, [VERIFIED])

    await screen.findByRole('list', { name: 'Findings' })

    expect(screen.queryByText(/AI suggestions are not confirmed problems/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add observation' })).not.toBeInTheDocument()
  })
})

describe('Add observation', () => {
  it('needs a description, then adds the observation and selects it', async () => {
    const fetchMock = renderFindings(REVIEWER_PROJECT)
    await userEvent.click(await screen.findByRole('button', { name: 'Add observation' }))
    const dialog = screen.getByRole('dialog', { name: 'Add observation' })

    await userEvent.click(within(dialog).getByRole('button', { name: 'Add observation' }))
    expect(within(dialog).getByText('Describe what you saw.')).toBeInTheDocument()

    await userEvent.type(within(dialog).getByLabelText(/What did you see/), 'Raised slab by the bus stop')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Pick a point' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add observation' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Add observation' })).not.toBeInTheDocument())
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      type_key: 'sidewalk_observation',
      notes: 'Raised slab by the bus stop',
      location: { latitude: 37.78, longitude: -122.42 },
      image_id: null,
    })
  })
})
