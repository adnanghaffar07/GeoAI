import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { authQueryKeys } from '@/api/auth'
import type { Finding } from '@/api/findings'
import type { ProjectDetail } from '@/api/projects'
import { AuthProvider } from '@/auth/auth-context'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectReviewPage } from '@/pages/project/project-review-page'
import { json, makeFinding, page, PROJECT, REVIEW_OPTIONS, REVIEWER_PROJECT } from '@/test/fixtures'
import { ADMIN_ME } from '@/test/render'

vi.mock('@/components/map/pick-location-map', () => ({
  PickLocationMap: ({ onPick, label }: { onPick: (point: { latitude: number; longitude: number }) => void; label?: string }) => (
    <button type="button" aria-label={label} onClick={() => onPick({ latitude: 37.776, longitude: -122.421 })}>
      map
    </button>
  ),
}))

interface Server {
  project?: ProjectDetail
  finding?: Finding
  review?: (body: Record<string, unknown>) => Response
}

/** Render the review screen inside a real (in-memory) router, as in the app. */
function renderReview({ project = REVIEWER_PROJECT, finding = makeFinding(), review }: Server = {}) {
  const posts: Record<string, unknown>[] = []
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (init?.method === 'POST' && url.includes('/review')) {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      posts.push(body)
      return Promise.resolve(review ? review(body) : json({ ...finding, version: finding.version + 1, review_status: 'verified' }))
    }
    if (url.includes('/review-options')) return Promise.resolve(json(REVIEW_OPTIONS))
    if (url.includes('/history')) return Promise.resolve(json([]))
    if (url.includes('/findings?')) return Promise.resolve(json(page([finding, makeFinding({ id: 'f2' })])))
    if (url.includes('/v1/findings/f2')) return Promise.resolve(json(makeFinding({ id: 'f2', predicted_type_key: 'surface_cracking' })))
    if (url.includes(`/v1/findings/${finding.id}`)) return Promise.resolve(json(finding))
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(project))
    return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
  })
  const router = createMemoryRouter(
    [
      {
        path: '/projects/:projectId',
        element: <ProjectLayout />,
        children: [
          { path: 'review/:findingId', element: <ProjectReviewPage /> },
          { path: 'findings', element: <p>Findings list</p> },
        ],
      },
    ],
    { initialEntries: [`/projects/p1/review/${finding.id}`] },
  )
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  queryClient.setQueryData(authQueryKeys.me, ADMIN_ME)
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return { posts, router, fetchMock }
}

describe('Review finding', () => {
  it('needs a type and a severity chosen by the reviewer before verifying', async () => {
    const { posts } = renderReview()
    await userEvent.click(await screen.findByRole('button', { name: 'Verify' }))

    expect(screen.getByText('Choose a type and a severity before verifying.')).toBeInTheDocument()
    expect(posts).toHaveLength(0)
    // The AI's guess is shown as a suggestion only: the type box starts empty.
    expect(screen.getByLabelText('Type')).toHaveValue('')
    expect(screen.getByText(/AI certainty 91%/)).toBeInTheDocument()
    expect(screen.getByText(/not how serious the problem is/)).toBeInTheDocument()
    expect(screen.getByText('TEST DETECTOR: not a real detection')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: 'Medium' }))
    expect(screen.queryByText('Choose a type and a severity before verifying.')).not.toBeInTheDocument()
  })

  it('verifies with the chosen values and then opens the next finding', async () => {
    const { posts, router } = renderReview()
    await userEvent.click(await screen.findByRole('button', { name: /Use the AI's suggestion/ }))
    await userEvent.click(screen.getByRole('radio', { name: 'Medium' }))
    await userEvent.click(screen.getByRole('button', { name: "Map: click to move the finding's pin" }))
    await userEvent.click(screen.getByRole('button', { name: 'Verify' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/p1/review/f2'))
    expect(posts).toEqual([
      { action: 'verify', version: 1, type_key: 'pothole', severity_key: 'medium', corrected_location: { latitude: 37.776, longitude: -122.421 } },
    ])
  })

  it('tells the reviewer to reload when someone else saved first', async () => {
    renderReview({
      review: () =>
        json(
          { error: { code: 'conflict', message: 'This finding was changed by someone else. Reload to see the latest version.', details: { current_version: 2 }, request_id: 'x' } },
          409,
        ),
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }))

    expect(await screen.findByText('This finding was changed by someone else.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  })

  it('supports keyboard shortcuts, but not while typing', async () => {
    const { posts } = renderReview()
    const notes = await screen.findByLabelText('Notes')

    await userEvent.type(notes, 'r')
    expect(posts).toHaveLength(0)

    notes.blur()
    await userEvent.keyboard('f')

    await waitFor(() => expect(posts).toEqual([{ action: 'needs_field_check', version: 1, notes: 'r' }]))
  })

  it('warns before leaving with unsaved changes', async () => {
    const { router } = renderReview()
    await userEvent.type(await screen.findByLabelText('Notes'), 'Near the drain')

    await userEvent.click(screen.getByRole('link', { name: 'Back to findings' }))
    expect(screen.getByRole('alertdialog', { name: 'Leave without saving?' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Stay' }))
    expect(router.state.location.pathname).toBe('/projects/p1/review/f1')
    expect(screen.getByLabelText('Notes')).toHaveValue('Near the drain')

    await userEvent.click(screen.getByRole('link', { name: 'Back to findings' }))
    await userEvent.click(screen.getByRole('button', { name: 'Leave' }))
    expect(await screen.findByText('Findings list')).toBeInTheDocument()
  })

  it('explains that only technical reviewers can review', async () => {
    renderReview({ project: { ...PROJECT, my_permissions: [...PROJECT.my_permissions, 'finding.view_verified'] } })

    expect(await screen.findByText(/Only technical reviewers can review findings/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Verify' })).not.toBeInTheDocument()
  })
})
