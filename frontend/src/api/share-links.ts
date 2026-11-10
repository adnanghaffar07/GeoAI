/** Shareable photo links (team-lead item 9). */

import { apiRequest } from '@/lib/api-client'

export interface ShareLink {
  id: string
  image_id: string
  created_at: string
  expires_at: string
  revoked_at: string | null
  state: 'active' | 'ended' | 'cancelled'
  /** Only when the link is made: the secret is never shown again. */
  url: string | null
}

export const shareLinksKey = (imageId: string) => ['images', imageId, 'share-links'] as const

export const listShareLinks = (imageId: string, signal?: AbortSignal): Promise<ShareLink[]> => apiRequest(`/v1/images/${imageId}/share-links`, { signal })

export const createShareLink = (imageId: string, days: number): Promise<ShareLink> =>
  apiRequest(`/v1/images/${imageId}/share-links`, { method: 'POST', body: { days } })

export const revokeShareLink = (imageId: string, linkId: string): Promise<ShareLink> =>
  apiRequest(`/v1/images/${imageId}/share-links/${linkId}/revoke`, { method: 'POST' })

/** The full address to send to someone. */
export const fullLink = (url: string) => `${window.location.origin}${url}`
