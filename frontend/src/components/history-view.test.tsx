import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { HistoryView } from '@/components/history-view'
import { json, page } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

describe('HistoryView', () => {
  it('lists events in plain words and filters by action and person', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      Promise.resolve(
        json(
          page([
            {
              id: 'e1',
              action: 'priority_config.created',
              actor_user_id: 'u1',
              actor_email: 'ada@city.test',
              actor_roles: ['org_admin', 'project_manager'],
              target_type: 'priority_config',
              target_id: 'c2',
              details: { version: 2, weights: { severity: 1 } },
              request_id: 'x',
              created_at: '2026-10-15T10:00:00Z',
            },
          ]),
        ),
      ),
    )
    renderWithProviders(<HistoryView scope={{ projectId: 'p1' }} people={[{ id: 'u1', name: 'Ada Admin' }]} />)

    expect(await screen.findByText(/ada@city\.test/)).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Saved inspection priority settings' })).toBeInTheDocument()
    expect(screen.getByText('Organization admin, Project manager')).toBeInTheDocument()
    expect(screen.getByText(/version: 2/)).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('What happened'), 'Downloaded a report')
    await userEvent.selectOptions(screen.getByLabelText('Person'), 'Ada Admin')

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/v1/projects/p1/audit-events?page=1&page_size=50&action=report.downloaded&actor_user_id=u1'))).toBe(true),
    )
  })
})
