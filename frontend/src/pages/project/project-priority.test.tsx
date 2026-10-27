import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { Inspection, PriorityConfig, PriorityItem } from '@/api/priority'
import type { ProjectDetail } from '@/api/projects'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectPriorityPage } from '@/pages/project/project-priority-page'
import { json, makeFinding, page, PROJECT, REVIEW_OPTIONS, REVIEWER_PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const MANAGER: ProjectDetail = {
  ...REVIEWER_PROJECT,
  my_permissions: [...REVIEWER_PROJECT.my_permissions, 'priority.view', 'priority.configure', 'inspection.plan', 'inspection.record', 'inspection.reopen'],
}

const CONFIG: PriorityConfig = {
  id: 'c1',
  version: 1,
  weights: { severity: 0.5, road_category: 0.3, facility_proximity: 0.2 },
  severity_points: { low: 33.3, medium: 66.7, high: 100 },
  road_category_points: { arterial: 100 },
  facility_types: ['school', 'hospital'],
  facility_radius_m: 200,
  is_placeholder: true,
  is_current: true,
  created_by_name: null,
  created_at: '2026-10-15T00:00:00Z',
}

const ITEM: PriorityItem = {
  finding: makeFinding({ id: 'f1', review_status: 'verified', type_key: 'pothole', severity_key: 'high' }),
  score: 50,
  breakdown: {
    weight_covered: 0.5,
    missing: ['road_category', 'facility_proximity'],
    inputs: [
      { key: 'severity', label: 'Reviewed severity', value: 'high', points: 100, weight: 0.5, contribution: 50, missing: false, reason: null },
      { key: 'road_category', label: 'Road category', value: null, points: null, weight: 0.3, contribution: null, missing: true, reason: 'The project has no road category set.' },
      { key: 'facility_proximity', label: 'Near selected facilities', value: null, points: null, weight: 0.2, contribution: null, missing: true, reason: 'No facility map is loaded yet.' },
    ],
  },
  inspection: null,
}

const INSPECTION: Inspection = {
  id: 'i1',
  finding_id: 'f1',
  owner_user_id: 'u2',
  owner_name: 'Bo Worker',
  planned_date: '2026-10-20',
  status: 'planned',
  outcome_note: null,
  has_evidence: false,
  inspected_by_name: null,
  inspected_at: null,
  resolved_by_name: null,
  resolved_at: null,
  reopen_reason: null,
  reopened_by_name: null,
  reopened_at: null,
  created_by_name: 'Ada Admin',
  created_at: '2026-10-15T00:00:00Z',
}

function renderPriority(project: ProjectDetail, item: PriorityItem = ITEM, history: Inspection[] = []) {
  const posts: { url: string; body: unknown; method?: string }[] = []
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (init?.method && init.method !== 'GET') {
      posts.push({ url, method: init.method, body: init.body instanceof FormData ? 'form' : JSON.parse(String(init.body)) })
      return Promise.resolve(json(INSPECTION, 201))
    }
    if (url.includes('/review-options')) return Promise.resolve(json(REVIEW_OPTIONS))
    if (url.includes('/priority-list')) return Promise.resolve(json({ ...page([item]), config: CONFIG }))
    if (url.includes('/priority-configs')) return Promise.resolve(json(page([CONFIG])))
    if (url.includes('/members')) return Promise.resolve(json(page([{ id: 'm1', user_id: 'u2', email: 'bo@city.test', full_name: 'Bo Worker', role: 'field_collector', added_at: '' }])))
    if (url.includes('/inspections?mine=true')) return Promise.resolve(json(page([{ inspection: INSPECTION, finding: ITEM.finding }])))
    if (url.includes('/v1/findings/f1/inspections')) return Promise.resolve(json(history))
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(project))
    return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
  })
  renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route path="priority" element={<ProjectPriorityPage />} />
      </Route>
    </Routes>,
    { route: '/projects/p1/priority' },
  )
  return { posts, fetchMock }
}

