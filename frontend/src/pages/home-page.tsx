import { useQuery } from '@tanstack/react-query'

import { getReadiness, healthQueryKeys } from '@/api/health'
import { useAuth } from '@/auth/auth-context'
import { DashboardView } from '@/components/dashboard/dashboard-view'
import { ErrorMessage } from '@/components/error-message'

/** Home: what to do next, then the organization dashboard (every project this person can see), then a small system status line. */
export function HomePage() {
  const { me, currentMembership } = useAuth()
  const readiness = useQuery({
    queryKey: healthQueryKeys.readiness,
    queryFn: ({ signal }) => getReadiness(signal),
  })

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">Home</h1>
        <p className="mt-1 text-asphalt-500">
          Welcome{me ? `, ${me.user.full_name}` : ''}.{' '}
          {currentMembership
            ? `You are working in ${currentMembership.organization_name}.`
            : 'You are not a member of any organization yet. Ask an administrator to invite you.'}
        </p>
      </div>

      {currentMembership && <DashboardView orgId={currentMembership.organization_id} />}

      <div className="border-t border-asphalt-100 pt-3 text-xs text-asphalt-500" aria-label="System status">
        {readiness.isPending && <p>Checking that everything is working…</p>}
        {readiness.isError && (
          <ErrorMessage
            title="Part of the app is not working right now"
            error={readiness.error}
            onRetry={() => void readiness.refetch()}
          />
        )}
        {readiness.isSuccess &&
          (Object.values(readiness.data.checks).every((status) => status === 'ok') ? (
            <p className="flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-green-600" aria-hidden />
              All systems are working.
            </p>
          ) : (
            <p role="alert" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
              <span className="font-medium">Part of the app is not working right now.</span>
              <span>
                {readiness.data.checks.queue && readiness.data.checks.queue !== 'ok'
                  ? 'Uploads still work, but AI analysis and reports may be delayed.'
                  : 'Some pages may not load.'}{' '}
                Please tell your administrator.
              </span>
            </p>
          ))}
      </div>
    </section>
  )
}
