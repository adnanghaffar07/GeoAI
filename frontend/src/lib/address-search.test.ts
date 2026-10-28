import { describe, expect, it, vi } from 'vitest'

import { PlaceSearchError, placeToArea, searchPlaces } from '@/lib/address-search'

const OUTLINE = {
  type: 'Polygon',
  coordinates: [[[-88.2, 41.7], [-88.1, 41.7], [-88.1, 41.8], [-88.2, 41.8], [-88.2, 41.7]]],
}


/** Coordinates rounded to ~1 mm, so tiny floating-point differences do not matter. */
const rounded = (area: { type: string; coordinates: unknown }) => ({
  ...area,
  coordinates: JSON.parse(JSON.stringify(area.coordinates), (_key, value: unknown) => (typeof value === 'number' ? Math.round(value * 1e8) / 1e8 : value)),
})

describe('placeToArea', () => {
  it('uses the real outline of an area such as a city or neighborhood', () => {
    const result = placeToArea({ place_id: 1, display_name: 'Naperville', boundingbox: ['41.7', '41.8', '-88.2', '-88.1'], geojson: OUTLINE })

    expect(result).toEqual({ area: OUTLINE, isOutline: true })
  })

  it('makes a rectangle around a street', () => {
    const street = { type: 'LineString', coordinates: [[-88.15, 41.77], [-88.14, 41.78]] }
    const { area, isOutline } = placeToArea({ place_id: 2, display_name: 'Main St', boundingbox: ['41.77', '41.78', '-88.15', '-88.14'], geojson: street })

    expect(isOutline).toBe(false)
    expect(rounded(area)).toEqual({
      type: 'Polygon',
      coordinates: [[[-88.15, 41.77], [-88.14, 41.77], [-88.14, 41.78], [-88.15, 41.78], [-88.15, 41.77]]],
    })
  })

  it('makes a block-sized area around a single address instead of a dot', () => {
    const { area } = placeToArea({
      place_id: 3,
      display_name: '400 S Eagle St',
      boundingbox: ['41.7700', '41.7701', '-88.1500', '-88.1499'],
      geojson: { type: 'Point', coordinates: [-88.15, 41.77] },
    })

    const ring = (area.coordinates as number[][][])[0]!
    const lats = ring.map((point) => point[1]!)
    expect(Math.max(...lats) - Math.min(...lats)).toBeGreaterThan(0.002) // about 300 m tall
  })
})

describe('searchPlaces', () => {
  it('asks OpenStreetMap search for up to 5 places with outlines', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([{ place_id: 9, display_name: 'Naperville, Illinois', boundingbox: ['41.7', '41.8', '-88.2', '-88.1'], geojson: OUTLINE }])),
    )

    const places = await searchPlaces('Naperville, IL')

    const url = new URL(String(fetchMock.mock.calls[0]![0]))
    expect(url.origin + url.pathname).toBe('https://nominatim.openstreetmap.org/search')
    expect(url.searchParams.get('q')).toBe('Naperville, IL')
    expect(url.searchParams.get('limit')).toBe('5')
    expect(url.searchParams.get('polygon_geojson')).toBe('1')
    expect(places).toEqual([{ id: '9', label: 'Naperville, Illinois', isOutline: true, area: OUTLINE }])
  })

  it('explains when the search cannot be reached or is busy', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(searchPlaces('Main St')).rejects.toThrow(PlaceSearchError)

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 429 }))
    await expect(searchPlaces('Main St')).rejects.toThrow('Too many searches')
  })
})
