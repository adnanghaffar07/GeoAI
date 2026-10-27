import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck, FileText, Images, LayoutDashboard, ListOrdered, ScanSearch, Settings, type LucideIcon } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams } from 'react-router'

import { getProject, projectQueryKeys, projectRoleLabel, type ProjectDetail } from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { LoadingScreen } from '@/components/ui/loading-screen'
import { cn } from '@/lib/utils'

interface Tab {
  to: string
  label: string
  icon: LucideIcon
  /** Shown only with one of these project permissions (from the server's `my_permissions`). */
  permission?: string[]
  /** Other pages that belong to this tab (it stays highlighted there), e.g. Upload belongs to Photos. */
  alsoActiveOn?: string[]
}

/** Six tabs at most. Upload is a button on Photos; Team and History live under Settings. */
const TABS: Tab[] = [
  { to: '', label: 'Overview', icon: LayoutDashboard },
  { to: 'photos', label: 'Photos', icon: Images, permission: ['image.status.view'], alsoActiveOn: ['upload'] },
  { to: 'findings', label: 'Findings', icon: ScanSearch, permission: ['finding.view_verified'], alsoActiveOn: ['review'] },
  { to: 'priority', label: 'Priority', icon: ListOrdered, permission: ['priority.view'] },
  { to: 'priority', label: 'My inspections', icon: ClipboardCheck, permission: ['inspection.record'] },
  { to: 'reports', label: 'Reports', icon: FileText, permission: ['report.view_all', 'report.view_shared'] },
  { to: 'settings', label: 'Settings', icon: Settings },
]

/** Frame for every page inside one project: name, the person's roles, and tabs. */
export function ProjectLayout() {
  const { projectId = '' } = useParams()
  const location = useLocation()
  const project = useQuery({ queryKey: projectQueryKeys.detail(projectId), queryFn: ({ signal }) => getProject(projectId, signal) })

  if (project.isPending) return <LoadingScreen label="Loading project…" />
  if (project.isError) return <ErrorMessage title="Could not open the project" error={project.error} onRetry={() => void project.refetch()} />

  const detail = project.data
  const allowed = TABS.filter((tab) => !tab.permission || tab.permission.some((key) => detail.my_permissions.includes(key)))
  // One tab per page: people who see the priority list get "Priority", others "My inspections".
  const tabs = allowed.filter((tab, index) => allowed.findIndex((other) => other.to === tab.to) === index)
  const roles = detail.my_roles.map(projectRoleLabel).join(', ') || 'Organization administrator'

  return (
    <section className="space-y-6">
      <header className="space-y-3">
        <NavLink to="/projects" className="text-sm link">
          All projects
        </NavLink>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[1.75rem] font-semibold tracking-tight">{detail.name}</h1>
          {detail.archived && <span className="pill bg-asphalt-100 text-asphalt-700">Archived (read-only)</span>}
        </div>
        <p className="text-sm text-asphalt-500">Your role here: {roles}</p>
        <nav aria-label="Project" className="-mx-4 flex gap-1 overflow-x-auto border-b border-asphalt-100 px-4 text-sm [scrollbar-width:none] sm:mx-0 sm:px-0">
          {tabs.map((tab) => {
            const href = tab.to === '' ? `/projects/${detail.id}` : `/projects/${detail.id}/${tab.to}`
            const section = location.pathname.slice(`/projects/${detail.id}/`.length).split('/')[0] ?? ''
            const active = tab.to === '' ? location.pathname.replace(/\/$/, '') === href : section === tab.to || Boolean(tab.alsoActiveOn?.includes(section))
            return (
              <Link
                key={tab.to}
                to={href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  '-mb-px flex shrink-0 items-center gap-2 border-b-[3px] px-3 py-2.5 whitespace-nowrap font-medium text-asphalt-500 transition-colors hover:text-asphalt-900',
                  active ? 'border-lane-500 font-semibold text-asphalt-900' : 'border-transparent',
                )}
              >
                <tab.icon className={cn('size-4', active ? 'text-asphalt-900' : 'text-asphalt-400')} aria-hidden />
                {tab.label}
              </Link>
            )
          })}
        </nav>
      </header>
      <Outlet context={detail} />
    </section>
  )
}

/** The project loaded by `ProjectLayout`, for pages inside it. */
// eslint-disable-next-line react-refresh/only-export-components -- hook belongs with its layout
export function useProject(): ProjectDetail {
  return useOutletContext<ProjectDetail>()
}

/** True when the signed-in person has this permission in the project. */
// eslint-disable-next-line react-refresh/only-export-components -- small helper used with useProject
export function hasProjectPermission(project: ProjectDetail, permission: string): boolean {
  return project.my_permissions.includes(permission)
}
