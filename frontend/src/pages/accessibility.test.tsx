import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'
import { describe, it, vi } from 'vitest'

import type { ProjectDetail } from '@/api/projects'
import type { ForecastStatusInfo, RiskAlert, RiskList } from '@/api/road-risk'
import { AlertPage, NotificationsPage } from '@/pages/notifications-page'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectPriorityPage } from '@/pages/project/project-priority-page'
import { ProjectRoadRiskPage } from '@/pages/project/project-road-risk-page'
import { ProjectRoadRiskSettingsPage } from '@/pages/project/project-road-risk-settings-page'
import { ProjectsPage } from '@/pages/projects-page'
import { RequestAccessPage } from '@/pages/request-access-page'
import { SignInPage } from '@/pages/sign-in-page'
import { expectNoAccessibilityProblems } from '@/test/a11y'
import { ADMIN_WITH_PROJECTS, json, page, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

// P9.4 (p9-system-testing-plan.md): labels, roles, names, headings and lists on the main screens.

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
  assistant_enabled: true,
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

const ALERT: RiskAlert = {
  id: 'a1',
  project_id: 'p1',
  project_name: 'Downtown streets',
  type: 'freeze_thaw_coming',
  title: 'Freeze-thaw coming: 1 road at high or medium risk',
  details: {
    label: 'TRIAL FORECAST',
    notice: 'Risk estimate, not a confirmed defect.',
    when: 'Sunday 1 November',
    source: 'National Weather Service',
    roads: [{ section_id: 's1', name: 'Main Street', level: 'high', reasons: ['Pothole reports here, last 12 months: 4'], missing_inputs: [] }],
    suggested_action: 'Inspect these roads before Sunday 1 November.',
  },
  created_at: '2026-10-30T15:00:00Z',
  closed_at: null,
  read: true,
}

function fakeServer() {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = String(input)
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(MANAGER))
    if (url.includes('/forecast-settings')) return Promise.resolve(json(STATUS))
    if (url.includes('/risk/map')) return Promise.resolve(json({ type: 'FeatureCollection', features: [] }))
    if (url.includes('/risk?')) return Promise.resolve(json(LIST))
    if (url.includes('/weather')) return Promise.resolve(json({ outlook: null, recent: null }))
    if (url.includes('/alerts')) return Promise.resolve(json(page([ALERT])))
    if (url.endsWith('/v1/notifications')) return Promise.resolve(json({ items: [ALERT], unread_count: 0, manages_projects: true }))
    if (url.endsWith('/v1/notifications/a1')) return Promise.resolve(json(ALERT))
    if (url.includes('/members')) return Promise.resolve(json(page([])))
    if (url.includes('/inspections')) return Promise.resolve(json(page([])))
    return Promise.resolve(json(page([])))
  })
}

function renderProject(route: string) {
  fakeServer()
  return renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route path="road-risk" element={<ProjectRoadRiskPage />} />
        <Route path="priority" element={<ProjectPriorityPage />} />
        <Route path="settings/road-risk" element={<ProjectRoadRiskSettingsPage />} />
      </Route>
    </Routes>,
    { route },
  )
}

describe('Accessibility of the main screens (P9.4)', { timeout: 20000 }, () => {
  it('sign-in page', async () => {
    const { container } = renderWithProviders(<SignInPage />, { me: null, route: '/sign-in' })
    await expectNoAccessibilityProblems(container)
  })

  it('request access page', async () => {
    const { container } = renderWithProviders(<RequestAccessPage />, { me: null, route: '/request-access' })
    await expectNoAccessibilityProblems(container)
  })

  it('projects list', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page([PROJECT])))
    const { container } = renderWithProviders(<ProjectsPage />, { me: ADMIN_WITH_PROJECTS })
    await screen.findByText('Downtown streets')
    await expectNoAccessibilityProblems(container)
  })

  it('road risk page', async () => {
    const { container } = renderProject('/projects/p1/road-risk')
    await screen.findAllByText('Main Street')
    await expectNoAccessibilityProblems(container)
  })

  it('road risk settings', async () => {
    const { container } = renderProject('/projects/p1/settings/road-risk')
    await screen.findByLabelText('Field collectors')
    await expectNoAccessibilityProblems(container)
  })

  it('priority page', async () => {
    const { container } = renderProject('/projects/p1/priority')
    await screen.findByRole('heading', { name: 'My inspections' })
    await expectNoAccessibilityProblems(container)
  })

  it('alerts list and alert page', async () => {
    fakeServer()
    const list = renderWithProviders(
      <Routes>
        <Route path="/notifications" element={<NotificationsPage />} />
      </Routes>,
      { route: '/notifications' },
    )
    await screen.findByText(ALERT.title)
    await expectNoAccessibilityProblems(list.container)
    list.unmount()

    const one = renderWithProviders(
      <Routes>
        <Route path="/notifications/:alertId" element={<AlertPage />} />
      </Routes>,
      { route: '/notifications/a1' },
    )
    await screen.findByText('Inspect these roads before Sunday 1 November.')
    await expectNoAccessibilityProblems(one.container)
  })
})
