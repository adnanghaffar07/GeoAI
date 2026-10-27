import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ListChecks, MapPinOff, Plus, SearchX, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { ModelLabel } from '@/components/findings/model-label'
import {
  addManualFinding,
  findingHistory,
  findingQueryKeys,
  findingsMap,
  getFinding,
  getReviewOptions,
  listFindings,
  TO_REVIEW,
  typeLabel,
  type Finding,
  type FindingFilters,
  type ReviewOptions,
} from '@/api/findings'
import { imageQueryKeys, listImages, originalUrl, type LatLon } from '@/api/images'
import { projectQueryKeys, type ProjectDetail } from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { FindingHistory } from '@/components/findings/finding-history'
import { FindingPhoto } from '@/components/findings/finding-photo'
import { StatusPill } from '@/components/findings/status-pill'
import { FindingsMap } from '@/components/map/findings-map'
import { PickLocationMap } from '@/components/map/pick-location-map'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { severityLabel } from '@/lib/findings'
import { cn } from '@/lib/utils'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

const PAGE_SIZE = 50

/** Status choices in the filter. "" = everything the person may see except rejected. */
const STATUS_CHOICES: { value: string; label: string; statuses: FindingFilters['review_status']; needs?: string }[] = [
  { value: '', label: 'All except rejected', statuses: undefined },
  { value: 'to_review', label: 'To review', statuses: TO_REVIEW, needs: 'finding.view_candidates' },
  { value: 'needs_field_check', label: 'Needs field check', statuses: ['needs_field_check'], needs: 'finding.view_candidates' },
  { value: 'verified', label: 'Verified', statuses: ['verified'] },
  { value: 'rejected', label: 'Rejected', statuses: ['rejected'], needs: 'finding.view_rejected' },
]

/** Filters live in the address, so a filtered view can be shared and survives a reload. */
function readFilters(params: URLSearchParams): FindingFilters {
  const status = STATUS_CHOICES.find((choice) => choice.value === (params.get('status') ?? ''))
  const location = params.get('location')
  return {
    review_status: status?.statuses,
    type_key: params.get('type') || undefined,
    severity_key: params.get('severity') || undefined,
    has_location: location === 'yes' ? true : location === 'no' ? false : undefined,
    created_from: params.get('from') || undefined,
    created_to: params.get('to') || undefined,
    image_id: params.get('image') || undefined,
  }
}

const FILTER_KEYS = ['status', 'type', 'severity', 'location', 'from', 'to', 'image']

