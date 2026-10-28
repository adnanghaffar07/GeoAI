/** Requests from new organizations, and their review by platform admins (CR-004). */

import { apiRequest } from '@/lib/api-client'

export type RequestStatus = 'pending' | 'approved' | 'rejected'

export interface OrganizationRequestForm {
  organization_name: string
  contact_name: string
  contact_email: string
  phone?: string
  city_or_agency: string
  note?: string
  /** Hidden trap field: people leave it empty, robots fill it in. */
  website?: string
}

export interface OrganizationRequest {
  id: string
  organization_name: string
  contact_name: string
  contact_email: string
  phone: string | null
  city_or_agency: string
  note: string | null
  status: RequestStatus
  created_at: string
  decided_at: string | null
  decided_by_name: string | null
  decision_note: string | null
  organization_id: string | null
}

export interface OrganizationRequestList {
  items: OrganizationRequest[]
  pending_count: number
}

export interface InvitationLinkResult {
  request: OrganizationRequest
  invitation_url: string
  invitation_expires_at: string
}

export const platformQueryKeys = {
  all: ['platform', 'organization-requests'] as const,
  list: (status: RequestStatus) => ['platform', 'organization-requests', status] as const,
}

export function sendOrganizationRequest(body: OrganizationRequestForm): Promise<{ message: string }> {
  return apiRequest('/v1/organization-requests', { method: 'POST', body })
}

export function listOrganizationRequests(status: RequestStatus, signal?: AbortSignal): Promise<OrganizationRequestList> {
  return apiRequest(`/v1/platform/organization-requests?status=${status}`, { signal })
}

export function approveOrganizationRequest(id: string, note: string): Promise<InvitationLinkResult> {
  return apiRequest(`/v1/platform/organization-requests/${id}/approve`, { method: 'POST', body: { note: note || null } })
}

export function rejectOrganizationRequest(id: string, reason: string): Promise<OrganizationRequest> {
  return apiRequest(`/v1/platform/organization-requests/${id}/reject`, { method: 'POST', body: { reason } })
}

export function newInvitationLink(id: string): Promise<InvitationLinkResult> {
  return apiRequest(`/v1/platform/organization-requests/${id}/invitation-link`, { method: 'POST' })
}
