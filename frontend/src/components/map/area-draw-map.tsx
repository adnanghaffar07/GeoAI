import { Marker, type Map as MapLibreMap, type MapMouseEvent } from 'maplibre-gl'
import { useEffect, useRef, useState, type RefObject } from 'react'
import { TerraDraw, TerraDrawLineStringMode, TerraDrawPolygonMode, TerraDrawSelectMode, type GeoJSONStoreFeatures } from 'terra-draw'
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter'

import type { PlaceShape } from '@/api/geo'
import type { AreaGeometry } from '@/api/projects'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { Button } from '@/components/ui/button'
import { areaFromPolygons, boundsOf, polygonsOf } from '@/lib/geojson'
import type { Place } from '@/lib/places'

export type DrawMode = 'polygon' | 'linestring' | 'select' | 'route'

/** West, south, east, north of the part of the map on screen. */
export type MapView = [number, number, number, number]

const round = (value: number) => Math.round(value * 1e7) / 1e7 // ~1 cm; Terra Draw limits precision

function toFeatures(place: Place): GeoJSONStoreFeatures[] {
  return polygonsOf(place.area).map((polygon) => ({
    type: 'Feature',
    properties: { mode: 'polygon', placeId: place.id },
    // Outer edge only: the drawing tool cannot edit shapes with holes (a road with two carriageways,
    // a city with pockets), so holes are filled; the area then always shows and can be edited.
    geometry: { type: 'Polygon', coordinates: polygon.slice(0, 1).map((ring) => ring.map(([lon = 0, lat = 0]) => [round(lon), round(lat)])) },
  }))
}

/** The shape of one place as it is now on the map (null when none of it is left). */
function placeArea(draw: TerraDraw, placeId: string): AreaGeometry | null {
  const polygons = draw
    .getSnapshot()
    .filter((feature) => feature.properties.placeId === placeId && feature.geometry.type === 'Polygon')
    .map((feature) => feature.geometry.coordinates as number[][][])
  return areaFromPolygons(polygons)
}

/** Top-right corner of a shape, where its Edit and Remove icons sit. */
const cornerOf = (area: AreaGeometry): [number, number] => {
  const [, [east, north]] = boundsOf(area)
  return [east, north]
}

const PENCIL =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/><path d="m15 5 4 4"/></svg>'
const TRASH =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>'

/** The two round icons on a place's corner (map markers are plain page elements, not React). */
function cornerIcons(label: string, onEdit: () => void, onRemove: () => void): HTMLElement {
  const box = document.createElement('div')
  box.className = 'flex gap-1 rounded-full bg-white/95 p-1 shadow-md ring-1 ring-asphalt-200'
  const make = (html: string, name: string, colours: string, action: () => void) => {
    const button = document.createElement('button')
    button.type = 'button'
    button.innerHTML = html
    button.title = name
    button.setAttribute('aria-label', name)
    button.className = `grid size-8 place-items-center rounded-full ${colours} focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-lane-600`
    button.addEventListener('click', (event) => {
      event.stopPropagation()
      action()
    })
    // Keep the drawing tool from treating a click on the icon as a click on the map.
    for (const type of ['mousedown', 'pointerdown', 'touchstart', 'dblclick'] as const) button.addEventListener(type, (event) => event.stopPropagation())
    box.append(button)
  }
  make(PENCIL, `Edit ${label}`, 'bg-asphalt-900 text-white hover:bg-asphalt-700', onEdit)
  make(TRASH, `Remove ${label}`, 'bg-red-600 text-white hover:bg-red-700', onRemove)
  return box
}

interface AreaDrawMapProps {
  /** The places when the map opens. To show a different set later, remount with a new `key`. */
  places: Place[]
  disabled?: boolean
  /** Width of the strip a drawn road becomes (meters), shown in the hint. */
  roadWidthM?: number
  /** Drawing tool to start with (kept when the map reopens after adding a shape). */
  initialMode?: DrawMode
  onModeChange?: (mode: DrawMode) => void
  /** The place being edited: its shape is selected and the map moves to it. */
  editingId?: string | null
  onEdit: (placeId: string | null) => void
  /** A new area drawn on the map. */
  onAreaDrawn: (area: AreaGeometry) => void
  /** A road drawn on the map (the server turns it into a strip). When absent, roads cannot be drawn. */
  onRoadDrawn?: (shape: PlaceShape) => void
  /** "Road between two points": the start and end clicked ([longitude, latitude] each). When absent, the tool is hidden. */
  onRoute?: (from: [number, number], to: [number, number]) => void
  /** Filled with a function that tells which part of the map is on screen (for "Find all parts by name"). */
  viewRef?: RefObject<(() => MapView | null) | null>
  /** A place's shape was moved or its corners changed. */
  onPlaceChanged: (placeId: string, area: AreaGeometry) => void
  /** The Remove icon was pressed (the page asks to confirm). */
  onRemoveRequest: (placeId: string) => void
  /** A place's shape was deleted on the map (Delete key). */
  onPlaceDeleted: (placeId: string) => void
  onClearAll: () => void
}

