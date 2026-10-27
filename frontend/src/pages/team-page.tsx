import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { ORG_ROLE_LABELS, roleLabel, type OrgRole } from '@/api/auth'
import {
  changeMemberRole,
  createInvitation,
  createPasswordReset,
  listInvitations,
  listMembers,
  orgQueryKeys,
  removeMember,
  revokeInvitation,
  type Member,
} from '@/api/organizations'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { OneTimeLink } from '@/components/one-time-link'
import { Button } from '@/components/ui/button'
import { SelectField, TextField } from '@/components/ui/field'
import { SkeletonRows } from '@/components/ui/loading-screen'

const ROLE_OPTIONS = Object.entries(ORG_ROLE_LABELS) as [OrgRole, string][]

const inviteSchema = z.object({
  email: z.string().trim().min(1, 'Enter an email address.').email('Enter a valid email address.'),
  org_role: z.enum(['org_admin', 'org_manager', 'org_member']),
})
type InviteValues = z.infer<typeof inviteSchema>

const formatDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })

/** S16 Organization: team. */
export function TeamPage() {
  const auth = useAuth()
  const membership = auth.currentMembership
  if (!membership) return <p className="text-asphalt-500">You are not part of any organization yet. Ask your administrator to invite you.</p>
  return <TeamPageContent orgId={membership.organization_id} orgName={membership.organization_name} />
}

function TeamPageContent({ orgId, orgName }: { orgId: string; orgName: string }) {
  const { can } = useAuth()
  const [shownLink, setShownLink] = useState<{ title: string; url: string; note: string } | null>(null)

  return (
    <section className="space-y-8">
      <header>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">Team</h1>
        <p className="mt-1 text-asphalt-500">Everyone in {orgName}, and what each person may do across the organization.</p>
      </header>

      <aside className="panel border-l-4 border-l-lane-500 p-5 text-sm leading-relaxed text-asphalt-700" aria-label="About roles">
        <p className="font-medium">Organization roles and project roles</p>
        <p className="mt-1">
          The roles on this page (Administrator, Manager, Member) decide what someone can do across the whole organization. The work
          roles <strong>Project manager</strong>, <strong>Field collector</strong>, <strong>Technical reviewer</strong> and{' '}
          <strong>Viewer</strong> are given inside each project: open the project, then <strong>Settings</strong> and{' '}
          <strong>Team</strong>. Invite people here first, then add them to projects.
        </p>
      </aside>

      {shownLink && <OneTimeLink {...shownLink} onDone={() => setShownLink(null)} />}

      {can('org.members.invite') && (
        <InviteForm
          orgId={orgId}
          onCreated={(url) =>
            setShownLink({
              title: 'Invitation created',
              url,
              note: 'Copy this link now and send it to the person (email, chat). It works once, for 7 days, and will not be shown again.',
            })
          }
        />
      )}

      <MembersTable
        orgId={orgId}
        onResetLink={(url, name) =>
          setShownLink({
            title: `Password reset link for ${name}`,
            url,
            note: 'Copy this link now and send it to the person. It works once, for 1 hour, and will not be shown again.',
          })
        }
      />

      {can('org.members.invite') && <PendingInvitations orgId={orgId} />}
    </section>
  )
}

function InviteForm({ orgId, onCreated }: { orgId: string; onCreated: (url: string) => void }) {
  const queryClient = useQueryClient()
  const form = useForm<InviteValues>({ resolver: zodResolver(inviteSchema), defaultValues: { email: '', org_role: 'org_member' } })
  const mutation = useMutation({
    mutationFn: (values: InviteValues) => createInvitation(orgId, values.email, values.org_role),
    onSuccess: (created) => {
      form.reset({ email: '', org_role: form.getValues('org_role') })
      void queryClient.invalidateQueries({ queryKey: orgQueryKeys.invitations(orgId) })
      onCreated(created.invite_url)
    },
  })

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      className="panel p-4"
      aria-labelledby="invite-heading"
    >
      <h2 id="invite-heading" className="font-medium">
        Invite a person
      </h2>
      <p className="mt-1 text-sm text-asphalt-500">You get a link to send to them. They use it once to set up their account.</p>
      <div className="mt-3 flex flex-wrap items-start gap-3">
        <TextField label="Email" type="email" className="min-w-64 flex-1" error={form.formState.errors.email?.message} {...form.register('email')} />
        <SelectField label="Role" className="w-44" {...form.register('org_role')}>
          {ROLE_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
        <Button type="submit" className="mt-6" busy={mutation.isPending}>
          Invite
        </Button>
      </div>
      {mutation.isError && (
        <div className="mt-3">
          <ErrorMessage title="Could not create the invitation" error={mutation.error} />
        </div>
      )}
    </form>
  )
}

