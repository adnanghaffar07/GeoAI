/** IDOT traffic cameras in the project area (team-lead items 8 and 10). */

import type { ImageInfo } from '@/api/images'
import { apiRequest } from '@/lib/api-client'

export interface Camera {
  id: number
  location: string
  direction: string
  latitude: number
  longitude: number
  /** IDOT's latest picture; the browser loads it straight from IDOT. */
  image_url: string
  page_url: string | null
  age_minutes: number | null
  too_old: boolean
}

export interface CameraList {
  cameras: Camera[]
  source: string
  licence: string
  licence_url: string
}

export const camerasKey = (projectId: string) => ['projects', projectId, 'cameras'] as const

export const listCameras = (projectId: string, signal?: AbortSignal): Promise<CameraList> => apiRequest(`/v1/projects/${projectId}/cameras`, { signal })

export const takeSnapshot = (projectId: string, cameraId: number): Promise<{ duplicate: boolean; image: ImageInfo }> =>
  apiRequest(`/v1/projects/${projectId}/cameras/${cameraId}/snapshot`, { method: 'POST' })

export const DIRECTION_LABELS: Record<string, string> = {
  N: 'facing north',
  S: 'facing south',
  E: 'facing east',
  W: 'facing west',
  NE: 'facing north-east',
  NW: 'facing north-west',
  SE: 'facing south-east',
  SW: 'facing south-west',
  NONE: '',
}
