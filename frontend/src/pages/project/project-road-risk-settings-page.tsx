import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { projectQueryKeys } from '@/api/projects'
import {
  getForecastSettings,
  requestRiskUpdate,
  roadRiskQueryKeys,
  saveForecastSettings,
  VISIBLE_ROLE_LABELS,
  type ForecastStatusInfo,
  type VisibleRole,
} from '@/api/road-risk'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { PageIntro } from '@/components/ui/page-intro'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

const STATUS_TEXT: Record<string, string> = {
  off: 'Off',
  setting_up: 'Setting up… (can take up to an hour for a new area)',
  ready: 'On and ready',
  failed: 'Set-up failed',
  too_large: 'Area too large',
}

/** F4d Settings → Road risk (project managers): on/off, update now, who else can see it (design §3.3). */
export function ProjectRoadRiskSettingsPage() {
  const project = useProject()
  const settings = useQuery({
    queryKey: roadRiskQueryKeys.settings(project.id),
    queryFn: ({ signal }) => getForecastSettings(project.id, signal),
    refetchInterval: (query) => (query.state.data?.status === 'setting_up' ? 10_000 : false),
  })
  useReadyRefresh(project.id, settings.data?.status)
  if (!hasProjectPermission(project, 'risk.configure')) return <p className="text-sm text-asphalt-500">Only project managers can change road risk.</p>
  if (settings.isPending) return <SkeletonRows rows={3} />
  if (settings.isError) return <ErrorMessage title="Could not load road risk settings" error={settings.error} onRetry={() => void settings.refetch()} />
  return <RoadRiskSettings key={settings.data.visible_to_roles.join()} projectId={project.id} archived={project.archived} status={settings.data} />
}

/** When set-up finishes, reload the project so the Road risk tab appears. */
// eslint-disable-next-line react-refresh/only-export-components -- small hook shared with the Road risk tab
export function useReadyRefresh(projectId: string, status: string | undefined) {
  const queryClient = useQueryClient()
  const previous = useRef(status)
  useEffect(() => {
    if (previous.current === 'setting_up' && status === 'ready') {
      void queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(projectId) })
      void queryClient.invalidateQueries({ queryKey: roadRiskQueryKeys.all(projectId) })
    }
    previous.current = status
  }, [projectId, status, queryClient])
}

