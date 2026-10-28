/** Sign-in, current user, invitation and password-reset links (api-spec §3.2). */

import { apiRequest } from '@/lib/api-client'

export interface Membership {
  organization_id: string
  organization_name: string
  org_role: OrgRole
  permissions: string[]
}

export type OrgRole = 'org_admin' | 'org_manager' | 'org_member'

export interface Me {
  /** `is_platform_admin`: may review requests from new organizations (CR-004). */
  user: { id: string; email: string; full_name: string; is_platform_admin?: boolean }
  memberships: Membership[]
}

export interface InvitationInfo {
  organization_name: string
  email: string
  org_role: OrgRole
  account_exists: boolean
}

export const authQueryKeys = {
  me: ['auth', 'me'] as const,
}

export function getMe(signal?: AbortSignal): Promise<Me> {
  return apiRequest<Me>('/v1/auth/me', { signal })
}

export function signIn(email: string, password: string): Promise<Me> {
  return apiRequest<Me>('/v1/auth/login', { method: 'POST', body: { email, password } })
}

export function signOut(): Promise<null> {
  return apiRequest<null>('/v1/auth/logout', { method: 'POST' })
}

export function getInvitation(token: string): Promise<InvitationInfo> {
  return apiRequest<InvitationInfo>(`/v1/auth/invitations/${encodeURIComponent(token)}`)
}

export function acceptInvitation(
  token: string,
  body: { full_name?: string; password?: string },
): Promise<{ result: 'signed_in' | 'sign_in_required' }> {
  return apiRequest(`/v1/auth/invitations/${encodeURIComponent(token)}/accept`, {
    method: 'POST',
    body,
  })
}

export function getPasswordReset(token: string): Promise<{ email: string }> {
  return apiRequest(`/v1/auth/password-resets/${encodeURIComponent(token)}`)
}

export function setNewPassword(token: string, password: string): Promise<null> {
  return apiRequest(`/v1/auth/password-resets/${encodeURIComponent(token)}`, {
    method: 'POST',
    body: { password },
  })
}

/** Plain-language names for roles, used everywhere on screen. */
export const ORG_ROLE_LABELS: Record<OrgRole, string> = {
  org_admin: 'Administrator',
  org_manager: 'Manager',
  org_member: 'Member',
}

export function roleLabel(role: string): string {
  return ORG_ROLE_LABELS[role as OrgRole] ?? role // unknown future roles shown as-is
}

export const PASSWORD_MIN_LENGTH = 10
