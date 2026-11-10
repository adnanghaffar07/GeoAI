/** Analysed photos on a map (team-lead item 5). */

import { apiRequest } from '@/lib/api-client'

export interface PhotoDefect {
  id: string
  type_key: string | null
  severity_key: string | null
  review_status: string
  bbox: [number, number, number, number] | null
}

export interface PhotoPinProps {
  id: string
  original_filename: string
  width_px: number
  height_px: number
  taken_at: string
  defect_count: number
  /** 3 = a verified defect, 2 = an AI suggestion waiting for review, 0 = nothing found. */
  worst: number
  defects: PhotoDefect[]
}

export interface PhotoMapData {
  type: 'FeatureCollection'
  truncated: boolean
  features: { type: 'Feature'; id: string; geometry: { type: 'Point'; coordinates: [number, number] }; properties: PhotoPinProps }[]
}

export const photoMapKey = (projectId: string) => ['projects', projectId, 'photo-map'] as const

export function photoMap(projectId: string, signal?: AbortSignal): Promise<PhotoMapData> {
  return apiRequest(`/v1/projects/${projectId}/photos.geojson`, { signal })
}

export const WORST_COLORS: Record<number, string> = { 3: '#047857', 2: '#d97706', 1: '#0284c7', 0: '#9aa5b1' }
export const WORST_LABELS: Record<number, string> = { 3: 'Verified problem', 2: 'AI suggestion to review', 1: 'Other finding', 0: 'Nothing found' }
