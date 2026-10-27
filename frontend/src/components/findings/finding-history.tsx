import { REVIEW_STATUS_LABELS, typeLabel, type ReviewEvent, type ReviewOptions } from '@/api/findings'
import { roleLabel, severityLabel } from '@/lib/findings'

const ACTION_LABELS: Record<string, string> = {
  create: 'Added',
  verify: 'Verified',
  reject: 'Rejected',
  needs_field_check: 'Marked "needs field check"',
  edit: 'Edited',
  merge: 'Merged',
  reopen_review: 'Reopened for review',
}

const FIELD_LABELS: Record<string, string> = {
  review_status: 'Status',
  type_key: 'Type',
  severity_key: 'Severity',
  notes: 'Notes',
  corrected_location: 'Pin on the map',
  location_quality: 'Location',
  location_source: 'Location came from',
}

const LOCATION_SOURCE: Record<string, string> = {
  photo_gps: 'the photo',
  device_gps: 'the phone',
  manual: 'picked on the map',
  none: 'none',
}

const LOCATION_QUALITY: Record<string, string> = {
  approximate: 'approximate',
  missing: 'missing',
  reviewer_confirmed: 'confirmed by reviewer',
}

/** One changed value in plain words. */
function describe(field: string, value: unknown, options: ReviewOptions | undefined): string {
  if (value === null || value === undefined || value === '') return '(none)'
  if (field === 'location_source') return LOCATION_SOURCE[String(value)] ?? String(value)
  if (field === 'review_status') return REVIEW_STATUS_LABELS[String(value)] ?? String(value)
  if (field === 'type_key') return typeLabel(String(value), options?.finding_types)
  if (field === 'severity_key') return severityLabel(String(value), options)
  if (field === 'location_quality') return LOCATION_QUALITY[String(value)] ?? String(value)
  if (field === 'corrected_location' && Array.isArray(value)) {
    const [longitude, latitude] = value as number[]
    return `${Number(latitude).toFixed(5)}, ${Number(longitude).toFixed(5)}`
  }
  return String(value)
}

/** Every review action on a finding: who, when, roles at the time, what changed (FR-34). */
export function FindingHistory({ events, options }: { events: ReviewEvent[]; options: ReviewOptions | undefined }) {
  if (events.length === 0) return <p className="text-sm text-asphalt-500">Nobody has reviewed this finding yet.</p>
  return (
    <ol className="space-y-3 border-l-2 border-asphalt-100 pl-4">
      {events.map((event) => (
        <li key={event.id} className="text-sm">
          <p>
            <span className="font-medium">{ACTION_LABELS[event.action] ?? event.action}</span> by {event.actor_name ?? 'unknown'}
            <span className="text-asphalt-500"> ({event.actor_roles.map(roleLabel).join(', ')})</span>
          </p>
          <p className="text-xs text-asphalt-500">
            {new Date(event.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
          {Object.keys(event.changes).length > 0 && (
            <ul className="mt-1 space-y-0.5 text-xs text-asphalt-600">
              {Object.entries(event.changes)
                .filter(([field]) => field !== 'severity_rubric_id')
                .map(([field, change]) => (
                  <li key={field}>
                    {FIELD_LABELS[field] ?? field}: {describe(field, change.old, options)} → {describe(field, change.new, options)}
                  </li>
                ))}
            </ul>
          )}
          {event.note && <p className="mt-1 rounded bg-asphalt-50 px-2 py-1 text-xs">Reason: {event.note}</p>}
        </li>
      ))}
    </ol>
  )
}
