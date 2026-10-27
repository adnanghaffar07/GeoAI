import type { ExpressionSpecification, GeoJSONSource, MapLayerMouseEvent } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import type { Dashboard } from '@/api/dashboard'
import { BaseMapNotice } from '@/components/map/area-map'
import { useMap } from '@/components/map/use-map'

const SOURCE = 'dashboard-findings'

interface DashboardMapProps {
  points: Dashboard['map_points']
  /** Colour per severity key (ordered, light -> dark). */
  severityColors: Record<string, string>
  onSelect: (point: Dashboard['map_points'][number]) => void
}

/** Verified findings across the chosen projects, coloured by severity. Click a pin to open it. */
export function DashboardMap({ points, severityColors, onSelect }: DashboardMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const pointsRef = useRef(points)
  const onSelectRef = useRef(onSelect)

  useEffect(() => {
    pointsRef.current = points
    onSelectRef.current = onSelect
  })

  useEffect(() => {
    if (!map) return
    const data = {
      type: 'FeatureCollection' as const,
      features: points.map((point) => ({
        type: 'Feature' as const,
        properties: { id: point.finding_id, severity: point.severity_key ?? '' },
        geometry: { type: 'Point' as const, coordinates: [point.longitude, point.latitude] },
      })),
    }
    const color = ['match', ['get', 'severity'], ...Object.entries(severityColors).flat(), '#6b6a66'] as unknown as ExpressionSpecification
    const source = map.getSource<GeoJSONSource>(SOURCE)
    if (source) source.setData(data)
    else {
      map.addSource(SOURCE, { type: 'geojson', data })
      map.addLayer({
        id: SOURCE,
        type: 'circle',
        source: SOURCE,
        paint: { 'circle-radius': 7, 'circle-color': color, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
      })
    }
    if (points.length > 0) {
      const lons = points.map((point) => point.longitude)
      const lats = points.map((point) => point.latitude)
      map.fitBounds(
        [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ],
        { padding: 48, maxZoom: 15, duration: 0 },
      )
    }
  }, [map, points, severityColors])

  useEffect(() => {
    if (!map) return
    const click = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id
      const point = pointsRef.current.find((item) => item.finding_id === id)
      if (point) onSelectRef.current(point)
    }
    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const normal = () => (map.getCanvas().style.cursor = '')
    map.on('click', SOURCE, click)
    map.on('mouseenter', SOURCE, pointer)
    map.on('mouseleave', SOURCE, normal)
    return () => {
      map.off('click', SOURCE, click)
      map.off('mouseenter', SOURCE, pointer)
      map.off('mouseleave', SOURCE, normal)
    }
  }, [map])

  return (
    <div className="relative h-72 overflow-hidden rounded-lg border border-asphalt-100">
      <div ref={containerRef} role="region" aria-label="Map of verified findings" className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
    </div>
  )
}
