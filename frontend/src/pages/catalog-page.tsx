import { useQuery } from '@tanstack/react-query'
import { ListX } from 'lucide-react'

import { listSeverityRubrics } from '@/api/findings'
import { listFindingTypes, projectQueryKeys } from '@/api/projects'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState } from '@/components/ui/page-intro'

/**
 * S17 Finding types and severity scale (read-only for now). Editing comes when the customer
 * sends their own list and scale (partner inputs), so placeholders are clearly marked.
 */
export function CatalogPage() {
  const { currentMembership } = useAuth()
  const orgId = currentMembership?.organization_id ?? ''
  const types = useQuery({
    queryKey: projectQueryKeys.findingTypes(orgId),
    queryFn: ({ signal }) => listFindingTypes(orgId, signal),
    enabled: Boolean(currentMembership),
  })
  const scales = useQuery({
    queryKey: ['organizations', orgId, 'severity-rubrics'],
    queryFn: ({ signal }) => listSeverityRubrics(orgId, signal),
    enabled: Boolean(currentMembership),
  })
  if (!currentMembership) return <p className="text-asphalt-500">You are not part of any organization yet. Ask your administrator to invite you.</p>
  const hasPlaceholders = types.data?.items.some((type) => type.is_placeholder)

  return (
    <section className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">Finding types</h1>
        <p className="mt-1 text-asphalt-500">
          The kinds of road problems that projects in {currentMembership.organization_name} can record, and the levels used to say how
          serious a problem is.
        </p>
      </header>
      {hasPlaceholders && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          This is a sample list (placeholder). It will be replaced by your city's own list of problem types and severity levels. You will
          be able to edit it then.
        </p>
      )}
      {types.isPending && <SkeletonRows />}
      {types.isError && <ErrorMessage title="Could not load the kinds of problems" error={types.error} onRetry={() => void types.refetch()} />}
      {types.isSuccess && types.data.items.length === 0 && (
        <EmptyState icon={<ListX />} title="No problem types yet">
          The list of problem types will appear here once it is set up.
        </EmptyState>
      )}
      {types.isSuccess && types.data.items.length > 0 && (
        <div className="overflow-x-auto panel">
          <table className="responsive-table w-full text-left text-sm">
            <thead className="border-b border-asphalt-100 bg-asphalt-50 text-asphalt-500">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Name</th>
                <th scope="col" className="px-4 py-2 font-medium">Code</th>
                <th scope="col" className="px-4 py-2 font-medium">Found by</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {types.data.items.map((type) => (
                <tr key={type.key} className="border-b border-asphalt-100 last:border-0">
                  <td className="px-4 py-2 max-sm:font-semibold">{type.label}</td>
                  <td data-label="Code" className="px-4 py-2 font-mono text-xs text-asphalt-500">{type.key}</td>
                  <td data-label="Found by" className="px-4 py-2">{type.source === 'ai' ? 'AI suggestion, checked by a reviewer' : 'Added by people'}</td>
                  <td data-label="Status" className="px-4 py-2 text-asphalt-500">
                    {type.is_active ? 'Active' : 'Not in use'}
                    {type.is_placeholder && ' · sample (placeholder)'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Severity scale</h2>
        <p className="text-sm text-asphalt-500">
          Reviewers pick one of these levels to say how serious a problem is when they verify it. The AI certainty (how sure the AI is) is
          never used as severity. If the scale changes, a new version is made, and each finding keeps the version it was reviewed with.
        </p>
        {scales.isPending && <SkeletonRows rows={2} />}
        {scales.isError && <ErrorMessage title="Could not load the severity scale" error={scales.error} onRetry={() => void scales.refetch()} />}
        {scales.isSuccess &&
          scales.data.items.map((scale) => (
            <div key={scale.id} className="panel space-y-2 p-4">
              <p className="text-sm font-medium">
                Version {scale.version}
                {scale.is_current && <span className="ml-2 pill bg-emerald-100 text-emerald-900">In use</span>}
                {scale.is_placeholder && <span className="ml-2 pill bg-amber-100 text-amber-900">Sample (placeholder)</span>}
              </p>
              <ol className="space-y-1 text-sm">
                {scale.levels.map((level) => (
                  <li key={level.key}>
                    <span className="font-medium">{level.label}</span>
                    <span className="text-asphalt-500"> · {level.definition || 'Description to come from your city'}</span>
                  </li>
                ))}
              </ol>
            </div>
          ))}
      </section>
    </section>
  )
}
