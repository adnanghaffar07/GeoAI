import { useQuery } from '@tanstack/react-query'
import { FolderOpen } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { listProjects, projectQueryKeys, projectRoleLabel, type ProjectSummary } from '@/api/projects'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState } from '@/components/ui/page-intro'

/** S04 Projects overview. */
export function ProjectsPage() {
  const auth = useAuth()
  const membership = auth.currentMembership
  const [showArchived, setShowArchived] = useState(false)
  const orgId = membership?.organization_id ?? ''
  const projects = useQuery({
    queryKey: projectQueryKeys.list(orgId, showArchived),
    queryFn: ({ signal }) => listProjects(orgId, showArchived, signal),
    enabled: Boolean(membership),
  })
  if (!membership) return <p className="text-asphalt-500">You are not part of any organization yet. Ask your administrator to invite you.</p>
  const canCreate = auth.can('project.create')

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[1.75rem] font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-asphalt-500">
            Each project is one road survey in {membership.organization_name}. Open a project to see its photos and road problems.
          </p>
        </div>
        {canCreate && (
          <Link to="/projects/new" className="btn btn-accent">
            Create project
          </Link>
        )}
      </header>

      <label className="flex items-center gap-2 text-sm text-asphalt-700">
        <input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} />
        Show archived projects
      </label>

      {projects.isPending && <SkeletonRows />}
      {projects.isError && <ErrorMessage title="Could not load projects" error={projects.error} onRetry={() => void projects.refetch()} />}
      {projects.isSuccess &&
        (projects.data.items.length === 0 ? (
          showArchived ? (
            <EmptyState icon={<FolderOpen />} title="No projects found">
              There are no projects you can see, including archived ones.
            </EmptyState>
          ) : canCreate ? (
            <EmptyState
              icon={<FolderOpen />}
              title="No projects yet"
              action={
                <Link to="/projects/new" className="btn btn-accent">
                  Create your first project
                </Link>
              }
            >
              Create a project for each area of roads you want to survey.
            </EmptyState>
          ) : (
            <EmptyState icon={<FolderOpen />} title="No projects yet">
              You haven't been added to a project yet. Ask your project manager.
            </EmptyState>
          )
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects.data.items.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </ul>
        ))}
    </section>
  )
}

function ProjectCard({ project }: { project: ProjectSummary }) {
  const roles = project.my_roles.map(projectRoleLabel).join(', ')
  return (
    <li>
      <Link
        to={`/projects/${project.id}`}
        className="group relative block h-full overflow-hidden panel p-5 transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-asphalt-200 hover:shadow-[0_8px_24px_-12px_rgb(27_38_51/0.35)]"
      >
        <span aria-hidden className="absolute inset-x-0 top-0 h-1 origin-left scale-x-0 bg-lane-500 transition-transform duration-200 group-hover:scale-x-100" />
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-medium">{project.name}</h2>
          {project.archived && <span className="pill bg-asphalt-100 text-asphalt-700">Archived</span>}
        </div>
        <p className="mt-1 text-xs text-asphalt-500">{roles ? `Your role: ${roles}` : 'Organization administrator'}</p>
        <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
          <Count label="Photos" value={project.counts.images} />
          <Count label="No location" value={project.counts.images_missing_location} />
          <Count label="With warnings" value={project.counts.images_with_quality_flags} />
        </dl>
      </Link>
    </li>
  )
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-xs text-asphalt-500">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
    </div>
  )
}
