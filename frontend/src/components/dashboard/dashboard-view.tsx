import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowUpRight, Camera, CheckCircle2, ClipboardList, FolderOpen, Hourglass } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'

import { dashboardQueryKeys, getDashboard, type Dashboard, type DashboardDays } from '@/api/dashboard'
import { listProjects, projectQueryKeys, projectRoleLabel } from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { ActivityChart, BarList, ChartCard, DonutChart, Sparkline, type SeriesSpec } from '@/components/dashboard/charts'
import { DashboardMap } from '@/components/dashboard/dashboard-map'
import { NextSteps } from '@/components/dashboard/next-steps'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState } from '@/components/ui/page-intro'
import { ordinal, REVIEW_STATUS_COLORS, SERIES, SINGLE } from '@/lib/chart-colors'
import { cn } from '@/lib/utils'

const RANGES: { days: DashboardDays; label: string }[] = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
  { days: null, label: 'All time' },
]

const REVIEW_LABELS: Record<string, string> = {
  waiting: 'Waiting for review',
  needs_field_check: 'Needs field check',
  verified: 'Verified',
  rejected: 'Rejected',
}
// Review status links into the findings list (one project only).
const REVIEW_FILTER: Record<string, string> = { waiting: 'to_review', needs_field_check: 'needs_field_check', verified: 'verified', rejected: 'rejected' }
const INSPECTION_ORDER = ['none', 'planned', 'inspected', 'resolved']
const INSPECTION_LABELS: Record<string, string> = { none: 'Not planned yet', planned: 'Planned', inspected: 'Inspected', resolved: 'Resolved' }

interface DashboardViewProps {
  orgId: string
  /** Fixed to one project (the project's own Overview tab). */
  projectId?: string
  showMap?: boolean
}