function MembersTable({ orgId, onResetLink }: { orgId: string; onResetLink: (url: string, name: string) => void }) {
  const members = useQuery({ queryKey: orgQueryKeys.members(orgId), queryFn: ({ signal }) => listMembers(orgId, signal) })

  return (
    <div>
      <h2 className="mb-2 font-medium">Members</h2>
      {members.isPending && <SkeletonRows />}
      {members.isError && <ErrorMessage title="Could not load members" error={members.error} onRetry={() => void members.refetch()} />}
      {members.isSuccess &&
        (members.data.items.length === 0 ? (
          <p className="text-sm text-asphalt-500">No members yet.</p>
        ) : (
          <div className="overflow-x-auto panel">
            <table className="responsive-table w-full text-left text-sm">
              <thead className="border-b border-asphalt-100 bg-asphalt-50 text-asphalt-500">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Name</th>
                  <th scope="col" className="px-4 py-2 font-medium">Email</th>
                  <th scope="col" className="px-4 py-2 font-medium">Role</th>
                  <th scope="col" className="px-4 py-2 font-medium">Joined</th>
                  <th scope="col" className="px-4 py-2 font-medium"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {members.data.items.map((member) => (
                  <MemberRow key={member.user_id} orgId={orgId} member={member} onResetLink={onResetLink} />
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </div>
  )
}

function MemberRow({ orgId, member, onResetLink }: { orgId: string; member: Member; onResetLink: (url: string, name: string) => void }) {
  const { can, me } = useAuth()
  const queryClient = useQueryClient()
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const isMe = me?.user.id === member.user_id
  const refresh = () => queryClient.invalidateQueries({ queryKey: orgQueryKeys.members(orgId) })

  const roleChange = useMutation({
    meta: { success: 'Role changed' },
    mutationFn: (role: OrgRole) => changeMemberRole(orgId, member.user_id, role),
    onSettled: refresh,
  })
  const removal = useMutation({
    meta: { success: 'Person removed from the organization' },
    mutationFn: () => removeMember(orgId, member.user_id),
    onSuccess: refresh,
  })
  const reset = useMutation({
    mutationFn: () => createPasswordReset(orgId, member.user_id),
    onSuccess: (link) => onResetLink(link.reset_url, member.full_name),
  })
  const error = roleChange.error ?? removal.error ?? reset.error

  return (
    <>
      <tr className="border-b border-asphalt-100 last:border-0">
        <td className="px-4 py-2 max-sm:font-semibold">
          {member.full_name}
          {isMe && <span className="ml-2 text-xs text-asphalt-500">(you)</span>}
        </td>
        <td data-label="Email" className="px-4 py-2 break-all text-asphalt-500">{member.email}</td>
        <td data-label="Role" className="px-4 py-2">
          {can('org.members.change_role') ? (
            <select
              aria-label={`Role for ${member.full_name}`}
              value={member.org_role}
              disabled={roleChange.isPending}
              onChange={(event) => roleChange.mutate(event.target.value as OrgRole)}
              className="rounded-lg border border-asphalt-200 bg-white px-2 py-1"
            >
              {ROLE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          ) : (
            roleLabel(member.org_role)
          )}
        </td>
        <td data-label="Joined" className="px-4 py-2 text-asphalt-500">{formatDate(member.joined_at)}</td>
        <td className="px-4 py-2">
          <div className="flex flex-wrap justify-end gap-2 max-sm:justify-start">
            {can('org.members.reset_password') && !isMe && (
              <Button variant="ghost" busy={reset.isPending} onClick={() => reset.mutate()}>
                Make password reset link
              </Button>
            )}
            {can('org.members.remove') &&
              (confirmingRemove ? (
                <>
                  <Button variant="danger" busy={removal.isPending} onClick={() => removal.mutate()}>
                    Yes, remove
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirmingRemove(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button variant="ghost" onClick={() => setConfirmingRemove(true)} title="Remove this person from the organization">
                  Remove
                </Button>
              ))}
          </div>
        </td>
      </tr>
      {error != null && (
        <tr>
          <td colSpan={5} className="px-4 pb-3">
            <ErrorMessage title={`Could not update ${member.full_name}`} error={error} />
          </td>
        </tr>
      )}
    </>
  )
}

function PendingInvitations({ orgId }: { orgId: string }) {
  const queryClient = useQueryClient()
  const invitations = useQuery({
    queryKey: orgQueryKeys.invitations(orgId),
    queryFn: ({ signal }) => listInvitations(orgId, signal),
  })
  const revoke = useMutation({
    meta: { success: 'Invitation cancelled' },
    mutationFn: (invitationId: string) => revokeInvitation(orgId, invitationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: orgQueryKeys.invitations(orgId) }),
  })

  return (
    <div>
      <h2 className="font-medium">Pending invitations</h2>
      <p className="mb-2 text-sm text-asphalt-500">Invitations that have not been used yet.</p>
      {invitations.isPending && <SkeletonRows rows={2} />}
      {invitations.isError && (
        <ErrorMessage title="Could not load invitations" error={invitations.error} onRetry={() => void invitations.refetch()} />
      )}
      {invitations.isSuccess &&
        (invitations.data.items.length === 0 ? (
          <p className="text-sm text-asphalt-500">No invitations are waiting. New invitations appear here until they are used.</p>
        ) : (
          <ul className="divide-y divide-asphalt-100 panel text-sm">
            {invitations.data.items.map((invitation) => (
              <li key={invitation.id} className="flex items-center justify-between gap-4 px-4 py-2">
                <span>
                  {invitation.email} · {roleLabel(invitation.org_role)}
                  <span className="ml-2 text-asphalt-500">link works until {formatDate(invitation.expires_at)}</span>
                </span>
                <Button variant="ghost" busy={revoke.isPending && revoke.variables === invitation.id} onClick={() => revoke.mutate(invitation.id)}>
                  Cancel invitation
                </Button>
              </li>
            ))}
          </ul>
        ))}
      {revoke.isError && <ErrorMessage title="Could not cancel the invitation" error={revoke.error} />}
    </div>
  )
}
