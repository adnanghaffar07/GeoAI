/** AI analysis jobs (api-spec §3.6). Findings and review are in `findings.ts`. */

import type { Page } from '@/api/organizations'
import { apiRequest } from '@/lib/api-client'

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface AnalysisJob {
  id: string
  image_id: string
  image_filename: string
  model_version: string
  /** True for the stand-in test detector: its results are not real detections. */
  is_test_detector: boolean
  /** A real model that has not passed its accuracy check (labelled TRIAL MODEL). */
  is_trial_model?: boolean
  status: JobStatus
  attempts: number
  failure_reason: string | null
  /** Number of AI suggestions; null when this person may not see suggestions. */
  candidate_count: number | null
  queued_at: string
  started_at: string | null
  finished_at: string | null
}

export interface StartAnalysisResult {
  created: number
  reused: number
  jobs: AnalysisJob[]
}

export interface AnalysisJobList extends Page<AnalysisJob> {
  status_counts: Partial<Record<JobStatus, number>>
}

export const TEST_DETECTOR_LABEL = 'TEST DETECTOR: not a real detection'
export const TRIAL_MODEL_LABEL = 'TRIAL MODEL: accuracy not approved'

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: 'Waiting for the AI',
  processing: 'AI is checking…',
  completed: 'Checked by the AI',
  failed: 'AI check failed',
}

export const analysisQueryKeys = {
  jobs: (projectId: string) => ['projects', projectId, 'analysis-jobs'] as const,
}

/** Start analysis for chosen photos, or (no ids) every photo not yet analysed. Never duplicates. */
export function startAnalysis(projectId: string, imageIds?: string[]): Promise<StartAnalysisResult> {
  return apiRequest(`/v1/projects/${projectId}/analysis-jobs`, { method: 'POST', body: imageIds ? { image_ids: imageIds } : {} })
}

export function listAnalysisJobs(projectId: string, signal?: AbortSignal): Promise<AnalysisJobList> {
  return apiRequest(`/v1/projects/${projectId}/analysis-jobs?page_size=1`, { signal })
}

export function retryAnalysisJob(jobId: string): Promise<AnalysisJob> {
  return apiRequest(`/v1/analysis-jobs/${jobId}/retry`, { method: 'POST' })
}
