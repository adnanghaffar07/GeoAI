import { NavLink, Navigate, Outlet, useOutletContext, useParams } from 'react-router'

import type { ProjectDetail } from '@/api/projects'
import { cn } from '@/lib/utils'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

/**
 * Project "Settings" tab: the project's details, its team and its history in one place,
 * so the project frame needs only six tabs (ui-screens §1).
 */
export function ProjectSettingsLayout() {
  const project = useProject()
  const base = `/projects/${project.id}/settings`
  const sections = [
    { to: base, label: 'Project details' },
    { to: `${base}/team`, label: 'Team' },
    ...(hasProjectPermission(project, 'project.audit.view') ? [{ to: `${base}/history`, label: 'History' }] : []),
  ]

  return (
    <div className="space-y-5">
      <nav aria-label="Project settings" className="flex flex-wrap gap-2">
        {sections.map((section) => (
          <NavLink
            key={section.to}
            to={section.to}
            end
            className={({ isActive }) =>
              cn(
                'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
                isActive
                  ? 'border-asphalt-900 bg-asphalt-900 text-white'
                  : 'border-asphalt-200 bg-white text-asphalt-600 hover:border-asphalt-400 hover:text-asphalt-900',
              )
            }
          >
            {section.label}
          </NavLink>
        ))}
      </nav>
      {/* Pages inside read the project with useProject(), so pass it on unchanged. */}
      <Outlet context={useOutletContext<ProjectDetail>()} />
    </div>
  )
}

/** Old project addresses (…/edit, …/team, …/history) still work: they open the same page in Settings. */
export function MovedProjectPage({ to }: { to: string }) {
  const { projectId = '' } = useParams()
  return <Navigate replace to={`/projects/${projectId}/${to}`} />
}
