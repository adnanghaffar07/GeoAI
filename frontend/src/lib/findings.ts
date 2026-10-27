import type { ReviewOptions } from '@/api/findings'

/** Display name of a severity level, from the organization's current scale. */
export function severityLabel(key: string | null, options: ReviewOptions | undefined): string {
  if (!key) return 'Not set'
  return options?.severity_rubric.levels.find((level) => level.key === key)?.label ?? key
}

const ROLE_LABELS: Record<string, string> = {
  org_admin: 'Organization admin',
  org_manager: 'Organization manager',
  org_member: 'Member',
  project_manager: 'Project manager',
  technical_reviewer: 'Technical reviewer',
  field_collector: 'Field collector',
  viewer: 'Viewer',
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role.replaceAll('_', ' ')
}

/** Colours per review status. AI suggestions look different from verified findings (S09). */
export const STATUS_STYLES: Record<string, string> = {
  ai_generated: 'border border-dashed border-amber-400 bg-amber-50 text-amber-900',
  awaiting_review: 'bg-amber-100 text-amber-900',
  needs_field_check: 'bg-sky-100 text-sky-900',
  verified: 'bg-emerald-100 text-emerald-900',
  rejected: 'bg-asphalt-100 text-asphalt-600 line-through decoration-asphalt-400',
  merged: 'bg-asphalt-100 text-asphalt-600',
}

/** Map pin colours, matching the pills above. */
export const STATUS_COLORS: Record<string, string> = {
  ai_generated: '#f2b705',
  awaiting_review: '#d97706',
  needs_field_check: '#0284c7',
  verified: '#047857',
  rejected: '#9aa5b1',
  merged: '#9aa5b1',
}
