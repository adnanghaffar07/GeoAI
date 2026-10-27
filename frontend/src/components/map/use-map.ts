import 'maplibre-gl/dist/maplibre-gl.css'

import { Map as MapLibreMap, NavigationControl, setWorkerUrl, type StyleSpecification } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState, type RefObject } from 'react'

// MapLibre draws in a background "worker" file whose address it works out at run time,
// which the build tool cannot see. Pointing to it here makes the build include it.
setWorkerUrl(workerUrl)

/**
 * Base map style. OpenFreeMap is free and allows app use; check its terms before the pilot
 * (tech-stack.md). Change with VITE_MAP_STYLE_URL in frontend/.env, e.g. a self-hosted style.
 */
export const MAP_STYLE_URL: string = import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty'

/** Used when the base map cannot load (offline, blocked): survey shapes still show and work. */
const PLAIN_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#eef2f6' } }],
}

const WORLD_VIEW = { center: [0, 20] as [number, number], zoom: 1 }

/**
 * Create a MapLibre map in `containerRef`. Returns the map once it is ready to draw on
 * (style loaded), and whether the base map fell back to the plain background.
 */
export function useMap(containerRef: RefObject<HTMLDivElement | null>) {
  const [map, setMap] = useState<MapLibreMap | null>(null)
  const [baseMapFailed, setBaseMapFailed] = useState(false)
  const created = useRef(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container || created.current) return
    created.current = true
    const instance = new MapLibreMap({ container, style: MAP_STYLE_URL, ...WORLD_VIEW, attributionControl: { compact: true } })
    instance.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    let fellBack = false
    instance.on('error', () => {
      // A style that never loads would leave the map unusable; switch to the plain one once.
      if (!instance.isStyleLoaded() && !fellBack) {
        fellBack = true
        setBaseMapFailed(true)
        instance.setStyle(PLAIN_STYLE)
      }
    })
    // Keep the map filling its box when the page layout changes (not only on window resize).
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => instance.resize())
    resizeObserver?.observe(container)
    instance.once('load', () => setMap(instance))
    // setStyle after a failure fires 'style.load' (not 'load') in some cases.
    instance.once('style.load', () => setMap(instance))
    return () => {
      created.current = false
      resizeObserver?.disconnect()
      setMap(null)
      instance.remove()
    }
  }, [containerRef])

  return { map, baseMapFailed }
}
