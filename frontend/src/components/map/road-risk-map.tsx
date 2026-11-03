import type { GeoJSONSource, LngLatBoundsLike, MapLayerMouseEvent } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import type { AreaGeometry } from '@/api/projects'
import type { RiskMapFeature } from '@/api/road-risk'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea, showArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { cn } from '@/lib/utils'

const SOURCE = 'road-risk'
/** With many roads, low ones appear only when zoomed in, so high and medium stand out. */
const MANY_ROADS = 300

/**
 * Road sections by risk level (F4d). Levels differ by line thickness and pattern as well as
 * colour: high = thick solid line, medium = dashed, low = thin grey. A legend with the words is
 * shown below the map (`RoadRiskLegend`).
 */
export function RoadRiskMap({
  area,
  features,
  onSelect,
  fitTo = 'area',
  className,
  label = 'Map of road risk',
}: {
  area: AreaGeometry
  features: RiskMapFeature[]
  onSelect?: (sectionId: string) => void
  /** "area": the survey area; "roads": the roads shown (e.g. one road on its page). */
  fitTo?: 'area' | 'roads'
  className?: string
  label?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const onSelectRef = useRef(onSelect)
  const fitted = useRef(false)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    if (!map) return
    showArea(map, area)
    const data = { type: 'FeatureCollection' as const, features }
    const source = map.getSource<GeoJSONSource>(SOURCE)
    if (source) source.setData(data)
    else {
      map.addSource(SOURCE, { type: 'geojson', data })
      map.addLayer({
        id: 'road-risk-low',
        type: 'line',
        source: SOURCE,
        filter: ['==', ['get', 'level'], 'low'],
        minzoom: features.length > MANY_ROADS ? 14 : 0,
        paint: { 'line-color': '#7b8a9c', 'line-width': 1.5 },
      })
      map.addLayer({
        id: 'road-risk-medium',
        type: 'line',
        source: SOURCE,
        filter: ['==', ['get', 'level'], 'medium'],
        paint: { 'line-color': '#b45309', 'line-width': 4, 'line-dasharray': [2, 1] },
      })
      map.addLayer({
        id: 'road-risk-high',
        type: 'line',
        source: SOURCE,
        filter: ['==', ['get', 'level'], 'high'],
        layout: { 'line-cap': 'round' },
        paint: { 'line-color': '#b91c1c', 'line-width': 7 },
      })
      map.addLayer({
        id: 'road-risk-unknown',
        type: 'line',
        source: SOURCE,
        filter: ['!', ['to-boolean', ['get', 'level']]],
        paint: { 'line-color': '#7b8a9c', 'line-width': 1.5, 'line-dasharray': [1, 2] },
      })
    }
    if (!fitted.current) {
      const coords = features.flatMap((feature) => feature.geometry.coordinates)
      if (fitTo === 'roads' && coords.length > 0) {
        const lons = coords.map((c) => c[0])
        const lats = coords.map((c) => c[1])
        const bounds: LngLatBoundsLike = [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ]
        map.fitBounds(bounds, { padding: 48, duration: 0, maxZoom: 17 })
      } else fitToArea(map, area)
      fitted.current = true
    }
    const layers = ['road-risk-high', 'road-risk-medium', 'road-risk-low']
    const handleClick = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.section_id
      if (typeof id === 'string') onSelectRef.current?.(id)
    }
    const pointer = () => (map.getCanvas().style.cursor = onSelectRef.current ? 'pointer' : '')
    const normal = () => (map.getCanvas().style.cursor = '')
    for (const layer of layers) {
      map.on('click', layer, handleClick)
      map.on('mouseenter', layer, pointer)
      map.on('mouseleave', layer, normal)
    }
    return () => {
      for (const layer of layers) {
        map.off('click', layer, handleClick)
        map.off('mouseenter', layer, pointer)
        map.off('mouseleave', layer, normal)
      }
    }
  }, [map, area, features, fitTo])

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-asphalt-100', className)}>
      <div ref={containerRef} role="region" aria-label={label} className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
    </div>
  )
}

/** The map's key, in words: what each line style means. */
export function RoadRiskLegend({ manyRoads = false }: { manyRoads?: boolean }) {
  const items: [string, string][] = [
    ['High risk', 'M0 6 H40'],
    ['Medium risk', 'M0 6 H40'],
    ['Low risk', 'M0 6 H40'],
  ]
  const styles = [
    { stroke: '#b91c1c', width: 7, dash: undefined },
    { stroke: '#b45309', width: 4, dash: '8 4' },
    { stroke: '#7b8a9c', width: 1.5, dash: undefined },
  ]
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-asphalt-600" aria-label="Map key">
      {items.map(([word, path], index) => (
        <li key={word} className="flex items-center gap-2">
          <svg width="40" height="12" aria-hidden>
            <path d={path} stroke={styles[index]!.stroke} strokeWidth={styles[index]!.width} strokeDasharray={styles[index]!.dash} strokeLinecap={index === 0 ? 'round' : 'butt'} />
          </svg>
          {word}
        </li>
      ))}
      {manyRoads && <li>Low-risk roads appear when you zoom in.</li>}
    </ul>
  )
}
