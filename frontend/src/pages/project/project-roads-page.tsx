import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { roadName, roadTypeLabel } from '@/api/road-risk'
import { CATEGORIES, categoryOf, COLOUR_BY_LABELS, getRoads, roadsKey, type Box, type ColourBy, type RoadProps } from '@/api/roads-view'
import { ErrorMessage } from '@/components/error-message'
import { RoadsMap } from '@/components/map/roads-map'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { useProject } from '@/pages/project/project-layout'

interface NamedRoad {
  name: string | null
  lengthM: number
  speeds: number[]
  first: RoadProps
  categories: Set<string>
}

/** Team-lead item 11: roads only, with names, coloured by risk, speed limit, road type, weather or traffic. */
export function ProjectRoadsPage() {
  const project = useProject()
  const navigate = useNavigate()
  const [colourBy, setColourBy] = useState<ColourBy>('risk')
  const [roadsOnly, setRoadsOnly] = useState(true)
  const [box, setBox] = useState<Box | null>(null)
  const query = useQuery({ queryKey: roadsKey(project.id, box), queryFn: ({ signal }) => getRoads(project.id, box, signal), placeholderData: keepPreviousData })
  const open = (sectionId: string) => void navigate(`/projects/${project.id}/road-risk/${sectionId}`)

  const roads = useMemo(() => query.data?.features.map((f) => f.properties) ?? [], [query.data])
  const counts = useMemo(() => {
    const out: Record<string, number> = {}
    for (const road of roads) out[categoryOf(road, colourBy)] = (out[categoryOf(road, colourBy)] ?? 0) + 1
    return out
  }, [roads, colourBy])
  const named = useMemo(() => {
    const groups = new Map<string, NamedRoad>()
    for (const road of roads) {
      const key = road.name ?? `(no name) ${road.road_type}`
      const group = groups.get(key) ?? { name: road.name, lengthM: 0, speeds: [], first: road, categories: new Set<string>() }
      group.lengthM += road.length_m
      if (road.speed_limit_mph && !group.speeds.includes(road.speed_limit_mph)) group.speeds.push(road.speed_limit_mph)
      group.categories.add(categoryOf(road, colourBy))
      groups.set(key, group)
    }
    return [...groups.values()].sort((a, b) => b.lengthM - a.lengthM)
  }, [roads, colourBy])
  const km = roads.reduce((sum, road) => sum + road.length_m, 0) / 1000
  const labels = Object.fromEntries(CATEGORIES[colourBy].map((c) => [c.key, c.label]))

  return (
    <div className="space-y-4">
      <PageIntro title="Roads">
        Only the roads, with their names. Colour them by risk, speed limit, road type, weather or traffic. Choose an area on the map to see just the roads inside it, and click a road for its details.
      </PageIntro>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col text-xs text-asphalt-600">
          Colour roads by
          <select className="control mt-1 h-9 py-1 text-sm" value={colourBy} onChange={(e) => setColourBy(e.target.value as ColourBy)}>
            {(Object.keys(COLOUR_BY_LABELS) as ColourBy[]).map((key) => (
              <option key={key} value={key}>
                {COLOUR_BY_LABELS[key]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-asphalt-700">
          <input type="checkbox" checked={roadsOnly} onChange={(e) => setRoadsOnly(e.target.checked)} />
          Show only the roads (hide the background map)
        </label>
      </div>
      {query.isError && <ErrorMessage error={query.error} onRetry={() => void query.refetch()} />}
      {query.isPending && <SkeletonRows />}
      {query.data && query.data.features.length === 0 && !box && (
        <EmptyState title="No roads yet">Roads appear here once road risk has been set up for this project (Settings, then Road risk).</EmptyState>
      )}
      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <RoadsMap area={project.boundary} data={query.data} colourBy={colourBy} roadsOnly={roadsOnly} box={box} onBox={setBox} onSelect={open} className="h-96 lg:h-[calc(100dvh-14rem)]" />
        <aside aria-label="Roads summary" className="space-y-3 rounded-lg border border-asphalt-100 p-3 text-sm">
          <h2 className="font-semibold text-asphalt-800">{box ? 'Roads in the chosen area' : 'All roads in the project'}</h2>
          <p className="text-asphalt-600">
            {roads.length.toLocaleString()} sections · {km.toFixed(1)} km · {named.filter((n) => n.name).length.toLocaleString()} named roads
          </p>
          <ul aria-label={`Key: ${COLOUR_BY_LABELS[colourBy]}`} className="space-y-1">
            {CATEGORIES[colourBy].map((c) => (
              <li key={c.key} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <span className="inline-block h-1.5 w-5 rounded" style={{ background: c.colour }} aria-hidden />
                  {c.label}
                </span>
                <span className="text-asphalt-600">{(counts[c.key] ?? 0).toLocaleString()}</span>
              </li>
            ))}
          </ul>
          <h3 className="pt-1 font-semibold text-asphalt-800">Roads (longest first)</h3>
          <ul aria-label="Roads" className="max-h-96 space-y-1 overflow-auto">
            {named.slice(0, 100).map((road) => (
              <li key={road.first.section_id}>
                <button type="button" className="w-full rounded px-1 py-0.5 text-left hover:bg-asphalt-50" onClick={() => open(road.first.section_id)}>
                  <span className="font-medium text-asphalt-800">{road.name ? roadName(road.name) : `Unnamed ${roadTypeLabel(road.first.road_type).toLowerCase()}`}</span>
                  <span className="block text-xs text-asphalt-500">
                    {(road.lengthM / 1000).toFixed(2)} km · {road.speeds.length ? road.speeds.sort((a, b) => a - b).map((v) => `${v} mph`).join(', ') : 'speed limit not on the map'} ·{' '}
                    {[...road.categories].map((key) => labels[key]).join(', ')}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {named.length > 100 && <p className="text-xs text-asphalt-500">Showing the 100 longest roads. Choose a smaller area to see the others.</p>}
        </aside>
      </div>
    </div>
  )
}
