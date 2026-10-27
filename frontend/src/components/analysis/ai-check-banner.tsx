import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CircleCheck, Sparkles } from 'lucide-react'

import { analysisQueryKeys, startAnalysis, type StartAnalysisResult } from '@/api/analysis'
import { findingQueryKeys } from '@/api/findings'
import { imageQueryKeys } from '@/api/images'
import { projectQueryKeys, type ProjectDetail } from '@/api/projects'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { hasProjectPermission } from '@/pages/project/project-layout'

const photos = (count: number) => `${count} ${count === 1 ? 'photo' : 'photos'}`

function sentMessage(result: StartAnalysisResult): string {
  const failed = result.jobs.filter((job) => job.status === 'failed').length
  if (result.created === 0) return 'Every photo you can check has already been sent to the AI.'
  const sent = `Sent ${photos(result.created)} to the AI. Results appear on each photo when ready.`
  return failed > 0 ? `${sent} ${failed} could not be sent; use "Try again" on those photos.` : sent
}

interface AiCheckBannerProps {
  project: ProjectDetail
  /** Also show a short "all checked" line when nothing is waiting (on the Photos page). */
  showWhenDone?: boolean
}

/**
 * The call to action for new photos: "N new photos are waiting for the AI check" with one big
 * button that sends them. Shown on the project Overview, the Photos page and after an upload.
 */
export function AiCheckBanner({ project, showWhenDone = false }: AiCheckBannerProps) {
  const queryClient = useQueryClient()
  const waiting = project.counts.images_waiting_for_ai ?? 0
  const start = useMutation({
    mutationFn: () => startAnalysis(project.id),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: imageQueryKeys.all(project.id) }),
        queryClient.invalidateQueries({ queryKey: analysisQueryKeys.jobs(project.id) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.detail(project.id) }),
        queryClient.invalidateQueries({ queryKey: findingQueryKeys.all(project.id) }),
        queryClient.invalidateQueries({ queryKey: ['organizations', project.organization_id, 'dashboard'] }),
      ]),
  })

  if (project.archived || !hasProjectPermission(project, 'analysis.run')) return null

  if (waiting === 0) {
    if (start.isSuccess) {
      return (
        <p role="status" className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <Sparkles className="size-4 shrink-0" aria-hidden />
          {sentMessage(start.data)}
        </p>
      )
    }
    if (!showWhenDone || project.counts.images === 0) return null
    return (
      <p className="flex items-center gap-2 text-sm text-asphalt-600">
        <CircleCheck className="size-4 text-emerald-700" aria-hidden />
        Every photo has been sent to the AI.
      </p>
    )
  }

  return (
    <section
      aria-labelledby="ai-check-title"
      className="relative overflow-hidden rounded-2xl border border-lane-300 bg-gradient-to-r from-lane-50 via-white to-white p-4 shadow-sm sm:p-5"
    >
      {/* Road-marking stripe on the left edge. */}
      <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-lane-500" />
      <div className="flex flex-col gap-4 pl-2 sm:flex-row sm:items-center">
        <span aria-hidden className="relative flex size-12 shrink-0 items-center justify-center rounded-full bg-lane-500 text-asphalt-950 shadow-[0_0_0_6px_var(--color-lane-100)]">
          <Sparkles className="size-6" />
          <span className="absolute -top-1 -right-1 flex size-6 items-center justify-center rounded-full bg-asphalt-900 text-xs font-bold text-white tabular-nums">
            {waiting > 99 ? '99+' : waiting}
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="ai-check-title" className="text-base font-semibold text-asphalt-900 sm:text-lg">
            {photos(waiting)} {waiting === 1 ? 'is' : 'are'} waiting for the AI check
          </h2>
          <p className="mt-0.5 text-sm text-asphalt-600">
            The AI looks for possible road problems in new photos. A reviewer then checks every suggestion.
          </p>
        </div>
        <Button variant="accent" busy={start.isPending} onClick={() => start.mutate()} className="w-full shrink-0 px-5 py-2.5 text-base sm:w-auto">
          <Sparkles className="size-4" aria-hidden />
          Check {photos(waiting)} now
        </Button>
      </div>
      {start.isError && (
        <div className="mt-3 pl-2">
          <ErrorMessage title="Could not send the photos to the AI" error={start.error} />
        </div>
      )}
    </section>
  )
}
