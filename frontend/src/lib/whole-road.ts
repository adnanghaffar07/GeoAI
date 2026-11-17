/**
 * "Whole road: make it always work" (owner, 2026-11-17).
 *
 * OpenStreetMap keeps a road in many short parts, and its free map servers are often slow. So the
 * parts are looked for in a chain, each step tried only if the one before fails, and the screen
 * says which source was used:
 *   1. the server's fast OpenStreetMap search (tag first, inside a box, all servers at once)
 *   2. OpenStreetMap's Nominatim search from the browser, with `dedupe=0` so every part is returned
 *   3. our own road database (areas loaded for road-risk forecasting)
 * "Road between two points" (the OSRM route finder) is separate: `routeBetween` below.
 * Only the road name and map positions are sent, never photos, project data or contact details.
 */

import { findWholeRoad, type PlaceShape } from '@/api/geo'
import { GEOCODER_URL, getJson } from '@/lib/address-search'

export type RoadSource = 'overpass' | 'nominatim' | 'database' | 'osrm'

export const SOURCE_NAMES: Record<RoadSource, string> = {
  overpass: 'OpenStreetMap fast search',
  nominatim: 'OpenStreetMap place search (backup)',
  database: 'our own road database (backup)',
  osrm: 'OpenStreetMap route finder',
}

export type Box = [number, number, number, number] // west, south, east, north

export interface RoadSearch {
  name: string
  byRef: boolean
  /** The middle of the place to search. */
  latitude: number
  longitude: number
  /** Half the width of the box searched (for "near the point"). */
  radiusM: number
  osmWayId?: number
  extent: 'radius' | 'box' | 'town'
  box?: Box
  town?: string
}

export interface RoadFound {
  shape: PlaceShape
  pieces: number
  lengthKm: number
  source: RoadSource
  /** True when the source may have left parts out (a full answer from the backup place search). */
  partial?: boolean
}

/** A map view bigger than this (degrees) makes the map servers time out (the server refuses it too). */
export const MAX_BOX_DEGREES = 0.6

const METERS_PER_DEGREE = 111_320

export function boxAround(latitude: number, longitude: number, radiusM: number): Box {
  const dLat = radiusM / METERS_PER_DEGREE
  const dLon = radiusM / (METERS_PER_DEGREE * Math.max(Math.cos((latitude * Math.PI) / 180), 0.05))
  return [longitude - dLon, latitude - dLat, longitude + dLon, latitude + dLat]
}

export const boxTooBig = (box: Box) => box[2] - box[0] > MAX_BOX_DEGREES || box[3] - box[1] > MAX_BOX_DEGREES

const ABBREVIATIONS: Record<string, string> = {
  st: 'street', rd: 'road', ave: 'avenue', av: 'avenue', blvd: 'boulevard', dr: 'drive', ln: 'lane', ct: 'court',
  hwy: 'highway', pkwy: 'parkway', pl: 'place', cir: 'circle', trl: 'trail', n: 'north', s: 'south', e: 'east', w: 'west',
}
const DIRECTIONS = new Set(['north', 'south', 'east', 'west'])

/** "N. Washington St", "North Washington Street" and "Washington Street" are one road (same rule as the server). */
export function normalName(name: string): string {
  const words = (name.toLowerCase().match(/[a-z0-9]+/g) ?? []).map((word) => ABBREVIATIONS[word] ?? word)
  const rest = words.filter((word) => !DIRECTIONS.has(word))
  return (rest.length >= 2 ? rest : words).join(' ')
}

export function lengthKm(lines: number[][][]): number {
  let meters = 0
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const [lon1 = 0, lat1 = 0] = line[i - 1] ?? []
      const [lon2 = 0, lat2 = 0] = line[i] ?? []
      const dLat = ((lat2 - lat1) * Math.PI) / 180
      const dLon = ((lon2 - lon1) * Math.PI) / 180
      const h = Math.sin(dLat / 2) ** 2 + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
      meters += 2 * 6_371_000 * Math.asin(Math.sqrt(h))
    }
  }
  return Math.round(meters / 100) / 10
}

// --- step 2: Nominatim -------------------------------------------------------------------------

interface NominatimRoad {
  osm_type?: string
  osm_id?: number
  place_id: number
  name?: string
  display_name: string
  geojson?: { type: string; coordinates: unknown }
  extratags?: Record<string, string>
}

/** Nominatim returns at most this many results per search. A full answer may have left parts out. */
export const NOMINATIM_LIMIT = 40
/** Nominatim's usage rule: at most one request a second. */
const NOMINATIM_PAUSE_MS = 1100

const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** The box cut into four equal tiles (west, south, east, north each). */
export function quarters(box: Box): Box[] {
  const [west, south, east, north] = box
  const midLon = (west + east) / 2
  const midLat = (south + north) / 2
  return [
    [west, midLat, midLon, north],
    [midLon, midLat, east, north],
    [west, south, midLon, midLat],
    [midLon, south, east, midLat],
  ]
}

/** One Nominatim search (optionally inside a box). Returns the raw places. */
async function askNominatim(search: RoadSearch, box: Box | null, signal?: AbortSignal): Promise<NominatimRoad[]> {
  const params = new URLSearchParams({
    q: search.extent === 'town' && search.town ? `${search.name}, ${search.town}` : search.name,
    format: 'jsonv2',
    limit: String(NOMINATIM_LIMIT),
    dedupe: '0',
    polygon_geojson: '1',
    extratags: '1',
  })
  if (box) {
    // Nominatim's viewbox: west, north, east, south.
    params.set('viewbox', [box[0], box[3], box[2], box[1]].join(','))
    params.set('bounded', '1')
  }
  return (await getJson(`${GEOCODER_URL}?${params.toString()}`, signal)) as NominatimRoad[]
}

