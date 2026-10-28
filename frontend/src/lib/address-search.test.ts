import { describe, expect, it, vi } from 'vitest'

import { PlaceSearchError, parseCoordinates, placeShape, searchPlaces } from '@/lib/address-search'

const OUTLINE = {
  type: 'Polygon',
  coordinates: [[[-88.2, 41.7], [-88.1, 41.7], [-88.1, 41.8], [-88.2, 41.8], [-88.2, 41.7]]],
}
const ROAD = { type: 'LineString', coordinates: [[-88.15, 41.77], [-88.14, 41.78]] }

describe('placeShape', () => {
  it('knows roads, areas and single locations', () => {
    expect(placeShape({ place_id: 1, display_name: 'Main St', geojson: ROAD })).toEqual({ shape: ROAD, kind: 'road' })
    expect(placeShape({ place_id: 2, display_name: 'Naperville', geojson: OUTLINE })).toEqual({ shape: OUTLINE, kind: 'area' })
    expect(placeShape({ place_id: 3, display_name: '400 S Eagle St', geojson: { type: 'Point', coordinates: [-88.15, 41.77] } })?.kind).toBe('address')
  })

  it('uses a rectangle when the place has no shape', () => {
    const found = placeShape({ place_id: 4, display_name: 'X', boundingbox: ['41.77', '41.78', '-88.15', '-88.14'] })

    expect(found).toEqual({
      kind: 'area',
      shape: { type: 'Polygon', coordinates: [[[-88.15, 41.77], [-88.14, 41.77], [-88.14, 41.78], [-88.15, 41.78], [-88.15, 41.77]]] },
    })
  })
})

describe('parseCoordinates', () => {
  it('reads "latitude, longitude" and ignores everything else', () => {
    expect(parseCoordinates('41.7731, -88.1501')).toEqual({ lat: 41.7731, lon: -88.1501 })
    expect(parseCoordinates(' 41.7731 -88.1501 ')).toEqual({ lat: 41.7731, lon: -88.1501 })
    expect(parseCoordinates('Main Street 12')).toBeNull()
    expect(parseCoordinates('95, 10')).toBeNull()
  })
})

describe('searchPlaces', () => {
  it('searches OpenStreetMap by name for up to 5 places with their shapes', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify([{ place_id: 9, display_name: 'Washington Street, Naperville', geojson: ROAD }])))

    const places = await searchPlaces('Washington Street, Naperville')

    const url = new URL(String(fetchMock.mock.calls[0]![0]))
    expect(url.origin + url.pathname).toBe('https://nominatim.openstreetmap.org/search')
    expect(url.searchParams.get('q')).toBe('Washington Street, Naperville')
    expect(url.searchParams.get('polygon_geojson')).toBe('1')
    expect(places).toEqual([{ id: '9', label: 'Washington Street, Naperville', kind: 'road', shape: ROAD }])
  })

  it('for coordinates, offers the nearest road and the point itself', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ place_id: 5, display_name: 'Eagle Street, Naperville', geojson: ROAD })))

    const places = await searchPlaces('41.7731, -88.1501')

    const url = new URL(String(fetchMock.mock.calls[0]![0]))
    expect(url.pathname).toBe('/reverse')
    expect(url.searchParams.get('lat')).toBe('41.7731')
    expect(places.map((place) => place.kind)).toEqual(['road', 'address'])
    expect(places[1]!.shape).toEqual({ type: 'Point', coordinates: [-88.1501, 41.7731] })
  })

  it('explains when the search cannot be reached or is busy', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(searchPlaces('Main St')).rejects.toThrow(PlaceSearchError)

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 429 }))
    await expect(searchPlaces('Main St')).rejects.toThrow('Too many searches')
  })
})
