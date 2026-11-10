import type { GeoJSONSource, MapLayerMouseEvent } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import type { Camera } from '@/api/cameras'
import type { AreaGeometry } from '@/api/projects'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea, showArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { cn } from '@/lib/utils'

const SOURCE = 'cameras'
const EMPTY = { type: 'FeatureCollection' as const, features: [] }

interface Props {
  area: AreaGeometry
  cameras: Camera[]
  selectedId: number | null
  onSelect: (cameraId: number) => void
  className?: string
}

/** IDOT cameras as pins; a camera with several directions is one pin per direction at the same place. */
export function CamerasMap({ area, cameras, selectedId, onSelect, className }: Props) {
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
    if (!fitted.current) {
      fitToArea(map, area)
      fitted.current = true
    }
    if (!map.getSource(SOURCE)) {
      map.addSource(SOURCE, { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'cameras-selected',
        type: 'circle',
        source: SOURCE,
        filter: ['==', ['get', 'id'], -1],
        paint: { 'circle-radius': 13, 'circle-color': '#1b2633', 'circle-opacity': 0.25, 'circle-stroke-color': '#1b2633', 'circle-stroke-width': 2 },
      })
      map.addLayer({
        id: 'cameras-points',
        type: 'circle',
        source: SOURCE,
        paint: {
          'circle-radius': 7,
          'circle-color': ['case', ['get', 'too_old'], '#9aa5b1', '#0369a1'],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      })
    }
    const click = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id
      if (typeof id === 'number') onSelectRef.current(id)
    }
    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const normal = () => (map.getCanvas().style.cursor = '')
    map.on('click', 'cameras-points', click)
    map.on('mouseenter', 'cameras-points', pointer)
    map.on('mouseleave', 'cameras-points', normal)
    return () => {
      map.off('click', 'cameras-points', click)
      map.off('mouseenter', 'cameras-points', pointer)
      map.off('mouseleave', 'cameras-points', normal)
    }
  }, [map, area])

  useEffect(() => {
    const data = {
      type: 'FeatureCollection' as const,
      features: cameras.map((c) => ({ type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [c.longitude, c.latitude] }, properties: { id: c.id, too_old: c.too_old } })),
    }
    map?.getSource<GeoJSONSource>(SOURCE)?.setData(data)
  }, [map, cameras])

  useEffect(() => {
    if (!map || !map.getLayer('cameras-selected')) return
    map.setFilter('cameras-selected', ['==', ['get', 'id'], selectedId ?? -1])
  }, [map, selectedId])

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-asphalt-100', className)}>
      <div ref={containerRef} role="region" aria-label="Map of traffic cameras" className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
    </div>
  )
}
