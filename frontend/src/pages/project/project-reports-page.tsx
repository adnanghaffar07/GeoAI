import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Download, FileText } from 'lucide-react'
import { useState } from 'react'

import { findingQueryKeys, getReviewOptions, type ReviewOptions } from '@/api/findings'
import { FORMAT_LABELS, listReports, reportFileUrl, reportQueryKeys, requestReport, shareReport, type Report, type ReportFormat } from '@/api/reports'
import type { ProjectDetail } from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { severityLabel } from '@/lib/findings'
import { cn } from '@/lib/utils'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

const POLL_MS = 3000
const isBusy = (report: Report) => report.status === 'queued' || report.status === 'processing'

/** S14 Reports: CSV, GeoJSON and PDF exports (FR-45 to FR-50). */
export function ProjectReportsPage() {
  const project = useProject()
  const canGenerate = hasProjectPermission(project, 'report.generate')
  const options = useQuery({ queryKey: findingQueryKeys.options(project.id), queryFn: ({ signal }) => getReviewOptions(project.id, signal), enabled: canGenerate })
  const reports = useQuery({
    queryKey: reportQueryKeys.list(project.id),
    queryFn: ({ signal }) => listReports(project.id, signal),
    // Keep checking while a report is being built.
    refetchInterval: (query) => (query.state.data?.items.some(isBusy) ? POLL_MS : false),
  })

  return (
    <div className="space-y-6">
      {canGenerate ? (
        <PageIntro title="Reports">
          Make a file of this project's verified findings to download or share: a table for Excel, a map file, or a PDF summary.
        </PageIntro>
      ) : (
        <PageIntro title="Shared reports">Reports the project manager has shared with you. Download one to open it.</PageIntro>
      )}
      {canGenerate && options.isPending && <SkeletonRows rows={2} />}
      {canGenerate && options.isError && (
        <ErrorMessage title="Could not load the report form" error={options.error} onRetry={() => void options.refetch()} />
      )}
      {canGenerate && options.data && <GenerateForm project={project} options={options.data} />}

      <section className="space-y-3" aria-label="Reports made so far">
        {canGenerate && <h3 className="font-semibold">Reports made so far</h3>}
        {reports.isPending && <SkeletonRows rows={3} />}
        {reports.isError && <ErrorMessage title="Could not load reports" error={reports.error} onRetry={() => void reports.refetch()} />}
        {reports.isSuccess &&
          (reports.data.items.length === 0 ? (
            canGenerate ? (
              <EmptyState icon={<FileText />} title="No reports yet">
                Use the form above to make the first report.
              </EmptyState>
            ) : (
              <EmptyState icon={<FileText />} title="No reports shared with you yet">
                The project manager decides which reports to share with you.
              </EmptyState>
            )
          ) : (
            <ul className="space-y-2" aria-label="Reports">
              {reports.data.items.map((report) => (
                <ReportRow key={report.id} report={report} project={project} options={options.data} />
              ))}
            </ul>
          ))}
      </section>
    </div>
  )
}

