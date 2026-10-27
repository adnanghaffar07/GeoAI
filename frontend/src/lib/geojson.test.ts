import { describe, expect, it } from 'vitest'

import { AreaFileError, areaFromGeoJsonText, boundsOf } from '@/lib/geojson'

const SQUARE = [
  [
    [-122.43, 37.77],
    [-122.41, 37.77],
    [-122.41, 37.79],
    [-122.43, 37.79],
    [-122.43, 37.77],
  ],
]
const shifted = SQUARE.map((ring) => ring.map(([lon = 0, lat = 0]) => [lon + 1, lat]))

describe('areaFromGeoJsonText', () => {
  it('reads a Feature with a Polygon', () => {
    const text = JSON.stringify({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: SQUARE } })
    expect(areaFromGeoJsonText(text)).toEqual({ type: 'Polygon', coordinates: SQUARE })
  })

  it('joins several polygons from a FeatureCollection into one MultiPolygon', () => {
    const text = JSON.stringify({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: SQUARE } },
        { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [0, 0] } },
        { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: shifted } },
      ],
    })
    expect(areaFromGeoJsonText(text)).toEqual({ type: 'MultiPolygon', coordinates: [SQUARE, shifted] })
  })

  it.each([
    ['not json', 'could not be read as JSON'],
    [JSON.stringify({ type: 'Point', coordinates: [1, 2] }), 'No area found'],
    [JSON.stringify({ type: 'Polygon', coordinates: [[[0, 0], [1, 1], [0, 0]]] }), 'fewer than 3 corners'],
    [
      JSON.stringify({ type: 'Polygon', coordinates: [[[500000, 4100000], [500100, 4100000], [500100, 4100100], [500000, 4100000]]] }),
      'WGS 84',
    ],
  ])('explains what is wrong with a bad file (%#)', (text, message) => {
    expect(() => areaFromGeoJsonText(text)).toThrow(AreaFileError)
    expect(() => areaFromGeoJsonText(text)).toThrow(message)
  })
})

describe('boundsOf', () => {
  it('returns the box around every polygon', () => {
    expect(boundsOf({ type: 'MultiPolygon', coordinates: [SQUARE, shifted] })).toEqual([
      [-122.43, 37.77],
      [-121.41, 37.79],
    ])
  })
})
