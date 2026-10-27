import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'

import { authQueryKeys, type Me } from '@/api/auth'
import { AuthProvider } from '@/auth/auth-context'

export const ADMIN_ME: Me = {
  user: { id: 'u1', email: 'admin@city.test', full_name: 'Ada Admin' },
  memberships: [
    {
      organization_id: 'org1',
      organization_name: 'City A',
      org_role: 'org_admin',
      permissions: [
        'org.view',
        'org.members.view',
        'org.members.invite',
        'org.members.change_role',
        'org.members.remove',
        'org.members.reset_password',
      ],
    },
  ],
}

/** Render a screen with the app's providers. `me: null` means signed out. */
export function renderWithProviders(ui: ReactElement, { me = ADMIN_ME, route = '/' }: { me?: Me | null; route?: string } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  queryClient.setQueryData(authQueryKeys.me, me)
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}
