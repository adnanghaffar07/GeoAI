import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import type { AreaGeometry } from '@/api/projects'
import { fitToArea, showArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { cn } from '@/lib/utils'

export interface MapPoint {
  id: string
  latitude: number
  longitude: number
}

const POINTS_SOURCE = 'photo-points'

function showPoints(map: MapLibreMap, points: MapPoint[]) {
  const data = {
    type: 'FeatureCollection' as const,
    features: points.map((point) => ({
      type: 'Feature' as const,
      properties: { id: point.id },
      geometry: { type: 'Point' as const, coordinates: [point.longitude, point.latitude] },
    })),
  }
  const source = map.getSource<GeoJSONSource>(POINTS_SOURCE)
  if (source) {
    source.setData(data)
    return
  }
  map.addSource(POINTS_SOURCE, { type: 'geojson', data })
  map.addLayer({
    id: 'photo-points',
    type: 'circle',
    source: POINTS_SOURCE,
    paint: { 'circle-radius': 5.5, 'circle-color': '#1b2633', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
  })
}

interface AreaMapProps {
  area: AreaGeometry
  /** Approximate photo (camera) locations. */
  points?: MapPoint[]
  className?: string
  label: string
}

/** Read-only map of a survey area with optional photo locations (S06 coverage map). */
export function AreaMap({ area, points = [], className, label }: AreaMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const fitted = useRef(false)

  useEffect(() => {
    if (!map) return
    showArea(map, area)
    showPoints(map, points)
    if (!fitted.current) {
      fitToArea(map, area)
      fitted.current = true
    }
  }, [map, area, points])

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-asphalt-100', className)}>
      <div ref={containerRef} role="region" aria-label={label} className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
    </div>
  )
}

export function BaseMapNotice() {
  return (
    <p className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs text-asphalt-500 shadow">
      Street map could not load. Shapes and points are still shown.
    </p>
  )
}
