import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, CircleCheck, CircleX, Inbox, Mail, MapPin, Phone, UserRound } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

import {
  approveOrganizationRequest,
  listOrganizationRequests,
  newInvitationLink,
  platformQueryKeys,
  rejectOrganizationRequest,
  type InvitationLinkResult,
  type OrganizationRequest,
  type RequestStatus,
} from '@/api/platform'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { OneTimeLink } from '@/components/one-time-link'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/page-intro'
import { cn } from '@/lib/utils'
import { NotFoundPage } from '@/pages/not-found-page'

const formatDate = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const formatDay = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })

const TABS: { status: RequestStatus; label: string }[] = [
  { status: 'pending', label: 'Waiting' },
  { status: 'approved', label: 'Approved' },
  { status: 'rejected', label: 'Rejected' },
]

const EMPTY: Record<RequestStatus, { title: string; text: string }> = {
  pending: { title: 'No requests are waiting', text: 'New requests from the “Request access” page appear here.' },
  approved: { title: 'No approved requests yet', text: 'Organizations you approve are listed here.' },
  rejected: { title: 'No rejected requests', text: 'Requests you reject are listed here with your reason.' },
}

/**
 * Platform admins only (CR-004): review requests from new organizations. Approving creates
 * the organization and a one-time invitation link for its first admin, which the platform
 * admin copies and emails to the contact person.
 */
