/**
 * Chart colours. Checked with a colour-blind safety validator (data-viz method):
 * - SERIES: three distinct colours for lines on one chart (pass all pairs, light surface).
 * - REVIEW_STATUS: state colours for the review donut (pass; always shown with names and
 *   numbers). Rejected is a deliberate neutral grey ("left out").
 * - ORDINAL: one blue, light -> dark, for ordered levels such as severity (pass).
 * - SINGLE: the colour for a chart with one measure (every bar the same colour).
 */
export const SERIES = { photos: '#2a78d6', suggestions: '#eb6834', verified: '#1baf7a' } as const

export const REVIEW_STATUS_COLORS: Record<string, string> = {
  waiting: '#c98500',
  needs_field_check: '#2a78d6',
  verified: '#008300',
  rejected: '#898781',
}

export const SINGLE = '#2a78d6'

/** Blue ramp steps 250 -> 650 (lightest still clears 2:1 on white). */
const ORDINAL_RAMP = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']

/** `count` steps from the ramp, light to dark, spread evenly. */
export function ordinal(count: number): string[] {
  if (count <= 1) return [ORDINAL_RAMP[2]!]
  return Array.from({ length: count }, (_, index) => ORDINAL_RAMP[Math.round((index * (ORDINAL_RAMP.length - 1)) / (count - 1))]!)
}

/** Chart chrome: recessive hairlines and muted text. */
export const CHROME = { grid: '#e1e0d9', axis: '#c3c2b7', muted: '#6b6a66', ink: '#1b2633' } as const
