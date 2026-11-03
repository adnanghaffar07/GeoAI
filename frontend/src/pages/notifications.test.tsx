import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { RiskAlert } from '@/api/road-risk'
import { AlertPage, NotificationsPage } from '@/pages/notifications-page'
import { json, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const ALERT: RiskAlert = {
  id: 'a1',
  project_id: 'p1',
  project_name: 'Downtown streets',
  type: 'freeze_thaw_coming',
  title: 'Freeze-thaw coming: 1 road at high or medium risk',
  details: {
    label: 'TRIAL FORECAST',
    notice: 'Risk estimate, not a confirmed defect.',
    when: 'Sunday 1 November, Monday 2 November, Tuesday 3 November',
    source: 'National Weather Service (NWS LOT grid 74,71)',
    roads: [{ section_id: 's1', name: 'Main Street', level: 'high', reasons: ['Pothole reports here, last 12 months: 4'], missing_inputs: [] }],
    suggested_action: 'Inspect these roads before Sunday 1 November.',
  },
  created_at: '2026-10-30T15:00:00Z',
  closed_at: null,
  read: false,
}

function renderAt(route: string) {
  const sent: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (init?.method === 'POST') {
      sent.push(url)
      return Promise.resolve(new Response(null, { status: 204 }))
    }
    if (url.endsWith('/v1/notifications')) return Promise.resolve(json({ items: [ALERT], unread_count: 1, manages_projects: true }))
    if (url.endsWith('/v1/notifications/a1')) return Promise.resolve(json(ALERT))
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json({ ...PROJECT, my_permissions: [...PROJECT.my_permissions, 'inspection.plan'] }))
    return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
  })
  renderWithProviders(
    <Routes>
      <Route path="/notifications" element={<NotificationsPage />} />
      <Route path="/notifications/:alertId" element={<AlertPage />} />
    </Routes>,
    { route },
  )
  return sent
}

describe('Alerts', () => {
  it('lists my alerts, unread first, and marks all as read', async () => {
    const sent = renderAt('/notifications')
    expect(await screen.findByText('Freeze-thaw coming: 1 road at high or medium risk')).toBeInTheDocument()
    expect(screen.getByText('(unread)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mark all as read' }))
    await waitFor(() => expect(sent).toEqual(['/api/v1/notifications/read-all']))
  })

  it('shows the alert with its roads, reasons, source and the trial label, and marks it read', async () => {
    const sent = renderAt('/notifications/a1')
    expect(await screen.findByText('Main Street')).toBeInTheDocument()
    expect(screen.getByText('Pothole reports here, last 12 months: 4')).toBeInTheDocument()
    expect(screen.getByText(/National Weather Service/)).toBeInTheDocument()
    expect(screen.getByText('TRIAL FORECAST')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/%/)
    await waitFor(() => expect(sent).toEqual(['/api/v1/notifications/a1/read']))
    expect(await screen.findByRole('button', { name: 'Plan inspection' })).toBeInTheDocument()
  })
})
