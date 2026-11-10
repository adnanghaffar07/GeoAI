import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera as CameraIcon, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { camerasKey, DIRECTION_LABELS, listCameras, takeSnapshot, type Camera, type CameraList } from '@/api/cameras'
import { imageQueryKeys } from '@/api/images'
import { ErrorMessage } from '@/components/error-message'
import { CamerasMap } from '@/components/map/cameras-map'
import { Button } from '@/components/ui/button'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

const cameraName = (c: Camera) => [c.location, DIRECTION_LABELS[c.direction] ?? c.direction].filter(Boolean).join(', ')

/** Team-lead items 8 and 10: IDOT traffic cameras in the project area (view only); "Take snapshot" saves a photo. */
export function ProjectCamerasPage() {
  const project = useProject()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const query = useQuery({ queryKey: camerasKey(project.id), queryFn: ({ signal }) => listCameras(project.id, signal), refetchInterval: 5 * 60_000 })
  const cameras = query.data?.cameras ?? []
  const selected = cameras.find((c) => c.id === selectedId) ?? null
  const canSave = hasProjectPermission(project, 'image.upload') && !project.archived

  return (
    <div className="space-y-4">
      <PageIntro title="Traffic cameras">
        Live pictures from the Illinois Department of Transportation's traffic cameras inside this project's area. Click a camera to see its latest picture. "Take snapshot" saves that picture as a project photo, so it can go to the AI check like any upload.
      </PageIntro>
      {query.isError && <ErrorMessage error={query.error} onRetry={() => void query.refetch()} />}
      {query.isPending && <SkeletonRows />}
      {query.data && cameras.length === 0 && <EmptyState title="No traffic cameras in this area">IDOT has no cameras inside this project's area.</EmptyState>}
      {cameras.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[1fr_24rem]">
          <CamerasMap area={project.boundary} cameras={cameras} selectedId={selectedId} onSelect={setSelectedId} className="h-96 lg:h-[calc(100dvh-14rem)]" />
          <aside aria-label="Selected camera" className="space-y-3 rounded-lg border border-asphalt-100 p-3 text-sm">
            {selected && query.data ? (
              <CameraPanel key={selected.id} camera={selected} list={query.data} projectId={project.id} canSave={canSave} />
            ) : (
              <p className="text-asphalt-500">Click a camera on the map, or choose one below.</p>
            )}
            <h2 className="pt-1 font-semibold text-asphalt-800">Cameras ({cameras.length})</h2>
            <ul aria-label="Cameras" className="max-h-72 space-y-0.5 overflow-auto">
              {cameras.map((c) => (
                <li key={c.id}>
                  <button type="button" aria-pressed={c.id === selectedId} className="w-full rounded px-1 py-0.5 text-left hover:bg-asphalt-50 aria-pressed:bg-asphalt-100" onClick={() => setSelectedId(c.id)}>
                    {cameraName(c)}
                    {c.too_old && <span className="text-xs text-asphalt-500"> · picture out of date</span>}
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      )}
    </div>
  )
}

function CameraPanel({ camera, list, projectId, canSave }: { camera: Camera; list: CameraList; projectId: string; canSave: boolean }) {
  const client = useQueryClient()
  const [stamp, setStamp] = useState(() => Date.now())
  const [failed, setFailed] = useState(false)
  const save = useMutation({
    mutationFn: () => takeSnapshot(projectId, camera.id),
    onSuccess: () => void client.invalidateQueries({ queryKey: imageQueryKeys.all(projectId) }),
  })
  return (
    <div className="space-y-2">
      <h2 className="font-semibold text-asphalt-800">{cameraName(camera)}</h2>
      <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded bg-asphalt-900">
        {failed ? (
          <span className="text-xs text-asphalt-200">Picture not available right now</span>
        ) : (
          <img src={`${camera.image_url}?t=${stamp}`} alt={`Traffic camera: ${cameraName(camera)}`} className="size-full object-contain" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
        )}
      </div>
      <p className="text-xs text-asphalt-500">
        {camera.age_minutes !== null ? `Picture taken about ${camera.age_minutes} minutes before the list was loaded.` : 'Picture time not known.'} Image: {list.source},{' '}
        <a className="underline" href={list.licence_url} target="_blank" rel="noreferrer">
          {list.licence}
        </a>
        .
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          onClick={() => {
            setFailed(false)
            setStamp(Date.now())
          }}
        >
          <RefreshCw className="size-4" aria-hidden />
          Refresh picture
        </Button>
        {canSave && (
          <Button busy={save.isPending} onClick={() => save.mutate()}>
            <CameraIcon className="size-4" aria-hidden />
            Take snapshot
          </Button>
        )}
      </div>
      {save.isError && <ErrorMessage error={save.error} />}
      {save.data && (
        <p role="status" className="rounded bg-asphalt-50 p-2 text-xs text-asphalt-700">
          {save.data.duplicate ? 'This picture was already saved.' : 'Saved as a photo.'}{' '}
          <Link className="underline" to={`/projects/${projectId}/photos`}>
            Open Photos
          </Link>{' '}
          to send it to the AI check.
        </p>
      )}
    </div>
  )
}
