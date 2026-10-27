import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Dashboard } from '@/api/dashboard'
import { HomePage } from '@/pages/home-page'
import { renderWithProviders } from '@/test/render'

vi.mock('@/components/dashboard/dashboard-map', () => ({
  DashboardMap: ({ points }: { points: unknown[] }) => <div>Map with {points.length} findings</div>,
}))

const ACCESS_ALL = { photos: true, photos_own_only: false, candidates: true, verified: true, rejected: true, priority: true, own_inspections: false }

function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    scope: { project_id: null, days: 30, date_from: '2026-09-16', date_to: '2026-10-15' },
    access: ACCESS_ALL,
    totals: {
      photos: 15,
      photos_analysed: 13,
      photos_missing_location: 2,
      waiting_review: 4,
      needs_field_check: 1,
      verified: 6,
      rejected: 2,
      verified_location_unconfirmed: 3,
      inspections_open: 2,
      inspections_resolved: 1,
    },
    review_status: { waiting: 4, needs_field_check: 1, verified: 6, rejected: 2 },
    verified_by_type: { pothole: 4, crack: 2 },
    verified_by_severity: { low: 1, high: 5 },
    inspection_status: { none: 3, planned: 2, inspected: 0, resolved: 1 },
    activity: [
      { date: '2026-10-14', photos: 10, suggestions: 8, verified: 2 },
      { date: '2026-10-15', photos: 5, suggestions: 3, verified: 4 },
    ],
    top_priority: [
      {
        finding_id: 'f1',
        project_id: 'p1',
        project_name: 'Market Street',
        type_key: 'pothole',
        severity_key: 'high',
        score: 87.4,
        weight_covered: 1,
        inspection_status: 'planned',
      },
    ],
    map_points: [{ finding_id: 'f1', project_id: 'p1', latitude: 37.77, longitude: -122.41, type_key: 'pothole', severity_key: 'high' }],
    map_truncated: false,
    projects: [{ id: 'p1', name: 'Market Street', my_roles: ['project_manager'], photos: 15, waiting_review: 4, verified: 6, rejected: 2, inspections_open: 2 }],
    finding_types: [
      { key: 'pothole', label: 'Pothole' },
      { key: 'crack', label: 'Crack' },
    ],
    severity_levels: [
      { key: 'low', label: 'Low' },
      { key: 'high', label: 'High' },
    ],
    ...overrides,
  }
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

/** Answer each address the page asks for; remember the dashboard requests. */
function mockApi(data: Dashboard, { readiness = json({ status: 'ok', checks: { database: 'ok', queue: 'ok' } }) } = {}) {
  const dashboardUrls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input instanceof Request ? input.url : input)
    if (url.includes('/dashboard')) {
      dashboardUrls.push(url)
      return json(data)
    }
    if (url.includes('/projects')) return json({ items: [{ id: 'p1', name: 'Market Street' }], total: 1, page: 1, page_size: 50 })
    return readiness.clone()
  })
  return dashboardUrls
}

afterEach(() => vi.restoreAllMocks())

