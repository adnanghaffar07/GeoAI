import { Marker } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import type { LatLon } from '@/api/images'
import type { AreaGeometry } from '@/api/projects'
import { BaseMapNotice } from '@/components/map/area-map'
import { fitToArea, showArea } from '@/components/map/map-layers'
import { useMap } from '@/components/map/use-map'

interface PickLocationMapProps {
  area: AreaGeometry
  value: LatLon | null
  onPick: (location: LatLon) => void
  label?: string
  className?: string
}

/** Click the map to choose a point (photo location, observation location, or a finding's pin). */
export function PickLocationMap({ area, value, onPick, label = 'Map for picking the photo location', className = 'h-80' }: PickLocationMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { map, baseMapFailed } = useMap(containerRef)
  const markerRef = useRef<Marker | null>(null)
  const onPickRef = useRef(onPick)

  useEffect(() => {
    onPickRef.current = onPick
  }, [onPick])

  useEffect(() => {
    if (!map) return
    showArea(map, area)
    fitToArea(map, area)
    map.getCanvas().style.cursor = 'crosshair'
    const handleClick = (event: { lngLat: { lat: number; lng: number } }) =>
      onPickRef.current({ latitude: event.lngLat.lat, longitude: event.lngLat.lng })
    map.on('click', handleClick)
    return () => {
      map.off('click', handleClick)
    }
  }, [map, area])

  useEffect(() => {
    if (!map) return
    if (!value) {
      markerRef.current?.remove()
      markerRef.current = null
      return
    }
    const position: [number, number] = [value.longitude, value.latitude]
    if (markerRef.current) markerRef.current.setLngLat(position)
    else markerRef.current = new Marker({ color: '#1b2633' }).setLngLat(position).addTo(map)
  }, [map, value])

  return (
    <div className={`relative overflow-hidden rounded-lg border border-asphalt-100 ${className}`}>
      <div ref={containerRef} role="region" aria-label={label} className="size-full" />
      {baseMapFailed && <BaseMapNotice />}
    </div>
  )
}
