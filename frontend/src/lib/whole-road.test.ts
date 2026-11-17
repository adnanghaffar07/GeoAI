import { afterEach, describe, expect, it, vi } from 'vitest'

import { boxAround, boxTooBig, findRoadParts, lengthKm, nominatimParts, normalName, quarters, routeBetween, type RoadSearch } from '@/lib/whole-road'
import { json } from '@/test/fixtures'

const SEARCH: RoadSearch = { name: 'Washington Street', byRef: false, latitude: 41.78, longitude: -88.15, radiusM: 5000, extent: 'radius' }
const PIECE_1 = { type: 'LineString', coordinates: [[-88.15, 41.77], [-88.15, 41.775]] }
const PIECE_2 = { type: 'LineString', coordinates: [[-88.15, 41.775], [-88.15, 41.779]] }
const UNAVAILABLE = json({ error: { code: 'service_unavailable', message: 'The fast map search did not answer in time.', details: null, request_id: 'r1' } }, 503)
const NOT_FOUND = json({ error: { code: 'not_found', message: 'No road called “Washington Street” was found in this place.', details: null, request_id: 'r2' } }, 404)

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('road names', () => {
  it('treats short and long spellings and directions as one road', () => {
    expect(normalName('N. Washington St')).toBe('washington street')
    expect(normalName('North Washington Street')).toBe('washington street')
    expect(normalName('Washington Street')).toBe('washington street')
    expect(normalName('North Avenue')).toBe('north avenue') // a direction that is the name stays
    expect(normalName('IL 59')).toBe('il 59')
  })

  it('makes a box twice as wide as the radius and knows a box that is too big', () => {
    const [west, south, east, north] = boxAround(41.78, -88.15, 5000)
    expect(north - south).toBeCloseTo(0.0899, 3)
    expect(east - west).toBeGreaterThan(0.1) // longitude degrees are shorter at this latitude
    expect(boxTooBig([-88.2, 41.7, -88.1, 41.8])).toBe(false)
    expect(boxTooBig([-89, 41, -88, 42])).toBe(true)
  })

  it('measures a line in kilometres', () => {
    expect(lengthKm([PIECE_1.coordinates, PIECE_2.coordinates])).toBeCloseTo(1, 0)
  })
})

describe('nominatimParts (backup 2)', () => {
  const place = (id: number, name: string, geojson: unknown, extra: object = {}) => ({ place_id: id, osm_type: 'way', osm_id: id, name, display_name: `${name}, Naperville`, geojson, ...extra })

  it('asks for every part inside the box and keeps only the road with that name', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json([
        place(1, 'Washington Street', PIECE_1),
        place(2, 'Washington St', PIECE_2), // short spelling: the same road
        place(2, 'Washington Street', PIECE_2), // the same part twice counts once
        place(3, 'Main Street', PIECE_1), // another road
        place(4, 'Washington Street', { type: 'Point', coordinates: [-88.15, 41.77] }), // not a road
      ]),
    )

    const found = await nominatimParts({ ...SEARCH, extent: 'box', box: [-88.2, 41.7, -88.1, 41.8] })

    const url = new URL(String(fetchMock.mock.calls[0]?.[0]))
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      q: 'Washington Street',
      dedupe: '0',
      limit: '40',
      bounded: '1',
      polygon_geojson: '1',
      format: 'jsonv2',
      viewbox: '-88.2,41.8,-88.1,41.7',
    })
    expect(found).toMatchObject({ pieces: 2, source: 'nominatim', shape: { type: 'MultiLineString' } })
    expect(found.lengthKm).toBeCloseTo(1, 0)
    expect(JSON.stringify(fetchMock.mock.calls)).not.toMatch(/@/) // no e-mail address goes out
  })

  it('matches a route number on the road\'s ref', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json([place(1, 'Illinois Route 59', PIECE_1, { extratags: { ref: 'IL 59;US 30' } }), place(2, 'Other', PIECE_2, { extratags: { ref: 'IL 53' } })]),
    )

    const found = await nominatimParts({ ...SEARCH, name: 'IL 59', byRef: true })

    expect(found.pieces).toBe(1)
  })

  it('uses the town in the question, without a box, for "town limits"', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json([place(1, 'Washington Street', PIECE_1)]))

    await nominatimParts({ ...SEARCH, extent: 'town', town: 'Naperville' })

    const url = new URL(String(fetchMock.mock.calls[0]?.[0]))
    expect(url.searchParams.get('q')).toBe('Washington Street, Naperville')
    expect(url.searchParams.has('viewbox')).toBe(false)
  })

  it('says so when no part matches', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json([place(3, 'Main Street', PIECE_1)]))

    await expect(nominatimParts(SEARCH)).rejects.toThrow('No road called “Washington Street”')
  })
})

