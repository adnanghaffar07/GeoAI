/**
 * Who is signed in, which organization they are working in, and what they may do.
 *
 * Screens ask `can('org.members.invite')`, never "is this an admin?", so permission
 * decisions can change on the server without changing screens (permission-matrix §6).
 * Screens also never depend on *how* someone signed in (owner's standing note).
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

import { authQueryKeys, getMe, type Me, type Membership } from '@/api/auth'
import { isApiError } from '@/lib/api-client'
import { logger } from '@/lib/logger'

const CURRENT_ORG_KEY = 'geoinfralens.currentOrganizationId'

interface AuthState {
  status: 'loading' | 'signed_out' | 'signed_in' | 'error'
  me: Me | null
  error: unknown
  currentMembership: Membership | null
  setCurrentOrganization: (organizationId: string) => void
  can: (permission: string) => boolean
  /** Store the result of a fresh sign-in. */
  setSignedIn: (me: Me) => void
  /** Forget everything cached about the previous user. */
  clearSession: () => void
  retry: () => void
}

const AuthContext = createContext<AuthState | null>(null)

function readStoredOrgId(): string | null {
  try {
    return window.localStorage.getItem(CURRENT_ORG_KEY)
  } catch {
    return null // storage can be blocked (private mode); the first organization is used
  }
}

function storeOrgId(organizationId: string): void {
  try {
    window.localStorage.setItem(CURRENT_ORG_KEY, organizationId)
  } catch {
    // Not critical: only a convenience for the next visit.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [preferredOrgId, setPreferredOrgId] = useState<string | null>(readStoredOrgId)

  const meQuery = useQuery({
    queryKey: authQueryKeys.me,
    queryFn: async ({ signal }) => {
      try {
        return await getMe(signal)
      } catch (error) {
        if (isApiError(error) && error.status === 401) return null // simply signed out
        throw error
      }
    },
    staleTime: 60_000,
  })

  const me = meQuery.data ?? null
  const currentMembership = useMemo(() => {
    if (!me || me.memberships.length === 0) return null
    return me.memberships.find((m) => m.organization_id === preferredOrgId) ?? me.memberships[0] ?? null
  }, [me, preferredOrgId])

  const setCurrentOrganization = useCallback((organizationId: string) => {
    setPreferredOrgId(organizationId)
    storeOrgId(organizationId)
  }, [])

  const can = useCallback(
    (permission: string) => currentMembership?.permissions.includes(permission) ?? false,
    [currentMembership],
  )

  const setSignedIn = useCallback(
    (fresh: Me) => {
      logger.info(`Signed in (${fresh.memberships.length} organization(s))`)
      queryClient.setQueryData(authQueryKeys.me, fresh)
    },
    [queryClient],
  )

  const clearSession = useCallback(() => {
    // First mark "nobody is signed in" on the same stored answer the screens are watching,
    // then forget everything else. (Clearing everything first left the screens holding the
    // old "signed in" answer, so the sign-in page bounced back to Overview.)
    queryClient.setQueryData(authQueryKeys.me, null)
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== authQueryKeys.me[0] })
    logger.info('Signed out: cached data cleared')
  }, [queryClient])

  let status: AuthState['status'] = 'loading'
  if (meQuery.isError) status = 'error'
  else if (meQuery.isSuccess) status = me ? 'signed_in' : 'signed_out'

  const value: AuthState = {
    status,
    me,
    error: meQuery.error,
    currentMembership,
    setCurrentOrganization,
    can,
    setSignedIn,
    clearSession,
    retry: () => void meQuery.refetch(),
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components -- hook belongs with its provider
export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
