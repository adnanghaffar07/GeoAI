/**
 * Find a road, address, neighbourhood or city by name, or a location by its coordinates.
 *
 * Uses OpenStreetMap's free Nominatim search by default. Its usage policy allows light use
 * (at most one search per second, no search-as-you-type), so the app searches only when the
 * person presses "Search". Only the typed words or coordinates are sent, never photos or
 * project data. A different or self-hosted service with the same answer format can be set
 * with VITE_GEOCODER_URL in frontend/.env.
 *
 * The shape found is turned into a survey area by the server (`api/geo.ts`): a road becomes
 * a strip along it, an address a circle around it, an area keeps its outline.
 */

import type { PlaceShape } from '@/api/geo'

export const GEOCODER_URL: string = import.meta.env.VITE_GEOCODER_URL || 'https://nominatim.openstreetmap.org/search'
const REVERSE_URL = GEOCODER_URL.replace(/\/search$/, '/reverse')

export type PlaceKind = 'road' | 'area' | 'address'

export interface PlaceResult {
  id: string
  /** Full name, e.g. "Washington Street, Naperville, DuPage County, Illinois, United States". */
  label: string
  kind: PlaceKind
  shape: PlaceShape
}

interface NominatimPlace {
  place_id: number
  display_name: string
  boundingbox?: [string, string, string, string] // south, north, west, east
  geojson?: { type: string; coordinates: unknown }
  lat?: string
  lon?: string
}

export class PlaceSearchError extends Error {}

const KIND_OF: Record<string, PlaceKind> = {
  LineString: 'road',
  MultiLineString: 'road',
  Polygon: 'area',
  MultiPolygon: 'area',
  Point: 'address',
}

/** The place's own shape, or (if it has none) a rectangle around it. */
export function placeShape(place: NominatimPlace): { shape: PlaceShape; kind: PlaceKind } | null {
  const geo = place.geojson
  if (geo && KIND_OF[geo.type]) return { shape: geo as PlaceShape, kind: KIND_OF[geo.type]! }
  if (place.boundingbox?.length === 4) {
    const [s, n, w, e] = place.boundingbox.map(Number) as [number, number, number, number]
    return { shape: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, kind: 'area' }
  }
  if (place.lat && place.lon) return { shape: { type: 'Point', coordinates: [Number(place.lon), Number(place.lat)] }, kind: 'address' }
  return null
}

/** "41.7731, -88.1501" (latitude, longitude) → numbers, or null if it is not coordinates. */
export function parseCoordinates(text: string): { lat: number; lon: number } | null {
  const match = /^\s*(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/.exec(text)
  if (!match) return null
  const lat = Number(match[1])
  const lon = Number(match[2])
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  return { lat, lon }
}

async function getJson(url: string, signal?: AbortSignal): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new PlaceSearchError('The place search could not be reached. Check your internet connection, or draw the area by hand.')
  }
  if (response.status === 429) throw new PlaceSearchError('Too many searches. Wait a moment and try again.')
  if (!response.ok) throw new PlaceSearchError('The place search is not working right now. Draw the area by hand, or try again later.')
  return response.json()
}

function toResult(place: NominatimPlace): PlaceResult | null {
  const found = placeShape(place)
  return found ? { id: String(place.place_id), label: place.display_name, ...found } : null
}

/**
 * Up to 5 matching places for a name, or for coordinates the road nearest to that point
 * plus the point itself. Throws PlaceSearchError with a plain message when the search fails.
 */
export async function searchPlaces(query: string, signal?: AbortSignal): Promise<PlaceResult[]> {
  const point = parseCoordinates(query)
  if (point) {
    const params = new URLSearchParams({ lat: String(point.lat), lon: String(point.lon), format: 'jsonv2', zoom: '17', polygon_geojson: '1' })
    const nearest = (await getJson(`${REVERSE_URL}?${params.toString()}`, signal)) as NominatimPlace & { error?: string }
    const here: PlaceResult = {
      id: `point-${point.lat},${point.lon}`,
      label: `This location (${point.lat}, ${point.lon})`,
      kind: 'address',
      shape: { type: 'Point', coordinates: [point.lon, point.lat] },
    }
    const road = nearest && !nearest.error ? toResult(nearest) : null
    return road ? [road, here] : [here]
  }
  const params = new URLSearchParams({
    q: query,
    format: 'jsonv2',
    limit: '5',
    polygon_geojson: '1',
    polygon_threshold: '0.0001', // simpler outlines (fewer corners) that are easy to adjust
  })
  const places = (await getJson(`${GEOCODER_URL}?${params.toString()}`, signal)) as NominatimPlace[]
  return places.map(toResult).filter((place): place is PlaceResult => place !== null)
}
