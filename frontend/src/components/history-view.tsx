import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { useState } from 'react'

import { ACTION_LABELS, actionLabel, listAuditEvents, type AuditEvent } from '@/api/audit'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState } from '@/components/ui/page-intro'
import { roleLabel } from '@/lib/findings'

const PAGE_SIZE = 50

/** Short readable text for an event's details (ids and long values left out). */
function detailText(event: AuditEvent): string {
  return Object.entries(event.details)
    .filter(([key, value]) => !key.endsWith('_id') && !key.endsWith('_ids') && value !== null && value !== '')
    .map(([key, value]) => {
      const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
      return `${key.replaceAll('_', ' ')}: ${text.length > 80 ? `${text.slice(0, 80)}…` : text}`
    })
    .join(' · ')
}

/** S19 History: who did what and when, filterable by person, action and date (FR-53). */
export function HistoryView({ scope, people }: { scope: { orgId: string } | { projectId: string }; people: { id: string; name: string }[] }) {
  const [action, setAction] = useState('')
  const [person, setPerson] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const filters = {
    action: action || undefined,
    actor_user_id: person || undefined,
    since: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
    until: to ? new Date(new Date(`${to}T00:00:00`).getTime() + 86_400_000).toISOString() : undefined,
    page,
  }
  const events = useQuery({
    queryKey: ['audit', scope, filters],
    queryFn: ({ signal }) => listAuditEvents(scope, filters, signal),
    placeholderData: keepPreviousData,
  })
  const lastPage = events.data ? Math.max(1, Math.ceil(events.data.total / PAGE_SIZE)) : 1
  const field = 'control h-9 py-1 text-sm'
  const change = (apply: () => void) => {
    apply()
    setPage(1)
  }
  const filtered = Boolean(action || person || from || to)
  const clearFilters = () =>
    change(() => {
      setAction('')
      setPerson('')
      setFrom('')
      setTo('')
    })

  return (
    <div className="space-y-4">
      <div className="panel grid grid-cols-2 gap-3 p-3 lg:grid-cols-4" role="group" aria-label="Filters">
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          What happened
          <select className={field} value={action} onChange={(event) => change(() => setAction(event.target.value))}>
            <option value="">Everything</option>
            {Object.entries(ACTION_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Person
          <select className={field} value={person} onChange={(event) => change(() => setPerson(event.target.value))}>
            <option value="">Everyone</option>
            {people.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          From
          <input type="date" className={field} value={from} onChange={(event) => change(() => setFrom(event.target.value))} />
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Until
          <input type="date" className={field} value={to} onChange={(event) => change(() => setTo(event.target.value))} />
        </label>
      </div>

      {events.isPending && <SkeletonRows rows={5} />}
      {events.isError && <ErrorMessage title="Could not load the history" error={events.error} onRetry={() => void events.refetch()} />}
      {events.isSuccess &&
        (events.data.items.length === 0 ? (
          filtered ? (
            <EmptyState
              icon={<History />}
              title="Nothing recorded for these filters"
              action={
                <Button variant="ghost" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            >
              Try a longer date range or fewer filters.
            </EmptyState>
          ) : (
            <EmptyState icon={<History />} title="Nothing recorded yet">
              Actions such as uploads, reviews and changes to settings will be listed here.
            </EmptyState>
          )
        ) : (
          <div className="overflow-x-auto panel">
            <table className="responsive-table w-full text-left text-sm">
              <thead className="border-b border-asphalt-100 bg-asphalt-50 text-asphalt-500">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">When</th>
                  <th scope="col" className="px-4 py-2 font-medium">Who</th>
                  <th scope="col" className="px-4 py-2 font-medium">What</th>
                  <th scope="col" className="px-4 py-2 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {events.data.items.map((event) => (
                  <tr key={event.id} className="border-b border-asphalt-100 align-top last:border-0">
                    <td className="px-4 py-2 whitespace-nowrap max-sm:font-semibold">
                      {new Date(event.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                    </td>
                    <td data-label="Who" className="px-4 py-2">
                      {event.actor_email ?? 'The system (automatic)'}
                      {event.actor_roles.length > 0 && <span className="block text-xs text-asphalt-500">{event.actor_roles.map(roleLabel).join(', ')}</span>}
                    </td>
                    <td data-label="What" className="px-4 py-2">
                      {actionLabel(event.action)}
                    </td>
                    <td data-label="Details" className="px-4 py-2 text-xs break-words text-asphalt-600">
                      {detailText(event)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      {lastPage > 1 && (
        <nav aria-label="Pages" className="flex items-center gap-3 text-sm">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span>
            Page {page} of {lastPage}
          </span>
          <Button variant="secondary" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </nav>
      )}
    </div>
  )
}
