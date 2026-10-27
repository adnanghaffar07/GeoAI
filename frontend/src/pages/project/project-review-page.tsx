import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, Eye, EyeOff, Minus, Plus } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router'

import { notify } from '@/lib/notify'
import {
  findingHistory,
  findingQueryKeys,
  getFinding,
  getReviewOptions,
  listFindings,
  reviewFinding,
  TO_REVIEW,
  typeLabel,
  type Finding,
  type ReviewAction,
  type ReviewOptions,
  type ReviewRequest,
} from '@/api/findings'
import type { LatLon } from '@/api/images'
import { projectQueryKeys, type ProjectDetail } from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { FindingHistory } from '@/components/findings/finding-history'
import { ModelLabel } from '@/components/findings/model-label'
import { FindingPhoto } from '@/components/findings/finding-photo'
import { StatusPill } from '@/components/findings/status-pill'
import { PickLocationMap } from '@/components/map/pick-location-map'
import { Button } from '@/components/ui/button'
import { LoadingScreen, SkeletonRows } from '@/components/ui/loading-screen'
import { isApiError } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'


const SAVED_MESSAGE: Record<ReviewAction, string> = {
  verify: 'Saved: verified.',
  reject: 'Saved: rejected.',
  needs_field_check: 'Saved: needs a field check.',
  edit: 'Changes saved.',
}
const ZOOM_LEVELS = [1, 1.5, 2, 3]

/** S10 Review finding: check one finding and decide (FR-30 to FR-38). */
export function ProjectReviewPage() {
  const project = useProject()
  const { findingId = '' } = useParams()
  const finding = useQuery({ queryKey: findingQueryKeys.detail(findingId), queryFn: ({ signal }) => getFinding(findingId, signal) })
  const options = useQuery({ queryKey: findingQueryKeys.options(project.id), queryFn: ({ signal }) => getReviewOptions(project.id, signal) })
  const backLink = `/projects/${project.id}/findings?selected=${findingId}`

  if (!hasProjectPermission(project, 'finding.review')) {
    return (
      <Notice backLink={backLink}>Only technical reviewers can review findings. Ask the project manager if you should be one.</Notice>
    )
  }
  if (finding.isPending || options.isPending) return <LoadingScreen label="Loading finding…" />
  if (finding.isError) return <ErrorMessage title="Could not open the finding" error={finding.error} onRetry={() => void finding.refetch()} />
  if (options.isError) return <ErrorMessage title="Could not load types and severity levels" error={options.error} onRetry={() => void options.refetch()} />

  // A new version from the server (after a save or a reload) starts a fresh form.
  return <ReviewWorkspace key={`${finding.data.id}:${finding.data.version}`} finding={finding.data} options={options.data} project={project} onReload={() => void finding.refetch()} />
}

function Notice({ children, backLink }: { children: React.ReactNode; backLink: string }) {
  return (
    <div className="space-y-3">
      <p className="rounded-lg border border-asphalt-200 bg-white p-4 text-sm">{children}</p>
      <Link to={backLink} className="link text-sm">
        Back to findings
      </Link>
    </div>
  )
}

interface FormState {
  typeKey: string
  severityKey: string
  notes: string
  /** The pin to save. `undefined` = not moved in this session. */
  pin: LatLon | null | undefined
  reason: string
}

function initialForm(finding: Finding): FormState {
  return { typeKey: finding.type_key ?? '', severityKey: finding.severity_key ?? '', notes: finding.notes ?? '', pin: undefined, reason: '' }
}

/** Only the fields the reviewer actually changed are sent (the server keeps everything else). */
function buildRequest(action: ReviewAction, finding: Finding, form: FormState): ReviewRequest {
  const request: ReviewRequest = { action, version: finding.version }
  if (form.typeKey && form.typeKey !== (finding.type_key ?? '')) request.type_key = form.typeKey
  if (form.severityKey && form.severityKey !== (finding.severity_key ?? '')) request.severity_key = form.severityKey
  if (form.notes !== (finding.notes ?? '')) request.notes = form.notes
  if (form.pin !== undefined) request.corrected_location = form.pin
  if (form.reason.trim()) request.reason = form.reason.trim()
  return request
}

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
}

