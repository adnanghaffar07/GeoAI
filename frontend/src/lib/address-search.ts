/**
 * Find a place by street, address, neighbourhood or city, and turn it into a survey area.
 *
 * Uses OpenStreetMap's free Nominatim search by default. Its usage policy allows light use
 * (at most one search per second, no search-as-you-type), so the app searches only when the
 * person presses "Search". Only the typed words are sent, never photos or project data.
 * A different or self-hosted service with the same answer format can be set with
 * VITE_GEOCODER_URL in frontend/.env.
 */

import type { AreaGeometry } from '@/api/projects'

export const GEOCODER_URL: string = import.meta.env.VITE_GEOCODER_URL || 'https://nominatim.openstreetmap.org/search'

/** Smallest area made around a single address or a very short street (in degrees, about 150 m). */
const MIN_HALF_SIZE = 0.0014

export interface PlaceResult {
  id: string
  /** Full name, e.g. "Main Street, Naperville, DuPage County, Illinois, United States". */
  label: string
  /** True when the place's real outline is used; false when it is a rectangle around it. */
  isOutline: boolean
  area: AreaGeometry
}

interface NominatimPlace {
  place_id: number
  display_name: string
  boundingbox: [string, string, string, string] // south, north, west, east
  geojson?: { type: string; coordinates: unknown }
}

export class PlaceSearchError extends Error {}

function rectangle(south: number, north: number, west: number, east: number): AreaGeometry {
  const midLat = (south + north) / 2
  const midLon = (west + east) / 2
  const halfLat = Math.max((north - south) / 2, MIN_HALF_SIZE)
  const halfLon = Math.max((east - west) / 2, MIN_HALF_SIZE / Math.max(Math.cos((midLat * Math.PI) / 180), 0.2))
  const [s, n, w, e] = [midLat - halfLat, midLat + halfLat, midLon - halfLon, midLon + halfLon]
  return { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }
}

export function placeToArea(place: NominatimPlace): { area: AreaGeometry; isOutline: boolean } {
  const shape = place.geojson
  if (shape?.type === 'Polygon' || shape?.type === 'MultiPolygon') {
    return { area: shape as AreaGeometry, isOutline: true }
  }
  const [south, north, west, east] = place.boundingbox.map(Number) as [number, number, number, number]
  return { area: rectangle(south, north, west, east), isOutline: false }
}

/** Up to 5 matching places. Throws PlaceSearchError with a plain message when the search fails. */
export async function searchPlaces(query: string, signal?: AbortSignal): Promise<PlaceResult[]> {
  const params = new URLSearchParams({
    q: query,
    format: 'jsonv2',
    limit: '5',
    polygon_geojson: '1',
    polygon_threshold: '0.0001', // simpler outlines (fewer corners) that are easy to adjust
  })
  let response: Response
  try {
    response = await fetch(`${GEOCODER_URL}?${params.toString()}`, { signal, headers: { Accept: 'application/json' } })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new PlaceSearchError('The place search could not be reached. Check your internet connection, or draw the area by hand.')
  }
  if (response.status === 429) throw new PlaceSearchError('Too many searches. Wait a moment and try again.')
  if (!response.ok) throw new PlaceSearchError('The place search is not working right now. Draw the area by hand, or try again later.')
  const places = (await response.json()) as NominatimPlace[]
  return places
    .filter((place) => Array.isArray(place.boundingbox) && place.boundingbox.length === 4)
    .map((place) => ({ id: String(place.place_id), label: place.display_name, ...placeToArea(place) }))
}