/**
 * Draw and adjust the survey area. Every place (searched road or area, drawn shape, uploaded
 * file) is a separate shape with Edit and Remove icons on its top-right corner.
 */
export function AreaDrawMap({
  places,
  disabled = false,
  roadWidthM = 30,
  initialMode,
  onModeChange,
  editingId = null,
  onEdit,
  onAreaDrawn,
  onRoadDrawn,
  onRoute,
  viewRef,
  onPlaceChanged,
  onRemoveRequest,
  onPlaceDeleted,
  onClearAll,
}: AreaDrawMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const drawRef = useRef<TerraDraw | null>(null)
  const callbacks = useRef({ onEdit, onAreaDrawn, onRoadDrawn, onRoute, onPlaceChanged, onRemoveRequest, onPlaceDeleted })
  const startMode: DrawMode = initialMode ?? (places.length > 0 ? 'select' : 'polygon')
  const [mode, setMode] = useState<DrawMode>(startMode)
  const [loadProblem, setLoadProblem] = useState(false)

  useEffect(() => {
    callbacks.current = { onEdit, onAreaDrawn, onRoadDrawn, onRoute, onPlaceChanged, onRemoveRequest, onPlaceDeleted }
  }, [onEdit, onAreaDrawn, onRoadDrawn, onRoute, onPlaceChanged, onRemoveRequest, onPlaceDeleted])

  // Tell the page which part of the map is on screen.
  useEffect(() => {
    if (!map || !viewRef) return
    viewRef.current = () => {
      const bounds = map.getBounds()
      return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
    }
    return () => {
      viewRef.current = null
    }
  }, [map, viewRef])

  useEffect(() => {
    if (!map) return
    const draw = new TerraDraw({
      adapter: new TerraDrawMapLibreGLAdapter({ map }),
      modes: [
        new TerraDrawPolygonMode({ styles: { fillColor: '#f2b705', fillOpacity: 0.2, outlineColor: '#1b2633', outlineWidth: 2.5 } }),
        new TerraDrawLineStringMode({ styles: { lineStringColor: '#c99600', lineStringWidth: 5 } }),
        new TerraDrawSelectMode({
          flags: {
            polygon: {
              feature: {
                draggable: true,
                coordinates: { midpoints: true, draggable: true, deletable: true },
              },
            },
          },
        }),
      ],
    })
    draw.start()
    const placeOf = new Map<string | number, string>() // shape id → place id
    const markers = new Map<string, Marker>()
    let quiet = false // our own removals are not reported as the person's
    const valid = places.flatMap((place) => {
      const results = draw.addFeatures(toFeatures(place))
      for (const result of results) if (result.valid && result.id != null) placeOf.set(result.id, place.id)
      if (results.some((result) => !result.valid)) setLoadProblem(true)
      if (!results.some((result) => result.valid)) return []
      return [place]
    })
    if (!disabled) {
      for (const place of valid) {
        const element = cornerIcons(place.label, () => callbacks.current.onEdit(place.id), () => callbacks.current.onRemoveRequest(place.id))
        markers.set(place.id, new Marker({ element, anchor: 'bottom-left', offset: [4, -4] }).setLngLat(cornerOf(place.area)).addTo(map))
      }
    }
    const all = areaFromPolygons(places.flatMap((place) => polygonsOf(place.area)))
    if (all) fitToArea(map, all)

    draw.on('finish', (id, context) => {
      const feature = draw.getSnapshotFeature(id)
      if (!feature) return
      if (context.mode === 'select') {
        const placeId = placeOf.get(id)
        const area = placeId ? placeArea(draw, placeId) : null
        if (placeId && area) {
          markers.get(placeId)?.setLngLat(cornerOf(area))
          callbacks.current.onPlaceChanged(placeId, area)
        }
        return
      }
      quiet = true
      draw.removeFeatures([id]) // shown again, as its own place, when the map reopens
      quiet = false
      if (feature.geometry.type === 'LineString') {
        callbacks.current.onRoadDrawn?.({ type: 'LineString', coordinates: feature.geometry.coordinates })
      } else if (feature.geometry.type === 'Polygon') {
        callbacks.current.onAreaDrawn({ type: 'Polygon', coordinates: feature.geometry.coordinates as number[][][] })
      }
    })
    draw.on('change', (ids, type) => {
      if (type !== 'delete' || quiet) return
      for (const id of ids) {
        const placeId = placeOf.get(id)
        if (!placeId) continue
        placeOf.delete(id)
        const rest = placeArea(draw, placeId)
        if (rest) callbacks.current.onPlaceChanged(placeId, rest)
        else {
          markers.get(placeId)?.remove()
          callbacks.current.onPlaceDeleted(placeId)
        }
      }
    })
    draw.setMode(disabled || startMode === 'route' ? 'static' : startMode)
    drawRef.current = draw
    return () => {
      drawRef.current = null
      for (const marker of markers.values()) marker.remove()
      // When the page closes, the map can be removed before this runs; then the drawing
      // layers are already gone with it and there is nothing left to stop.
      if (map.getStyle()) draw.stop()
    }
    // places is only read when the map opens (see prop docs).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, disabled])

  // Edit: select the place's shape so it can be dragged or reshaped, and bring it into view.
  useEffect(() => {
    const draw = drawRef.current
    if (!draw || !map || !editingId || disabled) return
    const shapes = draw.getSnapshot().filter((feature) => feature.properties.placeId === editingId)
    const first = shapes[0]
    if (!first) return
    draw.setMode('select')
    setMode('select')
    draw.selectFeature(first.id as string)
    const area = placeArea(draw, editingId)
    if (area) fitView(map, area)
  }, [editingId, map, disabled])

  // Road between two points: the first click is the start (A), the second the end (B).
  useEffect(() => {
    if (!map || disabled || mode !== 'route') return
    const pins: Marker[] = []
    let start: [number, number] | null = null
    const pin = (letter: string, at: [number, number]) => {
      const element = document.createElement('div')
      element.textContent = letter
      element.className = 'grid size-7 place-items-center rounded-full bg-asphalt-900 text-sm font-bold text-white shadow-md ring-2 ring-white'
      pins.push(new Marker({ element }).setLngLat(at).addTo(map))
    }
    const click = (event: MapMouseEvent) => {
      const point: [number, number] = [event.lngLat.lng, event.lngLat.lat]
      if (!start) {
        start = point
        pin('A', point)
        return
      }
      const from = start
      start = null
      callbacks.current.onRoute?.(from, point)
      setMode('select') // the route is added once found; the map reopens with it
      onModeChange?.('select')
    }
    map.on('click', click)
    const canvas = map.getCanvas()
    canvas.style.cursor = 'crosshair'
    return () => {
      map.off('click', click)
      canvas.style.cursor = ''
      for (const marker of pins) marker.remove()
    }
  }, [map, disabled, mode, onModeChange])

  const choose = (next: DrawMode) => {
    drawRef.current?.setMode(next === 'route' ? 'static' : next)
    setMode(next)
    onModeChange?.(next)
    if (next !== 'select') onEdit(null)
  }

  return (
    <div className="space-y-2">
      {!disabled && (
        <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Map drawing tools">
          <Button variant={mode === 'polygon' ? 'primary' : 'secondary'} onClick={() => choose('polygon')} aria-pressed={mode === 'polygon'}>
            Draw an area
          </Button>
          {onRoadDrawn && (
            <Button variant={mode === 'linestring' ? 'primary' : 'secondary'} onClick={() => choose('linestring')} aria-pressed={mode === 'linestring'}>
              Draw a road
            </Button>
          )}
          {onRoute && (
            <Button variant={mode === 'route' ? 'primary' : 'secondary'} onClick={() => choose('route')} aria-pressed={mode === 'route'}>
              Road between two points
            </Button>
          )}
          <Button variant={mode === 'select' ? 'primary' : 'secondary'} onClick={() => choose('select')} aria-pressed={mode === 'select'}>
            Move or adjust
          </Button>
          <Button variant="ghost" onClick={onClearAll}>
            Clear all
          </Button>
          <span className="text-xs text-asphalt-500">
            {mode === 'polygon'
              ? 'Click the map to add corners. Click the first corner again to finish.'
              : mode === 'linestring'
                ? `Click along the road, one click at each bend. Click the last point again (or press Enter) to finish. It is added as a ${roadWidthM} m wide strip.`
                : mode === 'route'
                  ? `Click the start point (A) on a street, then the end point (B). The streets between them are found and added as a ${roadWidthM} m wide strip.`
                  : 'Click a shape (or its pencil icon), then drag it or its corners. The bin icon removes that place only.'}
          </span>
        </div>
      )}
      <div className="relative h-96 overflow-hidden rounded-lg border border-asphalt-100">
        <div ref={containerRef} role="region" aria-label="Survey area map" className="size-full" />
        {baseMapFailed && <BaseMapNotice />}
      </div>
      {loadProblem && (
        <p className="text-sm text-amber-700">
          Part of this area could not be shown for editing. It is kept as it is unless you remove it or clear all.
        </p>
      )}
    </div>
  )
}

function fitView(map: MapLibreMap, area: AreaGeometry) {
  map.fitBounds(boundsOf(area), { padding: 48, duration: 400, maxZoom: 17 })
}
