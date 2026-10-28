import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ChangeEvent } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'

import { listMembers, orgQueryKeys } from '@/api/organizations'
import {
  archiveProject,
  createProject,
  listFindingTypes,
  projectQueryKeys,
  updateProject,
  type AreaGeometry,
  type ProjectDetail,
  type ProjectInput,
} from '@/api/projects'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { AreaDrawMap } from '@/components/map/area-draw-map'
import { PlaceSearch } from '@/components/map/place-search'
import { Button } from '@/components/ui/button'
import { TextField } from '@/components/ui/field'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { PageIntro } from '@/components/ui/page-intro'
import { AreaFileError, areaFromGeoJsonText } from '@/lib/geojson'
import { hasProjectPermission, useProject } from '@/pages/project/project-layout'

const MAX_AREA_FILE_BYTES = 5 * 1024 * 1024

const optionalText = (max: number) => z.string().trim().max(max, `Use at most ${max} characters.`)

const projectSchema = z
  .object({
    name: z.string().trim().min(1, 'Enter a project name.').max(200, 'Use at most 200 characters.'),
    finding_type_keys: z.array(z.string()).min(1, 'Choose at least one finding type.'),
    reviewer_user_ids: z.array(z.string()),
    road_category: optionalText(60),
    survey_start: z.string(),
    survey_end: z.string(),
    partner_reference: optionalText(120),
    boundary: z.custom<AreaGeometry | null>().refine((value) => value != null, 'Draw the survey area on the map or upload a GeoJSON file.'),
  })
  .refine((values) => !values.survey_start || !values.survey_end || values.survey_end >= values.survey_start, {
    path: ['survey_end'],
    message: 'The end date must be on or after the start date.',
  })
type ProjectFormInput = z.input<typeof projectSchema>
type ProjectValues = z.output<typeof projectSchema>

// A new project also needs its reviewers (spec); on edit the team is managed on the Team tab.
const newProjectSchema = projectSchema.refine((values) => values.reviewer_user_ids.length > 0, {
  path: ['reviewer_user_ids'],
  message: 'Choose at least one technical reviewer.',
})

const emptyToNull = (value: string) => (value.trim() === '' ? null : value.trim())

function toInput(values: ProjectValues): ProjectInput {
  return {
    name: values.name.trim(),
    boundary: values.boundary,
    finding_type_keys: values.finding_type_keys,
    road_category: emptyToNull(values.road_category),
    survey_start: emptyToNull(values.survey_start),
    survey_end: emptyToNull(values.survey_end),
    partner_reference: emptyToNull(values.partner_reference),
  }
}

/** S05 New project (`/projects/new`). */
export function NewProjectPage() {
  const { currentMembership, can } = useAuth()
  if (!currentMembership) return <p className="text-asphalt-500">You are not part of any organization yet. Ask your administrator to invite you.</p>
  if (!can('project.create')) return <p className="text-asphalt-500">Your role does not include creating projects. Ask your administrator if you need to.</p>
  return <ProjectForm orgId={currentMembership.organization_id} />
}

/** S05 Project settings (`/projects/:projectId/edit`, inside the project frame). Archived projects open read-only. */
export function EditProjectPage() {
  const project = useProject()
  return (
    <>
      <ProjectForm orgId={project.organization_id} project={project} />
      {!project.archived && hasProjectPermission(project, 'project.archive') && <ArchiveSection project={project} />}
    </>
  )
}

function ArchiveSection({ project }: { project: ProjectDetail }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const archive = useMutation({
    meta: { success: 'Project archived' },
    mutationFn: () => archiveProject(project.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectQueryKeys.all }),
  })
  return (
    <section className="mt-10 max-w-4xl rounded-lg border border-red-200 bg-white p-4" aria-labelledby="archive-heading">
      <h2 id="archive-heading" className="font-medium">
        Archive project
      </h2>
      <p className="mt-1 text-sm text-asphalt-500">
        Archive a project when the survey is finished. After that, nobody can upload photos or change anything in it. Nothing is deleted:
        you can still open it by ticking "Show archived projects" on the Projects page.
      </p>
      <div className="mt-3 flex gap-2">
        {confirming ? (
          <>
            <Button variant="danger" busy={archive.isPending} onClick={() => archive.mutate()}>
              Yes, archive this project
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <Button variant="danger" onClick={() => setConfirming(true)}>
            Archive project
          </Button>
        )}
      </div>
      {archive.isError && (
        <div className="mt-3">
          <ErrorMessage title="Could not archive the project" error={archive.error} />
        </div>
      )}
    </section>
  )
}

