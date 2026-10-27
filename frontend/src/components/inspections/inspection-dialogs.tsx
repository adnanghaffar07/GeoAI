import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'

import { typeLabel, type Finding } from '@/api/findings'
import {
  addEvidence,
  evidenceUrl,
  INSPECTION_LABELS,
  inspectionHistory,
  planInspection,
  priorityQueryKeys,
  recordInspection,
  reopenInspection,
  type Inspection,
} from '@/api/priority'
import { listProjectMembers, projectQueryKeys, type ProjectDetail } from '@/api/projects'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { LocationLine } from '@/components/findings/location-line'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { hasProjectPermission } from '@/pages/project/project-layout'

/** A date `days` from today as yyyy-mm-dd, in the person's own time zone. */
function dateIn(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

const formatDay = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { dateStyle: 'medium' })
const formatTime = (time: string) => new Date(time).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-asphalt-950/60 p-4" onKeyDown={(event) => event.key === 'Escape' && onClose()}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="page-enter max-h-[calc(100dvh-2rem)] w-full max-w-xl space-y-4 overflow-y-auto rounded-2xl bg-white p-4 shadow-2xl sm:p-5"
      >
        <h2 className="text-lg font-medium">{title}</h2>
        {children}
      </div>
    </div>
  )
}

/** People on the project, once each (a person can hold several roles). */
function useProjectPeople(projectId: string) {
  const members = useQuery({ queryKey: projectQueryKeys.members(projectId), queryFn: ({ signal }) => listProjectMembers(projectId, signal) })
  const people = useMemo(() => {
    const seen = new Map<string, string>()
    for (const member of members.data?.items ?? []) if (!seen.has(member.user_id)) seen.set(member.user_id, member.full_name)
    return [...seen.entries()].map(([id, name]) => ({ id, name }))
  }, [members.data])
  return { people, members }
}

function OwnerAndDate({
  projectId,
  owner,
  setOwner,
  day,
  setDay,
}: {
  projectId: string
  owner: string
  setOwner: (value: string) => void
  day: string
  setDay: (value: string) => void
}) {
  const { people, members } = useProjectPeople(projectId)
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="space-y-1 text-sm font-medium">
        Who inspects
        <select className="control" value={owner} onChange={(event) => setOwner(event.target.value)} required>
          <option value="">Choose a person…</option>
          {people.map((person) => (
            <option key={person.id} value={person.id}>
              {person.name}
            </option>
          ))}
        </select>
        {members.isError && <span className="text-xs text-red-700">Could not load the project team.</span>}
      </label>
      <label className="space-y-1 text-sm font-medium">
        Planned date
        <input type="date" className="control" value={day} onChange={(event) => setDay(event.target.value)} required />
      </label>
    </div>
  )
}

async function refresh(queryClient: ReturnType<typeof useQueryClient>, project: ProjectDetail, findingId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: priorityQueryKeys.all(project.id) }),
    queryClient.invalidateQueries({ queryKey: priorityQueryKeys.history(findingId) }),
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) }),
    queryClient.invalidateQueries({ queryKey: ['projects', project.id, 'findings'] }),
  ])
}

/** FR-43: plan a field inspection (owner and date). */
export function PlanInspectionDialog({ project, finding, onClose }: { project: ProjectDetail; finding: Finding; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [owner, setOwner] = useState('')
  const [day, setDay] = useState(dateIn(7))
  const plan = useMutation({
    mutationFn: () => planInspection(finding.id, { owner_user_id: owner, planned_date: day }),
    onSuccess: async () => {
      await refresh(queryClient, project, finding.id)
      onClose()
    },
    meta: { success: 'Inspection planned.' },
  })
  return (
    <Dialog title="Plan inspection" onClose={onClose}>
      <div className="space-y-0.5 text-sm text-asphalt-600">
        <p className="font-medium text-asphalt-900">{typeLabel(finding.type_key)}</p>
        <LocationLine location={finding.location} confirmed={finding.location_quality === 'reviewer_confirmed'} />
      </div>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (owner && day) plan.mutate()
        }}
      >
        <OwnerAndDate projectId={project.id} owner={owner} setOwner={setOwner} day={day} setDay={setDay} />
        {plan.isError && <ErrorMessage title="Could not plan the inspection" error={plan.error} />}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={plan.isPending} disabled={!owner || !day}>
            Plan inspection
          </Button>
        </div>
      </form>
    </Dialog>
  )
}

