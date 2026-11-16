import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MapPin, Pencil, Trash2 } from 'lucide-react'
import { useRef, useState, type ChangeEvent } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'

import { listMembers, orgQueryKeys } from '@/api/organizations'
import {
  archiveProject,
  createProject,
  deleteProject,
  listFindingTypes,
  projectQueryKeys,
  updateProject,
  type AreaGeometry,
  type ProjectDetail,
  type ProjectInput,
} from '@/api/projects'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { areaFromPlace, type PlaceShape } from '@/api/geo'
import { AreaDrawMap, type DrawMode } from '@/components/map/area-draw-map'
import { PlaceSearch } from '@/components/map/place-search'
import { Button } from '@/components/ui/button'
import { TextField } from '@/components/ui/field'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { PageIntro } from '@/components/ui/page-intro'
import { AreaFileError, areaFromGeoJsonText } from '@/lib/geojson'
import { newPlaceId, nextLabel, placesFromArea, type Place } from '@/lib/places'
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
      <DeleteSection project={project} />
    </>
  )
}

/** Owner, 2026-11-12: only an organization administrator can delete a project. */
function DeleteSection({ project }: { project: ProjectDetail }) {
  const { currentMembership } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const remove = useMutation({
    meta: { success: 'Project deleted' },
    mutationFn: () => deleteProject(project.id, typed),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.all })
      void navigate('/projects', { replace: true })
    },
  })
  if (currentMembership?.org_role !== 'org_admin' || currentMembership.organization_id !== project.organization_id) return null
  const matches = typed.trim() === project.name.trim()
  return (
    <section className="mt-6 max-w-4xl rounded-2xl border border-red-300 bg-red-50/40 p-5" aria-labelledby="delete-heading">
      <h2 id="delete-heading" className="font-semibold text-red-800">
        Delete project
      </h2>
      <p className="mt-1 text-sm text-asphalt-700">
        Only organization administrators can do this. The project disappears for everyone, its road risk stops and its share links stop
        working. Nothing is erased: photos, findings and history stay stored, and the deletion is recorded.
      </p>
      {open ? (
        <div className="mt-3 space-y-3">
          <TextField label={`Type the project's name to confirm: ${project.name}`} value={typed} onChange={(event) => setTyped(event.target.value)} />
          {remove.isError && <ErrorMessage title="Could not delete the project" error={remove.error} />}
          <div className="flex gap-2">
            <Button variant="danger" disabled={!matches} busy={remove.isPending} onClick={() => remove.mutate()}>
              Delete this project
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setOpen(false)
                setTyped('')
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="danger" className="mt-3" onClick={() => setOpen(true)}>
          Delete project…
        </Button>
      )}
    </section>
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

  const [roadWidth, setRoadWidth] = useState(30)
  const [drawMode, setDrawMode] = useState<DrawMode | undefined>(undefined)
  const setArea = (area: AreaGeometry | null) => form.setValue('boundary', area, { shouldValidate: form.formState.isSubmitted, shouldDirty: true })

  // Owner, 2026-11-16: every searched or drawn place stays separate (with its own Edit and
  // Remove icons) while the area is edited; the server joins them into one area for saving.
  const [places, setPlaces] = useState<Place[]>(() => placesFromArea(project?.boundary ?? null))
  const placesRef = useRef(places)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [removeId, setRemoveId] = useState<string | null>(null)
  const [joining, setJoining] = useState(false)
  const [joinProblem, setJoinProblem] = useState<string | null>(null)
  const joinRun = useRef(0)
  const applyPlaces = (next: Place[], { reopenMap = true } = {}) => {
    placesRef.current = next
    setPlaces(next)
    setRemoveId(null)
    if (reopenMap) {
      setEditingId(null)
      setMapKey((key) => key + 1)
    }
    const run = ++joinRun.current
    setJoinProblem(null)
    if (next.length <= 1) {
      setJoining(false)
      setArea(next[0]?.area ?? null)
      return
    }
    setJoining(true)
    joinPlaces(next, roadWidth)
      .then((area) => {
        if (run === joinRun.current) setArea(area)
      })
      .catch((cause: unknown) => {
        if (run === joinRun.current) setJoinProblem(cause instanceof Error ? cause.message : 'The places could not be joined. Try again.')
      })
      .finally(() => {
        if (run === joinRun.current) setJoining(false)
      })
  }
  const addPlace = (area: AreaGeometry, label: string, add = true) =>
    applyPlaces([...(add ? placesRef.current : []), { id: newPlaceId(), label, area }])
  const removePlace = (placeId: string) => applyPlaces(placesRef.current.filter((place) => place.id !== placeId))

  // A road drawn on the map: the server turns it into a strip of the chosen width.
  const joinShape = useMutation({
    mutationFn: (shape: PlaceShape) => areaFromPlace(shape, { roadWidthM: roadWidth, addTo: null }),
  })
  const addDrawnRoad = (shape: PlaceShape) => {
    joinShape.mutate(shape, {
      onSuccess: ({ area }) => addPlace(area, nextLabel(placesRef.current, 'Drawn road')),
      onError: () => setMapKey((key) => key + 1),
    })
  }

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
      addPlace(areaFromGeoJsonText(await file.text()), file.name, false)
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
                Select areas and roads by searching for them, or draw them on the map ("Draw an area", "Draw a road"). Everything
                you add is joined into one survey area. If you already have the area as a map file, you can upload it instead.
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
              currentArea={places.length > 0 ? (boundary ?? places[0]?.area ?? null) : null}
              roadWidthM={roadWidth}
              onRoadWidthChange={setRoadWidth}
              onChoose={(area, label, add) => {
                setFileProblem(null)
                addPlace(area, label, add)
              }}
            />
          )}
          <div className="relative">
            <AreaDrawMap
              key={mapKey}
              places={places}
              disabled={readOnly || joinShape.isPending}
              roadWidthM={roadWidth}
              initialMode={drawMode}
              onModeChange={setDrawMode}
              editingId={editingId}
              onEdit={setEditingId}
              onAreaDrawn={(area) => addPlace(area, nextLabel(placesRef.current, 'Drawn area'))}
              onRoadDrawn={addDrawnRoad}
              onPlaceChanged={(placeId, area) =>
                applyPlaces(
                  placesRef.current.map((place) => (place.id === placeId ? { ...place, area } : place)),
                  { reopenMap: false },
                )
              }
              onRemoveRequest={setRemoveId}
              onPlaceDeleted={(placeId) => applyPlaces(placesRef.current.filter((place) => place.id !== placeId), { reopenMap: false })}
              onClearAll={() => {
                setDrawMode('polygon')
                applyPlaces([])
              }}
            />
            {(joinShape.isPending || joining) && (
              <p role="status" className="absolute top-14 left-3 rounded-lg bg-white/95 px-3 py-2 text-sm font-medium shadow">
                Updating the area…
              </p>
            )}
            {removeId && (
              <RemovePlaceBox
                label={places.find((place) => place.id === removeId)?.label ?? 'this place'}
                onRemove={() => removePlace(removeId)}
                onKeep={() => setRemoveId(null)}
              />
            )}
          </div>
          {joinShape.isError && (
            <p role="alert" className="text-sm text-red-700">
              That shape could not be added: {joinShape.error instanceof Error ? joinShape.error.message : 'try drawing it again.'}
            </p>
          )}
          {joinProblem && (
            <p role="alert" className="text-sm text-red-700">
              {joinProblem}
            </p>
          )}
          {places.length > 0 && (
            <SelectedPlaces
              places={places}
              readOnly={readOnly}
              editingId={editingId}
              onEdit={(placeId) => setEditingId(placeId)}
              onRemove={setRemoveId}
            />
          )}
          {errors.boundary && <p className="text-sm text-red-700">{errors.boundary.message}</p>}
        </div>

        {save.isError && <ErrorMessage title="Could not save the project" error={save.error} />}

        {!readOnly && (
          <div className="flex gap-3">
            <Button type="submit" variant="accent" busy={save.isPending} disabled={joining || joinShape.isPending}>
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

/** Join the places into one survey area on the server (overlaps merge into one valid shape). */
async function joinPlaces(places: Place[], roadWidthM: number): Promise<AreaGeometry | null> {
  const [first, ...rest] = places
  if (!first) return null
  let area = first.area
  for (const place of rest) {
    area = (await areaFromPlace(place.area as PlaceShape, { roadWidthM, addTo: area })).area
  }
  return area
}

/** "Selected places": every place in the survey area, each with Edit and Remove. */
function SelectedPlaces({
  places,
  readOnly,
  editingId,
  onEdit,
  onRemove,
}: {
  places: Place[]
  readOnly: boolean
  editingId: string | null
  onEdit: (placeId: string) => void
  onRemove: (placeId: string) => void
}) {
  return (
    <div className="rounded-xl border border-asphalt-100 bg-white">
      <h3 className="border-b border-asphalt-100 px-4 py-2 text-sm font-medium text-asphalt-800">Selected places ({places.length})</h3>
      <ul aria-label="Selected places" className="divide-y divide-asphalt-100">
        {places.map((place) => (
          <li key={place.id} className={`flex items-center gap-3 px-4 py-2 text-sm ${editingId === place.id ? 'bg-amber-50' : ''}`}>
            <MapPin className="size-4 shrink-0 text-lane-600" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-asphalt-900">
              {place.label}
              {editingId === place.id && <span className="ml-2 text-xs text-amber-800">editing on the map</span>}
            </span>
            {!readOnly && (
              <span className="flex gap-1">
                <button
                  type="button"
                  aria-label={`Edit ${place.label}`}
                  title="Edit on the map"
                  onClick={() => onEdit(place.id)}
                  className="grid size-8 place-items-center rounded-full text-asphalt-700 hover:bg-asphalt-100 focus-visible:outline-2 focus-visible:outline-lane-600"
                >
                  <Pencil className="size-4" aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${place.label}`}
                  title="Remove this place"
                  onClick={() => onRemove(place.id)}
                  className="grid size-8 place-items-center rounded-full text-red-700 hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-red-600"
                >
                  <Trash2 className="size-4" aria-hidden />
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Asks before one place is removed (from its bin icon on the map or in the list). */
function RemovePlaceBox({ label, onRemove, onKeep }: { label: string; onRemove: () => void; onKeep: () => void }) {
  return (
    <div
      role="alertdialog"
      aria-label="Remove a place"
      className="absolute top-3 left-1/2 z-10 w-[min(26rem,calc(100%-1.5rem))] -translate-x-1/2 rounded-xl border border-red-200 bg-white p-4 shadow-lg"
    >
      <p className="text-sm text-asphalt-900">
        Remove <strong>{label}</strong> from the survey area? The other places stay.
      </p>
      <div className="mt-3 flex gap-2">
        <Button variant="danger" onClick={onRemove}>
          Remove
        </Button>
        <Button variant="secondary" onClick={onKeep}>
          Keep
        </Button>
      </div>
    </div>
  )
}
