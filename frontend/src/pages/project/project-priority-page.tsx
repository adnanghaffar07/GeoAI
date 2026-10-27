import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, ClipboardCheck, ListChecks, Settings2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { findingQueryKeys, getReviewOptions, typeLabel, type ReviewOptions } from '@/api/findings'
import {
  INSPECTION_LABELS,
  listInspections,
  listPriorityConfigs,
  getPriorityList,
  priorityQueryKeys,
  PRIORITY_INPUTS,
  savePriorityConfig,
  type PriorityConfig,
  type PriorityItem,
} from '@/api/priority'
import { projectQueryKeys, type ProjectDetail } from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { InspectionDialog, PlanInspectionDialog } from '@/components/inspections/inspection-dialogs'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { LocationLine } from '@/components/findings/location-line'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { severityLabel } from '@/lib/findings'
import { cn } from '@/lib/utils'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

const PAGE_SIZE = 50
const INPUT_NAMES: Record<string, string> = {
  severity: 'Reviewed severity',
  road_category: 'Road category',
  facility_proximity: 'Near selected facilities',
}

/** S12 Priority and inspection (FR-39 to FR-44). */
export function ProjectPriorityPage() {
  const project = useProject()
  if (!hasProjectPermission(project, 'priority.view')) return <MyInspections project={project} />
  return <PriorityRanking project={project} />
}

