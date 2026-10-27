import { QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { RouterProvider } from 'react-router'

import { AuthProvider } from '@/auth/auth-context'
import { ErrorBoundary } from '@/components/error-boundary'
import { OfflineBanner } from '@/components/offline-banner'
import { Toaster } from '@/components/toaster'
import { createQueryClient } from '@/lib/query-client'
import { router } from '@/router'

/** Root component: app-wide providers, then the router. */
export function App() {
  const [queryClient] = useState(createQueryClient)

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <OfflineBanner />
          <RouterProvider router={router} />
          <Toaster />
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
