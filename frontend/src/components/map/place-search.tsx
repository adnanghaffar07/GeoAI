import { useMutation } from '@tanstack/react-query'
import { Building2, Loader2, MapPin, Route, Search } from 'lucide-react'
import { useId, useState } from 'react'

import { areaFromPlace } from '@/api/geo'
import type { AreaGeometry } from '@/api/projects'
import { Button } from '@/components/ui/button'
import { PlaceSearchError, searchPlaces, type PlaceKind, type PlaceResult } from '@/lib/address-search'
import { cn } from '@/lib/utils'

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
  /** Called with the new area (the chosen place, or the current area plus the place). */
  onChoose: (area: AreaGeometry) => void
}

/**
 * Find a road, address, neighbourhood or city by name, or a location by coordinates, and set
 * the survey area from it. Roads become a strip along the road; several roads can be added.
 * Not a <form>: it sits inside the project form, so Enter is handled here instead.
 */
export function PlaceSearch({ currentArea, roadWidthM: width, onRoadWidthChange: setWidth, onChoose }: PlaceSearchProps) {
  const inputId = useId()
  const widthId = useId()
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'replace' | 'add'>('replace')
  const [message, setMessage] = useState<string | null>(null)
  const search = useMutation({ mutationFn: (text: string) => searchPlaces(text) })
  const build = useMutation({
    mutationFn: (place: PlaceResult) => areaFromPlace(place.shape, { roadWidthM: width, addTo: mode === 'add' ? currentArea : null }),
  })
  const adding = mode === 'add' && currentArea != null

  const run = () => {
    const text = query.trim()
    if (text.length < 3) return
    setMessage(null)
    build.reset()
    search.mutate(text)
  }

  const choose = (place: PlaceResult) => {
    build.mutate(place, {
      onSuccess: ({ area }) => {
        onChoose(area)
        search.reset()
        const name = place.label.split(',')[0]
        const what = place.kind === 'road' ? `Road “${name}” (${width} m wide)` : `“${name}”`
        setMessage(
          `${what} ${adding ? 'added to the area' : 'selected'}. Check it on the map; use Move or adjust to change it. To add another road, search again and choose “Add to the area”.`,
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
              <li key={place.id}>
                <button
                  type="button"
                  disabled={build.isPending}
                  onClick={() => choose(place)}
                  className="flex w-full items-start gap-3 px-3 py-2.5 text-left text-sm hover:bg-lane-50 focus-visible:bg-lane-50 disabled:opacity-60"
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
        Search by OpenStreetMap. Long roads can be split into parts: if only part of a road is selected, search again for the rest and add it.
      </p>
    </div>
  )
}
