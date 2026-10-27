import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectDetail } from '@/api/projects'
import type { Report } from '@/api/reports'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectReportsPage } from '@/pages/project/project-reports-page'
import { json, page, PROJECT, REVIEW_OPTIONS, REVIEWER_PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const MANAGER: ProjectDetail = {
  ...REVIEWER_PROJECT,
  my_permissions: [...REVIEWER_PROJECT.my_permissions, 'report.generate', 'report.include_unreviewed', 'report.share', 'report.view_all'],
}

const REPORT: Report = {
  id: 'r1',
  project_id: 'p1',
  format: 'csv',
  filters: { severity_key: ['high'] },
  include_unreviewed: false,
  settings_used: { severity_scale: { version: 1, is_placeholder: true }, includes_test_detector: true },
  status: 'completed',
  record_count: 12,
  shared_with_viewers: false,
  failure_reason: null,
  requested_by_name: 'Ada Admin',
  created_at: '2026-10-15T10:00:00Z',
  completed_at: '2026-10-15T10:00:05Z',
  file_name: 'geoinfralens-downtown-20261015-1000.csv',
}

function renderReports(project: ProjectDetail, reports: Report[]) {
  const posts: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (init?.method === 'POST') {
      posts.push({ url, body: JSON.parse(String(init.body)) })
      return Promise.resolve(json({ ...REPORT, status: 'queued' }, 202))
    }
    if (url.includes('/review-options')) return Promise.resolve(json(REVIEW_OPTIONS))
    if (url.includes('/reports')) return Promise.resolve(json(page(reports)))
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(project))
    return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
  })
  renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route path="reports" element={<ProjectReportsPage />} />
      </Route>
    </Routes>,
    { route: '/projects/p1/reports' },
  )
  return posts
}

describe('Reports', () => {
  it('requests a report with filters, verified-only by default', async () => {
    const posts = renderReports(MANAGER, [REPORT])
    await userEvent.click(await screen.findByText('CSV table (Excel)'))
    await userEvent.selectOptions(screen.getByLabelText('Severity'), 'High')
    await userEvent.click(screen.getByRole('button', { name: 'Make report' }))

    await waitFor(() =>
      expect(posts).toEqual([
        {
          url: '/api/v1/projects/p1/reports',
          body: {
            format: 'csv',
            filters: { type_key: [], severity_key: ['high'], created_from: null, created_to: null, has_location: null },
            include_unreviewed: false,
          },
        },
      ]),
    )
  })

  it('warns prominently when unreviewed data is included and never offers sharing for it', async () => {
    renderReports(MANAGER, [{ ...REPORT, include_unreviewed: true }])
    await userEvent.click(await screen.findByLabelText('Also include unreviewed AI suggestions'))

    expect(screen.getByRole('alert')).toHaveTextContent('This report will include UNREVIEWED AI suggestions')
    expect(screen.getByText('Includes UNREVIEWED AI suggestions')).toBeInTheDocument()
    expect(screen.getByText('Cannot be shared: it includes unreviewed suggestions')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Share with viewers' })).not.toBeInTheDocument()
  })

  it('lists finished reports with download, count and labels', async () => {
    renderReports(MANAGER, [REPORT])

    expect(await screen.findByText(/12 items in the report/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/v1/reports/r1/file')
    expect(screen.getByText(/Uses sample settings \(placeholder/)).toBeInTheDocument()
    expect(screen.getByText(/severity High/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Share with viewers' })).toBeInTheDocument()
  })

  it('shows viewers the shared reports only, without the form', async () => {
    const viewer: ProjectDetail = { ...PROJECT, my_permissions: ['project.view', 'finding.view_verified', 'report.view_shared'] }
    renderReports(viewer, [{ ...REPORT, shared_with_viewers: true }])

    expect(await screen.findByRole('heading', { name: 'Shared reports' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Make report' })).not.toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Download' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sharing|Share/ })).not.toBeInTheDocument()
  })
})
