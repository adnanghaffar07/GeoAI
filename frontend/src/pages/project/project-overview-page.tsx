import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { Camera, TriangleAlert, Upload } from 'lucide-react'
import { Link } from 'react-router'

import { imageQueryKeys, listImages } from '@/api/images'
import { DashboardView } from '@/components/dashboard/dashboard-view'
import { AiCheckBanner } from '@/components/analysis/ai-check-banner'
import { AreaMap, type MapPoint } from '@/components/map/area-map'
import { EmptyState, PageIntro } from '@/components/ui/page-intro'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

/** S06 Project dashboard: the shared dashboard (this project only) and the coverage map (no "% surveyed": not meaningful without a planned route). */
export function ProjectOverviewPage() {
  const project = useProject()
  const canSeePhotos = hasProjectPermission(project, 'image.status.view')
  const canUpload = hasProjectPermission(project, 'image.upload') && !project.archived
  const { counts } = project

  // Up to 200 photo locations for the small coverage map.
  const photos = useQuery({
    queryKey: [...imageQueryKeys.all(project.id), 'map'],
    queryFn: ({ signal }) => listImages(project.id, { pageSize: 200 }, signal),
    enabled: canSeePhotos,
  })
  const points = useMemo<MapPoint[]>(
    () =>
      (photos.data?.items ?? []).flatMap((image) =>
        image.location ? [{ id: image.id, latitude: image.location.latitude, longitude: image.location.longitude }] : [],
      ),
    [photos.data],
  )

  return (
    <div className="space-y-6">
      <PageIntro
        title="Project overview"
        actions={
          canUpload && (
            <Link to={`/projects/${project.id}/upload`} className="btn btn-accent">
              <Upload className="size-4" aria-hidden />
              Upload photos
            </Link>
          )
        }
      >
        What needs doing in this project, how far the work has got, and where the photos were taken.
      </PageIntro>

      <AiCheckBanner project={project} />

      {canSeePhotos && counts.images === 0 && (
        <EmptyState
          icon={<Camera />}
          title="No photos in this project yet"
          action={
            canUpload && (
              <Link to={`/projects/${project.id}/upload`} className="btn btn-accent">
                Upload the first photos
              </Link>
            )
          }
        >
          Upload photos of the roads you surveyed. The AI then suggests possible problems, and a reviewer checks each one.
        </EmptyState>
      )}

      {canSeePhotos && counts.images_with_quality_flags > 0 && (
        <p className="flex flex-wrap items-center gap-x-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <TriangleAlert className="size-4" aria-hidden />
          {counts.images_with_quality_flags} photo{counts.images_with_quality_flags === 1 ? ' may be' : 's may be'} hard to use (blurry, dark or
          similar).
          <Link to={`/projects/${project.id}/photos`} className="link">
            Check the photos
          </Link>
        </p>
      )}

      <DashboardView orgId={project.organization_id} projectId={project.id} showMap={false} />

      <div>
        <h2 className="mb-2 text-lg font-semibold">Survey area</h2>
        <AreaMap area={project.boundary} points={points} label="Survey area and photo locations" className="h-96" />
        {points.length > 0 && (
          <p className="mt-2 text-xs text-asphalt-500">
            Each dark dot is where a photo was taken. The position is approximate (where the camera was), not the exact spot of a problem.
          </p>
        )}
      </div>

    </div>
  )
}