/** S13: record the result (inspected / resolved with a note or photo), or reopen. */
export function InspectionDialog({ project, finding, onClose }: { project: ProjectDetail; finding: Finding; onClose: () => void }) {
  const history = useQuery({ queryKey: priorityQueryKeys.history(finding.id), queryFn: ({ signal }) => inspectionHistory(finding.id, signal) })
  const current = history.data?.at(-1)
  const earlier = history.data?.slice(0, -1).reverse() ?? []
  return (
    <Dialog title="Inspection" onClose={onClose}>
      <div className="space-y-0.5 text-sm text-asphalt-600">
        <p className="font-medium text-asphalt-900">{typeLabel(finding.type_key)}</p>
        <LocationLine location={finding.location} confirmed={finding.location_quality === 'reviewer_confirmed'} />
      </div>
      {history.isPending && <SkeletonRows rows={2} />}
      {history.isError && <ErrorMessage title="Could not load the inspection" error={history.error} onRetry={() => void history.refetch()} />}
      {current && <CurrentInspection key={`${current.id}:${current.status}:${current.has_evidence}`} project={project} finding={finding} inspection={current} />}
      {earlier.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-medium">Earlier inspections</h3>
          <ul className="space-y-2">
            {earlier.map((item) => (
              <li key={item.id} className="rounded-lg border border-asphalt-100 p-3 text-sm">
                <InspectionSummary inspection={item} />
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="flex justify-end">
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
    </Dialog>
  )
}

function InspectionSummary({ inspection }: { inspection: Inspection }) {
  return (
    <div className="space-y-1">
      <p>
        <span className="font-medium">{INSPECTION_LABELS[inspection.status]}</span> · {inspection.owner_name ?? 'unknown'} · planned for{' '}
        {formatDay(inspection.planned_date)}
      </p>
      {inspection.inspected_at && (
        <p className="text-xs text-asphalt-600">
          Inspected by {inspection.inspected_by_name}, {formatTime(inspection.inspected_at)}
        </p>
      )}
      {inspection.resolved_at && (
        <p className="text-xs text-asphalt-600">
          Resolved by {inspection.resolved_by_name}, {formatTime(inspection.resolved_at)}
        </p>
      )}
      {inspection.outcome_note && <p className="whitespace-pre-line rounded bg-asphalt-50 px-2 py-1 text-xs">Result: {inspection.outcome_note}</p>}
      {inspection.reopen_reason && (
        <p className="text-xs text-amber-800">
          Reopened by {inspection.reopened_by_name}
          {inspection.reopened_at && `, ${formatTime(inspection.reopened_at)}`}: {inspection.reopen_reason}
        </p>
      )}
      {inspection.has_evidence && (
        <a href={evidenceUrl(inspection.id)} target="_blank" rel="noreferrer" className="inline-block">
          <img src={evidenceUrl(inspection.id)} alt="Photo of the result" className="h-24 rounded border border-asphalt-100 object-cover" />
        </a>
      )}
    </div>
  )
}

function CurrentInspection({ project, finding, inspection }: { project: ProjectDetail; finding: Finding; inspection: Inspection }) {
  const queryClient = useQueryClient()
  const { me } = useAuth()
  const [note, setNote] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [reopening, setReopening] = useState(false)
  const [reason, setReason] = useState('')
  const [owner, setOwner] = useState(inspection.owner_user_id)
  const [day, setDay] = useState(dateIn(7))
  const active = inspection.status === 'planned' || inspection.status === 'inspected'
  // Managers record any inspection; others only their own (the server checks this too).
  const canRecord =
    !project.archived &&
    hasProjectPermission(project, 'inspection.record') &&
    (hasProjectPermission(project, 'inspection.plan') || inspection.owner_user_id === me?.user.id)
  const canReopen = !project.archived && hasProjectPermission(project, 'inspection.reopen') && inspection.status === 'resolved'

  const done = () => refresh(queryClient, project, finding.id)
  const record = useMutation({
    mutationFn: (status: 'inspected' | 'resolved') => recordInspection(inspection.id, { status, outcome_note: note.trim() || undefined }),
    onSuccess: done,
    meta: { success: 'Inspection result saved.' },
  })
  const upload = useMutation({ mutationFn: (file: File) => addEvidence(inspection.id, file), onSuccess: done, meta: { success: 'Photo added to the inspection.' } })
  const reopen = useMutation({
    mutationFn: () => reopenInspection(inspection.id, { reason: reason.trim(), owner_user_id: owner, planned_date: day }),
    onSuccess: done,
    meta: { success: 'Inspection reopened.' },
  })

  const resolve = () => {
    setProblem(null)
    if (!note.trim() && !inspection.outcome_note && !inspection.has_evidence) {
      setProblem('To mark it resolved, add a note or a photo of the result.')
      return
    }
    record.mutate('resolved')
  }

  return (
    <section className="space-y-3 rounded-lg border border-asphalt-200 p-3">
      <InspectionSummary inspection={inspection} />
      {active && canRecord && (
        <div className="space-y-3 border-t border-asphalt-100 pt-3">
          <label className="block space-y-1 text-sm font-medium">
            What was found or done
            <textarea className="control min-h-20" maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Photo of the result <span className="font-normal text-asphalt-500">(JPEG or PNG, optional)</span>
            <input
              type="file"
              accept="image/jpeg,image/png"
              className="block text-sm"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) upload.mutate(file)
                event.target.value = ''
              }}
            />
          </label>
          {upload.isPending && <p className="text-xs text-asphalt-500">Uploading photo…</p>}
          {upload.isError && <ErrorMessage title="Could not attach the photo" error={upload.error} />}
          {problem && (
            <p role="alert" className="text-sm text-red-700">
              {problem}
            </p>
          )}
          {record.isError && <ErrorMessage title="Could not save the result" error={record.error} />}
          <div className="flex flex-wrap gap-2">
            {inspection.status === 'planned' && (
              <Button variant="secondary" busy={record.isPending && record.variables === 'inspected'} onClick={() => record.mutate('inspected')}>
                Mark inspected
              </Button>
            )}
            <Button busy={record.isPending && record.variables === 'resolved'} onClick={resolve}>
              Mark resolved
            </Button>
          </div>
        </div>
      )}
      {canReopen &&
        (reopening ? (
          <form
            className="space-y-3 border-t border-asphalt-100 pt-3"
            onSubmit={(event) => {
              event.preventDefault()
              if (reason.trim() && owner && day) reopen.mutate()
            }}
          >
            <label className="block space-y-1 text-sm font-medium">
              Why reopen? <span className="font-normal text-asphalt-500">(required, kept in the history)</span>
              <textarea className="control min-h-16" maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} required />
            </label>
            <OwnerAndDate projectId={project.id} owner={owner} setOwner={setOwner} day={day} setDay={setDay} />
            {reopen.isError && <ErrorMessage title="Could not reopen" error={reopen.error} />}
            <div className="flex gap-2">
              <Button type="submit" busy={reopen.isPending} disabled={!reason.trim()}>
                Reopen and plan again
              </Button>
              <Button variant="ghost" onClick={() => setReopening(false)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <Button variant="secondary" onClick={() => setReopening(true)}>
            Reopen
          </Button>
        ))}
    </section>
  )
}
