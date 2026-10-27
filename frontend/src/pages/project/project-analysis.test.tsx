import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { ImageInfo } from '@/api/images'
import type { ProjectDetail } from '@/api/projects'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectPhotosPage } from '@/pages/project/project-photos-page'
import { json, makeImage, page, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const MANAGER: ProjectDetail = {
  ...PROJECT,
  my_roles: ['project_manager'],
  my_permissions: [
    ...PROJECT.my_permissions,
    'project.edit',
    'analysis.run',
    'analysis.status.view',
    'finding.view_verified',
    'finding.view_candidates',
  ],
}

const COLLECTOR: ProjectDetail = {
  ...PROJECT,
  my_permissions: [...PROJECT.my_permissions, 'analysis.run', 'analysis.status.view', 'finding.view_verified'],
}

const analysed = (change: Partial<NonNullable<ImageInfo['analysis']>>) => ({
  job_id: 'job1',
  status: 'completed' as const,
  failure_reason: null,
  model_version: 'stand-in-0.1',
  is_test_detector: true,
  candidate_count: 2,
  ...change,
})

type Handler = (url: string, init?: RequestInit) => Response | undefined

/** Answer requests by address; the project itself is always returned for /projects/p1. */
function mockServer(project: ProjectDetail, handler: Handler) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    const answer = handler(url, init)
    if (answer) return Promise.resolve(answer)
    if (url.endsWith('/v1/projects/p1')) return Promise.resolve(json(project))
    return Promise.resolve(json({ error: { code: 'not_found', message: 'nope' } }, 404))
  })
}

function renderProject(path: string) {
  renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route path="photos" element={<ProjectPhotosPage />} />
      </Route>
    </Routes>,
    { route: path },
  )
}

describe('Photos tab: AI analysis', () => {
  it('shows how many new photos wait for the AI and sends them with one button', async () => {
    let sent = false
    const waiting = (count: number) => ({ ...MANAGER, counts: { ...MANAGER.counts, images: 2, images_waiting_for_ai: count } })
    const fetchMock = mockServer(MANAGER, (url, init) => {
      if (url.includes('/analysis-jobs') && init?.method === 'POST') {
        sent = true
        return json({ created: 2, reused: 0, jobs: [] }, 202)
      }
      if (url.endsWith('/v1/projects/p1')) return json(waiting(sent ? 0 : 2))
      if (url.includes('/images?')) return json(page([makeImage()]))
      return undefined
    })
    renderProject('/projects/p1/photos')

    expect(await screen.findByRole('heading', { name: '2 photos are waiting for the AI check' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Check 2 photos now' }))

    expect(await screen.findByText(/^Sent 2 photos to the AI\./)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Check .* now/ })).not.toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(String(post?.[0])).toContain('/v1/projects/p1/analysis-jobs')
  })

  it('says every photo was sent when nothing is waiting', async () => {
    const done = { ...MANAGER, counts: { ...MANAGER.counts, images: 1, images_waiting_for_ai: 0 } }
    mockServer(done, (url) => (url.includes('/images?') ? json(page([makeImage()])) : undefined))
    renderProject('/projects/p1/photos')
    expect(await screen.findByText('Every photo has been sent to the AI.')).toBeInTheDocument()
  })

  it('does not offer the AI check to people who may not run it', async () => {
    const viewer = { ...PROJECT, counts: { ...PROJECT.counts, images: 3, images_waiting_for_ai: 3 } }
    mockServer(viewer, (url) => (url.includes('/images?') ? json(page([makeImage()])) : undefined))
    renderProject('/projects/p1/photos')
    expect(await screen.findAllByRole('listitem')).not.toHaveLength(0)
    expect(screen.queryByText(/waiting for the AI check/)).not.toBeInTheDocument()
  })

  it('shows status, suggestions, the test-detector label and Retry for failures', async () => {
    const fetchMock = mockServer(MANAGER, (url) => {
      if (url.includes('/analysis-jobs/job2/retry')) return json({}, 202)
      if (url.includes('/images?'))
        return json(
          page([
            makeImage({ id: 'a', original_filename: 'a.jpg', analysis: analysed({}) }),
            makeImage({ id: 'b', original_filename: 'b.jpg', analysis: analysed({ job_id: 'job3', candidate_count: 0 }) }),
            makeImage({
              id: 'c',
              original_filename: 'c.jpg',
              analysis: analysed({ job_id: 'job2', status: 'failed', candidate_count: null, failure_reason: 'The photo file is not available.' }),
            }),
          ]),
        )
      return undefined
    })
    renderProject('/projects/p1/photos')

    const cards = await screen.findAllByRole('listitem')
    const [first, second, third] = cards.filter((card) => card.querySelector('img'))
    expect(within(first!).getByRole('link', { name: '2 possible problems to review' })).toHaveAttribute('href', '/projects/p1/findings?image=a')
    expect(within(first!).getByText('TEST DETECTOR: not a real detection')).toBeInTheDocument()
    expect(within(second!).getByText('AI found no possible problems')).toBeInTheDocument()
    expect(within(third!).getByText('AI check failed')).toBeInTheDocument()
    expect(within(third!).getByText('The photo file is not available.')).toBeInTheDocument()

    await userEvent.click(within(third!).getByRole('button', { name: 'Try again' }))

    expect(fetchMock.mock.calls.some(([url, options]) => String(url).includes('/analysis-jobs/job2/retry') && options?.method === 'POST')).toBe(true)
  })

  it('labels trial-model results and never calls an empty result "no damage"', async () => {
    const trial = { model_version: 'frcnn-rdd2022-0.1', is_test_detector: false, is_trial_model: true }
    mockServer(MANAGER, (url) => {
      if (url.includes('/images?'))
        return json(
          page([
            makeImage({ id: 'a', original_filename: 'a.jpg', analysis: analysed(trial) }),
            makeImage({ id: 'b', original_filename: 'b.jpg', analysis: analysed({ ...trial, job_id: 'job3', candidate_count: 0 }) }),
          ]),
        )
      return undefined
    })
    renderProject('/projects/p1/photos')

    const cards = await screen.findAllByRole('listitem')
    const [first, second] = cards.filter((card) => card.querySelector('img'))
    expect(within(first!).getByText('TRIAL MODEL: accuracy not approved')).toBeInTheDocument()
    expect(within(first!).queryByText('TEST DETECTOR: not a real detection')).not.toBeInTheDocument()
    expect(within(second!).getByText('Trial model found nothing. Check the photo yourself.')).toBeInTheDocument()
  })

  it('never shows AI suggestions to collectors and hides Withdraw after analysis', async () => {
    mockServer(COLLECTOR, (url) => {
      if (url.includes('/images?'))
        return json(page([makeImage({ uploaded_by: 'u1', analysis: analysed({ candidate_count: null }) })]))
      return undefined
    })
    renderProject('/projects/p1/photos')

    expect(await screen.findByText('Checked by the AI')).toBeInTheDocument()
    expect(screen.queryByText(/possible problem/)).not.toBeInTheDocument()
    expect(screen.queryByText('AI found no possible problems')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Findings' })).toBeInTheDocument() // verified findings only
    expect(screen.queryByRole('button', { name: 'Withdraw photo' })).not.toBeInTheDocument()
  })
})
