import { useEffect, useRef, useState } from 'react'
import { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode, type GeoJSONStoreFeatures } from 'terra-draw'
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter'

import type { AreaGeometry } from '@/api/projects'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'
import { Button } from '@/components/ui/button'
import { areaFromPolygons, polygonsOf } from '@/lib/geojson'

type Mode = 'polygon' | 'select'

const round = (value: number) => Math.round(value * 1e7) / 1e7 // ~1 cm; Terra Draw limits precision

function toFeatures(area: AreaGeometry): GeoJSONStoreFeatures[] {
  return polygonsOf(area).map((polygon) => ({
    type: 'Feature',
    properties: { mode: 'polygon' },
    geometry: { type: 'Polygon', coordinates: polygon.map((ring) => ring.map(([lon = 0, lat = 0]) => [round(lon), round(lat)])) },
  }))
}

function drawnArea(draw: TerraDraw): AreaGeometry | null {
  const polygons = draw
    .getSnapshot()
    .filter((feature) => feature.geometry.type === 'Polygon' && feature.properties.mode === 'polygon')
    .map((feature) => feature.geometry.coordinates as number[][][])
  return areaFromPolygons(polygons)
}

interface AreaDrawMapProps {
  /** The area when the map opens. To load a different area later, remount with a new `key`. */
  initialArea: AreaGeometry | null
  onChange: (area: AreaGeometry | null) => void
  disabled?: boolean
}

/**
 * Draw the survey area: click to add corners, click the first corner to finish.
 * Several shapes are allowed (they are saved together as one area).
 */
export function AreaDrawMap({ initialArea, onChange, disabled = false }: AreaDrawMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const drawRef = useRef<TerraDraw | null>(null)
  const onChangeRef = useRef(onChange)
  const [mode, setMode] = useState<Mode>(initialArea ? 'select' : 'polygon')
  const [loadProblem, setLoadProblem] = useState(false)

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    if (!map) return
    const draw = new TerraDraw({
      adapter: new TerraDrawMapLibreGLAdapter({ map }),
      modes: [
        new TerraDrawPolygonMode({ styles: { fillColor: '#f2b705', fillOpacity: 0.2, outlineColor: '#1b2633', outlineWidth: 2.5 } }),
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
    if (initialArea) {
      const results = draw.addFeatures(toFeatures(initialArea))
      setLoadProblem(results.some((result) => !result.valid))
      fitToArea(map, initialArea)
    }
    const report = () => onChangeRef.current(drawnArea(draw))
    draw.on('finish', report)
    draw.on('change', (_ids, type) => {
      if (type === 'delete') report()
    })
    draw.setMode(disabled ? 'static' : initialArea ? 'select' : 'polygon')
    drawRef.current = draw
    return () => {
      drawRef.current = null
      // When the page closes, the map can be removed before this runs; then the drawing
      // layers are already gone with it and there is nothing left to stop.
      if (map.getStyle()) draw.stop()
    }
    // initialArea is only read when the map opens (see prop docs).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, disabled])

  const choose = (next: Mode) => {
    drawRef.current?.setMode(next)
    setMode(next)
  }

  const clearAll = () => {
    drawRef.current?.clear()
    onChangeRef.current(null)
    choose('polygon')
  }

  return (
    <div className="space-y-2">
      {!disabled && (
        <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Map drawing tools">
          <Button variant={mode === 'polygon' ? 'primary' : 'secondary'} onClick={() => choose('polygon')} aria-pressed={mode === 'polygon'}>
            Draw a shape
          </Button>
          <Button variant={mode === 'select' ? 'primary' : 'secondary'} onClick={() => choose('select')} aria-pressed={mode === 'select'}>
            Move or adjust
          </Button>
          <Button variant="ghost" onClick={clearAll}>
            Clear all
          </Button>
          <span className="text-xs text-asphalt-500">
            {mode === 'polygon'
              ? 'Click the map to add corners. Click the first corner again to finish.'
              : 'Click a shape, then drag it or its corners. Press Delete to remove a selected shape.'}
          </span>
        </div>
      )}
      <div className="relative h-96 overflow-hidden rounded-lg border border-asphalt-100">
        <div ref={containerRef} role="region" aria-label="Survey area map" className="size-full" />
        {baseMapFailed && <BaseMapNotice />}
      </div>
      {loadProblem && (
        <p className="text-sm text-amber-700">
          Part of this area could not be shown for editing. It is kept as it is unless you draw or clear shapes.
        </p>
      )}
    </div>
  )
}
