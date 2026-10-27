import { useQuery } from '@tanstack/react-query'

import { listMembers, orgQueryKeys } from '@/api/organizations'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { HistoryView } from '@/components/history-view'

/** S19 History of the whole organization (sign-ins, team changes, projects, exports…). */
export function SettingsHistoryPage() {
  const { currentMembership } = useAuth()
  const orgId = currentMembership?.organization_id ?? ''
  const members = useQuery({ queryKey: orgQueryKeys.members(orgId), queryFn: ({ signal }) => listMembers(orgId, signal), enabled: Boolean(orgId) })
  if (!currentMembership) return <p className="text-asphalt-500">You are not part of any organization yet. Ask your administrator to invite you.</p>
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">History</h1>
        <p className="mt-1 text-asphalt-500">A record of who did what in {currentMembership.organization_name}, and when. Entries can never be changed or deleted.</p>
      </header>
      {members.isError && (
        <ErrorMessage title="Could not load the list of people for the filter" error={members.error} onRetry={() => void members.refetch()} />
      )}
      <HistoryView scope={{ orgId }} people={(members.data?.items ?? []).map((member) => ({ id: member.user_id, name: member.full_name }))} />
    </section>
  )
}