/** S09 Map and findings: filters, a list and a map that always show the same findings. */
export function ProjectFindingsPage() {
  const project = useProject()
  const [params, setParams] = useSearchParams()
  const filters = useMemo(() => readFilters(params), [params])
  const page = Math.max(1, Number(params.get('page')) || 1)
  const selectedId = params.get('selected')
  const [adding, setAdding] = useState(false)
  const canAdd = hasProjectPermission(project, 'finding.create_manual') && !project.archived

  const options = useQuery({ queryKey: findingQueryKeys.options(project.id), queryFn: ({ signal }) => getReviewOptions(project.id, signal) })
  const list = useQuery({
    queryKey: findingQueryKeys.list(project.id, filters, page),
    queryFn: ({ signal }) => listFindings(project.id, filters, { page, pageSize: PAGE_SIZE }, signal),
    placeholderData: keepPreviousData,
  })
  const mapData = useQuery({
    queryKey: findingQueryKeys.map(project.id, filters),
    queryFn: ({ signal }) => findingsMap(project.id, filters, signal),
    placeholderData: keepPreviousData,
  })
  const inList = list.data?.items.find((item) => item.id === selectedId)
  // A pin can belong to a finding on another page of the list: load it on its own.
  const single = useQuery({
    queryKey: findingQueryKeys.detail(selectedId ?? ''),
    queryFn: ({ signal }) => getFinding(selectedId ?? '', signal),
    enabled: Boolean(selectedId) && list.isSuccess && !inList,
  })
  const selected = inList ?? single.data ?? null

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    // A different filter means a different list: start again from page 1.
    if (Object.keys(changes).some((key) => FILTER_KEYS.includes(key))) next.delete('page')
    setParams(next, { replace: true })
  }
  const select = (id: string | null) => update({ selected: id })
  const filtered = FILTER_KEYS.some((key) => params.get(key))
  const resetFilters = () => update(Object.fromEntries(FILTER_KEYS.map((key) => [key, null])))
  const seesSuggestions = hasProjectPermission(project, 'finding.view_candidates')
  const lastPage = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-4">
      <PageIntro
        title="Findings"
        actions={
          canAdd && (
            <Button variant="secondary" onClick={() => setAdding(true)}>
              <Plus className="size-4" aria-hidden />
              Add observation
            </Button>
          )
        }
      >
        {seesSuggestions
          ? 'Road problems suggested by the AI or added by people, as a list and on a map. Click one to see its photo and details.'
          : 'Road problems that a reviewer has checked and verified, as a list and on a map. Click one to see its photo and details.'}
      </PageIntro>

      {seesSuggestions && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong className="font-medium">AI suggestions are not confirmed problems.</strong> A reviewer checks each one. "AI certainty" shows
          how sure the AI is, not how serious the problem is. Map pins show roughly where the camera was, unless a reviewer moved them.
        </p>
      )}

      {options.isError && (
        <ErrorMessage title="Could not load the list of problem types" error={options.error} onRetry={() => void options.refetch()} />
      )}

      <FilterBar project={project} params={params} options={options.data} onChange={update} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-asphalt-500" aria-live="polite">
          {list.isSuccess && `${list.data.total} finding${list.data.total === 1 ? '' : 's'}`}
          {filters.image_id && ' for one photo'}
        </p>
        {filtered && (
          <Button variant="ghost" onClick={resetFilters}>
            Reset filters
          </Button>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="min-w-0 space-y-3">
          {list.isPending && <SkeletonRows rows={5} />}
          {list.isError && <ErrorMessage title="Could not load findings" error={list.error} onRetry={() => void list.refetch()} />}
          {list.isSuccess &&
            (list.data.items.length === 0 ? (
              filtered ? (
                <EmptyState
                  icon={<SearchX />}
                  title="No findings match these filters"
                  action={
                    <Button variant="ghost" onClick={resetFilters}>
                      Reset filters
                    </Button>
                  }
                >
                  Try fewer filters to see more findings.
                </EmptyState>
              ) : seesSuggestions ? (
                <EmptyState icon={<ListChecks />} title="No findings yet">
                  Findings appear here when the AI has checked photos (on the Photos tab), or when someone adds an observation.
                </EmptyState>
              ) : (
                <EmptyState icon={<ListChecks />} title="No verified findings yet">
                  Findings appear here once a reviewer has checked and verified them.
                </EmptyState>
              )
            ) : (
              <ul className="space-y-2" aria-label="Findings">
                {list.data.items.map((finding) => (
                  <FindingRow
                    key={finding.id}
                    finding={finding}
                    options={options.data}
                    selected={finding.id === selectedId}
                    onSelect={() => select(finding.id)}
                  />
                ))}
              </ul>
            ))}
          {lastPage > 1 && (
            <nav aria-label="Pages" className="flex items-center gap-3 text-sm">
              <Button variant="secondary" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>
                Previous
              </Button>
              <span>
                Page {page} of {lastPage}
              </span>
              <Button variant="secondary" disabled={page >= lastPage} onClick={() => update({ page: String(page + 1) })}>
                Next
              </Button>
            </nav>
          )}
        </div>
        <div className="lg:sticky lg:top-4 lg:self-start">
          <FindingsMap area={project.boundary} data={mapData.data} selectedId={selectedId} onSelect={select} className="h-80 lg:h-[calc(100dvh-8rem)]" />
          {mapData.isError && (
            <div className="mt-2">
              <ErrorMessage title="The map could not show the findings. The list is still correct." error={mapData.error} onRetry={() => void mapData.refetch()} />
            </div>
          )}
        </div>
      </div>

      {single.isError && <ErrorMessage title="Could not open this finding" error={single.error} onRetry={() => void single.refetch()} />}

      {selected && <FindingDrawer finding={selected} project={project} options={options.data} onClose={() => select(null)} />}
      {adding && options.data && (
        <AddObservationDialog
          project={project}
          options={options.data}
          onClose={() => setAdding(false)}
          onAdded={(finding) => {
            setAdding(false)
            // Show the new observation: it is "awaiting review".
            update({ ...Object.fromEntries(FILTER_KEYS.map((key) => [key, null])), selected: finding.id })
          }}
        />
      )}
    </div>
  )
}

