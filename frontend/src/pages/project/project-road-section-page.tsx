import { useQuery } from '@tanstack/react-query'
import { TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router'

import { INSPECTION_LABELS } from '@/api/priority'
import { formatDay, getSectionRisk, reasonText, roadName, roadRiskQueryKeys, roadTypeLabel, type RoadDetails } from '@/api/road-risk'
import { ErrorMessage } from '@/components/error-message'
import { InspectionDialog, PlanInspectionDialog } from '@/components/inspections/inspection-dialogs'
import { RoadRiskLegend, RoadRiskMap } from '@/components/map/road-risk-map'
import { FactorTable, LevelBadge, TrialNotice } from '@/components/road-risk/road-risk-parts'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

/** F4d: one road's level, reasons, factors, weekly history and inspections (design §3.2). */
export function ProjectRoadSectionPage() {
  const project = useProject()
  const { sectionId = '' } = useParams()
  const [dialog, setDialog] = useState<'plan' | 'view' | null>(null)
  const detail = useQuery({
    queryKey: roadRiskQueryKeys.section(project.id, sectionId),
    queryFn: ({ signal }) => getSectionRisk(project.id, sectionId, signal),
  })
  if (detail.isPending) return <SkeletonRows rows={4} />
  if (detail.isError)
    return (
      <div className="space-y-3">
        <ErrorMessage title="Could not load this road" error={detail.error} onRetry={() => void detail.refetch()} />
      </div>
    )

  const { section, history, inspections } = detail.data
  const road = { section_id: section.section_id, name: section.name, road_type: section.road_type, length_m: section.length_m }
  const open = inspections.find((item) => item.status === 'planned' || item.status === 'inspected')
  const canPlan = hasProjectPermission(project, 'inspection.plan') && !project.archived && !open
  const feature = { type: 'Feature' as const, geometry: detail.data.geometry, properties: { section_id: section.section_id, name: section.name, level: section.level, position: section.position } }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
            {roadName(section.name)} <LevelBadge level={section.level} />
          </h2>
          <p className="text-sm text-asphalt-500">
            {roadTypeLabel(section.road_type)} · {Math.round(section.length_m)} m · number {section.position} on this project's "Inspect first" list
          </p>
        </div>
        <div className="flex gap-2">
          {inspections.length > 0 && (
            <Button variant="secondary" onClick={() => setDialog('view')}>
              View inspection
            </Button>
          )}
          {canPlan && <Button onClick={() => setDialog('plan')}>Plan inspection</Button>}
        </div>
      </div>

      {detail.data.road && <RoadSpecs road={detail.data.road} />}

      <TrialNotice label={detail.data.label} notice={detail.data.notice}>
        {detail.data.levels_run && <p className="text-xs">Levels of {formatDay(detail.data.levels_run.as_of)}.</p>}
      </TrialNotice>

      {section.reasons.length > 0 && (
        <section className="space-y-1">
          <h3 className="font-medium">Main reasons</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-sm">
            {section.reasons.map((reason) => (
              <li key={reason.input}>{reasonText(reason)}</li>
            ))}
          </ul>
        </section>
      )}
      {section.missing_inputs.length > 0 && (
        <p className="flex items-center gap-1 text-sm text-amber-800">
          <TriangleAlert className="size-4" aria-hidden />
          Not known: {section.missing_inputs.join(', ')}. Nothing is guessed.
        </p>
      )}

      <FactorTable factors={section.factors} />

      {history.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-medium">Week by week</h3>
          <ol className="flex flex-wrap gap-2" aria-label="Level each week">
            {history.slice(0, 26).map((point) => (
              <li key={point.as_of} className="space-y-1 text-center text-xs">
                <LevelBadge level={point.level} kind="factor" />
                <p className="text-asphalt-500">{new Date(`${point.as_of}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="space-y-2">
        <h3 className="font-medium">Inspections of this road</h3>
        {inspections.length === 0 ? (
          <p className="text-sm text-asphalt-500">None yet.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {inspections.map((item) => (
              <li key={item.id}>
                {INSPECTION_LABELS[item.status] ?? item.status}
                {item.planned_date && ` · planned for ${new Date(`${item.planned_date}T00:00:00`).toLocaleDateString(undefined, { dateStyle: 'medium' })}`}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="space-y-2">
        <RoadRiskMap area={project.boundary} features={[feature]} fitTo="roads" className="h-72" label="Map of this road" />
        <RoadRiskLegend />
      </div>

      {dialog === 'plan' && <PlanInspectionDialog project={project} road={road} onClose={() => setDialog(null)} />}
      {dialog === 'view' && <InspectionDialog project={project} road={road} onClose={() => setDialog(null)} />}
    </div>
  )
}

/** Team-lead item 12: speed limit and other road details. "Not on the map" is shown, never a guess. */
function RoadSpecs({ road }: { road: RoadDetails }) {
  const unknown = 'Not on the map'
  const rows: [string, string][] = [
    ['Speed limit', road.speed_limit_mph ? `${road.speed_limit_mph} mph` : unknown],
    ['Lanes', road.lanes ? String(road.lanes) : unknown],
    ['Surface', road.surface ?? unknown],
    ['One-way', road.oneway === null ? unknown : road.oneway ? 'Yes' : 'No'],
    ['Route number', road.road_ref ?? unknown],
  ]
  return (
    <section aria-label="Road details" className="rounded-lg border border-asphalt-100 p-3">
      <h3 className="mb-2 text-sm font-semibold text-asphalt-800">Road details</h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-5">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-asphalt-500">{label}</dt>
            <dd className={value === unknown ? 'text-asphalt-400' : 'text-asphalt-800'}>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-asphalt-500">Source: {road.source} (OpenStreetMap). Check signs on site before relying on them.</p>
    </section>
  )
}
