import type { ExpressionSpecification, GeoJSONSource, MapLayerMouseEvent, MapMouseEvent } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'

import type { AreaGeometry } from '@/api/projects'
import { CATEGORIES, categoryOf, type Box, type ColourBy, type RoadsData } from '@/api/roads-view'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea, showArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const SOURCE = 'roads-view'
const BOX_SOURCE = 'roads-box'
const OURS = ['roads-view-lines', 'roads-view-names', 'roads-box-fill', 'roads-box-line', 'survey-area-fill', 'survey-area-line']
const EMPTY = { type: 'FeatureCollection' as const, features: [] }

const boxShape = (box: Box | null) =>
  box
    ? {
        type: 'Feature' as const,
        properties: {},
        geometry: { type: 'Polygon' as const, coordinates: [[[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]], [box[0], box[1]]]] },
      }
    : EMPTY

interface Props {
  area: AreaGeometry
  data: RoadsData | undefined
  colourBy: ColourBy
  roadsOnly: boolean
  box: Box | null
  onBox: (box: Box | null) => void
  onSelect: (sectionId: string) => void
  className?: string
}

/** Item 11: roads only (the base map can be hidden), with names, coloured by the chosen measure. */
export function RoadsMap({ area, data, colourBy, roadsOnly, box, onBox, onSelect, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const [picking, setPicking] = useState(false)
  const [corner, setCorner] = useState<[number, number] | null>(null)
  const handlers = useRef({ onSelect, onBox })
  const pickingRef = useRef(false)
  const fitted = useRef(false)

  useEffect(() => {
    handlers.current = { onSelect, onBox }
  }, [onSelect, onBox])

  useEffect(() => {
    pickingRef.current = picking
  }, [picking])

  useEffect(() => {
    if (!map) return
    showArea(map, area)
    if (!fitted.current) {
      fitToArea(map, area)
      fitted.current = true
    }
    if (!map.getSource(SOURCE)) {
      map.addSource(SOURCE, { type: 'geojson', data: EMPTY })
      map.addSource(BOX_SOURCE, { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'roads-box-fill', type: 'fill', source: BOX_SOURCE, paint: { 'fill-color': '#1b2633', 'fill-opacity': 0.06 } })
      map.addLayer({ id: 'roads-box-line', type: 'line', source: BOX_SOURCE, paint: { 'line-color': '#1b2633', 'line-width': 2 } })
      map.addLayer({
        id: 'roads-view-lines',
        type: 'line',
        source: SOURCE,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['get', 'colour'] as unknown as ExpressionSpecification, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 2, 16, 6] },
      })
      map.addLayer({
        id: 'roads-view-names',
        type: 'symbol',
        source: SOURCE,
        minzoom: 14,
        layout: { 'symbol-placement': 'line', 'text-field': ['coalesce', ['get', 'name'], ''], 'text-font': ['Noto Sans Regular'], 'text-size': 11 },
        paint: { 'text-color': '#1b2633', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
      })
    }
    const click = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.section_id
      if (typeof id === 'string' && !pickingRef.current) handlers.current.onSelect(id)
    }
    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const normal = () => (map.getCanvas().style.cursor = '')
    map.on('click', 'roads-view-lines', click)
    map.on('mouseenter', 'roads-view-lines', pointer)
    map.on('mouseleave', 'roads-view-lines', normal)
    return () => {
      map.off('click', 'roads-view-lines', click)
      map.off('mouseenter', 'roads-view-lines', pointer)
      map.off('mouseleave', 'roads-view-lines', normal)
    }
  }, [map, area])

  // Colour each road by the chosen measure.
  useEffect(() => {
    if (!map) return
    const colours = Object.fromEntries(CATEGORIES[colourBy].map((c) => [c.key, c.colour]))
    const features = (data?.features ?? []).map((f) => ({ ...f, properties: { section_id: f.properties.section_id, name: f.properties.name, colour: colours[categoryOf(f.properties, colourBy)] } }))
    map.getSource<GeoJSONSource>(SOURCE)?.setData({ type: 'FeatureCollection', features })
  }, [map, data, colourBy])

  // Roads only: hide every layer of the base map except its background.
  useEffect(() => {
    if (!map) return
    for (const layer of map.getStyle().layers ?? []) {
      if (OURS.includes(layer.id) || layer.type === 'background') continue
      map.setLayoutProperty(layer.id, 'visibility', roadsOnly ? 'none' : 'visible')
    }
  }, [map, roadsOnly])

  useEffect(() => {
    map?.getSource<GeoJSONSource>(BOX_SOURCE)?.setData(boxShape(box))
  }, [map, box])

  // Choosing an area: click one corner, then the opposite corner.
  useEffect(() => {
    if (!map || !picking) return
    map.getCanvas().style.cursor = 'crosshair'
    const pick = (event: MapMouseEvent) => {
      const point: [number, number] = [event.lngLat.lng, event.lngLat.lat]
      if (!corner) {
        setCorner(point)
        return
      }
      const chosen: Box = [Math.min(corner[0], point[0]), Math.min(corner[1], point[1]), Math.max(corner[0], point[0]), Math.max(corner[1], point[1])]
      setCorner(null)
      setPicking(false)
      handlers.current.onBox(chosen)
    }
    map.on('click', pick)
    return () => {
      map.off('click', pick)
      map.getCanvas().style.cursor = ''
    }
  }, [map, picking, corner])

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-asphalt-100', className)}>
      <div ref={containerRef} role="region" aria-label="Map of roads" className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
      <div className="absolute top-2 left-2 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          aria-pressed={picking}
          onClick={() => {
            setCorner(null)
            setPicking((value) => !value)
          }}
        >
          {picking ? (corner ? 'Now click the opposite corner' : 'Click one corner of the area') : 'Choose an area'}
        </Button>
        {box && (
          <Button variant="secondary" onClick={() => handlers.current.onBox(null)}>
            Show the whole project
          </Button>
        )}
      </div>
    </div>
  )
}
