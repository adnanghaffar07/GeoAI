/** The Overview dashboard (one request for all numbers and chart data). */

import { apiRequest } from '@/lib/api-client'

export type DashboardDays = 7 | 30 | 90 | null

export interface Dashboard {
  scope: { project_id: string | null; days: number | null; date_from: string; date_to: string }
  /** What this person may see; charts they may not see are not shown. */
  access: {
    photos: boolean
    photos_own_only: boolean
    candidates: boolean
    verified: boolean
    rejected: boolean
    priority: boolean
    own_inspections: boolean
  }
  totals: {
    photos: number
    photos_analysed: number
    photos_waiting_for_ai?: number
    photos_missing_location: number
    waiting_review: number
    needs_field_check: number
    verified: number
    rejected: number
    verified_location_unconfirmed: number
    inspections_open: number
    inspections_resolved: number
  }
  review_status: Partial<Record<'waiting' | 'needs_field_check' | 'verified' | 'rejected', number>>
  verified_by_type: Record<string, number>
  verified_by_severity: Record<string, number>
  inspection_status: Record<string, number>
  activity: { date: string; photos: number; suggestions: number; verified: number }[]
  top_priority: {
    finding_id: string
    project_id: string
    project_name: string
    type_key: string | null
    severity_key: string | null
    score: number
    weight_covered: number
    inspection_status: string
  }[]
  map_points: { finding_id: string; project_id: string; latitude: number; longitude: number; type_key: string | null; severity_key: string | null }[]
  map_truncated: boolean
  projects: { id: string; name: string; my_roles: string[]; photos: number; photos_waiting_for_ai?: number; waiting_review: number; verified: number; rejected: number; inspections_open: number }[]
  finding_types: { key: string; label: string }[]
  severity_levels: { key: string; label: string }[]
}

export const dashboardQueryKeys = {
  get: (orgId: string, projectId: string | null, days: DashboardDays) => ['organizations', orgId, 'dashboard', projectId, days] as const,
}

export function getDashboard(orgId: string, options: { projectId?: string | null; days: DashboardDays }, signal?: AbortSignal): Promise<Dashboard> {
  const query = new URLSearchParams()
  if (options.projectId) query.set('project_id', options.projectId)
  if (options.days) query.set('days', String(options.days))
  return apiRequest(`/v1/organizations/${orgId}/dashboard?${query}`, { signal })
}
