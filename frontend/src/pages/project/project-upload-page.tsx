import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type DragEvent } from 'react'
import { Link } from 'react-router'

import { imageQueryKeys, uploadImage, type LatLon, type UploadResult } from '@/api/images'
import { projectQueryKeys } from '@/api/projects'
import { AiCheckBanner } from '@/components/analysis/ai-check-banner'
import { Button } from '@/components/ui/button'
import { PageIntro } from '@/components/ui/page-intro'
import { isApiError } from '@/lib/api-client'
import { logger } from '@/lib/logger'
import { cn } from '@/lib/utils'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

/** Same limit as the server's default (MAX_UPLOAD_MB). The server is the final check. */
const MAX_FILE_MB = 20
const ACCEPTED_TYPES = ['image/jpeg', 'image/png']
/** How many files upload at the same time. */
const PARALLEL_UPLOADS = 3

type ItemStatus = 'waiting' | 'uploading' | 'done' | 'failed'

interface QueueItem {
  key: string
  file: File
  status: ItemStatus
  progress: number
  error?: string
  /** A problem with the file itself (wrong type, too large): retrying will not help. */
  permanent?: boolean
  result?: UploadResult
}

const fileKey = (file: File) => `${file.name}|${file.size}|${file.lastModified}`

function checkFile(file: File): string | null {
  if (file.type && !ACCEPTED_TYPES.includes(file.type)) return 'Only JPEG and PNG photos can be uploaded.'
  if (file.size > MAX_FILE_MB * 1024 * 1024) return `This file is larger than ${MAX_FILE_MB} MB.`
  return null
}

function getDeviceLocation(): Promise<LatLon | null> {
  if (!('geolocation' in navigator)) return Promise.resolve(null)
  return new Promise((resolve) =>
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
      () => resolve(null), // refused or unavailable: photos without GPS are flagged instead
      { enableHighAccuracy: true, timeout: 15_000 },
    ),
  )
}

