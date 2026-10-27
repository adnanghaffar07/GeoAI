/** Inspection priority and inspections (api-spec §3.8). */

import type { Finding } from '@/api/findings'
import type { Page } from '@/api/organizations'
import { apiRequest } from '@/lib/api-client'

export const PRIORITY_INPUTS = ['severity', 'road_category', 'facility_proximity'] as const
export type PriorityInputKey = (typeof PRIORITY_INPUTS)[number]

export interface PriorityConfig {
  id: string
  version: number
  weights: Record<PriorityInputKey, number>
  severity_points: Record<string, number>
  road_category_points: Record<string, number>
  facility_types: string[]
  facility_radius_m: number
  is_placeholder: boolean
  is_current: boolean
  created_by_name: string | null
  created_at: string
}

export type PriorityConfigInput = Pick<
  PriorityConfig,
  'weights' | 'severity_points' | 'road_category_points' | 'facility_types' | 'facility_radius_m' | 'is_placeholder'
>

export interface PriorityInput {
  key: PriorityInputKey
  label: string
  value: string | null
  points: number | null
  weight: number
  contribution: number | null
  missing: boolean
  reason: string | null
}

export interface PriorityBreakdown {
  inputs: PriorityInput[]
  /** Share of the total weight that had a value (1 = nothing missing). */
  weight_covered: number
  missing: PriorityInputKey[]
}

export type InspectionState = 'planned' | 'inspected' | 'resolved' | 'reopened'

export interface Inspection {
  id: string
  finding_id: string
  owner_user_id: string
  owner_name: string | null
  planned_date: string
  status: InspectionState
  outcome_note: string | null
  has_evidence: boolean
  inspected_by_name: string | null
  inspected_at: string | null
  resolved_by_name: string | null
  resolved_at: string | null
  reopen_reason: string | null
  reopened_by_name: string | null
  reopened_at: string | null
  created_by_name: string | null
  created_at: string
}

export interface PriorityItem {
  finding: Finding
  /** "Inspection priority" (0-100). It does not decide repairs or compliance. */
  score: number
  breakdown: PriorityBreakdown
  inspection: Inspection | null
}

export interface PriorityList extends Page<PriorityItem> {
  config: PriorityConfig
}

export interface AssignedInspection {
  inspection: Inspection
  finding: Finding
}

export const INSPECTION_LABELS: Record<string, string> = {
  none: 'No inspection',
  planned: 'Inspection planned',
  inspected: 'Inspected',
  resolved: 'Resolved',
  reopened: 'Reopened',
}

export const priorityQueryKeys = {
  all: (projectId: string) => ['projects', projectId, 'priority'] as const,
  list: (projectId: string, inspectionStatus: string, page: number) => ['projects', projectId, 'priority', 'list', inspectionStatus, page] as const,
  configs: (projectId: string) => ['projects', projectId, 'priority', 'configs'] as const,
  inspections: (projectId: string, mine: boolean) => ['projects', projectId, 'priority', 'inspections', mine] as const,
  history: (findingId: string) => ['findings', findingId, 'inspections'] as const,
}

export function getPriorityList(projectId: string, options: { inspectionStatus?: string; page?: number; pageSize?: number }, signal?: AbortSignal): Promise<PriorityList> {
  const query = new URLSearchParams({ page: String(options.page ?? 1), page_size: String(options.pageSize ?? 50) })
  if (options.inspectionStatus) query.set('inspection_status', options.inspectionStatus)
  return apiRequest(`/v1/projects/${projectId}/priority-list?${query}`, { signal })
}

export function listPriorityConfigs(projectId: string, signal?: AbortSignal): Promise<Page<PriorityConfig>> {
  return apiRequest(`/v1/projects/${projectId}/priority-configs`, { signal })
}

export function savePriorityConfig(projectId: string, body: PriorityConfigInput): Promise<PriorityConfig> {
  return apiRequest(`/v1/projects/${projectId}/priority-configs`, { method: 'POST', body })
}

export function listInspections(projectId: string, mine: boolean, signal?: AbortSignal): Promise<Page<AssignedInspection>> {
  return apiRequest(`/v1/projects/${projectId}/inspections${mine ? '?mine=true' : ''}`, { signal })
}

export function inspectionHistory(findingId: string, signal?: AbortSignal): Promise<Inspection[]> {
  return apiRequest(`/v1/findings/${findingId}/inspections`, { signal })
}

export function planInspection(findingId: string, body: { owner_user_id: string; planned_date: string }): Promise<Inspection> {
  return apiRequest(`/v1/findings/${findingId}/inspections`, { method: 'POST', body })
}

export function recordInspection(inspectionId: string, body: { status: 'inspected' | 'resolved'; outcome_note?: string }): Promise<Inspection> {
  return apiRequest(`/v1/inspections/${inspectionId}`, { method: 'PATCH', body })
}

export function addEvidence(inspectionId: string, file: File): Promise<Inspection> {
  const form = new FormData()
  form.append('file', file)
  return apiRequest(`/v1/inspections/${inspectionId}/evidence`, { method: 'POST', body: form })
}

export const evidenceUrl = (inspectionId: string) => `/api/v1/inspections/${inspectionId}/evidence`

export function reopenInspection(inspectionId: string, body: { reason: string; owner_user_id: string; planned_date: string }): Promise<Inspection> {
  return apiRequest(`/v1/inspections/${inspectionId}/reopen`, { method: 'POST', body })
}
