import { useMutation } from '@tanstack/react-query'
import { Building2, Loader2, MapPin, Route, Search } from 'lucide-react'
import { useId, useState } from 'react'

import { areaFromPlace, type PlaceShape } from '@/api/geo'
import type { AreaGeometry } from '@/api/projects'
import { Button } from '@/components/ui/button'
import { PlaceSearchError, searchPlaces, type PlaceKind, type PlaceResult } from '@/lib/address-search'
import { cn } from '@/lib/utils'
import { boxTooBig, findRoadParts, SOURCE_NAMES, type Box, type RoadSearch } from '@/lib/whole-road'

const WIDTHS = [
  { value: 20, label: '20 m (road only)' },
  { value: 30, label: '30 m (road and sidewalks)' },
  { value: 50, label: '50 m (wide street)' },
]

const KIND: Record<PlaceKind, { label: string; icon: typeof Route; note: (width: number) => string }> = {
  road: { label: 'Road', icon: Route, note: (width) => `Selects a ${width} m wide strip along this road` },
  area: { label: 'Area', icon: Building2, note: () => 'Uses this place’s outline' },
  address: { label: 'Location', icon: MapPin, note: () => 'Selects 150 m around this point' },
}

interface PlaceSearchProps {
  /** The area now on the map (needed to add a place to it). */
  currentArea: AreaGeometry | null
  /** Strip width for roads (shared with "Draw a road" on the map). */
  roadWidthM: number
  onRoadWidthChange: (width: number) => void
  /** The part of the map the person sees now (west, south, east, north), for "Find all parts by name". */
  getMapBox?: () => Box | null
  /** Called with the chosen place's own area, its name, and whether it is added to the places already selected. */
  onChoose: (area: AreaGeometry, label: string, add: boolean) => void
}

/**
 * Find a road, address, neighbourhood or city by name, or a location by coordinates, and set
 * the survey area from it. Roads become a strip along the road; several roads can be added.
 * Not a <form>: it sits inside the project form, so Enter is handled here instead.
 */
