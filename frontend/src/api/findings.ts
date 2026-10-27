/** Findings, review, manual observations and history (api-spec §3.7). */

import type { LatLon } from '@/api/images'
import type { Page } from '@/api/organizations'
import { apiRequest } from '@/lib/api-client'

export type ReviewStatus = 'ai_generated' | 'awaiting_review' | 'verified' | 'rejected' | 'needs_field_check' | 'merged'

export interface Finding {
  id: string
  project_id: string
  origin: 'ai' | 'manual'
  review_status: ReviewStatus
  inspection_status: string
  /** The AI's original answer. Never changed. */
  predicted_type_key: string | null
  /** The AI's own score. It is NOT severity. */
  predicted_confidence: number | null
  /** Box on the original photo, in pixels: [left, top, right, bottom]. */
  predicted_bbox: [number, number, number, number] | null
  model_version: string | null
  is_test_detector: boolean
  is_trial_model?: boolean
  analysis_job_id: string | null
  /** The reviewer's type and severity (or the type chosen for a manual observation). */
  type_key: string | null
  severity_key: string | null
  severity_rubric_id: string | null
  severity_rubric_version: number | null
  notes: string | null
  reviewed_by_name: string | null
  reviewed_at: string | null
  created_by_name: string | null
  /** The point to show: the reviewer's corrected point if set, otherwise the original. */
  location: LatLon | null
  /** Approximate camera position of the photo (or the point picked when adding). Never changed. */
  original_location: LatLon | null
  corrected_location: LatLon | null
  location_source: string
  location_quality: 'approximate' | 'missing' | 'reviewer_confirmed' | string
  photo: { id: string; original_filename: string; width_px: number; height_px: number } | null
  version: number
  created_at: string
  updated_at: string
}

export interface FindingFilters {
  review_status?: ReviewStatus[]
  type_key?: string
  severity_key?: string
  has_location?: boolean
  created_from?: string
  created_to?: string
  image_id?: string
}

export interface ReviewEvent {
  id: string
  action: 'create' | 'verify' | 'reject' | 'needs_field_check' | 'edit' | 'merge' | 'reopen_review'
  actor_name: string | null
  actor_roles: string[]
  changes: Record<string, { old: unknown; new: unknown }>
  note: string | null
  finding_version: number
  created_at: string
}

export interface FindingTypeOption {
  key: string
  label: string
  source: 'ai' | 'manual'
  is_placeholder: boolean
  in_project: boolean
}

export interface SeverityRubric {
  id: string
  version: number
  levels: { key: string; label: string; definition: string }[]
  is_placeholder: boolean
  is_current: boolean
  created_at: string
}

export interface ReviewOptions {
  finding_types: FindingTypeOption[]
  severity_rubric: SeverityRubric
}

export interface FindingsMap {
  type: 'FeatureCollection'
  features: {
    type: 'Feature'
    id: string
    geometry: { type: 'Point'; coordinates: [number, number] }
    properties: { id: string; review_status: ReviewStatus; type_key: string | null; severity_key: string | null; origin: string }
  }[]
  /** True when there were more located findings than the map shows. */
  truncated: boolean
}

export type ReviewAction = 'verify' | 'reject' | 'needs_field_check' | 'edit'

export interface ReviewRequest {
  action: ReviewAction
  version: number
  type_key?: string
  severity_key?: string
  /** null removes an earlier correction (the original location is never changed). */
  corrected_location?: LatLon | null
  notes?: string
  /** Why this decision was made; kept in the history. */
  reason?: string
}

export interface ManualFindingRequest {
  type_key: string
  notes: string
  location?: LatLon | null
  image_id?: string | null
}

export const REVIEW_STATUS_LABELS: Record<string, string> = {
  ai_generated: 'Unreviewed AI suggestion',
  awaiting_review: 'Awaiting review',
  needs_field_check: 'Needs field check',
  verified: 'Verified',
  rejected: 'Rejected',
  merged: 'Merged',
}

