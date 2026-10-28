/** Turn a searched place (road, address or area) into a survey area on the server (PostGIS). */

import type { AreaGeometry } from '@/api/projects'
import { apiRequest } from '@/lib/api-client'

export interface PlaceShape {
  type: 'Point' | 'LineString' | 'MultiLineString' | 'Polygon' | 'MultiPolygon'
  coordinates: unknown
}

export function areaFromPlace(
  shape: PlaceShape,
  options: { roadWidthM: number; addTo: AreaGeometry | null },
): Promise<{ area: AreaGeometry; area_square_meters: number }> {
  return apiRequest('/v1/geo/area-from-place', {
    method: 'POST',
    body: { shape, road_width_m: options.roadWidthM, add_to: options.addTo },
  })
}
