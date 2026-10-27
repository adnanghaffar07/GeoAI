import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'

import type { AreaGeometry } from '@/api/projects'
import { boundsOf } from '@/lib/geojson'

const AREA_SOURCE = 'survey-area'

/** Draw (or update) the survey area outline on a map. */
export function showArea(map: MapLibreMap, area: AreaGeometry | null) {
  const data = area ? { type: 'Feature' as const, properties: {}, geometry: area } : { type: 'FeatureCollection' as const, features: [] }
  const source = map.getSource<GeoJSONSource>(AREA_SOURCE)
  if (source) {
    source.setData(data)
    return
  }
  map.addSource(AREA_SOURCE, { type: 'geojson', data })
  map.addLayer({ id: 'survey-area-fill', type: 'fill', source: AREA_SOURCE, paint: { 'fill-color': '#f2b705', 'fill-opacity': 0.14 } })
  map.addLayer({ id: 'survey-area-line', type: 'line', source: AREA_SOURCE, paint: { 'line-color': '#1b2633', 'line-width': 2.5, 'line-dasharray': [3, 1.5] } })
}

export function fitToArea(map: MapLibreMap, area: AreaGeometry) {
  map.fitBounds(boundsOf(area), { padding: 32, duration: 0, maxZoom: 17 })
}
