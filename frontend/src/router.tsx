import type { ComponentType } from 'react'
import { createBrowserRouter } from 'react-router'

import { RequireAuth } from '@/auth/require-auth'
import { AppLayout } from '@/components/app-layout'
import { RouteErrorPage } from '@/components/route-error-page'
import { LoadingScreen } from '@/components/ui/loading-screen'
import { AcceptInvitationPage } from '@/pages/accept-invitation-page'
import { AccountPage } from '@/pages/account-page'
import { CatalogPage } from '@/pages/catalog-page'
import { NotFoundPage } from '@/pages/not-found-page'
import { ProjectLayout } from '@/pages/project/project-layout'
import { MovedProjectPage, ProjectSettingsLayout } from '@/pages/project/project-settings-layout'
import { ProjectTeamPage } from '@/pages/project/project-team-page'
import { ProjectUploadPage } from '@/pages/project/project-upload-page'
import { ProjectsPage } from '@/pages/projects-page'
import { RequestAccessPage } from '@/pages/request-access-page'
import { ResetPasswordPage } from '@/pages/reset-password-page'
import { SignInPage } from '@/pages/sign-in-page'
import { TeamPage } from '@/pages/team-page'

// Pages with maps or charts load on first use: those libraries are large, and sign-in should stay fast.
const lazyPage = (load: () => Promise<{ default: ComponentType }>) => async () => ({ Component: (await load()).default })

/** All pages. Addresses follow documentation/04-design/ui-screens.md. */
export const router = createBrowserRouter([
  // Public pages (no menu): S01–S03
  { path: '/sign-in', element: <SignInPage />, errorElement: <RouteErrorPage /> },
  { path: '/invite/:token', element: <AcceptInvitationPage />, errorElement: <RouteErrorPage /> },
  { path: '/reset-password/:token', element: <ResetPasswordPage />, errorElement: <RouteErrorPage /> },
  { path: '/request-access', element: <RequestAccessPage />, errorElement: <RouteErrorPage /> },
  // Signed-in app
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    errorElement: <RouteErrorPage />,
    // Shown while a page that loads on first use (see lazyPage) is fetched.
    hydrateFallbackElement: <LoadingScreen />,
    children: [
      { index: true, lazy: lazyPage(() => import('@/pages/home-page').then((m) => ({ default: m.HomePage }))) },
      // S04–S07 projects and photos (P4)
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'projects/new', lazy: lazyPage(() => import('@/pages/project-form-page').then((m) => ({ default: m.NewProjectPage }))) },
      {
        path: 'projects/:projectId',
        element: <ProjectLayout />,
        children: [
          { index: true, lazy: lazyPage(() => import('@/pages/project/project-overview-page').then((m) => ({ default: m.ProjectOverviewPage }))) },
          { path: 'photos', lazy: lazyPage(() => import('@/pages/project/project-photos-page').then((m) => ({ default: m.ProjectPhotosPage }))) },
          { path: 'upload', element: <ProjectUploadPage /> },
          { path: 'findings', lazy: lazyPage(() => import('@/pages/project/project-findings-page').then((m) => ({ default: m.ProjectFindingsPage }))) },
          { path: 'priority', lazy: lazyPage(() => import('@/pages/project/project-priority-page').then((m) => ({ default: m.ProjectPriorityPage }))) },
          { path: 'reports', lazy: lazyPage(() => import('@/pages/project/project-reports-page').then((m) => ({ default: m.ProjectReportsPage }))) },
          { path: 'review/:findingId', lazy: lazyPage(() => import('@/pages/project/project-review-page').then((m) => ({ default: m.ProjectReviewPage }))) },
          // Settings tab: project details, team and history together
          {
            path: 'settings',
            element: <ProjectSettingsLayout />,
            children: [
              { index: true, lazy: lazyPage(() => import('@/pages/project-form-page').then((m) => ({ default: m.EditProjectPage }))) },
              { path: 'team', element: <ProjectTeamPage /> },
              { path: 'history', lazy: lazyPage(() => import('@/pages/project/project-history-page').then((m) => ({ default: m.ProjectHistoryPage }))) },
            ],
          },
          // Earlier addresses of those pages (bookmarks, links in emails) keep working
          { path: 'edit', element: <MovedProjectPage to="settings" /> },
          { path: 'team', element: <MovedProjectPage to="settings/team" /> },
          { path: 'history', element: <MovedProjectPage to="settings/history" /> },
        ],
      },
      { path: 'settings/team', element: <TeamPage /> },
      { path: 'settings/catalog', element: <CatalogPage /> },
      { path: 'settings/history', lazy: lazyPage(() => import('@/pages/settings-history-page').then((m) => ({ default: m.SettingsHistoryPage }))) },
      { path: 'settings/retention', lazy: lazyPage(() => import('@/pages/settings-retention-page').then((m) => ({ default: m.SettingsRetentionPage }))) },
      { path: 'account', element: <AccountPage /> },
      // Platform admins only (CR-004)
      { path: 'platform/requests', lazy: lazyPage(() => import('@/pages/platform-requests-page').then((m) => ({ default: m.PlatformRequestsPage }))) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
