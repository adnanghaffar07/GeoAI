/** Photos: upload, list, location and withdraw (api-spec §3.5). */

import type { Page } from '@/api/organizations'
import { ApiError, apiRequest } from '@/lib/api-client'
import { logger } from '@/lib/logger'

export interface LatLon {
  latitude: number
  longitude: number
}

export type LocationSource = 'photo_gps' | 'device_gps' | 'manual' | 'none'

export interface ImageInfo {
  id: string
  project_id: string
  original_filename: string
  content_type: string
  size_bytes: number
  width_px: number
  height_px: number
  captured_at: string | null
  /** Where the camera was. Approximate: never the exact position of a defect. */
  location: LatLon | null
  location_source: LocationSource
  location_quality: string
  quality_flags: string[]
  status: 'stored' | 'withdrawn'
  uploaded_by: string
  uploaded_by_name: string | null
  created_at: string
  /** Current AI analysis of this photo, or null when it has not been sent for analysis. */
  analysis: ImageAnalysis | null
}

export interface ImageAnalysis {
  job_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  failure_reason: string | null
  model_version: string
  is_test_detector: boolean
  is_trial_model?: boolean
  /** Number of AI suggestions; null when this person may not see suggestions. */
  candidate_count: number | null
}

export interface UploadResult {
  /** True when this exact file was already in the project (nothing new was stored). */
  duplicate: boolean
  image: ImageInfo
}

/** Plain-language names for location sources and quality flags. */
export const LOCATION_SOURCE_LABELS: Record<LocationSource, string> = {
  photo_gps: 'Location from the photo',
  device_gps: 'Location from the phone',
  manual: 'Location picked on the map',
  none: 'No location yet',
}

const FLAG_LABELS: Record<string, string> = {
  missing_gps: 'Photo has no location',
  invalid_gps: 'Photo location could not be read',
  blurry: 'May be blurry',
  too_dark: 'May be too dark',
  outside_project_area: 'Taken outside the survey area',
  capture_time_no_timezone: 'Time zone of the photo time unknown',
  no_capture_time: 'Time taken unknown',
}

export function flagLabel(flag: string): string {
  return FLAG_LABELS[flag] ?? flag.replaceAll('_', ' ')
}

export const imageQueryKeys = {
  list: (projectId: string, missingOnly: boolean, page: number) => ['projects', projectId, 'images', missingOnly, page] as const,
  all: (projectId: string) => ['projects', projectId, 'images'] as const,
}

/** Address of the small preview. The browser sends the session cookie; access is checked every time. */
export const previewUrl = (imageId: string) => `/api/v1/images/${imageId}/preview`
export const originalUrl = (imageId: string) => `/api/v1/images/${imageId}/file`

export function listImages(
  projectId: string,
  options: { missingLocation?: boolean; page?: number; pageSize?: number },
  signal?: AbortSignal,
): Promise<Page<ImageInfo>> {
  const query = new URLSearchParams({ page: String(options.page ?? 1), page_size: String(options.pageSize ?? 24) })
  if (options.missingLocation) query.set('missing_location', 'true')
  return apiRequest(`/v1/projects/${projectId}/images?${query}`, { signal })
}

export function setImageLocation(imageId: string, location: LatLon): Promise<ImageInfo> {
  return apiRequest(`/v1/images/${imageId}/location`, { method: 'PATCH', body: location })
}

export function withdrawImage(imageId: string): Promise<ImageInfo> {
  return apiRequest(`/v1/images/${imageId}/withdraw`, { method: 'POST' })
}

function errorFromXhr(xhr: XMLHttpRequest): ApiError {
  try {
    const body = JSON.parse(xhr.responseText) as { error?: { code?: string; message?: string; request_id?: string } }
    if (body.error?.code && body.error.message) {
      return new ApiError({
        status: xhr.status,
        code: body.error.code,
        message: body.error.message,
        requestId: body.error.request_id ?? xhr.getResponseHeader('X-Request-ID'),
      })
    }
  } catch {
    // not JSON: fall through to the generic message
  }
  return new ApiError({
    status: xhr.status,
    code: 'unexpected_response',
    message: `The server returned an unexpected error (HTTP ${xhr.status}).`,
    requestId: xhr.getResponseHeader('X-Request-ID'),
  })
}

/**
 * Upload one photo with progress (fetch cannot report upload progress, so this uses XHR).
 * Safe to retry: the server recognises a file it already has and returns `duplicate: true`.
 */
export function uploadImage(
  projectId: string,
  file: File,
  options: { deviceLocation?: LatLon | null; onProgress?: (fraction: number) => void; signal?: AbortSignal } = {},
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    if (options.deviceLocation) {
      form.append('device_latitude', String(options.deviceLocation.latitude))
      form.append('device_longitude', String(options.deviceLocation.longitude))
    }
    const xhr = new XMLHttpRequest()
    const path = `/v1/projects/${projectId}/images`
    const started = performance.now()
    xhr.open('POST', `/api${path}`)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.withCredentials = true
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded / event.total)
    }
    xhr.onload = () => {
      logger.request('POST', path, xhr.status, performance.now() - started, xhr.getResponseHeader('X-Request-ID'))
      if (xhr.status === 200 || xhr.status === 201) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult)
        } catch {
          reject(new ApiError({ status: xhr.status, code: 'invalid_response', message: 'The server sent a response that could not be read.' }))
        }
      } else {
        reject(errorFromXhr(xhr))
      }
    }
    xhr.onerror = () => {
      logger.request('POST', path, 0, performance.now() - started, null)
      reject(new ApiError({ status: 0, code: 'network_error', message: 'Cannot reach the server. Check your connection and try again.' }))
    }
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    options.signal?.addEventListener('abort', () => xhr.abort())
    xhr.send(form)
  })
}
