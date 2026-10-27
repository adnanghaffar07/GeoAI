/** Projects, project teams and finding types (api-spec §3.4). */

import type { Page } from '@/api/organizations'
import { apiRequest } from '@/lib/api-client'

/** A survey area in GeoJSON (longitude, latitude). */
export type AreaGeometry = { type: 'Polygon'; coordinates: number[][][] } | { type: 'MultiPolygon'; coordinates: number[][][][] }

export interface ProjectCounts {
  images: number
  images_missing_location: number
  images_with_quality_flags: number
  /** Photos analysed by the current AI model version. */
  images_analysed: number
  /** Photos the current AI model has not been asked to check yet ("Check new photos" sends these). */
  images_waiting_for_ai?: number
  /** AI suggestions not yet reviewed by a person. */
  findings_to_review: number
  findings_needs_field_check: number
  findings_verified: number
  /** Verified findings whose position no reviewer has confirmed (includes no location). */
  verified_location_unconfirmed: number
  verified_by_type: Record<string, number>
  /** Inspections planned or inspected, not yet resolved. */
  inspections_open: number
}

export interface ProjectSummary {
  id: string
  organization_id: string
  name: string
  archived: boolean
  created_at: string
  my_roles: string[]
  counts: ProjectCounts
}

export interface ProjectDetail extends ProjectSummary {
  boundary: AreaGeometry
  finding_type_keys: string[]
  road_category: string | null
  survey_start: string | null
  survey_end: string | null
  partner_reference: string | null
  archived_at: string | null
  /** What the signed-in person may do in this project; buttons are shown from this. */
  my_permissions: string[]
}

export interface ProjectInput {
  name: string
  boundary: AreaGeometry
  finding_type_keys: string[]
  road_category: string | null
  survey_start: string | null
  survey_end: string | null
  partner_reference: string | null
}

export type ProjectRole = 'project_manager' | 'field_collector' | 'technical_reviewer' | 'viewer'

export interface ProjectMember {
  id: string
  user_id: string
  email: string
  full_name: string
  role: ProjectRole
  added_at: string
}

export interface EligibleMember {
  user_id: string
  email: string
  full_name: string
  org_role: string
}

export interface FindingType {
  key: string
  label: string
  source: 'ai' | 'manual'
  is_placeholder: boolean
  is_active: boolean
}

/** Plain-language names for project roles, with what each one does. */
export const PROJECT_ROLES: { value: ProjectRole; label: string; description: string }[] = [
  { value: 'project_manager', label: 'Project manager', description: 'Runs the project: settings, team, photos and reports.' },
  { value: 'field_collector', label: 'Field collector', description: 'Uploads photos and sees their own uploads.' },
  { value: 'technical_reviewer', label: 'Technical reviewer', description: 'Checks the AI suggestions and confirms or rejects them.' },
  { value: 'viewer', label: 'Viewer', description: 'Sees verified results only.' },
]

export function projectRoleLabel(role: string): string {
  return PROJECT_ROLES.find((item) => item.value === role)?.label ?? role
}

export const projectQueryKeys = {
  all: ['projects'] as const,
  list: (orgId: string, includeArchived: boolean) => ['projects', 'list', orgId, includeArchived] as const,
  detail: (projectId: string) => ['projects', projectId] as const,
  members: (projectId: string) => ['projects', projectId, 'members'] as const,
  eligible: (projectId: string) => ['projects', projectId, 'eligible-members'] as const,
  findingTypes: (orgId: string) => ['organizations', orgId, 'finding-types'] as const,
}

export function listProjects(orgId: string, includeArchived: boolean, signal?: AbortSignal): Promise<Page<ProjectSummary>> {
  const query = includeArchived ? '?include_archived=true' : ''
  return apiRequest(`/v1/organizations/${orgId}/projects${query}`, { signal })
}

export function createProject(orgId: string, body: ProjectInput & { reviewer_user_ids: string[] }): Promise<ProjectSummary> {
  return apiRequest(`/v1/organizations/${orgId}/projects`, { method: 'POST', body })
}

export function getProject(projectId: string, signal?: AbortSignal): Promise<ProjectDetail> {
  return apiRequest(`/v1/projects/${projectId}`, { signal })
}

export function updateProject(projectId: string, body: Partial<ProjectInput>): Promise<ProjectDetail> {
  return apiRequest(`/v1/projects/${projectId}`, { method: 'PATCH', body })
}

export function archiveProject(projectId: string): Promise<ProjectDetail> {
  return apiRequest(`/v1/projects/${projectId}/archive`, { method: 'POST' })
}

export function listProjectMembers(projectId: string, signal?: AbortSignal): Promise<Page<ProjectMember>> {
  return apiRequest(`/v1/projects/${projectId}/members`, { signal })
}

export function listEligibleMembers(projectId: string, signal?: AbortSignal): Promise<Page<EligibleMember>> {
  return apiRequest(`/v1/projects/${projectId}/eligible-members`, { signal })
}

export function addProjectMember(projectId: string, userId: string, role: ProjectRole): Promise<ProjectMember> {
  return apiRequest(`/v1/projects/${projectId}/members`, { method: 'POST', body: { user_id: userId, role } })
}

export function removeProjectMember(projectId: string, memberId: string): Promise<null> {
  return apiRequest(`/v1/projects/${projectId}/members/${memberId}`, { method: 'DELETE' })
}

export function listFindingTypes(orgId: string, signal?: AbortSignal): Promise<Page<FindingType>> {
  return apiRequest(`/v1/organizations/${orgId}/finding-types`, { signal })
}
