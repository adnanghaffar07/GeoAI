import { useMutation } from '@tanstack/react-query'
import { MapPin, Search } from 'lucide-react'
import { useId, useState } from 'react'

import type { AreaGeometry } from '@/api/projects'
import { Button } from '@/components/ui/button'
import { PlaceSearchError, searchPlaces, type PlaceResult } from '@/lib/address-search'

interface PlaceSearchProps {
  /** Called with the chosen place's area; it replaces the current area. */
  onChoose: (area: AreaGeometry, label: string) => void
  hasArea: boolean
}

/**
 * "Find a street, area or city": search, pick a result, and the survey area is set from it.
 * Not a <form>: it sits inside the project form, so Enter is handled here instead.
 */
export function PlaceSearch({ onChoose, hasArea }: PlaceSearchProps) {
  const inputId = useId()
  const [query, setQuery] = useState('')
  const [chosen, setChosen] = useState<PlaceResult | null>(null)
  const search = useMutation({ mutationFn: (text: string) => searchPlaces(text) })

  const run = () => {
    const text = query.trim()
    if (text.length < 3) return
    setChosen(null)
    search.mutate(text)
  }

  const choose = (place: PlaceResult) => {
    setChosen(place)
    search.reset()
    onChoose(place.area, place.label)
  }

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="block text-sm font-medium text-asphalt-800">
        Find a street, neighborhood or city
      </label>
      <div className="flex gap-2">
        <input
          id={inputId}
          type="search"
          className="control"
          placeholder="e.g. Washington Street, Naperville"
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
      <p className="text-xs text-asphalt-400">
        Add the city for better results.{hasArea ? ' Choosing a place replaces the current area.' : ''} Search by OpenStreetMap.
      </p>

      {search.isError && (
        <p role="alert" className="text-sm text-red-700">
          {search.error instanceof PlaceSearchError ? search.error.message : 'The place search failed. Try again.'}
        </p>
      )}
      {search.isSuccess && search.data.length === 0 && (
        <p role="status" className="text-sm text-asphalt-600">
          No place found. Check the spelling, or add the city (for example “Main Street, Aurora, Illinois”).
        </p>
      )}
      {search.isSuccess && search.data.length > 0 && (
        <ul aria-label="Places found" className="divide-y divide-asphalt-100 overflow-hidden rounded-lg border border-asphalt-200 bg-white">
          {search.data.map((place) => (
            <li key={place.id}>
              <button
                type="button"
                onClick={() => choose(place)}
                className="flex w-full items-start gap-2 px-3 py-2.5 text-left text-sm hover:bg-lane-50 focus-visible:bg-lane-50"
              >
                <MapPin className="mt-0.5 size-4 shrink-0 text-asphalt-400" aria-hidden />
                <span className="min-w-0">
                  <span className="block text-asphalt-900">{place.label}</span>
                  <span className="block text-xs text-asphalt-500">
                    {place.isOutline ? 'Uses the place’s outline' : 'Uses a rectangle around it'}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {chosen && (
        <p role="status" className="rounded-lg bg-lane-50 px-3 py-2 text-sm text-asphalt-800">
          Area set from “{chosen.label}”. Check it on the map and use <strong>Move or adjust</strong> to change the corners if needed.
        </p>
      )}
    </div>
  )
}
