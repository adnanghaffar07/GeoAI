/**
 * The places that make up a survey area (owner, 2026-11-16): each searched road, searched area,
 * drawn shape or uploaded file stays a separate place while the area is edited, so any one of
 * them can be changed or removed. They are joined into one area for saving.
 */
import type { AreaGeometry } from '@/api/projects'
import { areaFromPolygons, polygonsOf } from '@/lib/geojson'

export interface Place {
  id: string
  label: string
  area: AreaGeometry
}

let counter = 0
export function newPlaceId(): string {
  counter += 1
  return `place-${Date.now().toString(36)}-${counter}`
}

/** A saved area opened for editing: one place per separate part. */
export function placesFromArea(area: AreaGeometry | null): Place[] {
  if (!area) return []
  const parts = polygonsOf(area)
  return parts.map((polygon, index) => ({
    id: newPlaceId(),
    label: parts.length === 1 ? 'Saved area' : `Saved area, part ${index + 1}`,
    area: areaFromPolygons([polygon]) as AreaGeometry,
  }))
}

/** A label not used yet, e.g. "Drawn area 2". */
export function nextLabel(places: Place[], base: string): string {
  let n = 1
  while (places.some((place) => place.label === `${base} ${n}`)) n += 1
  return `${base} ${n}`
}