function ProjectForm({ orgId, project }: { orgId: string; project?: ProjectDetail }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isNew = !project
  const readOnly = Boolean(project && (project.archived || !project.my_permissions.includes('project.edit')))
  const [mapKey, setMapKey] = useState(0)
  const [fileProblem, setFileProblem] = useState<string | null>(null)

  const findingTypes = useQuery({ queryKey: projectQueryKeys.findingTypes(orgId), queryFn: ({ signal }) => listFindingTypes(orgId, signal) })
  const members = useQuery({
    queryKey: orgQueryKeys.members(orgId),
    queryFn: ({ signal }) => listMembers(orgId, signal),
    enabled: isNew,
  })

  const form = useForm<ProjectFormInput, unknown, ProjectValues>({
    resolver: zodResolver(isNew ? newProjectSchema : projectSchema),
    defaultValues: {
      name: project?.name ?? '',
      finding_type_keys: project?.finding_type_keys ?? [],
      reviewer_user_ids: [],
      road_category: project?.road_category ?? '',
      survey_start: project?.survey_start ?? '',
      survey_end: project?.survey_end ?? '',
      partner_reference: project?.partner_reference ?? '',
      boundary: project?.boundary ?? null,
    },
  })
  const errors = form.formState.errors

  const save = useMutation({
    meta: { success: isNew ? 'Project created' : 'Project details saved' },
    mutationFn: async (values: ProjectValues) => {
      if (project) {
        // Send only what was changed, so the project history lists real changes.
        const input = toInput(values)
        const dirty = form.formState.dirtyFields
        const changed = Object.fromEntries(Object.entries(input).filter(([key]) => dirty[key as keyof ProjectFormInput]))
        return (await updateProject(project.id, changed)).id
      }
      return (await createProject(orgId, { ...toInput(values), reviewer_user_ids: values.reviewer_user_ids })).id
    },
    // On failure nothing is reset: the person's entries stay on screen (S05).
    onSuccess: async (projectId) => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.all })
      void navigate(`/projects/${projectId}`)
    },
  })

  const setArea = (area: AreaGeometry | null) => form.setValue('boundary', area, { shouldValidate: form.formState.isSubmitted, shouldDirty: true })

  const loadAreaFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = '' // allow choosing the same file again
    if (!file) return
    setFileProblem(null)
    if (file.size > MAX_AREA_FILE_BYTES) {
      setFileProblem('This file is larger than 5 MB. Simplify the area and try again.')
      return
    }
    try {
      setArea(areaFromGeoJsonText(await file.text()))
      setMapKey((key) => key + 1) // reopen the map with the uploaded area
    } catch (cause) {
      setFileProblem(cause instanceof AreaFileError ? cause.message : 'The file could not be read.')
    }
  }

  const reviewerIds = useWatch({ control: form.control, name: 'reviewer_user_ids' })
  const boundary = useWatch({ control: form.control, name: 'boundary' })
  const typeKeys = useWatch({ control: form.control, name: 'finding_type_keys' })
  const toggle = (field: 'reviewer_user_ids' | 'finding_type_keys', value: string, checked: boolean) => {
    const current = form.getValues(field)
    form.setValue(field, checked ? [...current, value] : current.filter((item) => item !== value), {
      shouldValidate: form.formState.isSubmitted,
      shouldDirty: true,
    })
  }

  return (
    <section className="max-w-4xl space-y-6">
      <header>
        {isNew ? (
          <>
            <Link to="/projects" className="text-sm link">
              Back to projects
            </Link>
            <h1 className="mt-2 text-[1.75rem] font-semibold tracking-tight">Create project</h1>
            <p className="mt-1 text-asphalt-500">
              A project is one road survey: the area on the map, the kinds of road problems to look for, and who checks them.
            </p>
          </>
        ) : (
          <PageIntro title="Project details">The project's name, survey area and the kinds of road problems it looks for.</PageIntro>
        )}
        {readOnly && (
          <p className="mt-2 rounded-lg bg-asphalt-100 px-3 py-2 text-sm text-asphalt-700">
            {project?.archived ? 'This project is archived, so it can only be viewed.' : 'You can view this project but not change it.'}
          </p>
        )}
      </header>

      <form noValidate onSubmit={form.handleSubmit((values) => save.mutate(values))} className="space-y-6">
        <fieldset disabled={readOnly} className="space-y-6">
          <div className="grid gap-4 panel p-4 sm:grid-cols-2">
            <TextField label="Project name" className="sm:col-span-2" error={errors.name?.message} {...form.register('name')} />
            <TextField label="Road category (optional)" hint="For example: arterial, residential" error={errors.road_category?.message} {...form.register('road_category')} />
            <TextField label="Partner reference (optional)" hint="The customer's own project number" error={errors.partner_reference?.message} {...form.register('partner_reference')} />
            <TextField label="Survey start (optional)" type="date" error={errors.survey_start?.message} {...form.register('survey_start')} />
            <TextField label="Survey end (optional)" type="date" error={errors.survey_end?.message} {...form.register('survey_end')} />
          </div>

          <fieldset className="panel p-4" aria-describedby="types-help">
            <legend className="float-left mb-1 w-full font-semibold">Finding types</legend>
            <p id="types-help" className="clear-both text-sm text-asphalt-500">
              The kinds of road problems this survey looks for. Types marked "sample" are placeholders until your city provides its own list.
            </p>
            {findingTypes.isPending && <SkeletonRows rows={2} />}
            {findingTypes.isError && <ErrorMessage title="Could not load the kinds of problems" error={findingTypes.error} onRetry={() => void findingTypes.refetch()} />}
            {findingTypes.isSuccess && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {findingTypes.data.items
                  .filter((type) => type.is_active || typeKeys.includes(type.key))
                  .map((type) => (
                    <label key={type.key} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={typeKeys.includes(type.key)} onChange={(event) => toggle('finding_type_keys', type.key, event.target.checked)} />
                      {type.label}
                      <span className="text-xs text-asphalt-500">
                        {type.source === 'ai' ? 'AI can suggest' : 'Added by people'}
                        {type.is_placeholder && ' · sample (placeholder)'}
                      </span>
                    </label>
                  ))}
              </div>
            )}
            {errors.finding_type_keys && <p className="mt-2 text-sm text-red-700">{errors.finding_type_keys.message}</p>}
          </fieldset>

          {isNew && (
            <fieldset className="panel p-4" aria-describedby="reviewers-help">
              <legend className="float-left mb-1 w-full font-semibold">Technical reviewers</legend>
              <p id="reviewers-help" className="clear-both text-sm text-asphalt-500">
                People who check each AI suggestion and decide whether it is a real problem. You can choose yourself. You become the
                project manager automatically. After saving, add other people under the project's Settings, on the Team page.
              </p>
              {members.isPending && <SkeletonRows rows={2} />}
              {members.isError && <ErrorMessage title="Could not load the list of people" error={members.error} onRetry={() => void members.refetch()} />}
              {members.isSuccess && (
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {members.data.items
                    .filter((member) => member.is_active)
                    .map((member) => (
                      <label key={member.user_id} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={reviewerIds.includes(member.user_id)}
                          onChange={(event) => toggle('reviewer_user_ids', member.user_id, event.target.checked)}
                        />
                        {member.full_name}
                        <span className="truncate text-xs text-asphalt-500">{member.email}</span>
                      </label>
                    ))}
                </div>
              )}
              {errors.reviewer_user_ids && <p className="mt-2 text-sm text-red-700">{errors.reviewer_user_ids.message}</p>}
            </fieldset>
          )}
        </fieldset>

        <div className="space-y-3 panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-medium">Survey area</h2>
              <p className="text-sm text-asphalt-500">
                Search for roads, an address or an area to select them, or draw the area of roads to survey on the map. If you
                already have the area as a map file, you can upload it instead.
              </p>
              <p className="text-xs text-asphalt-400">Map file: GeoJSON with longitude/latitude (WGS 84).</p>
            </div>
            {!readOnly && (
              <label className="btn btn-secondary cursor-pointer">
                Upload area file
                <input type="file" accept=".geojson,.json,application/geo+json,application/json" className="sr-only" onChange={(event) => void loadAreaFile(event)} />
              </label>
            )}
          </div>
          {fileProblem && (
            <p role="alert" className="text-sm text-red-700">
              {fileProblem}
            </p>
          )}
          {!readOnly && (
            <PlaceSearch
              currentArea={boundary ?? null}
              onChoose={(area) => {
                setFileProblem(null)
                setArea(area)
                setMapKey((key) => key + 1) // reopen the map showing the new area
              }}
            />
          )}
          <AreaDrawMap key={mapKey} initialArea={form.getValues('boundary')} onChange={setArea} disabled={readOnly} />
          {errors.boundary && <p className="text-sm text-red-700">{errors.boundary.message}</p>}
        </div>

        {save.isError && <ErrorMessage title="Could not save the project" error={save.error} />}

        {!readOnly && (
          <div className="flex gap-3">
            <Button type="submit" variant="accent" busy={save.isPending}>
              Save project
            </Button>
            <Link to={project ? `/projects/${project.id}` : '/projects'} className="btn btn-ghost">
              Cancel
            </Link>
          </div>
        )}
      </form>
    </section>
  )
}