/** Statuses that still need a reviewer's decision. */
export const TO_REVIEW: ReviewStatus[] = ['ai_generated', 'awaiting_review']

const TYPE_LABELS: Record<string, string> = {
  pothole: 'Pothole',
  surface_cracking: 'Surface cracking',
  pavement_deterioration: 'Pavement deterioration',
  sidewalk_observation: 'Sidewalk observation',
}

/** Display name of a type key; uses the organization's labels when given. */
export function typeLabel(key: string | null, types?: { key: string; label: string }[]): string {
  if (!key) return 'Type not chosen'
  return types?.find((type) => type.key === key)?.label ?? TYPE_LABELS[key] ?? key.replaceAll('_', ' ')
}

export const findingQueryKeys = {
  all: (projectId: string) => ['projects', projectId, 'findings'] as const,
  list: (projectId: string, filters: FindingFilters, page: number) => ['projects', projectId, 'findings', 'list', filters, page] as const,
  map: (projectId: string, filters: FindingFilters) => ['projects', projectId, 'findings', 'map', filters] as const,
  queue: (projectId: string) => ['projects', projectId, 'findings', 'queue'] as const,
  detail: (findingId: string) => ['findings', findingId] as const,
  history: (findingId: string) => ['findings', findingId, 'history'] as const,
  options: (projectId: string) => ['projects', projectId, 'review-options'] as const,
}

export function filtersToQuery(filters: FindingFilters): URLSearchParams {
  const query = new URLSearchParams()
  for (const status of filters.review_status ?? []) query.append('review_status', status)
  if (filters.type_key) query.set('type_key', filters.type_key)
  if (filters.severity_key) query.set('severity_key', filters.severity_key)
  if (filters.has_location !== undefined) query.set('has_location', String(filters.has_location))
  if (filters.created_from) query.set('created_from', filters.created_from)
  if (filters.created_to) query.set('created_to', filters.created_to)
  if (filters.image_id) query.set('image_id', filters.image_id)
  return query
}

export function listFindings(
  projectId: string,
  filters: FindingFilters,
  options: { page?: number; pageSize?: number } = {},
  signal?: AbortSignal,
): Promise<Page<Finding>> {
  const query = filtersToQuery(filters)
  query.set('page', String(options.page ?? 1))
  query.set('page_size', String(options.pageSize ?? 50))
  return apiRequest(`/v1/projects/${projectId}/findings?${query}`, { signal })
}

export function findingsMap(projectId: string, filters: FindingFilters, signal?: AbortSignal): Promise<FindingsMap> {
  return apiRequest(`/v1/projects/${projectId}/findings.geojson?${filtersToQuery(filters)}`, { signal })
}

export function getFinding(findingId: string, signal?: AbortSignal): Promise<Finding> {
  return apiRequest(`/v1/findings/${findingId}`, { signal })
}

export function reviewFinding(findingId: string, body: ReviewRequest): Promise<Finding> {
  return apiRequest(`/v1/findings/${findingId}/review`, { method: 'POST', body })
}

export function findingHistory(findingId: string, signal?: AbortSignal): Promise<ReviewEvent[]> {
  return apiRequest(`/v1/findings/${findingId}/history`, { signal })
}

export function addManualFinding(projectId: string, body: ManualFindingRequest): Promise<Finding> {
  return apiRequest(`/v1/projects/${projectId}/findings`, { method: 'POST', body })
}

export function getReviewOptions(projectId: string, signal?: AbortSignal): Promise<ReviewOptions> {
  return apiRequest(`/v1/projects/${projectId}/review-options`, { signal })
}

export function listSeverityRubrics(orgId: string, signal?: AbortSignal): Promise<Page<SeverityRubric>> {
  return apiRequest(`/v1/organizations/${orgId}/severity-rubrics`, { signal })
}