describe('HomePage', () => {
  it('shows the dashboard: number cards, charts, priority list, map and projects', async () => {
    mockApi(dashboard())
    renderWithProviders(<HomePage />)

    expect(screen.getByText(/Welcome, Ada Admin/)).toBeInTheDocument()
    expect(await screen.findByText('13 analysed · 2 need a location')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Activity' })).toBeInTheDocument()
    const review = screen.getByRole('region', { name: 'Review progress' })
    expect(within(review).getByText('Waiting for review')).toBeInTheDocument()
    expect(within(review).getByText('13')).toBeInTheDocument() // total in the middle of the donut
    expect(screen.getByRole('region', { name: 'Verified findings by severity' })).toHaveTextContent('Set by a reviewer, never by the AI')
    const inspectFirst = screen.getByRole('region', { name: 'Inspect first' })
    expect(within(inspectFirst).getByRole('link')).toHaveTextContent('Pothole · High')
    expect(within(inspectFirst).getByRole('link')).toHaveAttribute('href', '/projects/p1/priority')
    expect(screen.getByText('Map with 1 findings')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Projects' })).getByRole('link', { name: 'Market Street' })).toBeInTheDocument()
    expect(await screen.findByText('All systems are working.')).toBeInTheDocument()
  })

  it('starts with "What to do next": one button per job, linking to the right page', async () => {
    mockApi(dashboard())
    renderWithProviders(<HomePage />)

    const steps = await screen.findByRole('region', { name: 'What to do next' })
    // A project manager is told the queue waits for a reviewer (only reviewers can decide).
    expect(within(steps).getByText('4 AI suggestions are waiting for a reviewer')).toBeInTheDocument()
    const [queue, fieldCheck] = within(steps).getAllByRole('link', { name: 'See them' })
    expect(queue).toHaveAttribute('href', '/projects/p1/findings?status=to_review')
    expect(fieldCheck).toHaveAttribute('href', '/projects/p1/findings?status=needs_field_check')
    expect(within(steps).getByRole('link', { name: 'Add locations' })).toHaveAttribute('href', '/projects/p1/photos?missing=1')
    expect(within(steps).getByRole('link', { name: 'See the priority list' })).toHaveAttribute('href', '/projects/p1/priority')
  })

  it('tells managers when new photos are waiting for the AI check', async () => {
    const project = { ...dashboard().projects[0]!, photos_waiting_for_ai: 3 }
    mockApi(dashboard({ projects: [project] }))
    renderWithProviders(<HomePage />)

    const steps = await screen.findByRole('region', { name: 'What to do next' })
    expect(within(steps).getByText('3 new photos are waiting for the AI check')).toBeInTheDocument()
    expect(within(steps).getByRole('link', { name: 'Check them' })).toHaveAttribute('href', '/projects/p1/photos')
  })

  it('does not ask viewers to send photos to the AI', async () => {
    mockApi(dashboard({ projects: [{ ...dashboard().projects[0]!, my_roles: ['viewer'], photos_waiting_for_ai: 3 }] }))
    renderWithProviders(<HomePage />)

    const steps = await screen.findByRole('region', { name: 'What to do next' })
    expect(within(steps).queryByText(/waiting for the AI check/)).not.toBeInTheDocument()
  })

  it('technical reviewers are asked to start reviewing', async () => {
    mockApi(dashboard({ projects: [{ ...dashboard().projects[0]!, my_roles: ['technical_reviewer'] }] }))
    renderWithProviders(<HomePage />)

    const steps = await screen.findByRole('region', { name: 'What to do next' })
    expect(within(steps).getByText('4 AI suggestions are waiting to be checked')).toBeInTheDocument()
    expect(within(steps).getByRole('link', { name: 'Start reviewing' })).toHaveAttribute('href', '/projects/p1/findings?status=to_review')
  })

  it('field collectors are offered uploading and their own inspections', async () => {
    mockApi(
      dashboard({
        access: { ...ACCESS_ALL, photos_own_only: true, candidates: false, rejected: false, priority: false, own_inspections: true },
        totals: { ...dashboard().totals, photos_missing_location: 0 },
      }),
    )
    renderWithProviders(<HomePage />)

    const steps = await screen.findByRole('region', { name: 'What to do next' })
    expect(within(steps).getByText('You have 2 inspections to do')).toBeInTheDocument()
    expect(within(steps).getByRole('link', { name: 'Upload photos' })).toHaveAttribute('href', '/projects/p1/upload')
    expect(within(steps).queryByRole('link', { name: 'Start reviewing' })).not.toBeInTheDocument()
  })

  it('viewers are not given open inspections as a job', async () => {
    mockApi(
      dashboard({
        access: { ...ACCESS_ALL, photos: false, candidates: false, rejected: false },
        projects: [{ id: 'p1', name: 'Market Street', my_roles: ['viewer'], photos: 15, waiting_review: 0, verified: 6, rejected: 2, inspections_open: 2 }],
      }),
    )
    renderWithProviders(<HomePage />)

    expect(await screen.findByText(/You are all caught up/)).toBeInTheDocument()
  })

  it('says so when nothing is waiting', async () => {
    mockApi(
      dashboard({
        totals: { ...dashboard().totals, photos_missing_location: 0, needs_field_check: 0 },
        projects: [{ id: 'p1', name: 'Market Street', my_roles: ['viewer'], photos: 15, waiting_review: 0, verified: 6, rejected: 2, inspections_open: 0 }],
      }),
    )
    renderWithProviders(<HomePage />)

    expect(await screen.findByText(/You are all caught up/)).toBeInTheDocument()
  })

  it('every chart can be read as a table', async () => {
    mockApi(dashboard())
    renderWithProviders(<HomePage />)

    const byType = await screen.findByRole('region', { name: 'Verified findings by type' })
    await userEvent.click(within(byType).getByRole('button', { name: 'Table' }))
    const rows = within(byType).getAllByRole('row')
    expect(rows.map((row) => row.textContent)).toEqual(['TypeFindings', 'Pothole4', 'Crack2'])
  })

  it('shows only what the role allows (viewer: no photos, no review queue)', async () => {
    mockApi(
      dashboard({
        access: { ...ACCESS_ALL, photos: false, candidates: false, rejected: false },
        review_status: { verified: 6 },
      }),
    )
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('Verified findings')).toBeInTheDocument()
    expect(screen.queryByText('Photos uploaded')).not.toBeInTheDocument()
    expect(screen.queryByText('Waiting for review')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Review progress' })).not.toBeInTheDocument() // one status only: no ring
    expect(within(screen.getByRole('region', { name: 'Projects' })).queryByText('Photos')).not.toBeInTheDocument()
  })

  it('changing the period or project asks the server again', async () => {
    const urls = mockApi(dashboard())
    renderWithProviders(<HomePage />)

    await screen.findByText('13 analysed · 2 need a location')
    expect(urls.at(-1)).toContain('days=30')
    await userEvent.click(screen.getByRole('radio', { name: '7 days' }))
    await vi.waitFor(() => expect(urls.at(-1)).toContain('days=7'))
    await userEvent.selectOptions(await screen.findByRole('combobox'), 'p1')
    await vi.waitFor(() => expect(urls.at(-1)).toContain('project_id=p1'))
    await userEvent.click(screen.getByRole('radio', { name: 'All time' }))
    await vi.waitFor(() => expect(urls.at(-1)).not.toContain('days='))
  })

  it('shows the error message and reference when a service is down', async () => {
    mockApi(dashboard(), {
      readiness: json(
        {
          error: {
            code: 'service_unavailable',
            message: 'A required service is temporarily unavailable.',
            details: { checks: { database: 'unavailable', queue: 'ok' } },
            request_id: 'abc123',
          },
        },
        503,
      ),
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('A required service is temporarily unavailable.')).toBeInTheDocument()
    expect(screen.getByText(/quote this reference: abc123/)).toBeInTheDocument()
  })
})
