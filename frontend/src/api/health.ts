/** Backend health endpoints. Field names match the backend (snake_case, see coding conventions). */

import { apiRequest } from '@/lib/api-client'

export type CheckStatus = 'ok' | 'unavailable'

export interface ReadinessResponse {
  status: 'ok'
  checks: Record<string, CheckStatus>
}

export const healthQueryKeys = {
  readiness: ['health', 'readiness'] as const,
}

export function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>('/health/ready', { signal })
}