describe('nominatimParts: a full answer (40) may have left parts out', () => {
  const piece = (id: number) => ({
    place_id: id,
    osm_type: 'way',
    osm_id: id,
    name: 'Liberty Street',
    display_name: 'Liberty Street, Naperville',
    geojson: { type: 'LineString', coordinates: [[-88.15 + id * 1e-4, 41.77], [-88.15 + id * 1e-4, 41.771]] },
  })
  const many = (from: number, count: number) => Array.from({ length: count }, (_, index) => piece(from + index))
  const BOX = { ...SEARCH, name: 'Liberty Street', extent: 'box' as const, box: [-88.2, 41.7, -88.1, 41.8] as [number, number, number, number] }

  it('cuts the box into four equal tiles', () => {
    const tiles = quarters([-88.2, 41.7, -88.1, 41.8])
    expect(tiles).toHaveLength(4)
    expect(tiles[0]).toEqual([-88.2, 41.75, -88.15, 41.8])
    expect(tiles[3]).toEqual([-88.15, 41.7, -88.1, 41.75])
  })

  it('asks again tile by tile when the answer is full and joins the parts', async () => {
    vi.useFakeTimers()
    const answers = [many(1, 40), many(100, 3), many(200, 3), many(300, 3), many(1, 2)]
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(json(answers.shift() ?? [])))

    const pending = nominatimParts(BOX)
    await vi.advanceTimersByTimeAsync(5000)
    const found = await pending
    vi.useRealTimers()

    expect(fetchMock).toHaveBeenCalledTimes(5) // the whole box, then four tiles
    expect(found.pieces).toBe(11) // 3 + 3 + 3 + 2; the full first answer is replaced by the tiles
    expect(found.partial).toBe(false)
  })

  it('says so when a tile is still full', async () => {
    vi.useFakeTimers()
    const answers = [many(1, 40), many(100, 40), [], [], []]
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(json(answers.shift() ?? [])))

    const pending = nominatimParts(BOX)
    await vi.advanceTimersByTimeAsync(5000)
    const found = await pending
    vi.useRealTimers()

    expect(found.partial).toBe(true)
  })

  it('says so for town limits, where there is no box to cut', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(many(1, 40)))

    const found = await nominatimParts({ ...SEARCH, name: 'Liberty Street', extent: 'town', town: 'Naperville' })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(found.partial).toBe(true)
  })

  it('is not partial when the answer is small', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(many(1, 5)))

    expect((await nominatimParts(BOX)).partial).toBe(false)
  })
})

