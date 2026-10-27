import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Image as ImageIcon, MapPinCheck, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { JOB_STATUS_LABELS, retryAnalysisJob } from '@/api/analysis'
import { findingQueryKeys } from '@/api/findings'

import {
  flagLabel,
  imageQueryKeys,
  listImages,
  LOCATION_SOURCE_LABELS,
  originalUrl,
  previewUrl,
  setImageLocation,
  withdrawImage,
  type ImageInfo,
  type LatLon,
} from '@/api/images'
import { projectQueryKeys, type ProjectDetail } from '@/api/projects'
import { useAuth } from '@/auth/auth-context'
import { AiCheckBanner } from '@/components/analysis/ai-check-banner'
import { ErrorMessage } from '@/components/error-message'
import { ModelLabel } from '@/components/findings/model-label'
import { PickLocationMap } from '@/components/map/pick-location-map'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

const PAGE_SIZE = 24
/** How often the list is refreshed while any photo on screen is waiting for or in analysis. */
const POLL_MS = 3000

const isActive = (image: ImageInfo) => image.analysis?.status === 'queued' || image.analysis?.status === 'processing'

/**
 * When the camera recorded no time zone, the server stores the camera's clock reading as-is,
 * so it is shown exactly as the camera recorded it rather than converted to local time.
 */
function formatCaptureTime(image: ImageInfo): string {
  if (!image.captured_at) return 'at unknown time'
  const zoneUnknown = image.quality_flags.includes('capture_time_no_timezone')
  const text = new Date(image.captured_at).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...(zoneUnknown ? { timeZone: 'UTC' } : {}),
  })
  return zoneUnknown ? `${text} (camera clock, time zone unknown)` : text
}

/** S08 Photos: list, location, withdraw, and AI analysis status. */
export function ProjectPhotosPage() {
  const project = useProject()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const missingOnly = searchParams.get('missing') === '1'
  const page = Math.max(1, Number(searchParams.get('page')) || 1)
  const [picking, setPicking] = useState<ImageInfo | null>(null)
  const canUpload = hasProjectPermission(project, 'image.upload') && !project.archived

  const photos = useQuery({
    queryKey: imageQueryKeys.list(project.id, missingOnly, page),
    queryFn: ({ signal }) => listImages(project.id, { missingLocation: missingOnly, page, pageSize: PAGE_SIZE }, signal),
    // Keep checking while analysis is running, so the status changes without reloading.
    refetchInterval: (query) => (query.state.data?.items.some(isActive) ? POLL_MS : false),
  })
  const anyActive = photos.data?.items.some(isActive) ?? false

  // When the last running analysis finishes, refresh the project totals (overview numbers).
  const wasActive = useRef(false)
  useEffect(() => {
    if (wasActive.current && !anyActive) {
      void queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) })
      void queryClient.invalidateQueries({ queryKey: findingQueryKeys.all(project.id) })
    }
    wasActive.current = anyActive
  }, [anyActive, project.id, queryClient])
  const lastPage = photos.data ? Math.max(1, Math.ceil(photos.data.total / PAGE_SIZE)) : 1

  const setParams = (next: { missing?: boolean; page?: number }) => {
    const params = new URLSearchParams()
    if (next.missing ?? missingOnly) params.set('missing', '1')
    if ((next.page ?? 1) > 1) params.set('page', String(next.page))
    setSearchParams(params)
  }

  return (
    <div className="space-y-4">
      <PageIntro
        title="Photos"
        actions={
          canUpload && (
            <Link to={`/projects/${project.id}/upload`} className="btn btn-accent">
              <Upload className="size-4" aria-hidden />
              Upload photos
            </Link>
          )
        }
      >
        Every photo taken for this project. Add a location where one is missing, and let the AI look for road problems in new photos.
      </PageIntro>
      <AiCheckBanner project={project} showWhenDone />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-asphalt-700">
          <input type="checkbox" checked={missingOnly} onChange={(event) => setParams({ missing: event.target.checked, page: 1 })} />
          Only photos without a location
        </label>
        {photos.isSuccess && (
          <p className="text-sm text-asphalt-500" aria-live="polite">
            {photos.data.total} photo{photos.data.total === 1 ? '' : 's'}
            {anyActive && ' · The AI is checking photos. This list updates by itself.'}
          </p>
        )}
      </div>

      {photos.isPending && <SkeletonRows rows={4} />}
      {photos.isError && <ErrorMessage title="Could not load photos" error={photos.error} onRetry={() => void photos.refetch()} />}
      {photos.isSuccess &&
        (photos.data.items.length === 0 ? (
          missingOnly ? (
            <EmptyState icon={<MapPinCheck />} title="Every photo has a location" />
          ) : (
            <EmptyState
              icon={<ImageIcon />}
              title="No photos yet"
              action={
                canUpload && (
                  <Link to={`/projects/${project.id}/upload`} className="btn btn-accent">
                    Upload the first photos
                  </Link>
                )
              }
            >
              Photos of the roads you surveyed appear here once they are uploaded.
            </EmptyState>
          )
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {photos.data.items.map((image) => (
              <PhotoCard key={image.id} image={image} project={project} onPickLocation={() => setPicking(image)} />
            ))}
          </ul>
        ))}

      {lastPage > 1 && (
        <nav aria-label="Pages" className="flex items-center gap-3 text-sm">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setParams({ page: page - 1 })}>
            Previous
          </Button>
          <span>
            Page {page} of {lastPage}
          </span>
          <Button variant="secondary" disabled={page >= lastPage} onClick={() => setParams({ page: page + 1 })}>
            Next
          </Button>
        </nav>
      )}

      {picking && <PickLocationDialog image={picking} project={project} onClose={() => setPicking(null)} />}
    </div>
  )
}

