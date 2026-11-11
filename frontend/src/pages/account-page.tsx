import { useQuery } from '@tanstack/react-query'
import { Building2, ChevronRight, Database, KeyRound, LogOut, Mail, UserRound } from 'lucide-react'
import { Link } from 'react-router'

import { roleLabel } from '@/api/auth'
import { dataStorageQueryKeys, getDataStorage } from '@/api/data-storage'
import { useAuth } from '@/auth/auth-context'
import { SignOutButton } from '@/components/sign-out-button'
import { DataStorageSummary } from '@/pages/settings-data-storage-page'

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')

function SectionTitle({ icon: Icon, children }: { icon: typeof Mail; children: string }) {
  return (
    <h2 className="flex items-center gap-2 text-lg font-semibold text-asphalt-900">
      <span className="flex size-8 items-center justify-center rounded-lg bg-lane-400 text-asphalt-900" aria-hidden>
        <Icon className="size-4" />
      </span>
      {children}
    </h2>
  )
}

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
    <section className="w-full space-y-6">
      <header className="flex flex-wrap items-center gap-5 rounded-2xl bg-asphalt-900 p-6 text-white shadow-sm">
        <span className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-lane-400 text-2xl font-bold text-asphalt-900" aria-hidden>
          {initials(me.user.full_name) || <UserRound className="size-7" />}
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">My account</h1>
          <p className="mt-1 truncate text-asphalt-200">
            {me.user.full_name} · {me.user.email}
          </p>
        </div>
        <SignOutButton />
      </header>

      <div className="grid gap-6 xl:grid-cols-2">
        <section aria-label="Profile" className="space-y-3 rounded-2xl border border-asphalt-100 bg-white p-5 shadow-sm">
          <SectionTitle icon={UserRound}>Profile</SectionTitle>
          <dl className="divide-y divide-asphalt-100">
            <div className="flex items-center gap-3 py-3">
              <dt className="flex w-24 shrink-0 items-center gap-2 text-sm text-asphalt-500">
                <UserRound className="size-4" aria-hidden />
                Name
              </dt>
              <dd className="font-medium text-asphalt-900">{me.user.full_name}</dd>
            </div>
            <div className="flex items-center gap-3 py-3">
              <dt className="flex w-24 shrink-0 items-center gap-2 text-sm text-asphalt-500">
                <Mail className="size-4" aria-hidden />
                Email
              </dt>
              <dd className="min-w-0 font-medium break-all text-asphalt-900">{me.user.email}</dd>
            </div>
          </dl>
          <p className="flex gap-2 rounded-xl bg-asphalt-50 p-3 text-sm text-asphalt-600">
            <KeyRound className="mt-0.5 size-4 shrink-0" aria-hidden />
            To change your password, ask your administrator to make a password reset link for you.
          </p>
        </section>

        <section aria-label="Organizations" className="space-y-3 rounded-2xl border border-asphalt-100 bg-white p-5 shadow-sm">
          <SectionTitle icon={Building2}>Organizations</SectionTitle>
          <ul className="space-y-2">
            {me.memberships.map((membership) => (
              <li key={membership.organization_id} className="flex items-center gap-3 rounded-xl border border-asphalt-100 p-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-asphalt-50 font-semibold text-asphalt-700" aria-hidden>
                  {initials(membership.organization_name)}
                </span>
                <span className="min-w-0 flex-1 truncate font-medium text-asphalt-900">{membership.organization_name}</span>
                <span className="rounded-full bg-lane-50 px-3 py-1 text-xs font-semibold text-asphalt-800 ring-1 ring-lane-300">{roleLabel(membership.org_role)}</span>
              </li>
            ))}
            {me.memberships.length === 0 && <li className="rounded-xl bg-asphalt-50 p-3 text-sm text-asphalt-500">You are not part of any organization yet.</li>}
          </ul>
        </section>
      </div>

      {storage.data && (
        <section aria-label="Where your data is stored" className="space-y-3 rounded-2xl border border-asphalt-100 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SectionTitle icon={Database}>Where your data is stored</SectionTitle>
            <Link to="/settings/data-storage" className="inline-flex items-center gap-1 text-sm font-medium text-asphalt-800 underline underline-offset-2">
              {storage.data.can_edit ? 'Change where files are kept' : 'More about data storage'}
              <ChevronRight className="size-4" aria-hidden />
            </Link>
          </div>
          <DataStorageSummary storage={storage.data} />
        </section>
      )}

      <p className="flex items-center gap-2 text-xs text-asphalt-500">
        <LogOut className="size-3.5" aria-hidden />
        Signing out ends your session on this device. You will be asked to agree to the terms again when you sign in.
      </p>
    </section>
  )
}
