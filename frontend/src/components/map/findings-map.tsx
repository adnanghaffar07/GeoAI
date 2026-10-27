import type { ExpressionSpecification, GeoJSONSource, MapLayerMouseEvent } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import type { FindingsMap as FindingsMapData } from '@/api/findings'
import type { AreaGeometry } from '@/api/projects'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea, showArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { STATUS_COLORS } from '@/lib/findings'
import { cn } from '@/lib/utils'

const SOURCE = 'findings'
const EMPTY: FindingsMapData = { type: 'FeatureCollection', features: [], truncated: false }

// MapLibre "match" expression: pin colour by review status.
const COLOR_BY_STATUS = ['match', ['get', 'review_status'], ...Object.entries(STATUS_COLORS).flat(), '#1b2633'] as unknown as ExpressionSpecification

interface FindingsMapProps {
  area: AreaGeometry
  data: FindingsMapData | undefined
  selectedId: string | null
  onSelect: (findingId: string) => void
  className?: string
}

/** Findings as pins (S09). Clicking a pin selects it; selecting in the list highlights it here. */
export function FindingsMap({ area, data, selectedId, onSelect, className }: FindingsMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const onSelectRef = useRef(onSelect)
  const fitted = useRef(false)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  // Layers and click handling, once per map.
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
        id: 'findings-selected',
        type: 'circle',
        source: SOURCE,
        filter: ['==', ['get', 'id'], ''],
        paint: { 'circle-radius': 13, 'circle-color': '#1b2633', 'circle-opacity': 0.25, 'circle-stroke-color': '#1b2633', 'circle-stroke-width': 2 },
      })
      map.addLayer({
        id: 'findings-points',
        type: 'circle',
        source: SOURCE,
        paint: {
          'circle-radius': 7,
          'circle-color': COLOR_BY_STATUS,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      })
    }
    const handleClick = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id
      if (typeof id === 'string') onSelectRef.current(id)
    }
    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const normal = () => (map.getCanvas().style.cursor = '')
    map.on('click', 'findings-points', handleClick)
    map.on('mouseenter', 'findings-points', pointer)
    map.on('mouseleave', 'findings-points', normal)
    return () => {
      map.off('click', 'findings-points', handleClick)
      map.off('mouseenter', 'findings-points', pointer)
      map.off('mouseleave', 'findings-points', normal)
    }
  }, [map, area])

  useEffect(() => {
    map?.getSource<GeoJSONSource>(SOURCE)?.setData(data ?? EMPTY)
  }, [map, data])

  // Highlight the selected finding and bring it into view if it is off-screen.
  useEffect(() => {
    if (!map || !map.getLayer('findings-selected')) return
    map.setFilter('findings-selected', ['==', ['get', 'id'], selectedId ?? ''])
    const feature = data?.features.find((item) => item.id === selectedId)
    if (feature && !map.getBounds().contains(feature.geometry.coordinates)) {
      map.easeTo({ center: feature.geometry.coordinates, duration: 400 })
    }
  }, [map, data, selectedId])

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-asphalt-100', className)}>
      <div ref={containerRef} role="region" aria-label="Map of findings" className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
      {data?.truncated && (
        <p className="absolute top-2 left-2 rounded bg-white/90 px-2 py-1 text-xs text-asphalt-600 shadow">
          Showing the newest {data.features.length} pins. Use the filters to narrow down.
        </p>
      )}
    </div>
  )
}
