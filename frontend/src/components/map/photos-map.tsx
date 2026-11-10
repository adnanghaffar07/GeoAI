import type { ExpressionSpecification, GeoJSONSource, MapLayerMouseEvent } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import { WORST_COLORS, type PhotoMapData } from '@/api/photo-map'
import type { AreaGeometry } from '@/api/projects'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea, showArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { cn } from '@/lib/utils'

const SOURCE = 'photos'
const EMPTY = { type: 'FeatureCollection' as const, features: [] }
const COLOR = ['match', ['get', 'worst'], ...Object.entries(WORST_COLORS).flatMap(([k, v]) => [Number(k), v]), '#1b2633'] as unknown as ExpressionSpecification

interface Props {
  area: AreaGeometry
  data: PhotoMapData | undefined
  selectedId: string | null
  onSelect: (photoId: string) => void
  className?: string
}

/** Analysed photos as pins, coloured by the most serious problem found on each. */
export function PhotosMap({ area, data, selectedId, onSelect, className }: Props) {
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
        id: 'photos-selected',
        type: 'circle',
        source: SOURCE,
        filter: ['==', ['get', 'id'], ''],
        paint: { 'circle-radius': 13, 'circle-color': '#1b2633', 'circle-opacity': 0.25, 'circle-stroke-color': '#1b2633', 'circle-stroke-width': 2 },
      })
      map.addLayer({
        id: 'photos-points',
        type: 'circle',
        source: SOURCE,
        paint: { 'circle-radius': 7, 'circle-color': COLOR, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
      })
    }
    const click = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id
      if (typeof id === 'string') onSelectRef.current(id)
    }
    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const normal = () => (map.getCanvas().style.cursor = '')
    map.on('click', 'photos-points', click)
    map.on('mouseenter', 'photos-points', pointer)
    map.on('mouseleave', 'photos-points', normal)
    return () => {
      map.off('click', 'photos-points', click)
      map.off('mouseenter', 'photos-points', pointer)
      map.off('mouseleave', 'photos-points', normal)
    }
  }, [map, area])

  useEffect(() => {
    // Defects are nested lists; the map only needs the flat properties.
    const flat = data ? { ...data, features: data.features.map((f) => ({ ...f, properties: { id: f.properties.id, worst: f.properties.worst } })) } : EMPTY
    map?.getSource<GeoJSONSource>(SOURCE)?.setData(flat)
  }, [map, data])

  useEffect(() => {
    if (!map || !map.getLayer('photos-selected')) return
    map.setFilter('photos-selected', ['==', ['get', 'id'], selectedId ?? ''])
  }, [map, selectedId])

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-asphalt-100', className)}>
      <div ref={containerRef} role="region" aria-label="Map of photos" className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
      {data?.truncated && (
        <p className="absolute top-2 left-2 rounded bg-white/90 px-2 py-1 text-xs text-asphalt-600 shadow">Showing the newest {data.features.length} photos.</p>
      )}
    </div>
  )
}