/** The Overview dashboard. Shows only what this person may see (the server decides). */
export function DashboardView({ orgId, projectId: fixedProject, showMap = true }: DashboardViewProps) {
  const navigate = useNavigate()
  const [days, setDays] = useState<DashboardDays>(30)
  const [chosenProject, setChosenProject] = useState('')
  const projectId = fixedProject ?? (chosenProject || null)

  const projects = useQuery({
    queryKey: projectQueryKeys.list(orgId, false),
    queryFn: ({ signal }) => listProjects(orgId, false, signal),
    enabled: !fixedProject,
  })
  const dashboard = useQuery({
    queryKey: dashboardQueryKeys.get(orgId, projectId, days),
    queryFn: ({ signal }) => getDashboard(orgId, { projectId, days }, signal),
    placeholderData: keepPreviousData,
  })

  return (
    <div className="space-y-4">
      {dashboard.data && dashboard.data.projects.length > 0 && <NextSteps data={dashboard.data} projectId={projectId} />}
      {dashboard.data && dashboard.data.projects.length > 0 && <h2 className="pt-4 text-lg font-semibold">Numbers and charts</h2>}
      {/* One filter row above everything it changes. */}
      <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Dashboard filters">
        {!fixedProject && (
          <label className="flex min-w-0 max-w-full items-center gap-2 text-sm">
            <span className="text-asphalt-600">Project</span>
            <select className="control h-9 w-auto min-w-0 max-w-full py-1 text-sm" value={chosenProject} onChange={(event) => setChosenProject(event.target.value)}>
              <option value="">All projects</option>
              {projects.data?.items.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="inline-flex rounded-lg border border-asphalt-200 bg-white p-0.5" role="radiogroup" aria-label="Period">
          {RANGES.map((range) => (
            <button
              key={range.label}
              type="button"
              role="radio"
              aria-checked={days === range.days}
              onClick={() => setDays(range.days)}
              className={cn(
                'rounded-md px-3 py-1 text-sm transition-colors',
                days === range.days ? 'bg-asphalt-800 text-white' : 'text-asphalt-600 hover:bg-asphalt-50',
              )}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      {dashboard.isPending && <SkeletonRows rows={6} />}
      {dashboard.isError && <ErrorMessage title="Could not load the dashboard" error={dashboard.error} onRetry={() => void dashboard.refetch()} />}
      {dashboard.data && (
        // While new numbers load, the old ones stay (dimmed) instead of flashing.
        <div className={cn('space-y-4 transition-opacity', dashboard.isPlaceholderData && 'opacity-60')} aria-busy={dashboard.isFetching}>
          <DashboardBody data={dashboard.data} projectId={projectId} showMap={showMap} navigate={navigate} />
        </div>
      )}
    </div>
  )
}

function DashboardBody({
  data,
  projectId,
  showMap,
  navigate,
}: {
  data: Dashboard
  projectId: string | null
  showMap: boolean
  navigate: ReturnType<typeof useNavigate>
}) {
  const { access, totals } = data
  const typeLabel = useMemo(() => Object.fromEntries(data.finding_types.map((type) => [type.key, type.label])), [data.finding_types])
  const levels = data.severity_levels
  const severityColors = useMemo(() => {
    const colors = ordinal(levels.length)
    return Object.fromEntries(levels.map((level, index) => [level.key, colors[index]!]))
  }, [levels])
  const severityLabel = (key: string | null) => levels.find((level) => level.key === key)?.label ?? 'Not set'
  const goToFindings = (query: string) => projectId && navigate(`/projects/${projectId}/findings?${query}`)

  if (data.projects.length === 0) {
    return (
      <EmptyState icon={<FolderOpen />} title="You are not on any project yet">
        When a project manager adds you to a project, its photos, findings and to-dos appear here.
      </EmptyState>
    )
  }

  const series: SeriesSpec[] = [
    ...(access.photos ? [{ key: 'photos', name: access.photos_own_only ? 'Your photos uploaded' : 'Photos uploaded', color: SERIES.photos }] : []),
    ...(access.candidates ? [{ key: 'suggestions', name: 'AI suggestions and observations', color: SERIES.suggestions }] : []),
    ...(access.verified ? [{ key: 'verified', name: 'Findings verified', color: SERIES.verified }] : []),
  ]
  // Every status this person may see is listed, even at zero, so "0 rejected" is visible too.
  const reviewKeys = (['waiting', 'needs_field_check', 'verified', 'rejected'] as const).filter((key) =>
    key === 'verified' ? access.verified : key === 'rejected' ? access.rejected : access.candidates,
  )
  const reviewSlices = reviewKeys
    .map((key) => ({ key, name: REVIEW_LABELS[key]!, value: data.review_status[key] ?? 0, color: REVIEW_STATUS_COLORS[key]! }))
  const typeItems = Object.entries(data.verified_by_type)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ key, name: typeLabel[key] ?? key, value, color: SINGLE }))
  const severityItems = levels
    .map((level) => ({ key: level.key, name: level.label, value: data.verified_by_severity[level.key] ?? 0, color: severityColors[level.key]! }))
    .concat(data.verified_by_severity.not_set ? [{ key: 'not_set', name: 'Not set', value: data.verified_by_severity.not_set, color: '#898781' }] : [])
  const inspectionColors = ordinal(INSPECTION_ORDER.length)
  const inspectionItems = INSPECTION_ORDER.filter((key) => key in data.inspection_status || access.priority).map((key, index) => ({
    key,
    name: INSPECTION_LABELS[key]!,
    value: data.inspection_status[key] ?? 0,
    color: inspectionColors[INSPECTION_ORDER.indexOf(key)] ?? inspectionColors[index]!,
  }))
  const activityRows = data.activity.map((day) => [day.date, ...series.map((item) => day[item.key as 'photos'] as number)])
  const period = data.scope.days ? `last ${data.scope.days} days` : `since ${new Date(`${data.scope.date_from}T00:00:00`).toLocaleDateString(undefined, { dateStyle: 'medium' })}`
  const sum = (key: 'photos' | 'suggestions' | 'verified') => data.activity.reduce((total, day) => total + day[key], 0)
  const scored = data.top_priority

  return (
    <>
      {/* Number cards */}
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {access.photos && (
          <KpiCard
            icon={<Camera className="size-4" aria-hidden />}
            label={access.photos_own_only ? 'Your photos' : 'Photos uploaded'}
            value={totals.photos}
            detail={`${totals.photos_analysed} analysed · ${totals.photos_missing_location} need a location`}
            trend={{ values: data.activity.map((day) => day.photos), color: SERIES.photos, text: `+${sum('photos')} in the ${period}` }}
          />
        )}
        {access.candidates && (
          <KpiCard
            icon={<Hourglass className="size-4" aria-hidden />}
            label="Waiting for review"
            value={totals.waiting_review}
            detail={`${totals.needs_field_check} need a check on site`}
            trend={{ values: data.activity.map((day) => day.suggestions), color: SERIES.suggestions, text: `+${sum('suggestions')} new in the ${period}` }}
            onClick={projectId ? () => goToFindings('status=to_review') : undefined}
          />
        )}
        {access.verified && (
          <KpiCard
            icon={<CheckCircle2 className="size-4" aria-hidden />}
            label="Verified findings"
            value={totals.verified}
            detail={`${totals.verified_location_unconfirmed} with an approximate location`}
            trend={{ values: data.activity.map((day) => day.verified), color: SERIES.verified, text: `+${sum('verified')} verified in the ${period}` }}
            onClick={projectId ? () => goToFindings('status=verified') : undefined}
          />
        )}
        {(access.priority || access.own_inspections) && (
          <KpiCard
            icon={<ClipboardList className="size-4" aria-hidden />}
            label={access.priority ? 'Open inspections' : 'Your open inspections'}
            value={totals.inspections_open}
            detail={`${totals.inspections_resolved} resolved so far`}
            progress={totals.inspections_open + totals.inspections_resolved > 0 ? totals.inspections_resolved / (totals.inspections_open + totals.inspections_resolved) : undefined}
            onClick={projectId ? () => navigate(`/projects/${projectId}/priority`) : undefined}
          />
        )}
      </dl>

      <div className="grid gap-4 lg:grid-cols-3">
        {series.length > 0 && (
          <ChartCard
            title="Activity"
            subtitle={`Per day, ${period}`}
            className={reviewSlices.length > 1 ? 'lg:col-span-2' : 'lg:col-span-3'}
            table={{ columns: ['Date', ...series.map((item) => item.name)], rows: activityRows.filter((row) => row.slice(1).some((value) => Number(value) > 0)) }}
          >
            <ActivityChart data={data.activity} series={series} />
          </ChartCard>
        )}
        {/* A ring with one status says nothing, so it shows only when there is a split. */}
        {reviewSlices.length > 1 && (
          <ChartCard title="Review progress" subtitle={projectId ? 'Click a status to see the findings' : 'All findings you can see'} table={{ columns: ['Status', 'Findings'], rows: reviewSlices.map((slice) => [slice.name, slice.value]) }}>
            <DonutChart slices={reviewSlices} centerLabel="findings" onSelect={projectId ? (key) => goToFindings(`status=${REVIEW_FILTER[key]}`) : undefined} />
          </ChartCard>
        )}
      </div>

      {access.verified && (
        <div className="grid gap-4 lg:grid-cols-3">
          <ChartCard title="Verified findings by type" table={{ columns: ['Type', 'Findings'], rows: typeItems.map((item) => [item.name, item.value]) }}>
            {typeItems.length ? <BarList items={typeItems} onSelect={projectId ? (key) => goToFindings(`status=verified&type=${key}`) : undefined} /> : <Empty>No verified findings yet.</Empty>}
          </ChartCard>
          <ChartCard title="Verified findings by severity" subtitle="How serious each problem is. Set by a reviewer, never by the AI." table={{ columns: ['Severity', 'Findings'], rows: severityItems.map((item) => [item.name, item.value]) }}>
            {totals.verified ? <BarList items={severityItems} onSelect={projectId ? (key) => key !== 'not_set' && goToFindings(`status=verified&severity=${key}`) : undefined} /> : <Empty>No verified findings yet.</Empty>}
          </ChartCard>
          {inspectionItems.length > 0 && (
            <ChartCard
              title={access.priority ? 'Inspections of verified findings' : 'Your inspections'}
              table={{ columns: ['Inspection', 'Findings'], rows: inspectionItems.map((item) => [item.name, item.value]) }}
            >
              {inspectionItems.some((item) => item.value > 0) ? (
                <BarList items={inspectionItems} onSelect={projectId && access.priority ? (key) => navigate(`/projects/${projectId}/priority?inspection=${key}`) : undefined} />
              ) : (
                <Empty>No inspections yet.</Empty>
              )}
            </ChartCard>
          )}
        </div>
      )}

      {(access.priority || (showMap && access.verified)) && (
        <div className={cn('grid gap-4', access.priority && showMap && access.verified && 'lg:grid-cols-2')}>
          {access.priority && (
            <section className="panel min-w-0 p-4" aria-label="Inspect first">
              <h3 className="font-medium">Inspect first</h3>
              <p className="mb-3 text-xs text-asphalt-500">The verified findings to look at first (score out of 100). It only orders inspections; it does not decide repairs.</p>
              {scored.length === 0 ? (
                <Empty>No verified findings to inspect.</Empty>
              ) : (
                <ol className="space-y-2">
                  {scored.map((item, index) => (
                    <li key={item.finding_id}>
                      <Link to={`/projects/${item.project_id}/priority`} className="group flex items-center gap-3 rounded-lg p-2 hover:bg-asphalt-50">
                        <span className="w-5 text-sm text-asphalt-500 tabular-nums">{index + 1}</span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {typeLabel[item.type_key ?? ''] ?? 'Finding'} · {severityLabel(item.severity_key)}
                          </span>
                          <span className="block truncate text-xs text-asphalt-500">
                            {item.project_name}
                            {item.inspection_status !== 'none' && ` · ${INSPECTION_LABELS[item.inspection_status] ?? item.inspection_status}`}
                          </span>
                        </span>
                        <span className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-asphalt-100 sm:block" aria-hidden>
                          <span className="block h-full rounded-full" style={{ width: `${item.score}%`, background: SINGLE }} />
                        </span>
                        <span className="w-8 text-right text-sm font-semibold tabular-nums">{Math.round(item.score)}</span>
                        <ArrowUpRight className="size-4 text-asphalt-400 group-hover:text-asphalt-700" aria-hidden />
                      </Link>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}
          {showMap && access.verified && (
            <section className="panel min-w-0 p-4" aria-label="Where the verified findings are">
              <h3 className="font-medium">Where the verified findings are</h3>
              <ul className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-asphalt-600" aria-label="Severity colours">
                {levels.map((level) => (
                  <li key={level.key} className="flex items-center gap-1">
                    <span className="size-2.5 rounded-full" style={{ background: severityColors[level.key] }} aria-hidden />
                    {level.label}
                  </li>
                ))}
                <li className="text-asphalt-500">· positions are approximate unless a reviewer confirmed them</li>
              </ul>
              {data.map_points.length ? (
                <DashboardMap
                  points={data.map_points}
                  severityColors={severityColors}
                  onSelect={(point) => navigate(`/projects/${point.project_id}/findings?status=verified&selected=${point.finding_id}`)}
                />
              ) : (
                <Empty>No verified findings with a location yet.</Empty>
              )}
              {data.map_truncated && <p className="mt-1 text-xs text-asphalt-500">Showing the {data.map_points.length} most recently verified.</p>}
            </section>
          )}
        </div>
      )}

      {!projectId && data.projects.length > 0 && <ProjectsTable data={data} />}

      <p className="flex items-center gap-1.5 text-xs text-asphalt-500">
        <AlertTriangle className="size-3.5" aria-hidden />
        The numbers are totals as of now; the activity chart shows the {period}. You only see what your role allows.
      </p>
    </>
  )
}

function KpiCard({
  icon,
  label,
  value,
  detail,
  trend,
  progress,
  onClick,
}: {
  icon: ReactNode
  label: string
  value: number
  detail: string
  trend?: { values: number[]; color: string; text: string }
  progress?: number
  onClick?: () => void
}) {
  const body = (
    <>
      <dt className="flex items-center gap-1.5 text-sm text-asphalt-600">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 text-3xl font-semibold tracking-tight">{value}</dd>
      <dd className="text-xs text-asphalt-500">{detail}</dd>
      {trend && (
        <dd className="mt-2">
          <Sparkline values={trend.values} color={trend.color} />
          <span className="text-xs text-asphalt-500">{trend.text}</span>
        </dd>
      )}
      {progress !== undefined && (
        <dd className="mt-3">
          <span className="block h-2 overflow-hidden rounded-full bg-asphalt-100" aria-hidden>
            <span className="block h-full rounded-full" style={{ width: `${Math.round(progress * 100)}%`, background: REVIEW_STATUS_COLORS.verified }} />
          </span>
          <span className="text-xs text-asphalt-500">{Math.round(progress * 100)}% resolved</span>
        </dd>
      )}
    </>
  )
  return onClick ? (
    <div className="panel p-4 transition-shadow hover:shadow-md">
      <button type="button" onClick={onClick} className="w-full text-left" aria-label={`${label}: ${value}. Open the list`}>
        {body}
      </button>
    </div>
  ) : (
    <div className="panel p-4">{body}</div>
  )
}

function ProjectsTable({ data }: { data: Dashboard }) {
  const { access } = data
  return (
    <section className="panel overflow-x-auto" aria-label="Projects">
      <h3 className="px-4 pt-4 font-medium">Projects</h3>
      <table className="responsive-table mt-2 w-full text-left text-sm">
        <thead className="border-y border-asphalt-100 bg-asphalt-50 text-asphalt-500">
          <tr>
            <th scope="col" className="px-4 py-2 font-medium">Project</th>
            {access.photos && <th scope="col" className="px-4 py-2 font-medium">Photos</th>}
            {access.candidates && <th scope="col" className="px-4 py-2 font-medium">Waiting</th>}
            <th scope="col" className="px-4 py-2 font-medium">Verified</th>
            {access.candidates && <th scope="col" className="px-4 py-2 font-medium">Reviewed</th>}
            {access.priority && <th scope="col" className="px-4 py-2 font-medium">Open inspections</th>}
          </tr>
        </thead>
        <tbody>
          {data.projects.map((project) => {
            const total = project.waiting_review + project.verified + project.rejected
            const reviewed = total ? (project.verified + project.rejected) / total : 0
            return (
              <tr key={project.id} className="border-b border-asphalt-100 last:border-0">
                <td className="px-4 py-2">
                  <Link to={`/projects/${project.id}`} className="font-medium link">
                    {project.name}
                  </Link>
                  <span className="block text-xs text-asphalt-500">{project.my_roles.map(projectRoleLabel).join(', ') || 'Organization administrator'}</span>
                </td>
                {access.photos && <td data-label="Photos" className="px-4 py-2 tabular-nums">{project.photos}</td>}
                {access.candidates && <td data-label="Waiting" className="px-4 py-2 tabular-nums">{project.waiting_review}</td>}
                <td data-label="Verified" className="px-4 py-2 tabular-nums">{project.verified}</td>
                {access.candidates && (
                  <td data-label="Reviewed" className="px-4 py-2">
                    <span className="flex items-center gap-2">
                      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-asphalt-100" aria-hidden>
                        <span className="block h-full rounded-full" style={{ width: `${Math.round(reviewed * 100)}%`, background: REVIEW_STATUS_COLORS.verified }} />
                      </span>
                      <span className="text-xs tabular-nums text-asphalt-600">{total ? `${Math.round(reviewed * 100)}%` : '—'}</span>
                    </span>
                  </td>
                )}
                {access.priority && <td data-label="Open inspections" className="px-4 py-2 tabular-nums">{project.inspections_open}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="flex min-h-24 items-center justify-center rounded-lg bg-asphalt-50 p-4 text-center text-sm text-asphalt-500">{children}</p>
}
