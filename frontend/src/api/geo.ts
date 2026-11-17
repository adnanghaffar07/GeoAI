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

/** Where a road's parts were found on the server: OpenStreetMap's map servers or our own road database. */
export type WholeRoadSource = 'overpass' | 'database'

export interface WholeRoad {
  shape: PlaceShape
  pieces: number
  length_km: number
  source: WholeRoadSource
}

export interface WholeRoadInput {
  name: string
  byRef: boolean
  latitude: number
  longitude: number
  /** Half the width of the box searched (the box is twice as wide). */
  radiusM: number
  osmWayId?: number
  /** Where to look: near the point (default), inside the map view (`box` = west, south, east, north) or inside the town limits. */
  extent?: 'radius' | 'box' | 'town'
  box?: [number, number, number, number]
  town?: string
  /** Sources to try, in this order (default: the map servers, then our own database). */
  sources?: WholeRoadSource[]
}

/** Every part of a named road in a chosen place (owner, 2026-11-16 and 2026-11-17). */
export function findWholeRoad(input: WholeRoadInput): Promise<WholeRoad> {
  return apiRequest('/v1/geo/whole-road', {
    method: 'POST',
    body: {
      name: input.name,
      by_ref: input.byRef,
      latitude: input.latitude,
      longitude: input.longitude,
      radius_m: input.radiusM,
      osm_way_id: input.osmWayId,
      extent: input.extent ?? 'radius',
      box: input.box,
      town: input.town,
      sources: input.sources,
    },
  })
}
