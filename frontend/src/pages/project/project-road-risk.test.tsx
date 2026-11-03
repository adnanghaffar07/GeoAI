import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectDetail } from '@/api/projects'
import type { ForecastStatusInfo, RiskList } from '@/api/road-risk'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectPriorityPage } from '@/pages/project/project-priority-page'
import { ProjectRoadRiskPage } from '@/pages/project/project-road-risk-page'
import { ProjectRoadRiskSettingsPage } from '@/pages/project/project-road-risk-settings-page'
import { json, page, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

vi.mock('@/components/map/road-risk-map', () => ({
  RoadRiskMap: () => <div>map</div>,
  RoadRiskLegend: () => <div>legend</div>,
}))

const MANAGER: ProjectDetail = {
  ...PROJECT,
  my_roles: ['project_manager'],
  road_risk_enabled: true,
  my_permissions: [...PROJECT.my_permissions, 'risk.view', 'risk.configure', 'inspection.plan', 'inspection.record'],
}

const STATUS: ForecastStatusInfo = {
  enabled: true,
  status: 'ready',
  level: 2,
  level_label: 'Tested Chicago risk levels',
  message: null,
  area_km2: 3.9,
  max_area_km2: 500,
  last_weekly_run: '2026-10-26',
  last_daily_run: '2026-10-30',
  can_configure: true,
  visible_to_roles: ['technical_reviewer', 'viewer'],
  label: 'TRIAL FORECAST',
  notice: 'Risk estimate, not a confirmed defect.',
}

const LIST: RiskList = {
  ...page([
    {
      section_id: 's1',
      name: 'Main Street',
      road_type: 'residential',
      length_m: 100,
      position: 1,
      level: 'high',
      rank_in_area: 3,
      reasons: [{ input: 'reports_365d', label: 'Pothole reports here, last 12 months', value: 4 }],
      missing_inputs: ['Number of lanes'],
      factors: [],
    },
  ]),
  status: STATUS,
  levels_run: { id: 'r1', kind: 'weekly_levels', as_of: '2026-10-26', model_version: 'forecast-chicago-0.2', data_dates: {}, finished_at: null },
  factors_run: null,
  counts: { high: 1, medium: 0, low: 0 },
  label: 'TRIAL FORECAST',
  notice: 'Risk estimate, not a confirmed defect.',
}

function renderAt(project: ProjectDetail, route: string, status: ForecastStatusInfo = STATUS) {
  const sent: { url: string; method: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (url.includes('/assistant'))
      return Promise.resolve(
        json({
          answer: 'Main Street is high risk because of: Pothole reports here, last 12 months: 4.',
          sources: [{ label: 'Main Street', path: '/projects/p1/road-risk/s1' }],
          used_model: false,
          questions_left_today: 49,
          label: 'TRIAL FORECAST · AI answer: check the linked pages',
          notice: 'Risk estimate, not a confirmed defect.',
        }),
      )
    if (init?.method && init.method !== 'GET') {
      sent.push({ url, method: init.method, body: init.body ? JSON.parse(String(init.body)) : null })
      return Promise.resolve(json(status))
    }
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(project))
    if (url.includes('/forecast-settings')) return Promise.resolve(json(status))
    if (url.includes('/risk/map')) return Promise.resolve(json({ type: 'FeatureCollection', features: [] }))
    if (url.includes('/risk?')) return Promise.resolve(json(LIST))
    if (url.includes('/weather')) return Promise.resolve(json({ outlook: null, recent: null }))
    if (url.includes('/members')) return Promise.resolve(json(page([{ id: 'm1', user_id: 'u2', email: 'bo@city.test', full_name: 'Bo Worker', role: 'field_collector', added_at: '' }])))
    if (url.includes('/inspections?mine=true'))
      return Promise.resolve(
        json(page([{ inspection: { id: 'i1', status: 'planned', planned_date: '2026-11-02', owner_user_id: 'u2' }, finding: null, road: { section_id: 's1', name: 'Main Street', road_type: 'residential', length_m: 100 } }])),
      )
    return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
  })
  renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route path="road-risk" element={<ProjectRoadRiskPage />} />
        <Route path="priority" element={<ProjectPriorityPage />} />
        <Route path="settings/road-risk" element={<ProjectRoadRiskSettingsPage />} />
      </Route>
    </Routes>,
    { route },
  )
  return sent
}