describe('findRoadParts: each source is tried when the one before fails', () => {
  const server = (source: string) => json({ shape: { type: 'MultiLineString', coordinates: [PIECE_1.coordinates] }, pieces: 1, length_km: 0.6, source })

  function mock(steps: { overpass: Response; nominatim: Response; database: Response }) {
    const order: string[] = []
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/v1/geo/whole-road')) {
        const sources = (JSON.parse(String(init?.body)) as { sources: string[] }).sources
        order.push(sources[0] ?? '')
        return Promise.resolve((sources[0] === 'overpass' ? steps.overpass : steps.database).clone())
      }
      order.push('nominatim')
      return Promise.resolve(steps.nominatim.clone())
    })
    return { order, fetchMock }
  }

  it('uses the fast map search first and stops there', async () => {
    const { order } = mock({ overpass: server('overpass'), nominatim: json([]), database: json({}) })

    const found = await findRoadParts(SEARCH)

    expect(found).toMatchObject({ source: 'overpass', pieces: 1, lengthKm: 0.6 })
    expect(order).toEqual(['overpass'])
  })

  it('goes on to the place search, then to our own database', async () => {
    const nominatimHit = json([{ place_id: 1, osm_type: 'way', osm_id: 1, name: 'Washington Street', display_name: 'Washington Street, Naperville', geojson: PIECE_1 }])
    const second = mock({ overpass: UNAVAILABLE, nominatim: nominatimHit, database: json({}) })
    expect((await findRoadParts(SEARCH)).source).toBe('nominatim')
    expect(second.order).toEqual(['overpass', 'nominatim'])
    vi.restoreAllMocks()

    const third = mock({ overpass: UNAVAILABLE, nominatim: json([]), database: server('database') })
    expect((await findRoadParts(SEARCH)).source).toBe('database')
    expect(third.order).toEqual(['overpass', 'nominatim', 'database'])
  })

  it('treats "nothing found" like a failure and goes on; the place search can also be down', async () => {
    mock({ overpass: NOT_FOUND, nominatim: new Response('busy', { status: 429 }), database: server('database') })

    expect((await findRoadParts(SEARCH)).source).toBe('database')
  })

  it('names every source it tried when all fail', async () => {
    mock({ overpass: UNAVAILABLE, nominatim: json([]), database: NOT_FOUND })

    const failed = findRoadParts(SEARCH)

    await expect(failed).rejects.toThrow(/OpenStreetMap fast search: The fast map search did not answer in time/)
    await expect(failed).rejects.toThrow(/OpenStreetMap place search \(backup\): No road called/)
    await expect(failed).rejects.toThrow(/our own road database \(backup\): No road called/)
    await expect(failed).rejects.toThrow(/Road between two points/)
  })
})

describe('routeBetween (Road between two points)', () => {
  const FROM: [number, number] = [-88.15, 41.77]
  const TO: [number, number] = [-88.14, 41.78]
  const route = (coordinates: number[][], distance = 1500) => json({ code: 'Ok', routes: [{ distance, geometry: { type: 'LineString', coordinates } }] })

  it('asks the free OSRM route finder and returns the streets between the two points', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(route([[-88.15, 41.77], [-88.145, 41.775], [-88.14, 41.78]]))

    const found = await routeBetween(FROM, TO)

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('https://router.project-osrm.org/route/v1/driving/-88.15,41.77;-88.14,41.78?overview=full&geometries=geojson')
    expect(found).toMatchObject({ source: 'osrm', lengthKm: 1.5, shape: { type: 'LineString' } })
    expect((found.shape.coordinates as number[][]).length).toBe(3)
  })

  it('keeps a very long route within the shape limit and keeps its last point', async () => {
    const long = Array.from({ length: 12_000 }, (_, i) => [-88.15 + i * 1e-6, 41.77])
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(route(long))

    const found = await routeBetween(FROM, TO)

    const points = found.shape.coordinates as number[][]
    expect(points.length).toBeLessThanOrEqual(5_001)
    expect(points[points.length - 1]).toEqual(long[long.length - 1])
  })

  it('explains in plain words when there is no route or the service is down', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ code: 'NoRoute', routes: [] }))
    await expect(routeBetween(FROM, TO)).rejects.toThrow('No street route was found')

    fetchMock.mockResolvedValue(new Response('error', { status: 500 }))
    await expect(routeBetween(FROM, TO)).rejects.toThrow('not working right now')

    fetchMock.mockRejectedValue(new TypeError('offline'))
    await expect(routeBetween(FROM, TO)).rejects.toThrow('could not be reached')

    await expect(routeBetween(FROM, FROM)).rejects.toThrow('two different points')
  })
})
