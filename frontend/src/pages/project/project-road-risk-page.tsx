import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, Gauge, Hourglass, ListChecks, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import type { ProjectDetail } from '@/api/projects'
import {
  formatDay,
  getForecastSettings,
  getRiskList,
  getRiskMap,
  alertQueryKeys,
  askAssistant,
  ASSISTANT_EXAMPLES,
  getWeather,
  listProjectAlerts,
  reasonText,
  riskExportUrl,
  roadName,
  roadRiskQueryKeys,
  roadTypeLabel,
  type ForecastStatusInfo,
  type RiskList,
  type SectionRisk,
} from '@/api/road-risk'
import { ErrorMessage } from '@/components/error-message'
import { PlanInspectionDialog } from '@/components/inspections/inspection-dialogs'
import { RoadRiskLegend, RoadRiskMap } from '@/components/map/road-risk-map'
import { LevelBadge, LevelMeaning, TrialNotice, WeatherStrip } from '@/components/road-risk/road-risk-parts'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'
import { SetupProgress, useReadyRefresh } from '@/pages/project/project-road-risk-settings-page'
import { AlertRow } from '@/pages/notifications-page'

const PAGE_SIZE = 25

/** F4d "Road risk" tab: map, "Inspect first" list, weather and download (forecasting-f4d-design.md §3.1). */
export function ProjectRoadRiskPage() {
  const project = useProject()
  const settings = useQuery({
    queryKey: roadRiskQueryKeys.settings(project.id),
    queryFn: ({ signal }) => getForecastSettings(project.id, signal),
    refetchInterval: (query) => (query.state.data?.status === 'setting_up' ? 10_000 : false),
  })
  useReadyRefresh(project.id, settings.data?.status)

  if (settings.isPending) return <SkeletonRows rows={4} />
  if (settings.isError) return <ErrorMessage title="Could not load road risk" error={settings.error} onRetry={() => void settings.refetch()} />
  if (settings.data.status !== 'ready' || !settings.data.enabled) return <NotReady project={project} status={settings.data} />
  return <RoadRisk project={project} status={settings.data} />
}

function NotReady({ project, status }: { project: ProjectDetail; status: ForecastStatusInfo }) {
  const settingsLink = status.can_configure && (
    <Link to={`/projects/${project.id}/settings/road-risk`} className="btn btn-secondary">
      Road risk settings
    </Link>
  )
  const text: Record<string, { title: string; body: string }> = {
    off: { title: 'Road risk is switched off for this project', body: 'A project manager can switch it on in Settings → Road risk.' },
    setting_up: {
      title: 'Setting up road risk for this area…',
      body: 'Roads, weather and map layers are being prepared. This can take up to an hour for a new area; this page fills in by itself.',
    },
    failed: { title: 'Road risk could not be set up', body: status.message ?? 'The set-up stopped. A project manager can try again in Settings.' },
    too_large: { title: 'This project area is too large for road risk', body: status.message ?? `Road risk works for areas up to ${status.max_area_km2} km².` },
  }
  const shown = text[status.enabled ? status.status : 'off'] ?? text.off!
  return (
    <div className="space-y-4">
      <PageIntro title="Road risk" />
      <EmptyState icon={status.status === 'setting_up' ? <Hourglass /> : <Gauge />} title={shown.title} action={settingsLink}>
        {shown.body}
      </EmptyState>
      {status.enabled && status.status === 'setting_up' && (
        <div className="panel space-y-2 p-4 text-sm">
          {status.message && <p>{status.message}</p>}
          <SetupProgress message={status.message} />
        </div>
      )}
    </div>
  )
}

