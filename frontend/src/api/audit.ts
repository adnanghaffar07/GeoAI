/** History (audit log) of an organization or a project (FR-53). */

import type { Page } from '@/api/organizations'
import { apiRequest } from '@/lib/api-client'

export interface AuditEvent {
  id: string
  action: string
  actor_user_id: string | null
  actor_email: string | null
  actor_roles: string[]
  target_type: string | null
  target_id: string | null
  details: Record<string, unknown>
  request_id: string | null
  created_at: string
}

export interface AuditFilters {
  action?: string
  actor_user_id?: string
  since?: string
  until?: string
  page?: number
}

export function listAuditEvents(scope: { orgId: string } | { projectId: string }, filters: AuditFilters, signal?: AbortSignal): Promise<Page<AuditEvent>> {
  const base = 'orgId' in scope ? `/v1/organizations/${scope.orgId}/audit-events` : `/v1/projects/${scope.projectId}/audit-events`
  const query = new URLSearchParams({ page: String(filters.page ?? 1), page_size: '50' })
  if (filters.action) query.set('action', filters.action)
  if (filters.actor_user_id) query.set('actor_user_id', filters.actor_user_id)
  if (filters.since) query.set('since', filters.since)
  if (filters.until) query.set('until', filters.until)
  return apiRequest(`${base}?${query}`, { signal })
}

/** Plain-language names for history entries. */
export const ACTION_LABELS: Record<string, string> = {
  'auth.signed_in': 'Signed in',
  'auth.sign_in_failed': 'Failed sign-in',
  'auth.signed_out': 'Signed out',
  'invitation.created': 'Invited a person',
  'invitation.revoked': 'Cancelled an invitation',
  'invitation.accepted': 'Accepted an invitation',
  'password_reset.created': 'Created a password reset link',
  'password_reset.used': 'Used a password reset link',
  'member.role_changed': 'Changed an organization role',
  'member.removed': 'Removed a person from the organization',
  'organization.created': 'Organization created',
  'organization.settings_changed': 'Changed organization settings',
  'project.created': 'Created the project',
  'project.changed': 'Changed project details',
  'project.archived': 'Archived the project',
  'project_member.added': 'Gave a project role',
  'project_member.removed': 'Removed a project role',
  'image.withdrawn': 'Withdrew a photo',
  'image.location_set': 'Set a photo location',
  'analysis.started': 'Started AI analysis',
  'priority_config.created': 'Saved inspection priority settings',
  'inspection.planned': 'Planned an inspection',
  'inspection.inspected': 'Marked an inspection inspected',
  'inspection.evidence_added': 'Added an inspection photo',
  'inspection.resolved': 'Resolved an inspection',
  'inspection.reopened': 'Reopened an inspection',
  'report.generated': 'Requested a report',
  'report.shared': 'Shared a report with viewers',
  'report.unshared': 'Stopped sharing a report',
  'report.downloaded': 'Downloaded a report',
}

export const actionLabel = (action: string) => ACTION_LABELS[action] ?? action
