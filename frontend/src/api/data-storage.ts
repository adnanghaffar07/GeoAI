/** Where the organization's files are kept (team lead plan, Phase 2: bring your own storage). */

import { apiRequest } from '@/lib/api-client'

export type StorageKind = 'app' | 's3'

export interface DataStorage {
  kind: StorageKind
  place: string
  endpoint: string | null
  bucket: string | null
  region: string | null
  prefix: string | null
  access_key_id: string | null
  has_secret: boolean
  location_note: string | null
  verified_at: string | null
  updated_at: string | null
  encryption: string
  can_edit: boolean
}

export interface DataStorageInput {
  kind: StorageKind
  endpoint?: string
  bucket?: string
  region?: string
  prefix?: string
  access_key_id?: string
  /** Empty: keep the saved secret key. */
  secret_key?: string
  location_note?: string
}

export const dataStorageQueryKeys = { one: (orgId: string) => ['organizations', orgId, 'data-storage'] as const }

export function getDataStorage(orgId: string, signal?: AbortSignal): Promise<DataStorage> {
  return apiRequest(`/v1/organizations/${orgId}/data-storage`, { signal })
}

export function saveDataStorage(orgId: string, body: DataStorageInput): Promise<DataStorage> {
  return apiRequest(`/v1/organizations/${orgId}/data-storage`, { method: 'PUT', body })
}