function PriorityRanking({ project }: { project: ProjectDetail }) {
  const [params, setParams] = useSearchParams()
  const inspectionStatus = params.get('inspection') ?? ''
  const page = Math.max(1, Number(params.get('page')) || 1)
  const [planning, setPlanning] = useState<PriorityItem | null>(null)
  const [open, setOpen] = useState<PriorityItem | null>(null)
  const options = useQuery({ queryKey: findingQueryKeys.options(project.id), queryFn: ({ signal }) => getReviewOptions(project.id, signal) })
  const list = useQuery({
    queryKey: priorityQueryKeys.list(project.id, inspectionStatus, page),
    queryFn: ({ signal }) => getPriorityList(project.id, { inspectionStatus, page, pageSize: PAGE_SIZE }, signal),
  })
  const canPlan = hasProjectPermission(project, 'inspection.plan') && !project.archived
  const lastPage = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1
  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }

  return (
    <div className="space-y-4">
      <PageIntro title="Inspection priority">
        Verified findings in order of what to go and look at first. The score (out of 100) only sets that order; it does not decide repairs, costs
        or compliance. AI suggestions that nobody has checked yet are never on this list.
      </PageIntro>
      {list.data?.config.is_placeholder && (
        <p className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          These scores use sample settings for now; they will be replaced by your city's own rules. Open "How this score was calculated" on any
          finding to see exactly where its score comes from.
        </p>
      )}

      {hasProjectPermission(project, 'priority.configure') && options.data && list.data && (
        <PrioritySettings project={project} options={options.data} current={list.data.config} />
      )}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Show
          <select className="control h-9 py-1 text-sm" value={inspectionStatus} onChange={(event) => update({ inspection: event.target.value || null, page: null })}>
            <option value="">All inspections</option>
            <option value="none">Not planned yet</option>
            <option value="planned">Planned</option>
            <option value="inspected">Inspected</option>
            <option value="resolved">Resolved</option>
          </select>
        </label>
        {list.isSuccess && (
          <p className="text-sm text-asphalt-500">
            {list.data.total} verified finding{list.data.total === 1 ? '' : 's'}
          </p>
        )}
      </div>

      {list.isPending && <SkeletonRows rows={4} />}
      {list.isError && <ErrorMessage title="Could not load the priority list" error={list.error} onRetry={() => void list.refetch()} />}
      {list.isSuccess &&
        (list.data.items.length === 0 ? (
          <EmptyState icon={<ListChecks />} title={inspectionStatus ? 'Nothing matches this choice' : 'Nothing to inspect yet'}>
            {inspectionStatus
              ? 'Choose "All inspections" to see the whole list.'
              : 'Findings appear here once a reviewer has checked and verified them.'}
          </EmptyState>
        ) : (
          <ol className="space-y-3" aria-label="Inspection priority">
            {list.data.items.map((item, index) => (
              <PriorityRow
                key={item.finding.id}
                rank={(page - 1) * PAGE_SIZE + index + 1}
                item={item}
                options={options.data}
                project={project}
                onPlan={canPlan && item.finding.inspection_status === 'none' ? () => setPlanning(item) : undefined}
                onOpen={item.inspection ? () => setOpen(item) : undefined}
              />
            ))}
          </ol>
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

      {planning && <PlanInspectionDialog project={project} finding={planning.finding} onClose={() => setPlanning(null)} />}
      {open && <InspectionDialog project={project} finding={open.finding} onClose={() => setOpen(null)} />}
    </div>
  )
}

function PriorityRow({
  rank,
  item,
  options,
  project,
  onPlan,
  onOpen,
}: {
  rank: number
  item: PriorityItem
  options: ReviewOptions | undefined
  project: ProjectDetail
  onPlan?: () => void
  onOpen?: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const { finding, breakdown, inspection } = item
  const missingCount = breakdown.missing.length
  return (
    <li className="panel p-4">
      <div className="flex flex-wrap items-start gap-4">
        <div className="w-16 shrink-0 text-center">
          <p className="text-xs text-asphalt-500">#{rank}</p>
          <p className="text-2xl font-semibold tabular-nums" aria-label={`Inspection priority ${item.score}`}>
            {Math.round(item.score)}
          </p>
          <p className="text-[0.65rem] text-asphalt-500">of 100</p>
        </div>
        <div className="min-w-0 flex-1 space-y-1 text-sm">
          <p className="font-medium">
            {typeLabel(finding.type_key, options?.finding_types)} · {severityLabel(finding.severity_key, options)} severity
          </p>
          <LocationLine location={finding.location} confirmed={finding.location_quality === 'reviewer_confirmed'} />
          <p className="text-xs">
            <span className={cn('pill', inspection && inspection.status !== 'reopened' ? 'bg-sky-100 text-sky-900' : 'bg-asphalt-100 text-asphalt-700')}>
              {INSPECTION_LABELS[finding.inspection_status] ?? finding.inspection_status}
            </span>
            {inspection && finding.inspection_status !== 'none' && (
              <span className="ml-2 text-asphalt-600">
                {inspection.owner_name} · {new Date(`${inspection.planned_date}T00:00:00`).toLocaleDateString(undefined, { dateStyle: 'medium' })}
              </span>
            )}
          </p>
          {missingCount > 0 && (
            <p className="text-xs text-amber-800">
              Part of the score is unknown: {breakdown.inputs.filter((input) => input.missing).map((input) => input.label.toLowerCase()).join(', ')}{' '}
              {missingCount === 1 ? 'is' : 'are'} not known yet, so {missingCount === 1 ? 'it adds' : 'they add'} nothing. Nothing is guessed.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {onPlan && (
            <Button variant="secondary" onClick={onPlan}>
              Plan inspection
            </Button>
          )}
          {onOpen && (
            <Button variant="ghost" onClick={onOpen}>
              <ClipboardCheck className="size-4" aria-hidden />
              View inspection
            </Button>
          )}
          <Link to={`/projects/${project.id}/findings?selected=${finding.id}`} className="btn btn-ghost">
            View finding
          </Link>
        </div>
      </div>
      <button type="button" className="mt-2 inline-flex items-center gap-1 text-sm link" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        <ChevronDown className={cn('size-4 transition-transform', expanded && 'rotate-180')} aria-hidden />
        How this score was calculated
      </button>
      {expanded && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-asphalt-500">
              <tr>
                <th className="py-1 pr-3 font-medium">What counts</th>
                <th className="py-1 pr-3 font-medium">For this finding</th>
                <th className="py-1 pr-3 font-medium">Points</th>
                <th className="py-1 pr-3 font-medium">Share of score</th>
                <th className="py-1 font-medium">Adds</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.inputs.map((input) => (
                <tr key={input.key} className="border-t border-asphalt-100 align-top">
                  <td className="py-1.5 pr-3">{input.label}</td>
                  {input.missing ? (
                    <td colSpan={4} className="py-1.5 text-amber-800">
                      Not known: {input.reason} <span className="text-asphalt-500">({Math.round(input.weight * 100)}% share, adds nothing)</span>
                    </td>
                  ) : (
                    <>
                      <td className="py-1.5 pr-3">{input.key === 'severity' ? severityLabel(input.value, options) : input.value}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{input.points}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{Math.round(input.weight * 100)}%</td>
                      <td className="py-1.5 tabular-nums">{input.contribution}</td>
                    </>
                  )}
                </tr>
              ))}
              <tr className="border-t border-asphalt-200 font-medium">
                <td className="py-1.5" colSpan={4}>
                  Priority score
                </td>
                <td className="py-1.5 tabular-nums">{item.score}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </li>
  )
}

/** S15 priority settings: shown as versions; saving creates a new version (recorded). */
function PrioritySettings({ project, options, current }: { project: ProjectDetail; options: ReviewOptions; current: PriorityConfig }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const configs = useQuery({
    queryKey: priorityQueryKeys.configs(project.id),
    queryFn: ({ signal }) => listPriorityConfigs(project.id, signal),
    enabled: open,
  })

  return (
    <section className="panel">
      <button type="button" className="flex w-full items-center justify-between gap-2 p-4 text-left" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span className="inline-flex items-center gap-2 font-medium">
          <Settings2 className="size-4" aria-hidden />
          Priority settings
          {current.is_placeholder && <span className="pill bg-amber-100 text-amber-900">Sample settings</span>}
        </span>
        <ChevronDown className={cn('size-4 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div className="space-y-4 border-t border-asphalt-100 p-4 text-sm">
          {editing ? (
            <SettingsForm
              project={project}
              options={options}
              current={current}
              onCancel={() => setEditing(false)}
              onSaved={async () => {
                setEditing(false)
                await queryClient.invalidateQueries({ queryKey: priorityQueryKeys.all(project.id) })
                await queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) })
              }}
            />
          ) : (
            <>
              <SettingsSummary config={current} options={options} />
              {!project.archived && (
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Change settings
                </Button>
              )}
            </>
          )}
          {configs.isSuccess && configs.data.items.length > 1 && (
            <div>
              <h3 className="font-medium">Earlier settings (kept for the record)</h3>
              <ul className="mt-1 space-y-1 text-xs text-asphalt-600">
                {configs.data.items
                  .filter((config) => !config.is_current)
                  .map((config) => (
                    <li key={config.id}>
                      Version {config.version}
                      {config.is_placeholder && ' (sample)'} · {config.created_by_name ?? 'set up automatically'} ·{' '}
                      {new Date(config.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })} · shares{' '}
                      {PRIORITY_INPUTS.map((key) => `${INPUT_NAMES[key]} ${Math.round(config.weights[key] * 100)}%`).join(', ')}
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function SettingsSummary({ config, options }: { config: PriorityConfig; options: ReviewOptions }) {
  return (
    <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[12rem_1fr]">
      <dt className="text-asphalt-500">Share of the score</dt>
      <dd>{PRIORITY_INPUTS.map((key) => `${INPUT_NAMES[key]} ${Math.round(config.weights[key] * 100)}%`).join(' · ')}</dd>
      <dt className="text-asphalt-500">Severity points</dt>
      <dd>
        {/* In scale order (low to high), not the order the server stored them. */}
        {options.severity_rubric.levels
          .filter((level) => level.key in config.severity_points)
          .map((level) => `${level.label} ${config.severity_points[level.key]}`)
          .join(' · ') || 'none'}
      </dd>
      <dt className="text-asphalt-500">Road category points</dt>
      <dd>
        {Object.entries(config.road_category_points)
          .map(([key, points]) => `${key} ${points}`)
          .join(' · ') || 'none'}
      </dd>
      <dt className="text-asphalt-500">Facilities</dt>
      <dd>
        {config.facility_types.join(', ') || 'none'} within {config.facility_radius_m} m{' '}
        <span className="text-amber-800">(no map of facilities has been loaded yet, so this part is always unknown)</span>
      </dd>
    </dl>
  )
}

function SettingsForm({
  project,
  options,
  current,
  onCancel,
  onSaved,
}: {
  project: ProjectDetail
  options: ReviewOptions
  current: PriorityConfig
  onCancel: () => void
  onSaved: () => Promise<void>
}) {
  const levels = options.severity_rubric.levels
  const [weights, setWeights] = useState(() => Object.fromEntries(PRIORITY_INPUTS.map((key) => [key, String(Math.round(current.weights[key] * 100))])))
  const [severity, setSeverity] = useState(() => Object.fromEntries(levels.map((level) => [level.key, String(current.severity_points[level.key] ?? '')])))
  const [roads, setRoads] = useState(() => Object.entries(current.road_category_points).map(([name, points]) => ({ name, points: String(points) })))
  const [facilityTypes, setFacilityTypes] = useState(current.facility_types.join(', '))
  const [radius, setRadius] = useState(String(current.facility_radius_m))
  const [confirmed, setConfirmed] = useState(!current.is_placeholder)
  const [problem, setProblem] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  const total = PRIORITY_INPUTS.reduce((sum, key) => sum + (Number(weights[key]) || 0), 0)
  const save = useMutation({
    mutationFn: () =>
      savePriorityConfig(project.id, {
        weights: Object.fromEntries(PRIORITY_INPUTS.map((key) => [key, (Number(weights[key]) || 0) / 100])) as PriorityConfig['weights'],
        severity_points: Object.fromEntries(Object.entries(severity).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])),
        road_category_points: Object.fromEntries(roads.filter((road) => road.name.trim()).map((road) => [road.name.trim(), Number(road.points) || 0])),
        facility_types: facilityTypes.split(',').map((item) => item.trim()).filter(Boolean),
        facility_radius_m: Number(radius) || 0,
        is_placeholder: !confirmed,
      }),
    onSuccess: onSaved,
    meta: { success: 'Priority settings saved. Scores have been recalculated.' },
  })

  const check = () => {
    if (total !== 100) return `The shares must add up to 100% (now ${total}%).`
    const points = [...Object.values(severity), ...roads.map((road) => road.points)].filter((value) => value !== '').map(Number)
    if (points.some((value) => Number.isNaN(value) || value < 0 || value > 100)) return 'Points must be between 0 and 100.'
    if (!(Number(radius) >= 1 && Number(radius) <= 5000)) return 'The distance must be between 1 and 5000 metres.'
    return null
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        const found = check()
        setProblem(found)
        if (!found) setConfirming(true)
      }}
    >
      <fieldset className="space-y-2">
        <legend className="font-medium">Share of the score for each part (must add up to 100%)</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          {PRIORITY_INPUTS.map((key) => (
            <label key={key} className="space-y-1 text-xs font-medium text-asphalt-600">
              {INPUT_NAMES[key]} (%)
              <input type="number" step="any" min={0} max={100} className="control" value={weights[key]} onChange={(event) => setWeights({ ...weights, [key]: event.target.value })} />
            </label>
          ))}
        </div>
        <p className={cn('text-xs', total === 100 ? 'text-asphalt-500' : 'text-red-700')}>Total: {total}%</p>
      </fieldset>
      <fieldset className="space-y-2">
        <legend className="font-medium">Points for each severity level (0–100)</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          {levels.map((level) => (
            <label key={level.key} className="space-y-1 text-xs font-medium text-asphalt-600">
              {level.label}
              <input type="number" step="any" min={0} max={100} className="control" value={severity[level.key]} onChange={(event) => setSeverity({ ...severity, [level.key]: event.target.value })} />
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="space-y-2">
        <legend className="font-medium">Points for each road category (0–100)</legend>
        <p className="text-xs text-asphalt-500">
          The project's road category is "{project.road_category || 'not set'}". Change it on the Settings tab.
        </p>
        {roads.map((road, index) => (
          <div key={index} className="flex gap-2">
            <input
              aria-label={`Road category ${index + 1} name`}
              className="control"
              value={road.name}
              onChange={(event) => setRoads(roads.map((item, i) => (i === index ? { ...item, name: event.target.value } : item)))}
            />
            <input
              aria-label={`Road category ${index + 1} points`}
              type="number"
              step="any"
              min={0}
              max={100}
              className="control w-28"
              value={road.points}
              onChange={(event) => setRoads(roads.map((item, i) => (i === index ? { ...item, points: event.target.value } : item)))}
            />
            <Button variant="ghost" onClick={() => setRoads(roads.filter((_, i) => i !== index))}>
              Remove
            </Button>
          </div>
        ))}
        <Button variant="ghost" onClick={() => setRoads([...roads, { name: '', points: '' }])}>
          Add road category
        </Button>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Facility types (comma separated)
          <input className="control" value={facilityTypes} onChange={(event) => setFacilityTypes(event.target.value)} />
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Within (metres)
          <input type="number" min={1} max={5000} className="control" value={radius} onChange={(event) => setRadius(event.target.value)} />
        </label>
      </div>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
        These are our city's confirmed values (removes the "Sample settings" label)
      </label>
      {problem && (
        <p role="alert" className="text-sm text-red-700">
          {problem}
        </p>
      )}
      {save.isError && <ErrorMessage title="Could not save the settings" error={save.error} />}
      {confirming ? (
        <div role="alertdialog" aria-label="Confirm new settings" className="space-y-2 rounded-lg border border-asphalt-200 bg-asphalt-50 p-3">
          <p>All scores will be recalculated with the new settings. The current settings are kept for the record, and the change is saved in the history.</p>
          <div className="flex gap-2">
            <Button busy={save.isPending} onClick={() => save.mutate()}>
              Yes, save the new settings
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Back
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button type="submit">Save settings</Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      )}
    </form>
  )
}

/** For people who cannot see the ranking (e.g. field collectors): inspections assigned to them. */
function MyInspections({ project }: { project: ProjectDetail }) {
  const [open, setOpen] = useState<string | null>(null)
  const list = useQuery({ queryKey: priorityQueryKeys.inspections(project.id, true), queryFn: ({ signal }) => listInspections(project.id, true, signal) })
  const selected = list.data?.items.find((item) => item.inspection.id === open)
  return (
    <div className="space-y-4">
      <PageIntro title="My inspections">
        Findings you have been asked to go and check on site. Open one to record what you found.
      </PageIntro>
      {list.isPending && <SkeletonRows rows={3} />}
      {list.isError && <ErrorMessage title="Could not load your inspections" error={list.error} onRetry={() => void list.refetch()} />}
      {list.isSuccess &&
        (list.data.items.length === 0 ? (
          <EmptyState icon={<ListChecks />} title="No inspections for you right now">
            When a project manager asks you to check a finding on site, it appears here.
          </EmptyState>
        ) : (
          <ul className="space-y-2">
            {list.data.items.map(({ inspection, finding }) => (
              <li key={inspection.id} className="panel flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
                <div>
                  <p className="font-medium">{typeLabel(finding.type_key)}</p>
                  <p className="text-xs text-asphalt-600">
                    {INSPECTION_LABELS[inspection.status]} · planned for{' '}
                    {new Date(`${inspection.planned_date}T00:00:00`).toLocaleDateString(undefined, { dateStyle: 'medium' })}
                  </p>
                  <LocationLine location={finding.location} confirmed={finding.location_quality === 'reviewer_confirmed'} />
                </div>
                <Button variant="secondary" onClick={() => setOpen(inspection.id)}>
                  Record result
                </Button>
              </li>
            ))}
          </ul>
        ))}
      {selected && <InspectionDialog project={project} finding={selected.finding} onClose={() => setOpen(null)} />}
    </div>
  )
}