/**
 * Every part of the road that OpenStreetMap's place search returns inside the box. `dedupe=0` makes
 * it return all parts instead of merging look-alikes. At most 40 come back per search, so when an
 * answer is full the box is cut into four tiles and each is asked in turn (one request a second).
 * If a tile is still full, or the town limits are used (no box to cut), `partial` is set.
 */
export async function nominatimParts(search: RoadSearch, signal?: AbortSignal): Promise<RoadFound> {
  const box = search.extent === 'town' ? null : (search.box ?? boxAround(search.latitude, search.longitude, search.radiusM))
  const first = await askNominatim(search, box, signal)
  let places = first
  let partial = first.length >= NOMINATIM_LIMIT
  if (partial && box) {
    partial = false
    places = []
    const tiles = quarters(box)
    for (const [index, tile] of tiles.entries()) {
      if (index > 0) await pause(NOMINATIM_PAUSE_MS)
      const answer = await askNominatim(search, tile, signal)
      if (answer.length >= NOMINATIM_LIMIT) partial = true
      places.push(...answer)
    }
  }
  const wanted = new Set([normalName(search.name)])
  const seen = new Set<string>()
  const lines: number[][][] = []
  for (const place of places) {
    const geometry = place.geojson
    if (geometry?.type !== 'LineString' && geometry?.type !== 'MultiLineString') continue
    const own = normalName(place.name ?? place.display_name.split(',')[0] ?? '')
    const sameName = own !== '' && wanted.has(own)
    const sameRef = (place.extratags?.ref ?? '').split(';').some((ref) => wanted.has(normalName(ref)))
    if (!(search.byRef ? sameRef : sameName)) continue
    const id = `${place.osm_type ?? ''}${place.osm_id ?? place.place_id}`
    if (seen.has(id)) continue
    seen.add(id)
    const parts = (geometry.type === 'LineString' ? [geometry.coordinates] : geometry.coordinates) as number[][][]
    lines.push(...parts.filter((part) => part.length >= 2))
  }
  if (lines.length === 0) throw new Error(`No road called “${search.name}” was returned.`)
  return { shape: { type: 'MultiLineString', coordinates: lines }, pieces: lines.length, lengthKm: lengthKm(lines), source: 'nominatim', partial }
}

// --- the chain ---------------------------------------------------------------------------------

export class RoadPartsError extends Error {}

const reason = (cause: unknown) => (cause instanceof Error ? cause.message : 'it did not answer')

/** Every part of the road: step 1, then 2, then 3. Throws one plain message naming what was tried. */
export async function findRoadParts(search: RoadSearch): Promise<RoadFound> {
  const server = (sources: ('overpass' | 'database')[]) => async (): Promise<RoadFound> => {
    const road = await findWholeRoad({ ...search, sources })
    return { shape: road.shape, pieces: road.pieces, lengthKm: road.length_km, source: road.source }
  }
  const steps: [RoadSource, () => Promise<RoadFound>][] = [
    ['overpass', server(['overpass'])],
    ['nominatim', () => nominatimParts(search)],
    ['database', server(['database'])],
  ]
  const tried: string[] = []
  for (const [source, run] of steps) {
    try {
      return await run()
    } catch (cause) {
      tried.push(`${SOURCE_NAMES[source]}: ${reason(cause)}`)
    }
  }
  throw new RoadPartsError(
    `The whole road “${search.name}” could not be found. Tried ${tried.join(' | ')} — Try again in a minute, use “Road between two points”, or add the parts one by one.`,
  )
}

// --- "Road between two points" (OSRM) -----------------------------------------------------------

export const ROUTER_URL: string = import.meta.env.VITE_ROUTER_URL || 'https://router.project-osrm.org/route/v1/driving'
const MAX_ROUTE_POINTS = 5_000

export interface RouteFound {
  shape: PlaceShape
  lengthKm: number
  source: 'osrm'
}

/** The driving route between two clicked points ([longitude, latitude] each), as a line along the streets. */
export async function routeBetween(from: [number, number], to: [number, number], signal?: AbortSignal): Promise<RouteFound> {
  if (Math.abs(from[0] - to[0]) < 1e-5 && Math.abs(from[1] - to[1]) < 1e-5) throw new RoadPartsError('Click two different points.')
  const url = `${ROUTER_URL}/${from[0]},${from[1]};${to[0]},${to[1]}?overview=full&geometries=geojson`
  let response: Response
  try {
    response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new RoadPartsError('The route finder could not be reached. Check your internet connection, or draw the road by hand.')
  }
  if (!response.ok) throw new RoadPartsError('The route finder is not working right now. Try again later, or draw the road by hand.')
  const data = (await response.json()) as { code?: string; routes?: { distance?: number; geometry?: { coordinates?: number[][] } }[] }
  const route = data.code === 'Ok' ? data.routes?.[0] : undefined
  const line = route?.geometry?.coordinates
  if (!line || line.length < 2) throw new RoadPartsError('No street route was found between these two points. Click points on streets, or draw the road by hand.')
  const step = Math.ceil(line.length / MAX_ROUTE_POINTS)
  const thin = step > 1 ? [...line.filter((_, index) => index % step === 0), line[line.length - 1] as number[]] : line
  return { shape: { type: 'LineString', coordinates: thin }, lengthKm: route?.distance ? Math.round(route.distance / 100) / 10 : lengthKm([thin]), source: 'osrm' }
}
