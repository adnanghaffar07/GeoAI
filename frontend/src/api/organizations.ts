/** Organization team management (api-spec §3.3). */

import type { OrgRole } from '@/api/auth'
import { apiRequest } from '@/lib/api-client'

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface Member {
  user_id: string
  email: string
  full_name: string
  org_role: OrgRole
  is_active: boolean
  joined_at: string
}

export interface Invitation {
  id: string
  email: string
  org_role: OrgRole
  expires_at: string
  created_at: string
}

export const orgQueryKeys = {
  members: (orgId: string) => ['organizations', orgId, 'members'] as const,
  invitations: (orgId: string) => ['organizations', orgId, 'invitations'] as const,
}

const base = (orgId: string) => `/v1/organizations/${orgId}`

export function listMembers(orgId: string, signal?: AbortSignal): Promise<Page<Member>> {
  return apiRequest(`${base(orgId)}/members`, { signal })
}

export function changeMemberRole(orgId: string, userId: string, orgRole: OrgRole): Promise<Member> {
  return apiRequest(`${base(orgId)}/members/${userId}`, {
    method: 'PATCH',
    body: { org_role: orgRole },
  })
}

export function removeMember(orgId: string, userId: string): Promise<null> {
  return apiRequest(`${base(orgId)}/members/${userId}`, { method: 'DELETE' })
}

export function createPasswordReset(
  orgId: string,
  userId: string,
): Promise<{ reset_url: string; expires_at: string }> {
  return apiRequest(`${base(orgId)}/members/${userId}/password-reset`, { method: 'POST' })
}

export function listInvitations(orgId: string, signal?: AbortSignal): Promise<Page<Invitation>> {
  return apiRequest(`${base(orgId)}/invitations`, { signal })
}

export function createInvitation(
  orgId: string,
  email: string,
  orgRole: OrgRole,
): Promise<Invitation & { invite_url: string }> {
  return apiRequest(`${base(orgId)}/invitations`, {
    method: 'POST',
    body: { email, org_role: orgRole },
  })
}

export function revokeInvitation(orgId: string, invitationId: string): Promise<null> {
  return apiRequest(`${base(orgId)}/invitations/${invitationId}`, { method: 'DELETE' })
}
