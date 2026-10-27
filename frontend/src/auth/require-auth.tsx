import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { LoadingScreen } from '@/components/ui/loading-screen'

/** Shows its children only to signed-in people; others are sent to the sign-in page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth()
  const location = useLocation()

  if (auth.status === 'loading') return <LoadingScreen />
  if (auth.status === 'error') {
    return (
      <main className="mx-auto max-w-md p-8">
        <ErrorMessage title="Could not load your account" error={auth.error} onRetry={auth.retry} />
      </main>
    )
  }
  if (auth.status === 'signed_out') {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/sign-in?next=${next}`} replace />
  }
  return children
}
