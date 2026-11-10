import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import { previewUrl } from '@/api/images'
import { photoMap, photoMapKey, WORST_COLORS, WORST_LABELS, type PhotoPinProps } from '@/api/photo-map'
import { typeLabel } from '@/api/findings'
import { ErrorMessage } from '@/components/error-message'
import { SharePhoto } from '@/components/share-photo'
import { PhotosMap } from '@/components/map/photos-map'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { boxStyle } from '@/lib/bbox'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

/** Team-lead item 5: every analysed photo on the map; click one to see it with all its problem boxes. */
export function ProjectPhotoMapPage() {
  const project = useProject()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const query = useQuery({ queryKey: photoMapKey(project.id), queryFn: ({ signal }) => photoMap(project.id, signal) })
  const selected = query.data?.features.find((f) => f.id === selectedId)?.properties

  return (
    <div className="space-y-4">
      <PageIntro title="Photo map">Every analysed photo that has a location. The colour shows the most serious problem found. Click a pin to see the photo.</PageIntro>
      <ul aria-label="Colour key" className="flex flex-wrap gap-3 text-xs text-asphalt-600">
        {[3, 2, 0].map((level) => (
          <li key={level} className="flex items-center gap-1">
            <span className="inline-block size-3 rounded-full" style={{ background: WORST_COLORS[level] }} aria-hidden />
            {WORST_LABELS[level]}
          </li>
        ))}
      </ul>
      {query.isError && <ErrorMessage error={query.error} onRetry={() => void query.refetch()} />}
      {query.isPending && <SkeletonRows />}
      {query.data && query.data.features.length === 0 && (
        <EmptyState title="No analysed photos with a location yet">Upload photos with GPS and send them to the AI check.</EmptyState>
      )}
      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <PhotosMap area={project.boundary} data={query.data} selectedId={selectedId} onSelect={setSelectedId} className="h-96 lg:h-[calc(100dvh-12rem)]" />
        <aside aria-label="Selected photo" className="rounded-lg border border-asphalt-100 p-3">
          {selected ? <PhotoPanel photo={selected} projectId={project.id} canShare={hasProjectPermission(project, 'image.share')} /> : <p className="text-sm text-asphalt-500">Click a pin on the map to see its photo.</p>}
        </aside>
      </div>
    </div>
  )
}

function PhotoPanel({ photo, projectId, canShare }: { photo: PhotoPinProps; projectId: string; canShare: boolean }) {
  return (
    <div className="space-y-3">
      <div className="relative bg-asphalt-900" style={{ aspectRatio: `${photo.width_px} / ${photo.height_px}` }}>
        <img src={previewUrl(photo.id)} alt={`Photo ${photo.original_filename}`} className="size-full object-fill" />
        {photo.defects.map(
          (d) =>
            d.bbox && (
              <div
                key={d.id}
                data-testid="photo-box"
                className="pointer-events-none absolute rounded-sm border-2 border-lane-400 shadow-[0_0_0_1px_rgba(0,0,0,0.6)]"
                style={boxStyle(d.bbox, photo.width_px, photo.height_px)}
                aria-hidden
              />
            ),
        )}
      </div>
      <p className="text-sm font-medium text-asphalt-800">{photo.original_filename}</p>
      <p className="text-xs text-asphalt-500">Taken {new Date(photo.taken_at).toLocaleString()}</p>
      {photo.defects.length === 0 ? (
        <p className="text-sm text-asphalt-600">No road problems found on this photo.</p>
      ) : (
        <ul aria-label="Problems on this photo" className="space-y-1 text-sm">
          {photo.defects.map((d) => (
            <li key={d.id}>
              <Link className="text-lane-700 underline" to={`/projects/${projectId}/findings?selected=${d.id}`}>
                {typeLabel(d.type_key)}
              </Link>
              <span className="text-asphalt-500"> · {d.review_status === 'verified' ? 'verified' : 'waiting for review'}</span>
            </li>
          ))}
        </ul>
      )}
      {canShare && <SharePhoto key={photo.id} imageId={photo.id} />}
    </div>
  )
}
