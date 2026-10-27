import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Users } from 'lucide-react'
import { useState } from 'react'

import {
  addProjectMember,
  listEligibleMembers,
  listProjectMembers,
  PROJECT_ROLES,
  projectQueryKeys,
  projectRoleLabel,
  removeProjectMember,
  type ProjectMember,
  type ProjectRole,
} from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { SelectField } from '@/components/ui/field'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

/** Project team: who has which project role. One person can hold several roles. */
export function ProjectTeamPage() {
  const project = useProject()
  const canManage = hasProjectPermission(project, 'project.members.manage') && !project.archived
  const members = useQuery({
    queryKey: projectQueryKeys.members(project.id),
    queryFn: ({ signal }) => listProjectMembers(project.id, signal),
  })

  return (
    <div className="max-w-4xl space-y-6">
      <PageIntro title="Project team">
        Who works on this project and what each person may do here. One person can have more than one role.
      </PageIntro>
      <details className="panel p-4 text-sm">
        <summary className="cursor-pointer font-medium">What the project roles mean</summary>
        <ul className="mt-2 space-y-1 text-asphalt-500">
          {PROJECT_ROLES.map((role) => (
            <li key={role.value}>
              <span className="font-medium text-asphalt-800">{role.label}:</span> {role.description}
            </li>
          ))}
        </ul>
      </details>

      {canManage && <AddMemberForm projectId={project.id} />}

      <div>
        <h3 className="mb-2 font-medium">People in this project</h3>
        {members.isPending && <SkeletonRows />}
        {members.isError && <ErrorMessage title="Could not load the project team" error={members.error} onRetry={() => void members.refetch()} />}
        {members.isSuccess &&
          (members.data.items.length === 0 ? (
            <EmptyState icon={<Users />} title="No one has been added to this project yet">
              {canManage ? 'Use the form above to add people from your organization.' : 'The project manager adds people to the project.'}
            </EmptyState>
          ) : (
            <div className="overflow-x-auto panel">
              <table className="responsive-table w-full text-left text-sm">
                <thead className="border-b border-asphalt-100 bg-asphalt-50 text-asphalt-500">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-medium">Name</th>
                    <th scope="col" className="px-4 py-2 font-medium">Email</th>
                    <th scope="col" className="px-4 py-2 font-medium">Project role</th>
                    <th scope="col" className="px-4 py-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {members.data.items.map((member) => (
                    <MemberRow key={member.id} projectId={project.id} member={member} canManage={canManage} />
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </div>
    </div>
  )
}

function AddMemberForm({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [userId, setUserId] = useState('')
  const [role, setRole] = useState<ProjectRole>('field_collector')
  const eligible = useQuery({
    queryKey: projectQueryKeys.eligible(projectId),
    queryFn: ({ signal }) => listEligibleMembers(projectId, signal),
  })
  const add = useMutation({
    meta: { success: 'Person added to the project' },
    mutationFn: () => addProjectMember(projectId, userId, role),
    onSuccess: () => {
      setUserId('')
      return queryClient.invalidateQueries({ queryKey: projectQueryKeys.members(projectId) })
    },
  })

  return (
    <form
      className="panel p-4"
      aria-labelledby="add-member-heading"
      onSubmit={(event) => {
        event.preventDefault()
        if (userId) add.mutate()
      }}
    >
      <h3 id="add-member-heading" className="font-medium">
        Add a person to this project
      </h3>
      <p className="mt-1 text-sm text-asphalt-500">
        Only people already in the organization can be added. To bring in someone new, invite them on the organization's Team page first.
      </p>
      {eligible.isError && <ErrorMessage title="Could not load the list of people" error={eligible.error} onRetry={() => void eligible.refetch()} />}
      <div className="mt-3 flex flex-wrap items-start gap-3">
        <SelectField label="Person" className="min-w-64 flex-1" value={userId} onChange={(event) => setUserId(event.target.value)} disabled={!eligible.isSuccess}>
          <option value="">Choose a person…</option>
          {eligible.data?.items.map((person) => (
            <option key={person.user_id} value={person.user_id}>
              {person.full_name} ({person.email})
            </option>
          ))}
        </SelectField>
        <SelectField label="Project role" className="w-52" value={role} onChange={(event) => setRole(event.target.value as ProjectRole)}>
          {PROJECT_ROLES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </SelectField>
        <Button type="submit" className="mt-6" disabled={!userId} busy={add.isPending}>
          Add to project
        </Button>
      </div>
      {add.isError && (
        <div className="mt-3">
          <ErrorMessage title="Could not add the person" error={add.error} />
        </div>
      )}
    </form>
  )
}

function MemberRow({ projectId, member, canManage }: { projectId: string; member: ProjectMember; canManage: boolean }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const removal = useMutation({
    meta: { success: 'Role removed' },
    mutationFn: () => removeProjectMember(projectId, member.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectQueryKeys.members(projectId) }),
  })

  return (
    <>
      <tr className="border-b border-asphalt-100 last:border-0">
        <td className="px-4 py-2 max-sm:font-semibold">{member.full_name}</td>
        <td data-label="Email" className="px-4 py-2 break-all text-asphalt-500">{member.email}</td>
        <td data-label="Project role" className="px-4 py-2">{projectRoleLabel(member.role)}</td>
        <td className="px-4 py-2">
          {canManage && (
            <div className="flex flex-wrap justify-end gap-2 max-sm:justify-start">
              {confirming ? (
                <>
                  <Button variant="danger" busy={removal.isPending} onClick={() => removal.mutate()}>
                    Yes, remove role
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirming(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button variant="ghost" onClick={() => setConfirming(true)} aria-label={`Remove ${member.full_name} as ${projectRoleLabel(member.role)}`}>
                  Remove role
                </Button>
              )}
            </div>
          )}
        </td>
      </tr>
      {removal.isError && (
        <tr>
          <td colSpan={4} className="px-4 pb-3">
            <ErrorMessage title={`Could not remove ${member.full_name}`} error={removal.error} />
          </td>
        </tr>
      )}
    </>
  )
}