export function PlatformRequestsPage() {
  const auth = useAuth()
  const [status, setStatus] = useState<RequestStatus>('pending')
  const [shownLink, setShownLink] = useState<InvitationLinkResult | null>(null)
  const list = useQuery({
    queryKey: platformQueryKeys.list(status),
    queryFn: ({ signal }) => listOrganizationRequests(status, signal),
    enabled: Boolean(auth.me?.user.is_platform_admin),
  })

  if (!auth.me?.user.is_platform_admin) return <NotFoundPage />

  const pendingCount = list.data?.pending_count

  return (
    <section className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">Organization requests</h1>
        <p className="mt-1 text-asphalt-500">
          Organizations that asked for access. Approving one creates it and gives you an invitation link to send to its contact person.
        </p>
      </header>

      {shownLink && (
        <OneTimeLink
          title={`Approved: “${shownLink.request.organization_name}” now exists.`}
          url={shownLink.invitation_url}
          note={`Copy this link and email it to ${shownLink.request.contact_email}. They open it to set their password and become the organization’s admin. It works once, until ${formatDay(shownLink.invitation_expires_at)}, and is not shown again. If it gets lost, open “Approved” and make a new one.`}
          onDone={() => setShownLink(null)}
        />
      )}

      <div role="tablist" aria-label="Request status" className="inline-flex rounded-xl bg-asphalt-100 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.status}
            type="button"
            role="tab"
            aria-selected={status === tab.status}
            onClick={() => setStatus(tab.status)}
            className={cn(
              'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              status === tab.status ? 'bg-white text-asphalt-900 shadow-sm' : 'text-asphalt-600 hover:text-asphalt-900',
            )}
          >
            {tab.label}
            {tab.status === 'pending' && pendingCount !== undefined && pendingCount > 0 && (
              <span className="rounded-full bg-lane-500 px-2 py-0.5 text-xs font-bold text-asphalt-950 tabular-nums">{pendingCount}</span>
            )}
          </button>
        ))}
      </div>

      {list.isPending ? (
        <p className="text-sm text-asphalt-500" role="status">
          Loading requests…
        </p>
      ) : list.isError ? (
        <ErrorMessage title="Could not load the requests" error={list.error} onRetry={() => void list.refetch()} />
      ) : list.data.items.length === 0 ? (
        <EmptyState icon={<Inbox />} title={EMPTY[status].title}>
          {EMPTY[status].text}
        </EmptyState>
      ) : (
        <ul className="space-y-4">
          {list.data.items.map((item) => (
            <li key={item.id}>
              <RequestCard item={item} onLink={setShownLink} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function RequestCard({ item, onLink }: { item: OrganizationRequest; onLink: (result: InvitationLinkResult) => void }) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'idle' | 'approve' | 'reject'>('idle')
  const [text, setText] = useState('')
  const textId = useId()
  const refresh = () => queryClient.invalidateQueries({ queryKey: platformQueryKeys.all })

  const approve = useMutation({
    mutationFn: () => approveOrganizationRequest(item.id, text.trim()),
    onSuccess: (result) => {
      onLink(result)
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return refresh()
    },
  })
  const reject = useMutation({
    mutationFn: () => rejectOrganizationRequest(item.id, text.trim()),
    meta: { success: 'Request rejected' },
    onSuccess: refresh,
  })
  const relink = useMutation({
    mutationFn: () => newInvitationLink(item.id),
    onSuccess: (result) => {
      onLink(result)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
  })

  return (
    <article aria-labelledby={`${item.id}-name`} className="panel overflow-hidden">
      <div className={cn('h-1', item.status === 'pending' ? 'bg-lane-500' : item.status === 'approved' ? 'bg-emerald-500' : 'bg-asphalt-300')} />
      <div className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id={`${item.id}-name`} className="flex items-center gap-2 text-lg font-semibold">
              <Building2 className="size-5 shrink-0 text-asphalt-400" aria-hidden />
              {item.organization_name}
            </h2>
            <p className="mt-0.5 flex items-center gap-1.5 text-sm text-asphalt-600">
              <MapPin className="size-4 shrink-0" aria-hidden />
              {item.city_or_agency}
            </p>
          </div>
          <p className="text-xs text-asphalt-500">Sent {formatDate(item.created_at)}</p>
        </div>

        <dl className="grid gap-2 text-sm sm:grid-cols-3">
          <Detail icon={UserRound} label="Contact">
            {item.contact_name}
          </Detail>
          <Detail icon={Mail} label="Email">
            <a href={`mailto:${item.contact_email}`} className="link break-all">
              {item.contact_email}
            </a>
          </Detail>
          <Detail icon={Phone} label="Phone">
            {item.phone ?? <span className="text-asphalt-400">Not given</span>}
          </Detail>
        </dl>

        {item.note && (
          <blockquote className="rounded-lg bg-asphalt-50 px-4 py-3 text-sm text-asphalt-700">
            <p className="mb-1 text-xs font-semibold tracking-wide text-asphalt-500 uppercase">Their note</p>
            {item.note}
          </blockquote>
        )}

        {item.status !== 'pending' && (
          <p
            className={cn(
              'flex items-start gap-2 rounded-lg px-4 py-3 text-sm',
              item.status === 'approved' ? 'bg-emerald-50 text-emerald-900' : 'bg-red-50 text-red-900',
            )}
          >
            {item.status === 'approved' ? (
              <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            ) : (
              <CircleX className="mt-0.5 size-4 shrink-0" aria-hidden />
            )}
            <span>
              {item.status === 'approved' ? 'Approved' : 'Rejected'} by {item.decided_by_name ?? 'a platform admin'}
              {item.decided_at && ` on ${formatDate(item.decided_at)}`}
              {item.decision_note && (
                <>
                  . {item.status === 'approved' ? 'Note' : 'Reason'}: {item.decision_note}
                </>
              )}
            </span>
          </p>
        )}

        {item.status === 'pending' && mode === 'idle' && (
          <div className="flex flex-wrap gap-2">
            <Button variant="accent" onClick={() => setMode('approve')}>
              <CircleCheck className="size-4" aria-hidden />
              Approve
            </Button>
            <Button variant="danger" onClick={() => setMode('reject')}>
              <CircleX className="size-4" aria-hidden />
              Reject
            </Button>
          </div>
        )}

        {item.status === 'pending' && mode !== 'idle' && (
          <form
            className={cn('space-y-3 rounded-xl border p-4', mode === 'approve' ? 'border-lane-300 bg-lane-50' : 'border-red-200 bg-red-50/60')}
            onSubmit={(event) => {
              event.preventDefault()
              if (mode === 'approve') approve.mutate()
              else reject.mutate()
            }}
          >
            <p className="text-sm font-medium text-asphalt-900">
              {mode === 'approve'
                ? `Approve “${item.organization_name}”? This creates the organization and an invitation link for ${item.contact_email}.`
                : `Reject the request from “${item.organization_name}”? Nothing is created.`}
            </p>
            <div>
              <label htmlFor={textId} className="mb-1.5 block text-sm font-medium text-asphalt-800">
                {mode === 'approve' ? 'Note for the history (optional)' : 'Reason (kept in the history)'}
              </label>
              <textarea
                id={textId}
                className="control min-h-20 bg-white"
                maxLength={2000}
                value={text}
                required={mode === 'reject'}
                minLength={mode === 'reject' ? 3 : undefined}
                onChange={(event) => setText(event.target.value)}
              />
            </div>
            {approve.isError && <ErrorMessage title="Could not approve" error={approve.error} />}
            {reject.isError && <ErrorMessage title="Could not reject" error={reject.error} />}
            <div className="flex flex-wrap gap-2">
              {mode === 'approve' ? (
                <Button type="submit" variant="accent" busy={approve.isPending}>
                  Approve and create organization
                </Button>
              ) : (
                <Button type="submit" variant="danger" busy={reject.isPending} disabled={text.trim().length < 3}>
                  Reject request
                </Button>
              )}
              <Button
                variant="ghost"
                onClick={() => {
                  setMode('idle')
                  setText('')
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        )}

        {item.status === 'approved' && (
          <div className="space-y-2">
            <Button variant="secondary" busy={relink.isPending} onClick={() => relink.mutate()}>
              <Mail className="size-4" aria-hidden />
              Make a new invite link
            </Button>
            <p className="text-xs text-asphalt-500">Use this if the contact lost the link or it expired. The old link stops working.</p>
            {relink.isError && <ErrorMessage title="Could not make a new link" error={relink.error} />}
          </div>
        )}
      </div>
    </article>
  )
}

function Detail({ icon: Icon, label, children }: { icon: typeof Mail; label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1.5 text-xs font-medium text-asphalt-500">
        <Icon className="size-3.5" aria-hidden />
        {label}
      </dt>
      <dd className="mt-0.5 text-asphalt-900">{children}</dd>
    </div>
  )
}