function PhotoCard({ image, project, onPickLocation }: { image: ImageInfo; project: ProjectDetail; onPickLocation: () => void }) {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const [previewFailed, setPreviewFailed] = useState(false)
  const [confirmWithdraw, setConfirmWithdraw] = useState(false)
  const editable = !project.archived
  const isOwn = me?.user.id === image.uploaded_by
  const canPick = editable && image.location_source === 'none' && hasProjectPermission(project, 'image.location.set')
  // Managers withdraw any photo; collectors only their own (the server checks this too).
  // Collectors may withdraw only before analysis (decision Q6).
  const isManager = hasProjectPermission(project, 'project.edit')
  const canWithdraw = editable && hasProjectPermission(project, 'image.withdraw') && (isManager || (isOwn && !image.analysis))

  const withdraw = useMutation({
    mutationFn: () => withdrawImage(image.id),
    meta: { success: 'Photo withdrawn' },
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: imageQueryKeys.all(project.id) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) }),
      ]),
  })

  return (
    <li className="overflow-hidden panel">
      <div className="flex aspect-[4/3] items-center justify-center bg-asphalt-100">
        {previewFailed ? (
          <span className="px-4 text-center text-xs text-asphalt-500">Preview not available</span>
        ) : (
          <img
            src={previewUrl(image.id)}
            alt={`Photo ${image.original_filename}`}
            loading="lazy"
            className="size-full object-cover"
            onError={() => setPreviewFailed(true)}
          />
        )}
      </div>
      <div className="space-y-2 p-3 text-sm">
        <p className="truncate font-medium" title={image.original_filename}>
          {image.original_filename}
        </p>
        <p className="text-xs text-asphalt-500">
          Taken {formatCaptureTime(image)} · uploaded by {image.uploaded_by_name ?? 'unknown person'}
        </p>
        <p className="text-xs">
          <span className={image.location ? 'text-emerald-700' : 'text-amber-700'}>{LOCATION_SOURCE_LABELS[image.location_source] ?? image.location_source}</span>
          {image.location && <span className="text-asphalt-500"> · roughly where the camera was, not the exact spot of a problem</span>}
        </p>
        {image.quality_flags.length > 0 && (
          <ul className="flex flex-wrap gap-1" aria-label="Photo warnings">
            {image.quality_flags.map((flag) => (
              <li key={flag} className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
                {flagLabel(flag)}
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          {canPick && (
            <Button variant="secondary" onClick={onPickLocation}>
              Add location on map
            </Button>
          )}
          {!previewFailed && (
            <a href={originalUrl(image.id)} target="_blank" rel="noreferrer" className="btn btn-ghost">
              Open full photo
            </a>
          )}
          {canWithdraw &&
            (confirmWithdraw ? null : (
              <Button variant="ghost" onClick={() => setConfirmWithdraw(true)}>
                Withdraw photo
              </Button>
            ))}
        </div>
        {canWithdraw && confirmWithdraw && (
          <div className="space-y-2 rounded-lg bg-asphalt-50 p-2" role="group" aria-label="Withdraw this photo?">
            <p className="text-xs text-asphalt-700">
              Withdraw this photo? It will be hidden from lists and not used again, but it is kept for the record.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="danger" busy={withdraw.isPending} onClick={() => withdraw.mutate()}>
                Yes, withdraw photo
              </Button>
              <Button variant="ghost" onClick={() => setConfirmWithdraw(false)}>
                Keep photo
              </Button>
            </div>
          </div>
        )}
        {withdraw.isError && <ErrorMessage title="Could not withdraw the photo" error={withdraw.error} />}
        <AnalysisStatus image={image} project={project} isOwn={isOwn} />
      </div>
    </li>
  )
}

/** Button that sends every photo not yet analysed to the AI (never twice). */
const CHIP_STYLES: Record<string, string> = {
  queued: 'bg-asphalt-100 text-asphalt-700',
  processing: 'bg-sky-50 text-sky-800',
  completed: 'bg-emerald-50 text-emerald-800',
  failed: 'bg-red-50 text-red-800',
}

/** The photo's AI analysis: status, number of suggestions, failure reason and Retry. */
function AnalysisStatus({ image, project, isOwn }: { image: ImageInfo; project: ProjectDetail; isOwn: boolean }) {
  const queryClient = useQueryClient()
  const analysis = image.analysis
  const retry = useMutation({
    mutationFn: (jobId: string) => retryAnalysisJob(jobId),
    meta: { success: 'Photo sent to the AI again' },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: imageQueryKeys.all(project.id) }),
  })
  if (!analysis) {
    return hasProjectPermission(project, 'analysis.status.view') ? <p className="text-xs text-asphalt-500">Not checked by the AI yet</p> : null
  }
  const canRetry =
    analysis.status === 'failed' &&
    !project.archived &&
    hasProjectPermission(project, 'analysis.run') &&
    (isOwn || hasProjectPermission(project, 'project.edit'))
  const count = analysis.candidate_count

  return (
    <div className="space-y-1.5 border-t border-asphalt-100 pt-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`pill ${CHIP_STYLES[analysis.status] ?? ''}`}>{JOB_STATUS_LABELS[analysis.status]}</span>
        {analysis.status === 'completed' && count !== null && (
          count === 0 ? (
            <span className="text-xs text-asphalt-500">
              {analysis.is_trial_model ? 'Trial model found nothing. Check the photo yourself.' : 'AI found no possible problems'}
            </span>
          ) : (
            <Link to={`/projects/${project.id}/findings?image=${image.id}`} className="text-xs link">
              {count} possible problem{count === 1 ? '' : 's'} to review
            </Link>
          )
        )}
      </div>
      {analysis.status === 'completed' && count !== null && (
        <ModelLabel testDetector={analysis.is_test_detector} trialModel={analysis.is_trial_model} />
      )}
      {analysis.status === 'failed' && (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-red-800">{analysis.failure_reason ?? 'No reason was given.'}</p>
          {canRetry && (
            <Button variant="secondary" busy={retry.isPending} onClick={() => retry.mutate(analysis.job_id)}>
              Try again
            </Button>
          )}
        </div>
      )}
      {retry.isError && <ErrorMessage title="Could not send the photo to the AI again" error={retry.error} />}
    </div>
  )
}

function PickLocationDialog({ image, project, onClose }: { image: ImageInfo; project: ProjectDetail; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [location, setLocation] = useState<LatLon | null>(null)
  const save = useMutation({
    mutationFn: (value: LatLon) => setImageLocation(image.id, value),
    meta: { success: 'Location saved' },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: imageQueryKeys.all(project.id) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) }),
      ])
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-asphalt-950/60 p-4" onKeyDown={(event) => event.key === 'Escape' && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="pick-title" className="page-enter max-h-[calc(100dvh-2rem)] w-full max-w-2xl space-y-3 overflow-y-auto rounded-2xl bg-white p-4 shadow-2xl sm:p-5">
        <h2 id="pick-title" className="text-lg font-medium">
          Where was this photo taken?
        </h2>
        <p className="text-sm text-asphalt-500">
          {image.original_filename} has no location. Click the map where you stood when taking the photo. You can set this only once, so
          check the point before saving. The photo itself is not changed.
        </p>
        <PickLocationMap area={project.boundary} value={location} onPick={setLocation} />
        <p className="text-sm text-asphalt-500" aria-live="polite">
          {location ? (
            <>
              Point chosen.{' '}
              <span className="text-xs text-asphalt-400">
                ({location.latitude.toFixed(6)}, {location.longitude.toFixed(6)})
              </span>
            </>
          ) : (
            'Click the map to choose a point.'
          )}
        </p>
        {save.isError && <ErrorMessage title="Could not save the location" error={save.error} />}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!location} busy={save.isPending} onClick={() => location && save.mutate(location)}>
            Save location
          </Button>
        </div>
      </div>
    </div>
  )
}
