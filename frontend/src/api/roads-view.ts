/** Roads-only view (team-lead item 11). */

import { apiRequest } from '@/lib/api-client'

export type Box = [number, number, number, number] // west, south, east, north

export interface RoadProps {
  section_id: string
  name: string | null
  road_type: string
  length_m: number
  level: string | null
  speed_limit_mph: number | null
  lanes: number | null
  surface: string | null
  oneway: boolean | null
  climate_level: string
  traffic_level: string
  roughness_level: string
}

export interface RoadsData {
  type: 'FeatureCollection'
  box: Box | null
  features: { type: 'Feature'; geometry: { type: 'LineString'; coordinates: [number, number][] }; properties: RoadProps }[]
}

export const roadsKey = (projectId: string, box: Box | null) => ['projects', projectId, 'road-risk', 'roads', box] as const

export function getRoads(projectId: string, box: Box | null, signal?: AbortSignal): Promise<RoadsData> {
  const query = box ? `?box=${box.map((v) => v.toFixed(6)).join(',')}` : ''
  return apiRequest(`/v1/projects/${projectId}/roads.geojson${query}`, { signal })
}

export type ColourBy = 'risk' | 'speed' | 'type' | 'climate' | 'traffic'

export const COLOUR_BY_LABELS: Record<ColourBy, string> = {
  risk: 'Risk level',
  speed: 'Speed limit',
  type: 'Road type',
  climate: 'Freeze-thaw weather (last 30 days)',
  traffic: 'Traffic',
}

interface Category {
  key: string
  label: string
  colour: string
}

const LEVELS: Category[] = [
  { key: 'high', label: 'High', colour: '#b91c1c' },
  { key: 'medium', label: 'Medium', colour: '#d97706' },
  { key: 'low', label: 'Low', colour: '#2563eb' },
  { key: 'missing', label: 'Not known', colour: '#9aa5b1' },
]

export const CATEGORIES: Record<ColourBy, Category[]> = {
  risk: LEVELS,
  climate: LEVELS,
  traffic: LEVELS,
  speed: [
    { key: 's25', label: '25 mph or less', colour: '#2563eb' },
    { key: 's35', label: '30–35 mph', colour: '#059669' },
    { key: 's45', label: '40–45 mph', colour: '#d97706' },
    { key: 's50', label: '50 mph or more', colour: '#b91c1c' },
    { key: 'missing', label: 'Not on the map', colour: '#9aa5b1' },
  ],
  type: [
    { key: 'main', label: 'Main road', colour: '#b91c1c' },
    { key: 'collector', label: 'Collector road', colour: '#d97706' },
    { key: 'local', label: 'Local street', colour: '#2563eb' },
    { key: 'missing', label: 'Other', colour: '#9aa5b1' },
  ],
}

/** Which category of the chosen colouring a road falls in. */
export function categoryOf(road: RoadProps, by: ColourBy): string {
  if (by === 'risk') return road.level ?? 'missing'
  if (by === 'climate' || by === 'traffic') {
    const level = by === 'climate' ? road.climate_level : road.traffic_level
    return ['high', 'medium', 'low'].includes(level) ? level : 'missing'
  }
  if (by === 'speed') {
    const mph = road.speed_limit_mph
    if (!mph) return 'missing'
    return mph <= 25 ? 's25' : mph <= 35 ? 's35' : mph <= 45 ? 's45' : 's50'
  }
  const type = road.road_type.replace('_link', '')
  if (['motorway', 'trunk', 'primary', 'secondary'].includes(type)) return 'main'
  if (type === 'tertiary') return 'collector'
  if (['residential', 'unclassified', 'living_street'].includes(type)) return 'local'
  return 'missing'
}
