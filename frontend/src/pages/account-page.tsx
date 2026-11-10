import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { roleLabel } from '@/api/auth'
import { dataStorageQueryKeys, getDataStorage } from '@/api/data-storage'
import { useAuth } from '@/auth/auth-context'
import { SignOutButton } from '@/components/sign-out-button'
import { DataStorageSummary } from '@/pages/settings-data-storage-page'

/**
 * S20 My account. If the sign-in method changes later (e.g. single sign-on), only this
 * page and the sign-in pages change (owner's standing note).
 */
export function AccountPage() {
  const { me, currentMembership } = useAuth()
  const orgId = currentMembership?.organization_id ?? ''
  const storage = useQuery({ queryKey: dataStorageQueryKeys.one(orgId), queryFn: ({ signal }) => getDataStorage(orgId, signal), enabled: Boolean(orgId) })
  if (!me) return null

  return (
    <section className="max-w-xl space-y-6">
      <header>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">My account</h1>
        <p className="mt-1 text-asphalt-500">Your name, your email and the organizations you belong to.</p>
      </header>
      <dl className="grid grid-cols-[8rem_1fr] gap-y-2 panel p-4 text-sm">
        <dt className="text-asphalt-500">Name</dt>
        <dd>{me.user.full_name}</dd>
        <dt className="text-asphalt-500">Email</dt>
        <dd>{me.user.email}</dd>
      </dl>
      <div>
        <h2 className="mb-2 font-medium">Organizations</h2>
        <ul className="divide-y divide-asphalt-100 panel text-sm">
          {me.memberships.map((membership) => (
            <li key={membership.organization_id} className="flex justify-between px-4 py-2">
              <span>{membership.organization_name}</span>
              <span className="text-asphalt-500">{roleLabel(membership.org_role)}</span>
            </li>
          ))}
          {me.memberships.length === 0 && <li className="px-4 py-2 text-asphalt-500">You are not part of any organization yet.</li>}
        </ul>
      </div>
      {storage.data && (
        <div>
          <h2 className="mb-2 font-medium">Where your data is stored</h2>
          <DataStorageSummary storage={storage.data} />
          <Link to="/settings/data-storage" className="mt-2 inline-block text-sm underline">
            {storage.data.can_edit ? 'Change where files are kept' : 'More about data storage'}
          </Link>
        </div>
      )}
      <p className="text-sm text-asphalt-500">To change your password, ask your administrator to make a password reset link for you.</p>
      <SignOutButton />
    </section>
  )
}