describe('Inspection priority', () => {
  it('shows the score with its breakdown and flags missing inputs', async () => {
    renderPriority(MANAGER)

    const list = await screen.findByRole('list', { name: 'Inspection priority' })
    expect(within(list).getByLabelText('Inspection priority 50')).toBeInTheDocument()
    expect(within(list).getByText(/Part of the score is unknown: .* are not known yet, so they add nothing\. Nothing is guessed\./)).toBeInTheDocument()
    expect(screen.getByText(/These scores use sample settings for now/)).toBeInTheDocument()

    await userEvent.click(within(list).getByRole('button', { name: 'How this score was calculated' }))

    expect(within(list).getByText(/Not known: The project has no road category set\./)).toBeInTheDocument()
    expect(within(list).getByText('Reviewed severity')).toBeInTheDocument()
    expect(within(list).getAllByText('50').length).toBeGreaterThan(0)
  })

  it('plans an inspection with an owner and a date', async () => {
    const { posts } = renderPriority(MANAGER)
    await userEvent.click(await screen.findByRole('button', { name: 'Plan inspection' }))
    const dialog = screen.getByRole('dialog', { name: 'Plan inspection' })

    await userEvent.selectOptions(await within(dialog).findByLabelText('Who inspects'), 'Bo Worker')
    await userEvent.clear(within(dialog).getByLabelText('Planned date'))
    await userEvent.type(within(dialog).getByLabelText('Planned date'), '2026-10-20')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Plan inspection' }))

    await waitFor(() => expect(posts).toEqual([{ url: '/api/v1/findings/f1/inspections', method: 'POST', body: { owner_user_id: 'u2', planned_date: '2026-10-20' } }]))
  })

  it('saving settings checks the weights and asks for confirmation', async () => {
    const { posts } = renderPriority(MANAGER)
    await userEvent.click(await screen.findByRole('button', { name: /Priority settings.*Sample settings/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Change settings' }))

    const severityWeight = screen.getByLabelText('Reviewed severity (%)')
    await userEvent.clear(severityWeight)
    await userEvent.type(severityWeight, '60')
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(screen.getByText('The shares must add up to 100% (now 110%).')).toBeInTheDocument()

    await userEvent.clear(screen.getByLabelText('Road category (%)'))
    await userEvent.type(screen.getByLabelText('Road category (%)'), '20')
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    await userEvent.click(screen.getByRole('button', { name: 'Yes, save the new settings' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.body).toMatchObject({ weights: { severity: 0.6, road_category: 0.2, facility_proximity: 0.2 }, is_placeholder: true })
  })

  it('resolving needs a note or a photo', async () => {
    const { posts } = renderPriority(MANAGER, { ...ITEM, inspection: INSPECTION, finding: { ...ITEM.finding, inspection_status: 'planned' } }, [INSPECTION])
    await userEvent.click(await screen.findByRole('button', { name: 'View inspection' }))
    const dialog = screen.getByRole('dialog', { name: 'Inspection' })

    await userEvent.click(await within(dialog).findByRole('button', { name: 'Mark resolved' }))
    expect(within(dialog).getByText('To mark it resolved, add a note or a photo of the result.')).toBeInTheDocument()
    expect(posts).toHaveLength(0)

    await userEvent.type(within(dialog).getByLabelText('What was found or done'), 'Filled with cold mix')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Mark resolved' }))

    await waitFor(() => expect(posts).toEqual([{ url: '/api/v1/inspections/i1', method: 'PATCH', body: { status: 'resolved', outcome_note: 'Filled with cold mix' } }]))
  })

  it('shows field collectors only the inspections assigned to them', async () => {
    const collector: ProjectDetail = { ...PROJECT, my_permissions: [...PROJECT.my_permissions, 'inspection.record', 'finding.view_verified'] }
    renderPriority(collector)

    expect(await screen.findByRole('heading', { name: 'My inspections' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'My inspections' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Inspection priority' })).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Record result' })).toBeInTheDocument()
  })
})
