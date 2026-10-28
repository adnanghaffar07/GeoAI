import { useQuery } from '@tanstack/react-query'
import { Archive, Building2, FolderKanban, History, LayoutDashboard, Menu, Tags, UserRound, Users, X, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'

import { listOrganizationRequests, platformQueryKeys } from '@/api/platform'
import { useAuth } from '@/auth/auth-context'
import { BrandName } from '@/components/brand-mark'
import { SignOutButton } from '@/components/sign-out-button'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Shown only if the user has this permission in the current organization. */
  permission?: string
}

/** Everyday pages. */
const MAIN_ITEMS: NavItem[] = [
  { to: '/', label: 'Home', icon: LayoutDashboard },
  { to: '/projects', label: 'Projects', icon: FolderKanban, permission: 'org.view' },
  { to: '/account', label: 'My account', icon: UserRound },
]

/** Organization settings, mostly for administrators; the group is hidden when none are allowed. */
const SETTINGS_ITEMS: NavItem[] = [
  { to: '/settings/team', label: 'Team', icon: Users, permission: 'org.members.view' },
  { to: '/settings/catalog', label: 'Finding types', icon: Tags, permission: 'org.settings.edit' },
  { to: '/settings/history', label: 'Activity history', icon: History, permission: 'org.audit.view' },
  { to: '/settings/retention', label: 'Data retention', icon: Archive, permission: 'org.retention.edit' },
]

/** Platform admins only (CR-004). */
const PLATFORM_ITEM: NavItem = { to: '/platform/requests', label: 'Organization requests', icon: Building2 }

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')

/** App frame: dark left menu on desktop, a top bar with a slide-down menu on phones (ui-screens §1). */
export function AppLayout() {
  const auth = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const allowed = (item: NavItem) => !item.permission || auth.can(item.permission)
  const mainItems = MAIN_ITEMS.filter(allowed)
  const settingsItems = SETTINGS_ITEMS.filter(allowed)
  const name = auth.me?.user.full_name ?? ''
  const isPlatformAdmin = Boolean(auth.me?.user.is_platform_admin)
  // Number of waiting requests beside the menu item (refreshed every few minutes).
  const waiting = useQuery({
    queryKey: platformQueryKeys.list('pending'),
    queryFn: ({ signal }) => listOrganizationRequests('pending', signal),
    enabled: isPlatformAdmin,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  })

  return (
    <div className="min-h-screen md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded-lg focus:bg-white focus:p-3">
        Skip to content
      </a>

      <div className="flex items-center justify-between bg-asphalt-900 px-4 py-3 md:hidden">
        <BrandName tone="light" />
        <button
          type="button"
          aria-expanded={menuOpen}
          aria-controls="main-menu"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          onClick={() => setMenuOpen((open) => !open)}
          className="rounded-lg p-2 text-white hover:bg-white/10"
        >
          {menuOpen ? <X className="size-5" aria-hidden /> : <Menu className="size-5" aria-hidden />}
        </button>
      </div>

      <aside
        id="main-menu"
        className={cn(
          'w-full flex-col gap-7 bg-asphalt-900 px-4 pt-4 pb-5 text-asphalt-200 md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0 md:overflow-y-auto md:pt-6',
          menuOpen ? 'flex' : 'hidden',
        )}
      >
        <div className="hidden px-2 md:block">
          <BrandName tone="light" />
        </div>
        <OrganizationSwitcher />
        <nav aria-label="Main" className="flex flex-col gap-1 text-[15px]">
          {mainItems.map((item) => (
            <MenuLink key={item.to} item={item} onNavigate={() => setMenuOpen(false)} />
          ))}
          {settingsItems.length > 0 && (
            <>
              <p className="mt-5 mb-1 px-3 text-xs font-semibold tracking-wide text-asphalt-300 uppercase">Organization settings</p>
              {settingsItems.map((item) => (
                <MenuLink key={item.to} item={item} onNavigate={() => setMenuOpen(false)} />
              ))}
            </>
          )}
          {isPlatformAdmin && (
            <>
              <p className="mt-5 mb-1 px-3 text-xs font-semibold tracking-wide text-asphalt-300 uppercase">Platform</p>
              <MenuLink item={PLATFORM_ITEM} badge={waiting.data?.pending_count} onNavigate={() => setMenuOpen(false)} />
            </>
          )}
        </nav>
        <div className="mt-auto flex items-center gap-3 rounded-xl bg-white/5 p-3">
          <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-lane-500 text-sm font-bold text-asphalt-950">
            {initials(name)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">{name}</p>
            <p className="truncate text-xs text-asphalt-300">{auth.me?.user.email}</p>
          </div>
          <SignOutButton compact />
        </div>
      </aside>

      <main id="main" className="min-w-0 flex-1 px-4 py-8 sm:px-6 md:px-10 md:py-10">
        <div key={location.pathname.split('/').slice(0, 3).join('/')} className="page-enter mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

function MenuLink({ item, badge, onNavigate }: { item: NavItem; badge?: number; onNavigate: () => void }) {
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 font-medium transition-colors',
          isActive ? 'bg-white/10 text-white' : 'text-asphalt-200 hover:bg-white/5 hover:text-white',
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Yellow lane marker beside the current page. */}
          <span
            aria-hidden
            className={cn('absolute top-2 bottom-2 -left-4 w-1 rounded-r bg-lane-500 transition-opacity', isActive ? 'opacity-100' : 'opacity-0')}
          />
          <item.icon className={cn('size-[18px]', isActive ? 'text-lane-400' : 'text-asphalt-300 group-hover:text-white')} aria-hidden />
          {item.label}
          {badge !== undefined && badge > 0 && (
            <span className="ml-auto rounded-full bg-lane-500 px-2 py-0.5 text-xs font-bold text-asphalt-950 tabular-nums">
              {badge}
              <span className="sr-only"> waiting</span>
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}

function OrganizationSwitcher() {
  const auth = useAuth()
  const memberships = auth.me?.memberships ?? []
  if (memberships.length === 0) return null
  if (memberships.length === 1) {
    return (
      <div className="rounded-lg border border-white/10 px-3 py-2">
        <p className="text-xs text-asphalt-300">Organization</p>
        <p className="truncate text-sm font-semibold text-white">{memberships[0]?.organization_name}</p>
      </div>
    )
  }
  return (
    <label className="block rounded-lg border border-white/10 px-3 py-2 text-sm">
      <span className="block text-xs text-asphalt-300">Organization</span>
      <select
        value={auth.currentMembership?.organization_id}
        onChange={(event) => auth.setCurrentOrganization(event.target.value)}
        className="mt-0.5 w-full cursor-pointer bg-transparent font-semibold text-white focus:outline-none [&>option]:text-asphalt-900"
      >
        {memberships.map((membership) => (
          <option key={membership.organization_id} value={membership.organization_id}>
            {membership.organization_name}
          </option>
        ))}
      </select>
    </label>
  )
}