/** S07 Upload photos. */
export function ProjectUploadPage() {
  const project = useProject()
  const queryClient = useQueryClient()
  const [items, setItems] = useState<QueueItem[]>([])
  const [allowed, setAllowed] = useState(false)
  const [useDeviceLocation, setUseDeviceLocation] = useState(false)
  const [running, setRunning] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [locationNote, setLocationNote] = useState<string | null>(null)
  // The latest queue, for the upload loop (state inside an async loop would be stale).
  const itemsRef = useRef(items)
  useEffect(() => {
    itemsRef.current = items
  }, [items])

  if (!hasProjectPermission(project, 'image.upload'))
    return <p className="text-asphalt-500">Your role in this project does not include uploading photos. Ask the project manager if you need to.</p>
  if (project.archived) return <p className="text-asphalt-500">This project is archived (closed), so no more photos can be added.</p>

  const update = (key: string, change: Partial<QueueItem>) =>
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...change } : item)))

  const addFiles = (files: FileList | File[]) => {
    setItems((current) => {
      const known = new Set(current.map((item) => item.key))
      const added: QueueItem[] = []
      for (const file of Array.from(files)) {
        const key = fileKey(file)
        if (known.has(key)) continue // same file chosen twice
        known.add(key)
        const problem = checkFile(file)
        added.push({ key, file, status: problem ? 'failed' : 'waiting', progress: 0, error: problem ?? undefined, permanent: Boolean(problem) })
      }
      return [...current, ...added]
    })
  }

  const uploadOne = async (item: QueueItem, deviceLocation: LatLon | null) => {
    update(item.key, { status: 'uploading', progress: 0, error: undefined })
    try {
      const result = await uploadImage(project.id, item.file, {
        deviceLocation,
        onProgress: (fraction) => update(item.key, { progress: fraction }),
      })
      update(item.key, { status: 'done', progress: 1, result })
    } catch (cause) {
      const permanent = isApiError(cause) && [413, 415, 422].includes(cause.status)
      update(item.key, {
        status: 'failed',
        error: isApiError(cause) ? cause.message : 'The upload failed. Try again.',
        permanent,
      })
    }
  }

  /** Upload every waiting file (files already done are never sent again). */
  const start = async (only?: string) => {
    setRunning(true)
    setLocationNote(null)
    let deviceLocation: LatLon | null = null
    if (useDeviceLocation) {
      deviceLocation = await getDeviceLocation()
      if (!deviceLocation) setLocationNote('This device did not share its location. Photos without a location will be marked "No location yet", and you can add one later.')
    }
    const queue = itemsRef.current.filter((item) => (only ? item.key === only : item.status === 'waiting'))
    logger.info(`Uploading ${queue.length} photo(s), ${PARALLEL_UPLOADS} at a time${deviceLocation ? ', with this device\'s location for photos without GPS' : ''}`)
    const workers = Array.from({ length: Math.min(PARALLEL_UPLOADS, queue.length) }, async () => {
      for (let next = queue.shift(); next; next = queue.shift()) await uploadOne(next, deviceLocation)
    })
    await Promise.all(workers)
    setRunning(false)
    logger.info('Upload finished')
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: imageQueryKeys.all(project.id) }),
      queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) }),
    ])
  }

  const retry = (key: string) => {
    update(key, { status: 'waiting', error: undefined })
    void start(key)
  }
  const remove = (key: string) => setItems((current) => current.filter((item) => item.key !== key))

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    addFiles(event.dataTransfer.files)
  }

  const waiting = items.filter((item) => item.status === 'waiting').length
  const done = items.filter((item) => item.status === 'done')
  const withoutLocation = done.filter((item) => item.result && !item.result.image.location).length

  return (
    <div className="max-w-3xl space-y-5">
      <PageIntro title="Upload photos">
        Add the road photos you took for this project. After uploading, the AI can check them for possible road problems.
      </PageIntro>
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'rounded-lg border-2 border-dashed bg-white p-6 text-center',
          dragging ? 'border-lane-500 bg-lane-50' : 'border-asphalt-200 hover:border-asphalt-300',
        )}
      >
        <p className="hidden text-asphalt-500 md:block">Drag photos here, or</p>
        <div className="mt-3 flex flex-wrap justify-center gap-3">
          <label className="btn btn-accent cursor-pointer">
            Choose photos
            <input
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              multiple
              className="sr-only"
              onChange={(event) => {
                if (event.target.files) addFiles(event.target.files)
                event.target.value = ''
              }}
            />
          </label>
          <label className="btn btn-secondary cursor-pointer md:hidden">
            Take photo
            <input
              type="file"
              accept="image/jpeg"
              capture="environment"
              className="sr-only"
              onChange={(event) => {
                if (event.target.files) addFiles(event.target.files)
                event.target.value = ''
              }}
            />
          </label>
        </div>
        <p className="mt-3 text-xs text-asphalt-500">JPEG or PNG photos, up to {MAX_FILE_MB} MB each. Where and when each photo was taken is read from the photo, if the camera saved it.</p>
      </div>

      <div className="space-y-2 panel p-4 text-sm">
        <label className="flex items-start gap-2">
          <input type="checkbox" className="mt-0.5" checked={allowed} onChange={(event) => setAllowed(event.target.checked)} />
          <span>
            I am allowed to upload these photos. I have checked they do not show more personal information (faces, number plates,
            house interiors) than the survey needs.
          </span>
        </label>
        <label className="flex items-start gap-2">
          <input type="checkbox" className="mt-0.5" checked={useDeviceLocation} onChange={(event) => setUseDeviceLocation(event.target.checked)} />
          <span>
            If a photo has no location saved in it, use this device's current location instead.{' '}
            <span className="text-asphalt-500">Only tick this if you are standing where you took the photos. It is an approximate position.</span>
          </span>
        </label>
        {locationNote && <p className="text-amber-700">{locationNote}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="accent" disabled={!allowed || waiting === 0} busy={running} onClick={() => void start()}>
          {waiting > 0 ? `Upload ${waiting} ${waiting === 1 ? 'photo' : 'photos'}` : 'Upload photos'}
        </Button>
        {!allowed && waiting > 0 && <span className="text-sm text-asphalt-500">Tick the first box above to upload.</span>}
      </div>

      {done.length > 0 && !running && (
        <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {done.length} {done.length === 1 ? 'photo is' : 'photos are'} now in the project.{' '}
          {withoutLocation > 0 ? (
            <>
              {withoutLocation} {withoutLocation === 1 ? 'has' : 'have'} no location yet.{' '}
              <Link to={`/projects/${project.id}/photos?missing=1`} className="font-medium underline">
                Add location on map
              </Link>
            </>
          ) : (
            <Link to={`/projects/${project.id}/photos`} className="font-medium underline">
              See photos
            </Link>
          )}
        </p>
      )}

      {done.length > 0 && !running && <AiCheckBanner project={project} />}

      {items.length > 0 && (
        <ul className="divide-y divide-asphalt-100 panel text-sm" aria-label="Photos to upload">
          {items.map((item) => (
            <QueueRow key={item.key} item={item} onRetry={() => retry(item.key)} onRemove={() => remove(item.key)} disabled={running} />
          ))}
        </ul>
      )}
    </div>
  )
}

function QueueRow({ item, onRetry, onRemove, disabled }: { item: QueueItem; onRetry: () => void; onRemove: () => void; disabled: boolean }) {
  const image = item.result?.image
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{item.file.name}</p>
        {item.status === 'uploading' && (
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-asphalt-100" role="progressbar" aria-label={`Uploading ${item.file.name}`} aria-valuenow={Math.round(item.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded bg-lane-500 transition-all" style={{ width: `${Math.round(item.progress * 100)}%` }} />
          </div>
        )}
        {item.status === 'failed' && <p className="text-red-700">{item.error}</p>}
        {item.status === 'done' && image && (
          <p className="text-asphalt-500">
            {item.result?.duplicate ? 'Already uploaded before (not added twice)' : 'Uploaded'}
            {' · '}
            <span className={image.location ? 'text-emerald-700' : 'text-amber-700'}>{image.location ? 'Has location' : 'No location yet'}</span>
          </p>
        )}
      </div>
      <span className="text-xs text-asphalt-500">
        {item.status === 'waiting' && 'Waiting'}
        {item.status === 'uploading' && `${Math.round(item.progress * 100)}%`}
        {item.status === 'done' && 'Done'}
      </span>
      {item.status === 'failed' && !item.permanent && (
        <Button variant="secondary" onClick={onRetry} disabled={disabled}>
          Try again
        </Button>
      )}
      {(item.status === 'waiting' || item.status === 'failed') && (
        <Button variant="ghost" onClick={onRemove} disabled={disabled}>
          Remove
        </Button>
      )}
    </li>
  )
}