describe('Road risk', () => {
  it('shows the tab only where road risk is on and allowed', async () => {
    renderAt(MANAGER, '/projects/p1/road-risk')
    expect(await screen.findByRole('link', { name: 'Road risk' })).toBeInTheDocument()
  })

  it('hides the tab when road risk is off', async () => {
    renderAt({ ...MANAGER, road_risk_enabled: false }, '/projects/p1/priority')
    await screen.findByRole('link', { name: 'My inspections' })
    expect(screen.queryByRole('link', { name: 'Road risk' })).not.toBeInTheDocument()
  })

  it('lists roads with level words, plain reasons and the trial label, never a percentage', async () => {
    renderAt(MANAGER, '/projects/p1/road-risk')
    const list = await screen.findByRole('list', { name: 'Inspect first' })
    expect(within(list).getByText('Main Street')).toBeInTheDocument()
    expect(within(list).getByText('High risk')).toBeInTheDocument()
    expect(within(list).getByText('Pothole reports here, last 12 months: 4')).toBeInTheDocument()
    expect(within(list).getByText(/Some inputs are not known: Number of lanes/)).toBeInTheDocument()
    expect(list.textContent).not.toMatch(/%/)
    expect(screen.getAllByText('TRIAL FORECAST').length).toBeGreaterThan(0)
    expect(screen.getByText('Risk estimate, not a confirmed defect.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Download CSV/ })).toHaveAttribute('href', '/api/v1/projects/p1/risk/export?format=csv')
  })

  it('plans an inspection of a road', async () => {
    const sent = renderAt(MANAGER, '/projects/p1/road-risk')
    await userEvent.click(await screen.findByRole('button', { name: 'Plan inspection' }))
    const dialog = screen.getByRole('dialog', { name: 'Plan inspection' })
    expect(within(dialog).getByText('Main Street')).toBeInTheDocument()
    await userEvent.selectOptions(await within(dialog).findByLabelText('Who inspects'), 'Bo Worker')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Plan inspection' }))
    await waitFor(() => expect(sent[0]).toMatchObject({ url: '/api/v1/projects/p1/road-sections/s1/inspections', method: 'POST', body: { owner_user_id: 'u2' } }))
  })

  it('lets the manager choose who else sees road risk', async () => {
    const sent = renderAt(MANAGER, '/projects/p1/settings/road-risk')
    await userEvent.click(await screen.findByLabelText('Field collectors'))
    await userEvent.click(screen.getByRole('button', { name: 'Save who can see it' }))
    await waitFor(() =>
      expect(sent).toEqual([{ url: '/api/v1/projects/p1/forecast-settings', method: 'PUT', body: { visible_to_roles: ['technical_reviewer', 'viewer', 'field_collector'] } }]),
    )
  })

  it('switches road risk on', async () => {
    const sent = renderAt(MANAGER, '/projects/p1/settings/road-risk', { ...STATUS, enabled: false, status: 'off' })
    await userEvent.click(await screen.findByRole('button', { name: 'Switch on' }))
    await waitFor(() => expect(sent).toEqual([{ url: '/api/v1/projects/p1/forecast-settings', method: 'PUT', body: { enabled: true } }]))
  })

  it('answers a question with links when the manager has switched questions on', async () => {
    const sent = renderAt(MANAGER, '/projects/p1/road-risk', { ...STATUS, assistant_enabled: true })
    await userEvent.type(await screen.findByLabelText('Your question'), 'Why is Main Street high risk?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    const answer = await screen.findByRole('region', { name: 'Answer' })
    expect(within(answer).getByText(/Main Street is high risk because of/)).toBeInTheDocument()
    expect(within(answer).getByRole('link', { name: 'Main Street' })).toHaveAttribute('href', '/projects/p1/road-risk/s1')
    expect(within(answer).getByText(/Questions left today: 49/)).toBeInTheDocument()
    expect(sent).toEqual([])
  })

  it('hides the question box while questions are off', async () => {
    renderAt(MANAGER, '/projects/p1/road-risk')
    await screen.findByRole('list', { name: 'Inspect first' })
    expect(screen.queryByLabelText('Your question')).not.toBeInTheDocument()
  })

  it('shows a road inspection in My inspections', async () => {
    const collector: ProjectDetail = { ...PROJECT, my_permissions: [...PROJECT.my_permissions, 'inspection.record'] }
    renderAt(collector, '/projects/p1/priority')
    expect(await screen.findByText('Main Street')).toBeInTheDocument()
    expect(screen.getByText('Road')).toBeInTheDocument()
  })
})
