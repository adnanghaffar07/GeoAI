import { ArrowRight, Camera, CircleCheckBig, ClipboardList, Hourglass, MapPinOff, SearchCheck, Sparkles, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'

import type { Dashboard } from '@/api/dashboard'

interface Step {
  key: string
  icon: LucideIcon
  /** Plain sentence, e.g. "7 AI suggestions are waiting for your review". */
  text: string
  /** Which project, when the home page covers several. */
  project?: string
  action: string
  to: string
}

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`

/**
 * Builds the to-do list from the dashboard numbers, for this person's role only (the server
 * already left out what they may not see). Each step links straight to the page that does it.
 */
function buildNextSteps(data: Dashboard, projectId: string | null): Step[] {
  const { access, totals } = data
  const steps: Step[] = []
  const single = projectId ?? (data.projects.length === 1 ? data.projects[0]!.id : null)
  const projectsWith = (pick: (project: Dashboard['projects'][number]) => number) =>
    data.projects.filter((project) => (projectId ? project.id === projectId : true) && pick(project) > 0)

  // New photos not yet checked by the AI: managers, administrators (no project role) and collectors can send them.
  // (A project's own Overview shows the big "waiting for the AI check" banner instead.)
  if (access.photos && !projectId) {
    const canRunAi = (project: Dashboard['projects'][number]) =>
      project.my_roles.length === 0 || project.my_roles.includes('project_manager') || project.my_roles.includes('field_collector')
    for (const project of projectsWith((p) => p.photos_waiting_for_ai ?? 0).filter(canRunAi).slice(0, 3)) {
      const count = project.photos_waiting_for_ai ?? 0
      steps.push({
        key: `ai-${project.id}`,
        icon: Sparkles,
        text: `${plural(count, 'new photo is', 'new photos are')} waiting for the AI check`,
        project: project.name,
        action: 'Check them',
        to: `/projects/${project.id}/photos`,
      })
    }
  }

  if (access.candidates) {
    for (const project of projectsWith((p) => p.waiting_review).slice(0, 3)) {
      // Only technical reviewers can decide; managers are told the queue is waiting for a reviewer.
      const reviews = project.my_roles.includes('technical_reviewer')
      steps.push({
        key: `review-${project.id}`,
        icon: Hourglass,
        text: reviews
          ? `${plural(project.waiting_review, 'AI suggestion is', 'AI suggestions are')} waiting to be checked`
          : `${plural(project.waiting_review, 'AI suggestion is', 'AI suggestions are')} waiting for a reviewer`,
        project: projectId ? undefined : project.name,
        action: reviews ? 'Start reviewing' : 'See them',
        to: `/projects/${project.id}/findings?status=to_review`,
      })
    }
    if (totals.needs_field_check > 0 && single) {
      steps.push({
        key: 'field-check',
        icon: SearchCheck,
        text: `${plural(totals.needs_field_check, 'finding needs', 'findings need')} someone to check it on site`,
        action: 'See them',
        to: `/projects/${single}/findings?status=needs_field_check`,
      })
    }
  }

  if (access.photos && totals.photos_missing_location > 0) {
    steps.push({
      key: 'location',
      icon: MapPinOff,
      text: `${plural(totals.photos_missing_location, 'photo has', 'photos have')} no location, so ${totals.photos_missing_location === 1 ? 'it' : 'they'} cannot go on the map`,
      action: single ? 'Add locations' : 'Open projects',
      to: single ? `/projects/${single}/photos?missing=1` : '/projects',
    })
  }

  if (access.priority || access.own_inspections) {
    // Open inspections are a job for managers (and administrators, who have no project role) or the person
    // doing them; viewers only watch, so it is not on their list.
    const doesInspections = (project: Dashboard['projects'][number]) =>
      access.own_inspections || project.my_roles.length === 0 || project.my_roles.includes('project_manager')
    for (const project of projectsWith((p) => p.inspections_open).filter(doesInspections).slice(0, 3)) {
      steps.push({
        key: `inspect-${project.id}`,
        icon: ClipboardList,
        text: access.priority
          ? `${plural(project.inspections_open, 'inspection is', 'inspections are')} still open`
          : `You have ${plural(project.inspections_open, 'inspection', 'inspections')} to do`,
        project: projectId ? undefined : project.name,
        action: access.priority ? 'See the priority list' : 'See my inspections',
        to: `/projects/${project.id}/priority`,
      })
    }
  }

  // Field collectors: uploading is their main job, so Home always offers it (a project page has its own Upload button).
  if (access.photos_own_only && !projectId) {
    const target = single ?? data.projects[0]?.id
    if (target) {
      steps.push({
        key: 'upload',
        icon: Camera,
        text: 'Took new photos on the road?',
        project: projectId || data.projects.length === 1 ? undefined : data.projects.find((p) => p.id === target)?.name,
        action: 'Upload photos',
        to: `/projects/${target}/upload`,
      })
    }
  }
  return steps
}

/** "What to do next": the few things this person can act on now, each with one button. */
export function NextSteps({ data, projectId }: { data: Dashboard; projectId: string | null }) {
  const steps = buildNextSteps(data, projectId)

  return (
    <section aria-labelledby="next-steps-heading" className="panel overflow-hidden">
      <div className="flex items-center gap-2 border-b border-asphalt-100 bg-lane-50 px-4 py-3">
        <span aria-hidden className="h-4 w-1 rounded bg-lane-500" />
        <h2 id="next-steps-heading" className="font-semibold">
          What to do next
        </h2>
      </div>
      {steps.length === 0 ? (
        <p className="flex items-center gap-3 px-4 py-5 text-sm text-asphalt-600">
          <CircleCheckBig className="size-5 shrink-0 text-green-700" aria-hidden />
          You are all caught up. Nothing is waiting for you right now.
        </p>
      ) : (
        <ul className="divide-y divide-asphalt-100">
          {steps.map((step) => (
            <li key={step.key} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
              <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-asphalt-50 text-asphalt-700">
                <step.icon className="size-[18px]" />
              </span>
              {/* On phones the text takes the whole row and the button goes underneath. */}
              <span className="min-w-0 flex-1 basis-[calc(100%-3.25rem)] text-sm sm:basis-0">
                <span className="block font-medium text-asphalt-900">{step.text}</span>
                {step.project && <span className="block truncate text-xs text-asphalt-500">{step.project}</span>}
              </span>
              <Link to={step.to} className="btn btn-secondary ml-13 sm:ml-auto">
                {step.action}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
