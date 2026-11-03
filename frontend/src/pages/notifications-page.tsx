import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, ClipboardCheck, CloudRain, DatabaseZap, Snowflake, TriangleAlert, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { getProject, projectQueryKeys } from '@/api/projects'
import {
  ALERT_TYPE_LABELS,
  alertQueryKeys,
  getNotification,
  listNotifications,
  markAlertRead,
  markAllAlertsRead,
  type AlertType,
  type RiskAlert,
} from '@/api/road-risk'
import { ErrorMessage } from '@/components/error-message'
import { PlanInspectionDialog } from '@/components/inspections/inspection-dialogs'
import { LevelBadge, TrialNotice } from '@/components/road-risk/road-risk-parts'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { cn } from '@/lib/utils'

const ALERT_ICONS: Record<AlertType, LucideIcon> = {
  turned_high: TriangleAlert,
  freeze_thaw_coming: Snowflake,
  heavy_rain_coming: CloudRain,
  data_problem: DatabaseZap,
  inspection_assigned: ClipboardCheck,
}

const when = (time: string) => new Date(time).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** F4e: my alerts (project managers), newest open first (forecasting-f4e-design.md §4). */
export function NotificationsPage() {
  const queryClient = useQueryClient()
  const list = useQuery({ queryKey: alertQueryKeys.all, queryFn: ({ signal }) => listNotifications(signal) })
  const readAll = useMutation({
    mutationFn: markAllAlertsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: alertQueryKeys.all }),
    meta: { success: 'All alerts marked as read.' },
  })
  return (
    <div className="space-y-5">
      <PageIntro
        title="Alerts"
        actions={
          list.data && list.data.unread_count > 0 && (
            <Button variant="secondary" busy={readAll.isPending} onClick={() => readAll.mutate()}>
              Mark all as read
            </Button>
          )
        }
      >
        Road-risk alerts for project managers, and inspections you have been asked to do. They close by themselves when the event is over or the
        inspection is resolved.
      </PageIntro>
      {list.isPending && <SkeletonRows rows={3} />}
      {list.isError && <ErrorMessage title="Could not load the alerts" error={list.error} onRetry={() => void list.refetch()} />}
      {list.isSuccess &&
        (list.data.items.length === 0 ? (
          <EmptyState icon={<Bell />} title="No alerts">
            {list.data.manages_projects
              ? 'When road risk finds something important in a project you manage, it appears here.'
              : 'Alerts go to project managers.'}
          </EmptyState>
        ) : (
          <ul className="space-y-2" aria-label="Alerts">
            {list.data.items.map((alert) => (
              <AlertRow key={alert.id} alert={alert} />
            ))}
          </ul>
        ))}
    </div>
  )
}

export function AlertRow({ alert }: { alert: RiskAlert }) {
  const Icon = ALERT_ICONS[alert.type]
  return (
    <li className={cn('panel flex flex-wrap items-center justify-between gap-3 p-4 text-sm', !alert.read && 'border-l-4 border-l-lane-500')}>
      <div className="flex min-w-0 items-start gap-3">
        <Icon className="mt-0.5 size-5 shrink-0 text-asphalt-600" aria-hidden />
        <div className="min-w-0">
          <p className={cn(!alert.read && 'font-semibold')}>
            {alert.title}
            {!alert.read && <span className="sr-only"> (unread)</span>}
          </p>
          <p className="text-xs text-asphalt-500">
            {alert.project_name} · {ALERT_TYPE_LABELS[alert.type]} · {when(alert.created_at)}
            {alert.closed_at && ' · closed'}
          </p>
        </div>
      </div>
      <Link to={`/notifications/${alert.id}`} className="btn btn-secondary">
        Open
      </Link>
    </li>
  )
}

