/** Reports and exports (api-spec §3.9). */

import type { Page } from '@/api/organizations'
import { apiRequest } from '@/lib/api-client'

export type ReportFormat = 'csv' | 'geojson' | 'pdf'

export interface ReportFilters {
  type_key?: string[]
  severity_key?: string[]
  created_from?: string | null
  created_to?: string | null
  has_location?: boolean | null
}

export interface Report {
  id: string
  project_id: string
  format: ReportFormat
  filters: ReportFilters
  include_unreviewed: boolean
  settings_used: {
    severity_scale?: { version: number; is_placeholder: boolean }
    priority_settings?: { version: number; is_placeholder: boolean }
    ai_model_versions?: string[]
    includes_test_detector?: boolean
    includes_trial_model?: boolean
  }
  status: 'queued' | 'processing' | 'completed' | 'failed'
  record_count: number | null
  shared_with_viewers: boolean
  failure_reason: string | null
  requested_by_name: string | null
  created_at: string
  completed_at: string | null
  file_name: string | null
}

export const FORMAT_LABELS: Record<ReportFormat, string> = {
  csv: 'CSV table (Excel)',
  geojson: 'GeoJSON map data (GIS)',
  pdf: 'PDF summary',
}

export const reportQueryKeys = {
  list: (projectId: string) => ['projects', projectId, 'reports'] as const,
}

export function listReports(projectId: string, signal?: AbortSignal): Promise<Page<Report>> {
  return apiRequest(`/v1/projects/${projectId}/reports?page_size=100`, { signal })
}

export function requestReport(projectId: string, body: { format: ReportFormat; filters: ReportFilters; include_unreviewed: boolean }): Promise<Report> {
  return apiRequest(`/v1/projects/${projectId}/reports`, { method: 'POST', body })
}

export function shareReport(reportId: string, shared: boolean): Promise<Report> {
  return apiRequest(`/v1/reports/${reportId}/share`, { method: 'POST', body: { shared } })
}

export const reportFileUrl = (reportId: string) => `/api/v1/reports/${reportId}/file`
