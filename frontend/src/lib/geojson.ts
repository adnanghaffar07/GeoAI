/**
 * Turning GeoJSON into a survey area, and small geometry helpers for maps.
 *
 * The server checks the shape properly (PostGIS); this only gives quick, plain feedback.
 */

import type { AreaGeometry } from '@/api/projects'

type Ring = number[][]
type PolygonCoords = Ring[]

export class AreaFileError extends Error {}

function polygonsIn(value: unknown): PolygonCoords[] {
  if (typeof value !== 'object' || value === null) return []
  const item = value as { type?: unknown; coordinates?: unknown; geometry?: unknown; features?: unknown; geometries?: unknown }
  switch (item.type) {
    case 'Polygon':
      return [item.coordinates as PolygonCoords]
    case 'MultiPolygon':
      return item.coordinates as PolygonCoords[]
    case 'Feature':
      return polygonsIn(item.geometry)
    case 'FeatureCollection':
      return Array.isArray(item.features) ? item.features.flatMap(polygonsIn) : []
    case 'GeometryCollection':
      return Array.isArray(item.geometries) ? item.geometries.flatMap(polygonsIn) : []
    default:
      return []
  }
}

function isValidPoint(point: unknown): boolean {
  if (!Array.isArray(point) || point.length < 2) return false
  const [lon, lat] = point as unknown[]
  return typeof lon === 'number' && typeof lat === 'number' && Math.abs(lon) <= 180 && Math.abs(lat) <= 90
}

/** Read a GeoJSON file's text. All polygons in it become one survey area. */
export function areaFromGeoJsonText(text: string): AreaGeometry {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new AreaFileError('This file is not valid GeoJSON (it could not be read as JSON).')
  }
  const polygons = polygonsIn(parsed)
  if (polygons.length === 0) {
    throw new AreaFileError('No area found in the file. It needs at least one Polygon or MultiPolygon.')
  }
  for (const polygon of polygons) {
    if (!Array.isArray(polygon) || polygon.length === 0) throw new AreaFileError('An area in the file has no points.')
    for (const ring of polygon) {
      if (!Array.isArray(ring) || ring.length < 4) {
        throw new AreaFileError('An area in the file has fewer than 3 corners.')
      }
      if (!ring.every(isValidPoint)) {
        throw new AreaFileError(
          'The file has points that are not longitude/latitude. Export it in WGS 84 (EPSG:4326) and try again.',
        )
      }
    }
  }
  return polygons.length === 1
    ? { type: 'Polygon', coordinates: polygons[0] as number[][][] }
    : { type: 'MultiPolygon', coordinates: polygons as number[][][][] }
}

/** The polygons of an area, whichever type it is. */
export function polygonsOf(area: AreaGeometry): PolygonCoords[] {
  return area.type === 'Polygon' ? [area.coordinates as PolygonCoords] : (area.coordinates as PolygonCoords[])
}

/** Combine drawn polygons into one area (null when nothing is drawn). */
export function areaFromPolygons(polygons: PolygonCoords[]): AreaGeometry | null {
  if (polygons.length === 0) return null
  return polygons.length === 1
    ? { type: 'Polygon', coordinates: polygons[0] as number[][][] }
    : { type: 'MultiPolygon', coordinates: polygons as number[][][][] }
}

/** [[west, south], [east, north]] around the area, for fitting a map to it. */
export function boundsOf(area: AreaGeometry): [[number, number], [number, number]] {
  let west = 180
  let south = 90
  let east = -180
  let north = -90
  for (const polygon of polygonsOf(area)) {
    for (const ring of polygon) {
      for (const [lon = 0, lat = 0] of ring) {
        west = Math.min(west, lon)
        east = Math.max(east, lon)
        south = Math.min(south, lat)
        north = Math.max(north, lat)
      }
    }
  }
  return [
    [west, south],
    [east, north],
  ]
}