export function PlaceSearch({ currentArea, roadWidthM: width, onRoadWidthChange: setWidth, getMapBox, onChoose }: PlaceSearchProps) {
  const inputId = useId()
  const widthId = useId()
  const partsNameId = useId()
  const partsWhereId = useId()
  const partsTownId = useId()
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'replace' | 'add'>('replace')
  const [message, setMessage] = useState<string | null>(null)
  const [partsName, setPartsName] = useState('')
  const [partsWhere, setPartsWhere] = useState<PartsWhere>('town')
  const [partsTown, setPartsTown] = useState('')
  const [partsProblem, setPartsProblem] = useState<string | null>(null)
  const search = useMutation({ mutationFn: (text: string) => searchPlaces(text) })
  const build = useMutation({
    mutationFn: (place: PlaceResult) => areaFromPlace(place.shape, { roadWidthM: width, addTo: null }),
  })
  const adding = mode === 'add' && currentArea != null
  // Owner, 2026-11-16 and 2026-11-17: "Whole road" and "Find all parts by name" collect every part of a
  // road. The parts are looked for in a chain of sources (see lib/whole-road.ts).
  const whole = useMutation({
    mutationFn: async (job: WholeJob) => {
      const road = await findRoadParts(job.search)
      const { area } = await areaFromPlace(road.shape, { roadWidthM: width, addTo: null })
      return { area, road }
    },
  })
  const busyAny = build.isPending || whole.isPending

  const startWhole = (job: WholeJob, afterwards?: () => void) => {
    build.reset()
    whole.mutate(job, {
      onSuccess: ({ area, road }) => {
        onChoose(area, `${job.town ? `${job.name}, ${job.town}` : job.name} (whole road)`, adding)
        afterwards?.()
        setMessage(
          `Whole road “${job.name}” ${adding ? 'added to the area' : 'selected'}: ${road.pieces} part${road.pieces === 1 ? '' : 's'}, about ${road.lengthKm} km, ${job.where}, ${width} m wide. Source: ${SOURCE_NAMES[road.source]}.${road.partial ? ' This source may have left some parts out: look for gaps on the map and fill them with “Road between two points”.' : ''} Check it on the map; the bin icon removes it.`,
        )
        setMode('add')
      },
    })
  }

  const chooseWhole = (place: PlaceResult) => {
    const name = place.roadName ?? place.label.split(',')[0] ?? ''
    const [longitude, latitude] = centreOf(place.shape)
    startWhole(
      {
        placeId: place.id,
        name,
        town: place.label.split(',')[1]?.trim(),
        where: `within ${WHOLE_ROAD_M / 1000} km of the place found`,
        search: { name, byRef: ROUTE_NUMBER.test(name), latitude, longitude, radiusM: WHOLE_ROAD_M, osmWayId: place.osmWayId, extent: 'radius' },
      },
      () => search.reset(),
    )
  }

  // "Find all parts by name": a typed road name, searched in the town limits, the map view or within 5, 10 or 20 km.
  const findParts = () => {
    setMessage(null)
    const name = (partsName.trim() || query.trim()).slice(0, 200)
    if (name.length < 2) return setPartsProblem('Type the road name or route number.')
    const first = search.data?.[0]
    const view = getMapBox?.() ?? null
    const common = { name, byRef: ROUTE_NUMBER.test(name), radiusM: WHOLE_ROAD_M }
    const go = (searchFor: RoadSearch, where: string, town?: string) => {
      setPartsProblem(null)
      startWhole({ name, town, where, search: searchFor })
    }
    if (partsWhere === 'view') {
      if (!view) return setPartsProblem('The map is not ready yet. Wait a moment, then try again.')
      if (boxTooBig(view)) return setPartsProblem('The map shows too large a place. Zoom in a little, or choose “Within 20 km”.')
      return go({ ...common, longitude: (view[0] + view[2]) / 2, latitude: (view[1] + view[3]) / 2, extent: 'box', box: view }, 'in the map view')
    }
    // The middle of the search: the place found, or (when nothing was searched) the middle of the map.
    const [longitude, latitude] = first ? centreOf(first.shape) : view ? [(view[0] + view[2]) / 2, (view[1] + view[3]) / 2] : [NaN, NaN]
    if (Number.isNaN(longitude) || Number.isNaN(latitude)) return setPartsProblem('Search for the place first (for example “Naperville, Illinois”), or move the map to it.')
    if (partsWhere === 'town') {
      const town = partsTown.trim() || (first ? townOf(first) : '')
      if (!town) return setPartsProblem('Type the town name.')
      return go({ ...common, longitude, latitude, extent: 'town', town }, `inside the limits of ${town}`, town)
    }
    const km = Number(partsWhere)
    go({ ...common, longitude, latitude, radiusM: km * 1000, extent: 'radius' }, `within ${km} km of the place`)
  }

  const run = () => {
    const text = query.trim()
    if (text.length < 3) return
    setMessage(null)
    build.reset()
    search.mutate(text)
  }

  const choose = (place: PlaceResult) => {
    whole.reset()
    build.mutate(place, {
      onSuccess: ({ area }) => {
        const name = place.label.split(',')[0] ?? place.label
        onChoose(area, place.label.split(',').slice(0, 2).join(',').trim() || name, adding)
        search.reset()
        const what = place.kind === 'road' ? `Road “${name}” (${width} m wide)` : `“${name}”`
        setMessage(
          `${what} ${adding ? 'added to the area' : 'selected'}. Check it on the map: the pencil icon on its corner changes it, the bin icon removes it. To add another road, search again and choose “Add to the area”.`,
        )
        setMode('add') // the next place is added, so nothing already selected is lost by accident
      },
    })
  }

  return (
    <div className="space-y-3 rounded-xl border border-asphalt-100 bg-asphalt-50/60 p-4">
      <div>
        <label htmlFor={inputId} className="block text-sm font-medium text-asphalt-800">
          Find a road, address or area
        </label>
        <p className="mt-0.5 text-xs text-asphalt-500">
          Type a road name with the city (e.g. “Washington Street, Naperville”), an address, a neighborhood, or coordinates (e.g.
          “41.7731, -88.1501”).
        </p>
      </div>
      <div className="flex gap-2">
        <input
          id={inputId}
          type="search"
          className="control"
          placeholder="Road name, address, area or coordinates"
          value={query}
          maxLength={200}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault() // do not submit the project form
              run()
            }
          }}
        />
        <Button variant="secondary" busy={search.isPending} disabled={query.trim().length < 3} onClick={run}>
          <Search className="size-4" aria-hidden />
          Search
        </Button>
      </div>

      <details className="rounded-lg border border-asphalt-100 bg-white/70 px-3 py-2">
        <summary className="cursor-pointer text-sm font-medium text-asphalt-800">Find all parts of a road by name</summary>
        <div className="mt-3 space-y-3">
          <p className="text-xs text-asphalt-500">
            Type a road name or route number and choose where to look. Search the place above first (or move the map to it): the
            place found is the middle of the search.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-48 flex-1">
              <label htmlFor={partsNameId} className="mb-1 block text-xs font-medium text-asphalt-700">
                Road name or route number
              </label>
              <input
                id={partsNameId}
                className="control"
                placeholder={query.trim() || 'e.g. Washington Street or IL 59'}
                value={partsName}
                maxLength={200}
                onChange={(event) => setPartsName(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor={partsWhereId} className="mb-1 block text-xs font-medium text-asphalt-700">
                Where to look
              </label>
              <select id={partsWhereId} className="control py-1.5" value={partsWhere} onChange={(event) => setPartsWhere(event.target.value as PartsWhere)}>
                <option value="town">Town limits</option>
                <option value="view">The map I see now</option>
                <option value="5">Within 5 km</option>
                <option value="10">Within 10 km</option>
                <option value="20">Within 20 km</option>
              </select>
            </div>
            {partsWhere === 'town' && (
              <div>
                <label htmlFor={partsTownId} className="mb-1 block text-xs font-medium text-asphalt-700">
                  Town
                </label>
                <input
                  id={partsTownId}
                  className="control"
                  placeholder={search.data?.[0] ? townOf(search.data[0]) : 'e.g. Naperville'}
                  value={partsTown}
                  maxLength={100}
                  onChange={(event) => setPartsTown(event.target.value)}
                />
              </div>
            )}
            <Button variant="secondary" busy={whole.isPending && !whole.variables?.placeId} disabled={busyAny} onClick={findParts}>
              <Route className="size-4" aria-hidden />
              Find all parts by name
            </Button>
          </div>
          {partsProblem && (
            <p role="alert" className="text-sm text-red-700">
              {partsProblem}
            </p>
          )}
        </div>
      </details>

      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div>
          <label htmlFor={widthId} className="mb-1 block text-xs font-medium text-asphalt-700">
            Road width (searched and drawn roads)
          </label>
          <select id={widthId} className="control py-1.5" value={width} onChange={(event) => setWidth(Number(event.target.value))}>
            {WIDTHS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        {currentArea && (
          <fieldset className="flex flex-wrap gap-4 text-sm">
            <legend className="mb-1 text-xs font-medium text-asphalt-700">When I choose a place</legend>
            <label className="flex items-center gap-2">
              <input type="radio" name={`${inputId}-mode`} checked={mode === 'add'} onChange={() => setMode('add')} />
              Add to the area
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name={`${inputId}-mode`} checked={mode === 'replace'} onChange={() => setMode('replace')} />
              Replace the area
            </label>
          </fieldset>
        )}
      </div>

      {search.isError && (
        <p role="alert" className="text-sm text-red-700">
          {search.error instanceof PlaceSearchError ? search.error.message : 'The place search failed. Try again.'}
        </p>
      )}
      {build.isError && (
        <p role="alert" className="text-sm text-red-700">
          {build.error instanceof Error ? build.error.message : 'This place could not be used. Try another result.'}
        </p>
      )}
      {whole.isError && (
        <p role="alert" className="text-sm text-red-700">
          {whole.error instanceof Error ? whole.error.message : 'The whole road could not be found. Add its parts one by one.'}
        </p>
      )}
      {search.isSuccess && search.data.length === 0 && (
        <p role="status" className="text-sm text-asphalt-600">
          Nothing found. Check the spelling, or add the city (for example “Main Street, Aurora, Illinois”).
        </p>
      )}
      {search.isSuccess && search.data.length > 0 && (
        <ul aria-label="Places found" className="divide-y divide-asphalt-100 overflow-hidden rounded-lg border border-asphalt-200 bg-white">
          {search.data.map((place) => {
            const kind = KIND[place.kind]
            const busy = build.isPending && build.variables?.id === place.id
            return (
              <li key={place.id} className="flex flex-wrap items-stretch">
                <button
                  type="button"
                  disabled={busyAny}
                  onClick={() => choose(place)}
                  className="flex min-w-0 flex-1 items-start gap-3 px-3 py-2.5 text-left text-sm hover:bg-lane-50 focus-visible:bg-lane-50 disabled:opacity-60"
                >
                  {busy ? (
                    <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-asphalt-500" aria-hidden />
                  ) : (
                    <kind.icon className="mt-0.5 size-4 shrink-0 text-asphalt-400" aria-hidden />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block text-asphalt-900">{place.label}</span>
                    <span className="block text-xs text-asphalt-500">{kind.note(width)}</span>
                  </span>
                  <span
                    className={cn(
                      'pill shrink-0',
                      place.kind === 'road' ? 'bg-lane-100 text-asphalt-900' : place.kind === 'area' ? 'bg-asphalt-100 text-asphalt-800' : 'bg-sky-50 text-sky-800',
                    )}
                  >
                    {kind.label}
                  </span>
                </button>
                {place.kind === 'road' && (
                  <button
                    type="button"
                    disabled={busyAny}
                    onClick={() => chooseWhole(place)}
                    aria-label={`Whole road: ${place.roadName ?? place.label.split(',')[0]} (${place.label.split(',')[1]?.trim() ?? ''})`}
                    title={`Every part of this road within ${WHOLE_ROAD_M / 1000} km`}
                    className="flex shrink-0 items-center gap-1.5 border-l border-asphalt-100 px-3 text-xs font-medium text-lane-800 hover:bg-lane-50 focus-visible:bg-lane-50 disabled:opacity-60"
                  >
                    {whole.isPending && whole.variables?.placeId === place.id ? (
                      <Loader2 className="size-4 animate-spin" aria-hidden />
                    ) : (
                      <Route className="size-4" aria-hidden />
                    )}
                    Whole road
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {message && (
        <p role="status" className="rounded-lg bg-lane-50 px-3 py-2 text-sm text-asphalt-800">
          {message}
        </p>
      )}
      <p className="text-xs text-asphalt-400">
        Search by OpenStreetMap. OpenStreetMap stores a road in many short parts, so choosing a road selects one part. “Whole road” selects every part with the same name within {WHOLE_ROAD_M / 1000} km. If the map servers are slow, backup sources are tried and the message says which one was used.
      </p>
    </div>
  )
}

const WHOLE_ROAD_M = 5000
/** Route numbers ("IL 59", "US 34", "I-88") are matched on the road's route number, not its name. */
const ROUTE_NUMBER = /^(IL|US|I|SR|CR)[ -]?\d+[A-Z]?$/i

type PartsWhere = 'town' | 'view' | '5' | '10' | '20'

interface WholeJob {
  search: RoadSearch
  name: string
  town?: string
  /** For the message: "within 5 km of the place found". */
  where: string
  /** The search result whose "Whole road" button was pressed (shows its spinner). */
  placeId?: string
}

/** The town of a search result: a road's town is the second word group of its name, an area's the first. */
function townOf(place: PlaceResult): string {
  return (place.kind === 'road' ? place.label.split(',')[1] : place.label.split(',')[0])?.trim() ?? ''
}

/** A point on the place (longitude, latitude): the middle bend of a road, or the middle of an area's box. */
function centreOf(shape: PlaceShape): [number, number] {
  const numbers = (shape.coordinates as unknown[]).flat(Infinity) as number[]
  const count = Math.floor(numbers.length / 2)
  if (shape.type === 'Polygon' || shape.type === 'MultiPolygon') {
    const lons = numbers.filter((_, index) => index % 2 === 0)
    const lats = numbers.filter((_, index) => index % 2 === 1)
    return [(Math.min(...lons) + Math.max(...lons)) / 2, (Math.min(...lats) + Math.max(...lats)) / 2]
  }
  const middle = Math.floor(count / 2)
  return [numbers[2 * middle] ?? 0, numbers[2 * middle + 1] ?? 0]
}