function RoadRisk({ project, status }: { project: ProjectDetail; status: ForecastStatusInfo }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const level = params.get('level') ?? ''
  const page = Math.max(1, Number(params.get('page')) || 1)
  const [planning, setPlanning] = useState<SectionRisk | null>(null)
  const list = useQuery({
    queryKey: roadRiskQueryKeys.list(project.id, level, page),
    queryFn: ({ signal }) => getRiskList(project.id, { level, page, pageSize: PAGE_SIZE }, signal),
  })
  const mapData = useQuery({ queryKey: roadRiskQueryKeys.map(project.id), queryFn: ({ signal }) => getRiskMap(project.id, signal) })
  const weather = useQuery({ queryKey: roadRiskQueryKeys.weather(project.id), queryFn: ({ signal }) => getWeather(project.id, signal) })
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
    <div className="space-y-5">
      <PageIntro
        title="Road risk"
        actions={
          <>
            <a href={riskExportUrl(project.id, 'csv')} className="btn btn-secondary" download>
              <Download className="size-4" aria-hidden />
              Download CSV
            </a>
            <a href={riskExportUrl(project.id, 'geojson')} className="btn btn-secondary" download>
              <Download className="size-4" aria-hidden />
              Download GeoJSON
            </a>
          </>
        }
      >
        Which roads are most likely to get new potholes soon, so you can inspect them first. Open a road to see why.
      </PageIntro>

      <TrialNotice label={status.label} notice={status.notice}>
        <LevelMeaning level={status.level} />
        {list.data && <UpdatedLine list={list.data} />}
      </TrialNotice>

      {hasProjectPermission(project, 'alert.view') && <ProjectAlerts projectId={project.id} />}

      {status.assistant_enabled && <AskBox projectId={project.id} />}

      {list.data && <Counts list={list.data} />}

      {weather.isSuccess && <WeatherStrip weather={weather.data} />}
      {weather.isError && <ErrorMessage title="Could not load the weather" error={weather.error} onRetry={() => void weather.refetch()} />}

      <div className="space-y-2">
        <RoadRiskMap
          area={project.boundary}
          features={mapData.data?.features ?? []}
          onSelect={(sectionId) => void navigate(`/projects/${project.id}/road-risk/${sectionId}`)}
          className="h-96"
        />
        <RoadRiskLegend manyRoads={(mapData.data?.features.length ?? 0) > 300} />
        {mapData.isError && <ErrorMessage title="Could not load the map of roads" error={mapData.error} onRetry={() => void mapData.refetch()} />}
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h3 className="text-lg font-semibold">Inspect first</h3>
          <label className="space-y-1 text-xs font-medium text-asphalt-600">
            Show
            <select className="control h-9 py-1 text-sm" value={level} onChange={(event) => update({ level: event.target.value || null, page: null })}>
              <option value="">All roads</option>
              <option value="high">High risk</option>
              <option value="medium">Medium risk</option>
              <option value="low">Low risk</option>
            </select>
          </label>
        </div>
        {list.isPending && <SkeletonRows rows={4} />}
        {list.isError && <ErrorMessage title="Could not load the road list" error={list.error} onRetry={() => void list.refetch()} />}
        {list.isSuccess &&
          (list.data.items.length === 0 ? (
            <EmptyState icon={<ListChecks />} title={level ? 'No roads at this level' : 'No road levels yet'}>
              {level
                ? 'Choose "All roads" to see the whole list.'
                : status.level === 2
                  ? 'The first levels appear after the next Monday update.'
                  : 'The first risk factors appear after the next morning update.'}
            </EmptyState>
          ) : (
            <ol className="space-y-3" aria-label="Inspect first">
              {list.data.items.map((item) => (
                <RoadRow
                  key={item.section_id}
                  item={item}
                  projectId={project.id}
                  showFactors={status.level === 1}
                  onPlan={canPlan ? () => setPlanning(item) : undefined}
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
      </section>

      {planning && (
        <PlanInspectionDialog
          project={project}
          road={{ section_id: planning.section_id, name: planning.name, road_type: planning.road_type, length_m: planning.length_m }}
          onClose={() => setPlanning(null)}
        />
      )}
    </div>
  )
}

function UpdatedLine({ list }: { list: RiskList }) {
  const weatherUpTo = list.factors_run?.data_dates.weather_up_to
  return (
    <p className="text-xs">
      {list.levels_run && <>Levels of {formatDay(list.levels_run.as_of)}. </>}
      {list.factors_run && <>Risk factors updated {formatDay(list.factors_run.as_of)}</>}
      {weatherUpTo && <> (weather up to {formatDay(weatherUpTo)})</>}
      {list.factors_run && '.'}
    </p>
  )
}

function Counts({ list }: { list: RiskList }) {
  const total = list.counts.high + list.counts.medium + list.counts.low
  if (total === 0) return null
  return (
    <ul className="flex flex-wrap gap-3 text-sm" aria-label="Roads by level">
      {(['high', 'medium', 'low'] as const).map((key) => (
        <li key={key} className="flex items-center gap-2">
          <LevelBadge level={key} />
          <span className="font-medium">{list.counts[key].toLocaleString()}</span>
        </li>
      ))}
    </ul>
  )
}

function RoadRow({ item, projectId, showFactors, onPlan }: { item: SectionRisk; projectId: string; showFactors: boolean; onPlan?: () => void }) {
  const flagged = item.factors.filter((f) => f.kind === 'risk' && (f.level === 'high' || f.level === 'medium'))
  return (
    <li className="panel flex flex-wrap items-start justify-between gap-3 p-4 text-sm">
      <div className="min-w-0 space-y-1.5">
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-asphalt-500">{item.position}.</span>
          <span className="font-medium">{roadName(item.name)}</span>
          <LevelBadge level={item.level} />
        </p>
        <p className="text-xs text-asphalt-500">
          {roadTypeLabel(item.road_type)} · {Math.round(item.length_m)} m
        </p>
        {showFactors ? (
          flagged.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-asphalt-700" aria-label="Main risk factors">
              {flagged.map((factor) => (
                <li key={factor.factor}>
                  {factor.label} ({factor.level})
                </li>
              ))}
            </ul>
          )
        ) : (
          item.reasons.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-asphalt-700" aria-label="Main reasons">
              {item.reasons.map((reason) => (
                <li key={reason.input}>{reasonText(reason)}</li>
              ))}
            </ul>
          )
        )}
        {item.missing_inputs.length > 0 && (
          <p className="flex items-center gap-1 text-xs text-amber-800">
            <TriangleAlert className="size-3.5" aria-hidden />
            Some inputs are not known: {item.missing_inputs.join(', ')}. Nothing is guessed.
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Link to={`/projects/${projectId}/road-risk/${item.section_id}`} className="btn btn-ghost">
          Open
        </Link>
        {onPlan && (
          <Button variant="secondary" onClick={onPlan}>
            Plan inspection
          </Button>
        )}
      </div>
    </li>
  )
}

/** F4e: the project's open alerts at the top of the tab (E-D3: no separate tab). */
function ProjectAlerts({ projectId }: { projectId: string }) {
  const alerts = useQuery({ queryKey: alertQueryKeys.project(projectId), queryFn: ({ signal }) => listProjectAlerts(projectId, signal) })
  if (!alerts.data || alerts.data.items.length === 0) return null
  return (
    <section className="space-y-2" aria-label="Open alerts">
      <h3 className="font-medium">Open alerts</h3>
      <ul className="space-y-2">
        {alerts.data.items.map((alert) => (
          <AlertRow key={alert.id} alert={alert} />
        ))}
      </ul>
    </section>
  )
}

/** CR-006 "Ask about road risk": a short answer from this project's data, with links (never acts). */
function AskBox({ projectId }: { projectId: string }) {
  const [question, setQuestion] = useState('')
  const ask = useMutation({ mutationFn: (text: string) => askAssistant(projectId, text) })
  const send = (text: string) => {
    const trimmed = text.trim()
    if (trimmed.length >= 3) {
      setQuestion(trimmed)
      ask.mutate(trimmed)
    }
  }
  return (
    <section className="panel space-y-3 p-4" aria-label="Ask about road risk">
      <h3 className="font-medium">Ask about road risk</h3>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          send(question)
        }}
      >
        <label className="sr-only" htmlFor="ask-question">
          Your question
        </label>
        <input
          id="ask-question"
          className="control min-w-0 flex-1"
          maxLength={500}
          placeholder="e.g. Why is Main Street high risk?"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <Button type="submit" busy={ask.isPending} disabled={question.trim().length < 3}>
          Ask
        </Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {ASSISTANT_EXAMPLES.map((example) => (
          <button key={example} type="button" className="pill bg-asphalt-100 text-asphalt-700 hover:bg-asphalt-200" onClick={() => send(example)}>
            {example}
          </button>
        ))}
      </div>
      {ask.isPending && <p className="text-sm text-asphalt-500">Working out the answer… this can take up to a minute.</p>}
      {ask.isError && <ErrorMessage title="Could not answer" error={ask.error} />}
      {ask.data && (
        <div role="region" className="space-y-2 rounded-lg border border-asphalt-100 p-3 text-sm" aria-label="Answer">
          <p className="pill bg-lane-100 text-asphalt-800">{ask.data.label}</p>
          <p className="whitespace-pre-line">{ask.data.answer}</p>
          {ask.data.sources.length > 0 && (
            <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
              Sources:
              {ask.data.sources.map((source) => (
                <Link key={source.path} to={source.path} className="link">
                  {source.label}
                </Link>
              ))}
            </p>
          )}
          <p className="text-xs text-asphalt-500">
            {ask.data.used_model ? 'Written by the AI model from the data above.' : 'Built-in answer (the AI model was off or too slow).'}{' '}
            {ask.data.notice} Questions left today: {ask.data.questions_left_today}.
          </p>
        </div>
      )}
    </section>
  )
}