/** F4e alert page: the event, its roads with reasons, sources and buttons (design §2). */
export function AlertPage() {
  const { alertId = '' } = useParams()
  const queryClient = useQueryClient()
  const [planning, setPlanning] = useState<string | null>(null)
  const alert = useQuery({ queryKey: alertQueryKeys.one(alertId), queryFn: ({ signal }) => getNotification(alertId, signal) })
  const projectId = alert.data?.project_id ?? ''
  const project = useQuery({ queryKey: projectQueryKeys.detail(projectId), queryFn: ({ signal }) => getProject(projectId, signal), enabled: Boolean(projectId) })
  const unread = alert.data && !alert.data.read
  useEffect(() => {
    if (unread) void markAlertRead(alertId).then(() => queryClient.invalidateQueries({ queryKey: alertQueryKeys.all }))
  }, [alertId, unread, queryClient])

  if (alert.isPending) return <SkeletonRows rows={4} />
  if (alert.isError)
    return (
      <div className="space-y-3">
        <ErrorMessage title="Could not load this alert" error={alert.error} onRetry={() => void alert.refetch()} />
      </div>
    )
  const { details } = alert.data
  const roads = details.roads ?? []
  const canPlan = project.data?.my_permissions.includes('inspection.plan') && !project.data.archived
  const planningRoad = roads.find((road) => road.section_id === planning)

  return (
    <div className="space-y-5">
      <PageIntro title={alert.data.title}>
        {alert.data.project_name} · {ALERT_TYPE_LABELS[alert.data.type]} · {when(alert.data.created_at)}
        {alert.data.closed_at && ` · closed ${when(alert.data.closed_at)}`}
      </PageIntro>
      {alert.data.type !== 'inspection_assigned' && (
      <TrialNotice label={details.label ?? 'TRIAL FORECAST'} notice={details.notice ?? 'Risk estimate, not a confirmed defect.'}>
        {details.model_version && <p className="text-xs">Model {details.model_version}{details.levels_of && `, levels of ${details.levels_of}`}.</p>}
      </TrialNotice>
      )}
      <section className="panel space-y-1 p-4 text-sm">
        {details.when && (
          <p>
            <strong>When:</strong> {details.when}
          </p>
        )}
        {details.source && (
          <p>
            <strong>Source:</strong> {details.source}
            {details.issued_at && `, issued ${when(details.issued_at)}`}
          </p>
        )}
        {details.reason && (
          <p>
            <strong>What happened:</strong> {details.reason}
          </p>
        )}
        {details.suggested_action && (
          <p>
            <strong>Suggested action:</strong> {details.suggested_action}
          </p>
        )}
        {details.planned_by && (
          <p>
            <strong>Planned by:</strong> {details.planned_by}
          </p>
        )}
        {details.path && (
          <Link to={details.path} className="btn btn-accent mt-2">
            Open my inspections
          </Link>
        )}
      </section>
      {roads.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-medium">
            {roads.length} road{roads.length === 1 ? '' : 's'}
          </h3>
          <ul className="space-y-2" aria-label="Roads in this alert">
            {roads.map((road) => (
              <li key={road.section_id} className="panel flex flex-wrap items-start justify-between gap-3 p-4 text-sm">
                <div className="space-y-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    {road.name} <LevelBadge level={road.level} />
                    {road.previous_level && <span className="text-xs font-normal text-asphalt-500">last week: {road.previous_level}</span>}
                  </p>
                  {road.reasons.length > 0 && (
                    <ul className="list-disc pl-5 text-asphalt-700">
                      {road.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  )}
                  {road.missing_inputs.length > 0 && <p className="text-xs text-amber-800">Not known: {road.missing_inputs.join(', ')}.</p>}
                </div>
                <div className="flex gap-2">
                  <Link to={`/projects/${alert.data.project_id}/road-risk/${road.section_id}`} className="btn btn-ghost">
                    Open
                  </Link>
                  {canPlan && (
                    <Button variant="secondary" onClick={() => setPlanning(road.section_id)}>
                      Plan inspection
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {planningRoad && project.data && (
        <PlanInspectionDialog
          project={project.data}
          road={{ section_id: planningRoad.section_id, name: planningRoad.name, road_type: 'road', length_m: 0 }}
          onClose={() => setPlanning(null)}
        />
      )}
    </div>
  )
}