function FilterBar({
  project,
  params,
  options,
  onChange,
}: {
  project: ProjectDetail
  params: URLSearchParams
  options: ReviewOptions | undefined
  onChange: (changes: Record<string, string | null>) => void
}) {
  // People who only see verified findings get no status choice (there is only one status).
  const statusChoices = hasProjectPermission(project, 'finding.view_candidates')
    ? STATUS_CHOICES.filter((choice) => !choice.needs || hasProjectPermission(project, choice.needs))
    : []
  const field = 'control h-9 py-1 text-sm'
  return (
    <div className="panel grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-6" role="group" aria-label="Filters">
      {statusChoices.length > 1 && (
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Status
          <select className={field} value={params.get('status') ?? ''} onChange={(event) => onChange({ status: event.target.value || null })}>
            {statusChoices.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="space-y-1 text-xs font-medium text-asphalt-600">
        Type
        <select className={field} value={params.get('type') ?? ''} onChange={(event) => onChange({ type: event.target.value || null })}>
          <option value="">All types</option>
          {options?.finding_types.map((type) => (
            <option key={type.key} value={type.key}>
              {type.label}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1 text-xs font-medium text-asphalt-600">
        Severity
        <select className={field} value={params.get('severity') ?? ''} onChange={(event) => onChange({ severity: event.target.value || null })}>
          <option value="">Any severity</option>
          {options?.severity_rubric.levels.map((level) => (
            <option key={level.key} value={level.key}>
              {level.label}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1 text-xs font-medium text-asphalt-600">
        Location
        <select className={field} value={params.get('location') ?? ''} onChange={(event) => onChange({ location: event.target.value || null })}>
          <option value="">With or without</option>
          <option value="yes">Has a location</option>
          <option value="no">No location</option>
        </select>
      </label>
      <label className="space-y-1 text-xs font-medium text-asphalt-600">
        Added from
        <input type="date" className={field} value={params.get('from') ?? ''} onChange={(event) => onChange({ from: event.target.value || null })} />
      </label>
      <label className="space-y-1 text-xs font-medium text-asphalt-600">
        Added until
        <input type="date" className={field} value={params.get('to') ?? ''} onChange={(event) => onChange({ to: event.target.value || null })} />
      </label>
    </div>
  )
}

/** The type to show: the reviewer's (or creator's) choice, otherwise the AI's suggestion. */
function shownType(finding: Finding, options: ReviewOptions | undefined): string {
  if (finding.type_key) return typeLabel(finding.type_key, options?.finding_types)
  return `AI suggests: ${typeLabel(finding.predicted_type_key, options?.finding_types)}`
}

function FindingRow({ finding, options, selected, onSelect }: { finding: Finding; options: ReviewOptions | undefined; selected: boolean; onSelect: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={cn(
          'flex w-full gap-3 rounded-xl border bg-white p-2 text-left transition-colors hover:border-asphalt-300',
          selected ? 'border-asphalt-800 ring-2 ring-lane-400' : 'border-asphalt-100',
        )}
      >
        <FindingPhoto finding={finding} className="w-24 shrink-0 self-start rounded-md sm:w-28" />
        <div className="min-w-0 flex-1 space-y-1 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{shownType(finding, options)}</span>
            <StatusPill status={finding.review_status} />
          </div>
          <p className="text-xs text-asphalt-600">
            {finding.severity_key ? `Severity: ${severityLabel(finding.severity_key, options)}` : 'Severity not set'}
            {finding.predicted_confidence !== null && ` · AI certainty ${Math.round(finding.predicted_confidence * 100)}% (not severity)`}
            {finding.origin === 'manual' && ' · Added by a person'}
          </p>
          {!finding.location && (
            <p className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800">
              <MapPinOff className="size-3.5" aria-hidden />
              No location, so not on the map
            </p>
          )}
          <ModelLabel testDetector={finding.is_test_detector} trialModel={finding.is_trial_model} className="text-[0.65rem]" />
        </div>
      </button>
    </li>
  )
}

/** Where the finding is, in words first; the coordinates are secondary. */
function LocationText({ finding }: { finding: Finding }) {
  if (!finding.location) return <>No location. The photo had none and nobody has added one, so it is not on the map.</>
  const point = `${finding.location.latitude.toFixed(5)}, ${finding.location.longitude.toFixed(5)}`
  let text = 'Roughly where the camera was (approximate, not the exact spot of the problem)'
  if (finding.location_quality === 'reviewer_confirmed') text = 'Moved and confirmed by a reviewer'
  else if (finding.origin === 'manual' && finding.location_source === 'manual') text = 'Picked on the map when it was added (approximate)'
  return (
    <>
      {text}
      <span className="block text-xs text-asphalt-400">{point}</span>
    </>
  )
}

/** Side panel with the finding's photo, details and history (FR-29). */
function FindingDrawer({ finding, project, options, onClose }: { finding: Finding; project: ProjectDetail; options: ReviewOptions | undefined; onClose: () => void }) {
  const canReview = hasProjectPermission(project, 'finding.review') && !project.archived && finding.review_status !== 'merged'
  const canSeeHistory = hasProjectPermission(project, 'finding.history.view')
  const history = useQuery({
    queryKey: findingQueryKeys.history(finding.id),
    queryFn: ({ signal }) => findingHistory(finding.id, signal),
    enabled: canSeeHistory,
  })
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => closeRef.current?.focus(), [finding.id])

  return (
    <aside
      aria-label="Finding details"
      className="page-enter fixed inset-0 z-40 flex flex-col overflow-y-auto bg-white shadow-2xl sm:inset-y-0 sm:right-0 sm:left-auto sm:w-[26rem] sm:border-l sm:border-asphalt-100"
      onKeyDown={(event) => event.key === 'Escape' && onClose()}
    >
      <header className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-asphalt-100 bg-white px-4 py-3">
        <h2 className="truncate font-medium">{shownType(finding, options)}</h2>
        <button ref={closeRef} type="button" onClick={onClose} className="btn btn-ghost px-2" aria-label="Close details">
          <X className="size-5" aria-hidden />
        </button>
      </header>
      <div className="space-y-4 p-4 text-sm">
        <FindingPhoto finding={finding} className="rounded-lg" />
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={finding.review_status} />
          <ModelLabel as="span" testDetector={finding.is_test_detector} trialModel={finding.is_trial_model} className="text-[0.65rem]" />
        </div>
        <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2">
          {finding.origin === 'ai' && (
            <>
              <dt className="text-asphalt-500">AI suggestion</dt>
              <dd>
                {typeLabel(finding.predicted_type_key, options?.finding_types)}
                {finding.predicted_confidence !== null && (
                  <span className="text-asphalt-500">
                    {' '}
                    · AI certainty {Math.round(finding.predicted_confidence * 100)}% (how sure the AI is, not how serious the problem is)
                  </span>
                )}
              </dd>
            </>
          )}
          <dt className="text-asphalt-500">Type</dt>
          <dd>{finding.type_key ? typeLabel(finding.type_key, options?.finding_types) : 'Not chosen yet'}</dd>
          <dt className="text-asphalt-500">Severity</dt>
          <dd>
            {finding.severity_key ? severityLabel(finding.severity_key, options) : 'Not set yet'}
            {finding.severity_rubric_version && <span className="text-asphalt-500"> (scale version {finding.severity_rubric_version})</span>}
          </dd>
          <dt className="text-asphalt-500">Location</dt>
          <dd>
            <LocationText finding={finding} />
          </dd>
          {finding.notes && (
            <>
              <dt className="text-asphalt-500">Notes</dt>
              <dd className="whitespace-pre-line">{finding.notes}</dd>
            </>
          )}
          {finding.created_by_name && (
            <>
              <dt className="text-asphalt-500">Added by</dt>
              <dd>{finding.created_by_name}</dd>
            </>
          )}
          {finding.reviewed_by_name && (
            <>
              <dt className="text-asphalt-500">Last review</dt>
              <dd>
                {finding.reviewed_by_name}
                {finding.reviewed_at && `, ${new Date(finding.reviewed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`}
              </dd>
            </>
          )}
          {finding.model_version && (
            <>
              <dt className="text-asphalt-500">AI model</dt>
              <dd>{finding.model_version}</dd>
            </>
          )}
        </dl>
        <div className="flex flex-wrap gap-2">
          {canReview && (
            <Link to={`/projects/${project.id}/review/${finding.id}`} className="btn btn-primary">
              Review this finding
            </Link>
          )}
          {finding.photo && (
            <a href={originalUrl(finding.photo.id)} target="_blank" rel="noreferrer" className="btn btn-ghost">
              Open full photo
            </a>
          )}
        </div>
        {canSeeHistory && (
          <section className="space-y-2">
            <h3 className="font-medium">History</h3>
            {history.isPending && <SkeletonRows rows={2} />}
            {history.isError && <ErrorMessage title="Could not load the history" error={history.error} onRetry={() => void history.refetch()} />}
            {history.isSuccess && <FindingHistory events={history.data} options={options} />}
          </section>
        )}
      </div>
    </aside>
  )
}

/** S11: a problem seen by a person (e.g. on a sidewalk). It goes to review as "Awaiting review". */
function AddObservationDialog({
  project,
  options,
  onClose,
  onAdded,
}: {
  project: ProjectDetail
  options: ReviewOptions
  onClose: () => void
  onAdded: (finding: Finding) => void
}) {
  const queryClient = useQueryClient()
  const defaultType = options.finding_types.find((type) => type.source === 'manual')?.key ?? options.finding_types[0]?.key ?? ''
  const [typeKey, setTypeKey] = useState(defaultType)
  const [notes, setNotes] = useState('')
  const [location, setLocation] = useState<LatLon | null>(null)
  const [imageId, setImageId] = useState('')
  const [triedSubmit, setTriedSubmit] = useState(false)
  const photos = useQuery({
    queryKey: [...imageQueryKeys.all(project.id), 'choose'],
    queryFn: ({ signal }) => listImages(project.id, { pageSize: 100 }, signal),
    enabled: hasProjectPermission(project, 'image.status.view'),
  })
  const add = useMutation({
    meta: { success: 'Observation added. It is waiting for review.' },
    mutationFn: () => addManualFinding(project.id, { type_key: typeKey, notes: notes.trim(), location, image_id: imageId || null }),
    onSuccess: async (finding) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: findingQueryKeys.all(project.id) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) }),
      ])
      onAdded(finding)
    },
  })
  const noteMissing = notes.trim() === ''

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-asphalt-950/60 p-4" onKeyDown={(event) => event.key === 'Escape' && onClose()}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-title"
        className="page-enter max-h-[calc(100dvh-2rem)] w-full max-w-2xl space-y-4 overflow-y-auto rounded-2xl bg-white p-4 shadow-2xl sm:p-5"
        onSubmit={(event) => {
          event.preventDefault()
          setTriedSubmit(true)
          if (!noteMissing && typeKey) add.mutate()
        }}
      >
        <div>
          <h2 id="add-title" className="text-lg font-medium">
            Add observation
          </h2>
          <p className="text-sm text-asphalt-500">
            For a problem you saw yourself, for example on a sidewalk. A reviewer checks it before it counts as verified.
          </p>
        </div>
        <label className="block space-y-1 text-sm font-medium">
          Type
          <select className="control" value={typeKey} onChange={(event) => setTypeKey(event.target.value)}>
            {options.finding_types.map((type) => (
              <option key={type.key} value={type.key}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1 text-sm font-medium">
          What did you see? <span className="font-normal text-asphalt-500">(required)</span>
          <textarea
            className="control min-h-24"
            value={notes}
            maxLength={2000}
            onChange={(event) => setNotes(event.target.value)}
            aria-invalid={triedSubmit && noteMissing}
            aria-describedby={triedSubmit && noteMissing ? 'notes-error' : undefined}
          />
        </label>
        {triedSubmit && noteMissing && (
          <p id="notes-error" className="text-sm text-red-700">
            Describe what you saw.
          </p>
        )}
        {photos.isError && <ErrorMessage title="Could not load the project's photos" error={photos.error} onRetry={() => void photos.refetch()} />}
        {photos.isSuccess && photos.data.items.length > 0 && (
          <label className="block space-y-1 text-sm font-medium">
            Photo <span className="font-normal text-asphalt-500">(optional)</span>
            <select className="control" value={imageId} onChange={(event) => setImageId(event.target.value)}>
              <option value="">No photo</option>
              {photos.data.items.map((image) => (
                <option key={image.id} value={image.id}>
                  {image.original_filename}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="space-y-1">
          <p className="text-sm font-medium">
            Where is it? <span className="font-normal text-asphalt-500">(optional: click the map where the problem is)</span>
          </p>
          <PickLocationMap area={project.boundary} value={location} onPick={setLocation} />
          <p className="text-sm text-asphalt-500" aria-live="polite">
            {location ? (
              <>
                Point chosen.{' '}
                <span className="text-xs text-asphalt-400">
                  ({location.latitude.toFixed(6)}, {location.longitude.toFixed(6)})
                </span>
              </>
            ) : imageId ? (
              "No point chosen. The photo's location will be used, if it has one."
            ) : (
              'No point chosen. Without one, it will not appear on the map.'
            )}
            {location && (
              <button type="button" className="ml-2 link" onClick={() => setLocation(null)}>
                Clear
              </button>
            )}
          </p>
        </div>
        {add.isError && <ErrorMessage title="Could not add the observation" error={add.error} />}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={add.isPending}>
            Add observation
          </Button>
        </div>
      </form>
    </div>
  )
}