function GenerateForm({ project, options }: { project: ProjectDetail; options: ReviewOptions }) {
  const queryClient = useQueryClient()
  const [format, setFormat] = useState<ReportFormat>('pdf')
  const [typeKey, setTypeKey] = useState('')
  const [severityKey, setSeverityKey] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [location, setLocation] = useState('')
  const [unreviewed, setUnreviewed] = useState(false)
  const canIncludeUnreviewed = hasProjectPermission(project, 'report.include_unreviewed')
  const generate = useMutation({
    meta: { success: 'Report is being made. It will appear in the list when ready.' },
    mutationFn: () =>
      requestReport(project.id, {
        format,
        filters: {
          type_key: typeKey ? [typeKey] : [],
          severity_key: severityKey ? [severityKey] : [],
          created_from: from || null,
          created_to: to || null,
          has_location: location === 'yes' ? true : location === 'no' ? false : null,
        },
        include_unreviewed: unreviewed,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reportQueryKeys.list(project.id) }),
  })
  const field = 'control h-9 py-1 text-sm'

  return (
    <form
      className="panel space-y-4 p-4"
      onSubmit={(event) => {
        event.preventDefault()
        generate.mutate()
      }}
    >
      <h3 className="font-semibold">Make a new report</h3>
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">File type</legend>
        <div className="flex flex-wrap gap-2">
          {(Object.keys(FORMAT_LABELS) as ReportFormat[]).map((value) => (
            <label
              key={value}
              className={cn(
                'cursor-pointer rounded-lg border px-3 py-1.5 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-lane-400',
                format === value ? 'border-asphalt-800 bg-asphalt-800 text-white' : 'border-asphalt-200 bg-white',
              )}
            >
              <input type="radio" name="format" value={value} checked={format === value} onChange={() => setFormat(value)} className="sr-only" />
              {FORMAT_LABELS[value]}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Type
          <select className={field} value={typeKey} onChange={(event) => setTypeKey(event.target.value)}>
            <option value="">All types</option>
            {options.finding_types.map((type) => (
              <option key={type.key} value={type.key}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Severity
          <select className={field} value={severityKey} onChange={(event) => setSeverityKey(event.target.value)}>
            <option value="">Any severity</option>
            {options.severity_rubric.levels.map((level) => (
              <option key={level.key} value={level.key}>
                {level.label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Location
          <select className={field} value={location} onChange={(event) => setLocation(event.target.value)}>
            <option value="">With or without</option>
            <option value="yes">Has a location</option>
            <option value="no">No location</option>
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Added from
          <input type="date" className={field} value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="space-y-1 text-xs font-medium text-asphalt-600">
          Added until
          <input type="date" className={field} value={to} onChange={(event) => setTo(event.target.value)} />
        </label>
      </div>
      <p className="text-sm text-asphalt-600">
        Reports include only <strong className="font-medium">verified findings</strong>. Each file also says when it was made, which filters
        and settings were used, and how exact the locations are.{' '}
        {format === 'geojson' && 'The map file leaves out findings without a location and marks positions that nobody has confirmed.'}
      </p>
      {canIncludeUnreviewed && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={unreviewed} onChange={(event) => setUnreviewed(event.target.checked)} />
          Also include unreviewed AI suggestions
        </label>
      )}
      {unreviewed && (
        <p role="alert" className="flex gap-2 rounded-lg border-2 border-amber-500 bg-amber-50 p-3 text-sm font-medium text-amber-900">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          This report will include UNREVIEWED AI suggestions. They are not confirmed problems; each one is labelled UNREVIEWED, and the report
          cannot be shared with viewers.
        </p>
      )}
      {generate.isError && <ErrorMessage title="Could not start making the report" error={generate.error} />}
      <Button type="submit" variant="accent" busy={generate.isPending}>
        <FileText className="size-4" aria-hidden />
        Make report
      </Button>
    </form>
  )
}

function filterText(report: Report, options: ReviewOptions | undefined): string {
  const f = report.filters
  const parts: string[] = []
  if (f.type_key?.length) parts.push(f.type_key.map((key) => options?.finding_types.find((t) => t.key === key)?.label ?? key).join(', '))
  if (f.severity_key?.length) parts.push(`severity ${f.severity_key.map((key) => severityLabel(key, options)).join(', ')}`)
  if (f.created_from) parts.push(`from ${f.created_from}`)
  if (f.created_to) parts.push(`until ${f.created_to}`)
  if (f.has_location === true) parts.push('with a location')
  if (f.has_location === false) parts.push('without a location')
  return parts.length ? parts.join(' · ') : 'All findings'
}

const STATUS_TEXT: Record<Report['status'], string> = {
  queued: 'Waiting to start…',
  processing: 'Being made…',
  completed: 'Ready',
  failed: 'Could not be made',
}

function ReportRow({ report, project, options }: { report: Report; project: ProjectDetail; options: ReviewOptions | undefined }) {
  const queryClient = useQueryClient()
  const canShare = hasProjectPermission(project, 'report.share') && report.status === 'completed'
  const share = useMutation({
    meta: { success: 'Sharing updated' },
    mutationFn: (shared: boolean) => shareReport(report.id, shared),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reportQueryKeys.list(project.id) }),
  })
  const placeholder = report.settings_used.severity_scale?.is_placeholder || report.settings_used.priority_settings?.is_placeholder

  return (
    <li className="panel flex flex-wrap items-start justify-between gap-3 p-4 text-sm">
      <div className="min-w-0 space-y-1">
        <p className="font-medium">
          {FORMAT_LABELS[report.format]} · <span className={report.status === 'failed' ? 'text-red-700' : 'text-asphalt-600'}>{STATUS_TEXT[report.status]}</span>
          {report.record_count !== null && ` · ${report.record_count} item${report.record_count === 1 ? '' : 's'} in the report`}
        </p>
        <p className="text-xs text-asphalt-600">
          {filterText(report, options)} · made by {report.requested_by_name ?? 'unknown person'},{' '}
          {new Date(report.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
        </p>
        <div className="flex flex-wrap gap-1">
          {report.include_unreviewed && <span className="pill border border-amber-500 bg-amber-50 text-amber-900">Includes UNREVIEWED AI suggestions</span>}
          {placeholder && <span className="pill bg-amber-100 text-amber-900">Uses sample settings (placeholder, not your city's yet)</span>}
          {report.settings_used.includes_test_detector && <span className="pill bg-amber-100 text-amber-900">Includes TEST DETECTOR results (not real detections)</span>}
          {report.settings_used.includes_trial_model && <span className="pill bg-amber-100 text-amber-900">Includes TRIAL MODEL results (accuracy not approved)</span>}
          {report.shared_with_viewers && <span className="pill bg-emerald-100 text-emerald-900">Shared with viewers</span>}
        </div>
        {report.failure_reason && <p className="text-xs text-red-700">{report.failure_reason}</p>}
        {share.isError && <ErrorMessage title="Could not change who can see this report" error={share.error} />}
      </div>
      <div className="flex flex-wrap gap-2">
        {report.status === 'completed' && (
          <a href={reportFileUrl(report.id)} className="btn btn-secondary" download={report.file_name ?? undefined}>
            <Download className="size-4" aria-hidden />
            Download
          </a>
        )}
        {canShare &&
          (report.include_unreviewed ? (
            <span className="self-center text-xs text-asphalt-500">Cannot be shared: it includes unreviewed suggestions</span>
          ) : (
            <Button variant="ghost" busy={share.isPending} onClick={() => share.mutate(!report.shared_with_viewers)}>
              {report.shared_with_viewers ? 'Stop sharing' : 'Share with viewers'}
            </Button>
          ))}
      </div>
    </li>
  )
}