function ReviewWorkspace({ finding, options, project, onReload }: { finding: Finding; options: ReviewOptions; project: ProjectDetail; onReload: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>(() => initialForm(finding))
  const [showBox, setShowBox] = useState(true)
  const [zoom, setZoom] = useState(0)
  const [problem, setProblem] = useState<string | null>(null)
  const leaving = useRef(false)
  const editable = !project.archived && finding.review_status !== 'merged'
  const rubric = options.severity_rubric

  // The review queue: suggestions and observations still waiting for a decision.
  const queue = useQuery({
    queryKey: findingQueryKeys.queue(project.id),
    queryFn: ({ signal }) => listFindings(project.id, { review_status: TO_REVIEW }, { pageSize: 200 }, signal),
  })
  const nextId = useMemo(() => {
    const ids = queue.data?.items.map((item) => item.id) ?? []
    const here = ids.indexOf(finding.id)
    const after = here >= 0 ? [...ids.slice(here + 1), ...ids.slice(0, here)] : ids
    return after.find((id) => id !== finding.id) ?? null
  }, [queue.data, finding.id])
  const waiting = (queue.data?.total ?? 0) - (queue.data?.items.some((item) => item.id === finding.id) ? 1 : 0)

  const history = useQuery({
    queryKey: findingQueryKeys.history(finding.id),
    queryFn: ({ signal }) => findingHistory(finding.id, signal),
    enabled: hasProjectPermission(project, 'finding.history.view'),
  })

  const initial = initialForm(finding)
  const dirty =
    form.typeKey !== initial.typeKey ||
    form.severityKey !== initial.severityKey ||
    form.notes !== initial.notes ||
    form.pin !== undefined ||
    form.reason.trim() !== ''

  // FR-36: warn before leaving with unsaved changes (inside the app and when closing the tab).
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !leaving.current && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const goNext = (id: string | null) => {
    leaving.current = true
    navigate(id ? `/projects/${project.id}/review/${id}` : `/projects/${project.id}/findings?selected=${finding.id}`)
  }

  const save = useMutation({
    mutationFn: (request: ReviewRequest) => reviewFinding(finding.id, request),
    onSuccess: async (updated, request) => {
      queryClient.setQueryData(findingQueryKeys.detail(finding.id), updated)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: findingQueryKeys.all(project.id) }),
        queryClient.invalidateQueries({ queryKey: findingQueryKeys.history(finding.id) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) }),
      ])
      notify.success(SAVED_MESSAGE[request.action] + (request.action !== 'edit' && nextId ? ' Here is the next one.' : ''))
      // The next finding opens only after this decision is saved (spec).
      if (request.action !== 'edit') goNext(nextId)
    },
  })
  const conflict = isApiError(save.error) && save.error.status === 409 && save.error.code === 'conflict' && save.error.details !== null

  const decide = (action: ReviewAction) => {
    if (!editable || save.isPending) return
    setProblem(null)
    if (action === 'verify' && !(form.typeKey && form.severityKey)) {
      setProblem('Choose a type and a severity before verifying.')
      return
    }
    if (action === 'edit' && !dirty) {
      setProblem('Nothing has changed yet.')
      return
    }
    save.mutate(buildRequest(action, finding, form))
  }

  // Keyboard shortcuts (not while typing in a box).
  const decideRef = useRef(decide)
  useEffect(() => {
    decideRef.current = decide
  })
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)) return
      const key = event.key.toLowerCase()
      if (key === 'v') decideRef.current('verify')
      else if (key === 'r') decideRef.current('reject')
      else if (key === 'f') decideRef.current('needs_field_check')
      else if (key === 'b') setShowBox((value) => !value)
      else if (key === '+' || key === '=') setZoom((value) => Math.min(ZOOM_LEVELS.length - 1, value + 1))
      else if (key === '-') setZoom((value) => Math.max(0, value - 1))
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const pinShown = form.pin === undefined ? finding.location : (form.pin ?? finding.original_location)
  const pinMoved = form.pin !== undefined ? form.pin !== null : finding.corrected_location !== null
  const aiType = finding.predicted_type_key
  const set = (changes: Partial<FormState>) => {
    setProblem(null) // an earlier hint ("choose a type…") no longer applies once the form changes
    setForm((current) => ({ ...current, ...changes }))
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to={`/projects/${project.id}/findings?selected=${finding.id}`} className="link inline-flex items-center gap-1 text-sm">
          <ChevronLeft className="size-4" aria-hidden />
          Back to findings
        </Link>
        <p className="text-sm text-asphalt-500">{queue.isSuccess && `${Math.max(0, waiting)} other finding${waiting === 1 ? '' : 's'} waiting for review`}</p>
      </div>

      {project.archived && <p className="rounded-lg border border-asphalt-200 bg-asphalt-50 p-3 text-sm">This project is archived: findings can be viewed but not changed.</p>}
      {rubric.is_placeholder && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          The severity levels are a sample until your city confirms its own list. Each saved severity remembers which list was used.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* Photo */}
        <section aria-label="Photo" className="min-w-0 space-y-2">
          {finding.photo ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="secondary" onClick={() => setShowBox((value) => !value)} disabled={!finding.predicted_bbox} aria-pressed={showBox}>
                  {showBox ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                  {showBox ? 'Hide AI box' : 'Show AI box'}
                </Button>
                <div className="flex items-center gap-1" role="group" aria-label="Zoom">
                  <Button variant="ghost" className="px-2" onClick={() => setZoom((value) => Math.max(0, value - 1))} disabled={zoom === 0} aria-label="Zoom out">
                    <Minus className="size-4" aria-hidden />
                  </Button>
                  <span className="w-10 text-center text-sm tabular-nums">{ZOOM_LEVELS[zoom]}×</span>
                  <Button
                    variant="ghost"
                    className="px-2"
                    onClick={() => setZoom((value) => Math.min(ZOOM_LEVELS.length - 1, value + 1))}
                    disabled={zoom === ZOOM_LEVELS.length - 1}
                    aria-label="Zoom in"
                  >
                    <Plus className="size-4" aria-hidden />
                  </Button>
                </div>
              </div>
              <FindingPhoto finding={finding} showBox={showBox} zoom={ZOOM_LEVELS[zoom]} original className="max-h-[70dvh] rounded-lg" />
              <p className="text-xs text-asphalt-500">
                Shortcuts (when not typing): <kbd>V</kbd> verify · <kbd>R</kbd> reject · <kbd>F</kbd> needs field check · <kbd>B</kbd> box on/off · <kbd>+</kbd>/<kbd>-</kbd> zoom
              </p>
            </>
          ) : (
            <>
              <p className="rounded-lg border border-dashed border-asphalt-200 bg-white p-4 text-sm text-asphalt-500">No photo was attached to this observation.</p>
              <p className="text-xs text-asphalt-500">
                Shortcuts (when not typing): <kbd>V</kbd> verify · <kbd>R</kbd> reject · <kbd>F</kbd> needs field check
              </p>
            </>
          )}
        </section>

        {/* Decision */}
        <section aria-label="Review" className="min-w-0 space-y-4">
          <div className="panel space-y-2 p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={finding.review_status} />
            </div>
            {finding.origin === 'ai' ? (
              <>
                <p>
                  AI suggests <strong className="font-medium">{typeLabel(aiType, options.finding_types)}</strong>
                  {finding.predicted_confidence !== null && (
                    <span className="text-asphalt-600"> · AI certainty {Math.round(finding.predicted_confidence * 100)}%</span>
                  )}
                </p>
                <p className="text-xs text-asphalt-500">
                  AI certainty is how sure the AI is about the type, not how serious the problem is. You decide that below. (AI model {finding.model_version})
                </p>
                <ModelLabel testDetector={finding.is_test_detector} trialModel={finding.is_trial_model} />
              </>
            ) : (
              <p>
                Added by a person{finding.created_by_name && ` (${finding.created_by_name})`}. There is no AI suggestion.
              </p>
            )}
          </div>

          <fieldset disabled={!editable} className="space-y-3">
            <label className="block space-y-1 text-sm font-medium">
              Type
              <select className="control" value={form.typeKey} onChange={(event) => set({ typeKey: event.target.value })}>
                <option value="">Choose a type…</option>
                {options.finding_types.map((type) => (
                  <option key={type.key} value={type.key}>
                    {type.label}
                    {!type.in_project ? ' (not tracked in this project)' : ''}
                  </option>
                ))}
              </select>
            </label>
            {aiType && form.typeKey !== aiType && options.finding_types.some((type) => type.key === aiType) && (
              <button type="button" className="link text-sm" onClick={() => set({ typeKey: aiType })}>
                Use the AI's suggestion ({typeLabel(aiType, options.finding_types)})
              </button>
            )}

            <div role="radiogroup" aria-label="Severity" className="space-y-1">
              <p className="text-sm font-medium">
                Severity <span className="font-normal text-asphalt-500">(how serious is it?)</span>
              </p>
              <div className="flex flex-wrap gap-2">
                {rubric.levels.map((level) => (
                  <label
                    key={level.key}
                    title={level.definition || undefined}
                    className={cn(
                      'cursor-pointer rounded-lg border px-3 py-1.5 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-lane-400',
                      form.severityKey === level.key ? 'border-asphalt-800 bg-asphalt-800 text-white' : 'border-asphalt-200 bg-white',
                    )}
                  >
                    <input
                      type="radio"
                      name="severity"
                      value={level.key}
                      checked={form.severityKey === level.key}
                      onChange={() => set({ severityKey: level.key })}
                      className="sr-only"
                    />
                    {level.label}
                  </label>
                ))}
              </div>
              {(() => {
                const chosen = rubric.levels.find((level) => level.key === form.severityKey)
                return chosen?.definition ? <p className="text-xs text-asphalt-500">{chosen.label}: {chosen.definition}</p> : null
              })()}
            </div>

            <label className="block space-y-1 text-sm font-medium">
              Notes
              <textarea className="control min-h-20" value={form.notes} maxLength={2000} onChange={(event) => set({ notes: event.target.value })} />
            </label>

            <div className="space-y-1">
              <p className="text-sm font-medium">Location</p>
              <PickLocationMap
                area={project.boundary}
                value={pinShown}
                onPick={(point) => set({ pin: point })}
                label="Map: click to move the finding's pin"
                className="h-56"
              />
              <p className="text-xs text-asphalt-500">
                {pinShown
                  ? pinMoved
                    ? 'Pin moved by a reviewer. The original position is kept separately.'
                    : finding.location_source === 'manual'
                      ? 'Point picked when this was added (approximate). Click the map to move the pin.'
                      : 'Approximate camera position, not the exact spot of the problem. Click the map to move the pin.'
                  : 'No location yet. Click the map to set one; until then this finding is not shown on the map.'}
                {pinMoved && editable && (
                  <button type="button" className="ml-2 link" onClick={() => set({ pin: finding.corrected_location ? null : undefined })}>
                    Back to original position
                  </button>
                )}
              </p>
            </div>

            <label className="block space-y-1 text-sm font-medium">
              Reason for the decision <span className="font-normal text-asphalt-500">(optional, kept in the history)</span>
              <input className="control" value={form.reason} maxLength={2000} onChange={(event) => set({ reason: event.target.value })} />
            </label>
          </fieldset>

          {problem && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {problem}
            </p>
          )}
          {conflict ? (
            <div role="alert" className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              <p className="font-medium">This finding was changed by someone else.</p>
              <p>Reload to see the latest version. Your changes on this screen will be cleared, so note anything you want to keep.</p>
              <Button
                variant="secondary"
                onClick={() => {
                  leaving.current = true
                  onReload()
                }}
              >
                Reload
              </Button>
            </div>
          ) : (
            save.isError && <ErrorMessage title="Could not save the review" error={save.error} />
          )}

          {editable && (
            <p className="text-xs text-asphalt-500">
              <strong className="font-medium text-asphalt-700">Verify</strong> if it is a real problem, <strong className="font-medium text-asphalt-700">Reject</strong> if
              it is not, or <strong className="font-medium text-asphalt-700">Needs field check</strong> if someone must look on site to be sure.
            </p>
          )}
          {editable && (
            <div className="flex flex-wrap gap-2">
              <Button busy={save.isPending && save.variables?.action === 'verify'} onClick={() => decide('verify')}>
                Verify
              </Button>
              <Button variant="danger" busy={save.isPending && save.variables?.action === 'reject'} onClick={() => decide('reject')}>
                Reject
              </Button>
              <Button variant="secondary" busy={save.isPending && save.variables?.action === 'needs_field_check'} onClick={() => decide('needs_field_check')}>
                Needs field check
              </Button>
              <Button variant="ghost" busy={save.isPending && save.variables?.action === 'edit'} onClick={() => decide('edit')} disabled={!dirty}>
                Save without deciding
              </Button>
            </div>
          )}
          {editable && form.typeKey && form.severityKey && !pinMoved && finding.location_quality !== 'reviewer_confirmed' && (
            <p className="text-xs text-amber-800">
              {finding.location ? 'Location not confirmed: the pin is the approximate camera position.' : 'This finding has no location.'}
            </p>
          )}
          {nextId && (
            <Button variant="ghost" onClick={() => navigate(`/projects/${project.id}/review/${nextId}`)}>
              Skip to the next finding
            </Button>
          )}

          {hasProjectPermission(project, 'finding.history.view') && (
            <section className="space-y-2">
              <h2 className="font-medium">History</h2>
              {history.isPending && <SkeletonRows rows={2} />}
              {history.isError && <ErrorMessage title="Could not load the history" error={history.error} />}
              {history.isSuccess && <FindingHistory events={history.data} options={options} />}
            </section>
          )}
        </section>
      </div>

      {blocker.state === 'blocked' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-asphalt-950/60 p-4">
          <div role="alertdialog" aria-modal="true" aria-labelledby="leave-title" className="page-enter w-full max-w-md space-y-3 rounded-2xl bg-white p-5 shadow-2xl">
            <h2 id="leave-title" className="text-lg font-medium">
              Leave without saving?
            </h2>
            <p className="text-sm text-asphalt-600">Your changes to this finding have not been saved.</p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => blocker.reset()}>
                Stay
              </Button>
              <Button variant="danger" onClick={() => blocker.proceed()}>
                Leave
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
