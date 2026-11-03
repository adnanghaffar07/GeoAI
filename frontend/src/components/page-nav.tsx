import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ChevronRight } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router'

import type { ProjectDetail } from '@/api/projects'
import { projectQueryKeys } from '@/api/projects'
import { alertQueryKeys, roadRiskQueryKeys, type RiskAlert, type SectionDetail } from '@/api/road-risk'

/**
 * Back button and breadcrumb trail on every page (owner request 2026-11-03, SQA):
 * e.g. Home > Projects > Wicker Park > Road risk > Main Street. "Back" always goes to the page one level
 * up (never the browser history), so it behaves the same however the page was opened.
 * Names come from data the page already loaded; nothing extra is fetched.
 */

interface Crumb {
  label: string
  /** Empty for a level that has no page of its own (e.g. organization "Settings"). */
  to: string | null
}

const LABELS: Record<string, string> = {
  projects: 'Projects',
  new: 'New project',
  photos: 'Photos',
  upload: 'Upload photos',
  findings: 'Findings',
  review: 'Review',
  priority: 'Priority',
  reports: 'Reports',
  settings: 'Settings',
  team: 'Team',
  history: 'History',
  'road-risk': 'Road risk',
  notifications: 'Alerts',
  account: 'My account',
  catalog: 'Finding types',
  retention: 'Data retention',
  platform: 'Platform',
  requests: 'Organization requests',
  edit: 'Edit',
}

/** Paths that are not pages of their own (shown as plain text in the trail). */
const NOT_A_PAGE = [/^\/settings$/, /^\/platform$/]

function cached<T>(queryKey: readonly unknown[]) {
  // Reads what the page loaded (and follows updates) without asking the server.
  return { queryKey, queryFn: (): Promise<T> => Promise.reject(new Error('not loaded')), enabled: false }
}

// eslint-disable-next-line react-refresh/only-export-components -- pure helper, tested on its own
export function buildCrumbs(path: string, names: { project?: string; road?: string; alert?: string }): Crumb[] {
  const parts = path.split('/').filter(Boolean)
  const crumbs: Crumb[] = [{ label: 'Home', to: '/' }]
  let at = ''
  parts.forEach((part, index) => {
    at += `/${part}`
    const before = parts[index - 1]
    let label = LABELS[part] ?? part
    if (part === 'review') {
      // A finding's review page belongs to Findings.
      crumbs.push({ label: 'Findings', to: at.replace(/review$/, 'findings') })
      return
    }
    if (before === 'projects' && part !== 'new') label = names.project ?? 'Project'
    else if (before === 'road-risk') label = names.road ?? 'Road'
    else if (before === 'notifications') label = names.alert ?? 'Alert'
    else if (before === 'review') label = 'Finding'
    const isPage = !NOT_A_PAGE.some((pattern) => pattern.test(at))
    crumbs.push({ label, to: isPage ? at : null })
  })
  return crumbs
}

export function PageNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const parts = location.pathname.split('/').filter(Boolean)
  const projectId = parts[0] === 'projects' && parts[1] && parts[1] !== 'new' ? parts[1] : ''
  const sectionId = parts[2] === 'road-risk' ? (parts[3] ?? '') : ''
  const alertId = parts[0] === 'notifications' ? (parts[1] ?? '') : ''
  const project = useQuery(cached<ProjectDetail>(projectQueryKeys.detail(projectId)))
  const road = useQuery(cached<SectionDetail>(roadRiskQueryKeys.section(projectId, sectionId)))
  const alert = useQuery(cached<RiskAlert>(alertQueryKeys.one(alertId)))

  if (parts.length === 0) return null // Home has nowhere to go back to
  const crumbs = buildCrumbs(location.pathname, {
    project: project.data?.name,
    road: road.data ? (road.data.section.name ?? 'Unnamed road') : undefined,
    alert: alert.data?.title,
  })
  const parent = [...crumbs.slice(0, -1)].reverse().find((crumb) => crumb.to)

  return (
    <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2">
      {parent?.to && (
        <button type="button" className="btn btn-secondary h-9 px-3 py-0" onClick={() => void navigate(parent.to ?? '/')}>
          <ArrowLeft className="size-4" aria-hidden />
          Back
        </button>
      )}
      <nav aria-label="Breadcrumb" className="min-w-0">
        <ol className="flex flex-wrap items-center gap-1 text-sm text-asphalt-500">
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1
            return (
              <li key={`${index}-${crumb.label}`} className="flex min-w-0 items-center gap-1">
                {index > 0 && <ChevronRight className="size-3.5 shrink-0 text-asphalt-300" aria-hidden />}
                {last || !crumb.to ? (
                  <span aria-current={last ? 'page' : undefined} className={last ? 'truncate font-semibold text-asphalt-900' : 'truncate'}>
                    {crumb.label}
                  </span>
                ) : (
                  <Link to={crumb.to} className="truncate rounded px-1 hover:bg-asphalt-100 hover:text-asphalt-900">
                    {crumb.label}
                  </Link>
                )}
              </li>
            )
          })}
        </ol>
      </nav>
    </div>
  )
}
