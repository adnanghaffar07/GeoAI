import { ExternalLink, MapPin, MapPinOff } from 'lucide-react'

interface LocationLineProps {
  location: { latitude: number; longitude: number } | null | undefined
  /** A reviewer moved the pin to the real spot; otherwise it is the approximate camera position. */
  confirmed?: boolean
}

/** Where a finding is, in words first, with the coordinates and a map link for people going on site. */
export function LocationLine({ location, confirmed = false }: LocationLineProps) {
  if (!location) {
    return (
      <p className="flex items-center gap-1 text-xs text-amber-800">
        <MapPinOff className="size-3.5" aria-hidden />
        No location yet
      </p>
    )
  }
  const coordinates = `${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}`
  return (
    <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-asphalt-600">
      <MapPin className="size-3.5" aria-hidden />
      <span>{confirmed ? 'Location confirmed by a reviewer' : 'Approximate location (where the photo was taken)'}</span>
      <span className="text-asphalt-400 tabular-nums">{coordinates}</span>
      <a
        href={`https://www.google.com/maps/search/?api=1&query=${location.latitude},${location.longitude}`}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex items-center gap-0.5 link"
      >
        Open in Google Maps
        <ExternalLink className="size-3" aria-hidden />
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    </p>
  )
}