function RoadRiskSettings({ projectId, archived, status }: { projectId: string; archived: boolean; status: ForecastStatusInfo }) {
  const queryClient = useQueryClient()
  const [roles, setRoles] = useState<VisibleRole[]>(status.visible_to_roles)
  const done = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: roadRiskQueryKeys.all(projectId) }),
      queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(projectId) }),
    ])
  }
  const save = useMutation({
    mutationFn: (body: { enabled?: boolean; visible_to_roles?: VisibleRole[]; assistant_enabled?: boolean }) => saveForecastSettings(projectId, body),
    onSuccess: done,
    meta: { success: 'Road risk settings saved.' },
  })
  const update = useMutation({ mutationFn: () => requestRiskUpdate(projectId), onSuccess: done, meta: { success: 'Update started in the background.' } })
  const changed = roles.join() !== status.visible_to_roles.join()
  const on = status.enabled

  return (
    <div className="space-y-6">
      <PageIntro title="Road risk">
        A trial forecast of which roads are most likely to get new potholes soon. In Chicago it uses the tested levels; elsewhere it shows risk
        factors only (weather and road facts). It works for project areas up to {status.max_area_km2} km².
      </PageIntro>

      <section className="panel space-y-3 p-4">
        <h3 className="font-medium">Forecast for this project</h3>
        <p className="text-sm">
          Status: <strong>{on ? STATUS_TEXT[status.status] : 'Off'}</strong>
          {status.area_km2 !== null && <> · project area {status.area_km2.toLocaleString()} km²</>}
        </p>
        {status.message && <p className="text-sm text-asphalt-600">{status.message}</p>}
        {on && status.status === 'setting_up' && <SetupProgress message={status.message} />}
        {on && status.status === 'ready' && (
          <p className="text-xs text-asphalt-500">
            Last updates: daily {status.last_daily_run ?? 'not yet'}
            {status.level === 2 && <>, weekly {status.last_weekly_run ?? 'not yet'}</>}.
          </p>
        )}
        {save.isError && <ErrorMessage title="Could not save" error={save.error} />}
        {update.isError && <ErrorMessage title="Could not start the update" error={update.error} />}
        <div className="flex flex-wrap gap-2">
          {on && status.status !== 'failed' ? (
            <Button variant="secondary" disabled={archived} busy={save.isPending} onClick={() => save.mutate({ enabled: false })}>
              Switch off
            </Button>
          ) : (
            <Button disabled={archived} busy={save.isPending} onClick={() => save.mutate({ enabled: true })}>
              {status.status === 'failed' ? 'Try again' : 'Switch on'}
            </Button>
          )}
          {on && status.status === 'ready' && (
            <Button variant="ghost" disabled={archived} busy={update.isPending} onClick={() => update.mutate()}>
              Update now
            </Button>
          )}
        </div>
        {on && status.status === 'ready' && (
          <p className="text-xs text-asphalt-500">"Update now" refreshes weather, risk factors and the outlook in the background (after 06:00 Chicago time).</p>
        )}
      </section>

      <section className="panel space-y-3 p-4">
        <h3 className="font-medium">Ask about road risk (AI answers)</h3>
        <p className="text-sm text-asphalt-600">
          A question box in the Road risk tab. Answers come only from this project's road-risk data, with links to the pages used; a free AI
          model on this computer writes the sentence. Nothing leaves the computer. Off by default.
        </p>
        <p className="text-sm">
          Status: <strong>{status.assistant_enabled ? 'On' : 'Off'}</strong>
        </p>
        <Button
          variant="secondary"
          disabled={archived}
          busy={save.isPending}
          onClick={() => save.mutate({ assistant_enabled: !status.assistant_enabled })}
        >
          {status.assistant_enabled ? 'Switch off questions' : 'Switch on questions'}
        </Button>
      </section>

      <section className="panel space-y-3 p-4">
        <h3 className="font-medium">Who can see road risk</h3>
        <p className="text-sm text-asphalt-600">Project managers always can. Tick who else may see it. Alerts stay with project managers.</p>
        <fieldset className="space-y-2 text-sm">
          <legend className="sr-only">Roles that can see road risk</legend>
          <label className="flex items-center gap-2 text-asphalt-500">
            <input type="checkbox" checked disabled /> Project managers (always)
          </label>
          {(Object.keys(VISIBLE_ROLE_LABELS) as VisibleRole[]).map((role) => (
            <label key={role} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={roles.includes(role)}
                disabled={archived}
                onChange={(event) => setRoles(event.target.checked ? [...roles, role] : roles.filter((item) => item !== role))}
              />
              {VISIBLE_ROLE_LABELS[role]}
            </label>
          ))}
        </fieldset>
        <Button variant="secondary" disabled={!changed || archived} busy={save.isPending} onClick={() => save.mutate({ visible_to_roles: roles })}>
          Save who can see it
        </Button>
      </section>
    </div>
  )
}

/** Step N of 4 as a bar, from the server's message; this page checks again every 10 seconds. */
export function SetupProgress({ message }: { message: string | null }) {
  const match = message?.match(/Step (\d) of (\d)/)
  const step = match ? Number(match[1]) : 0
  const total = match ? Number(match[2]) : 4
  return (
    <div className="space-y-1">
      <div className="h-2 overflow-hidden rounded-full bg-asphalt-100" role="progressbar" aria-label="Set-up progress" aria-valuemin={0} aria-valuemax={total} aria-valuenow={step}>
        <div className="h-full rounded-full bg-lane-500 transition-all" style={{ width: `${Math.max(5, (step / total) * 100)}%` }} />
      </div>
      <p className="text-xs text-asphalt-500">This page checks again every 10 seconds.</p>
    </div>
  )
}
