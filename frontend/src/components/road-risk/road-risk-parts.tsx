import type { ReactNode } from 'react'
import { CircleAlert, CircleHelp, CircleMinus, CloudRain, Snowflake, Sun, TriangleAlert, type LucideIcon } from 'lucide-react'

import { LEVEL_WORDS, formatNumber, type FactorLevel, type RiskFactor, type Weather } from '@/api/road-risk'
import { cn } from '@/lib/utils'

/**
 * Small building blocks of the road-risk screens (F4d).
 * Levels are always shown as a word with an icon, never by colour alone.
 */

const LEVEL_STYLE: Record<FactorLevel, { icon: LucideIcon; className: string }> = {
  high: { icon: TriangleAlert, className: 'bg-red-50 text-red-800 ring-red-200' },
  medium: { icon: CircleAlert, className: 'bg-amber-50 text-amber-900 ring-amber-200' },
  low: { icon: CircleMinus, className: 'bg-asphalt-50 text-asphalt-700 ring-asphalt-200' },
  missing: { icon: CircleHelp, className: 'bg-white text-asphalt-500 ring-asphalt-200' },
}

/** "High risk" / "Medium risk" / "Low risk" (or a factor level) with its icon. */
export function LevelBadge({ level, kind = 'risk', className }: { level: FactorLevel | null; kind?: 'risk' | 'factor'; className?: string }) {
  if (!level) return null
  const style = LEVEL_STYLE[level]
  const Icon = style.icon
  const word = LEVEL_WORDS[level]
  const text = kind === 'risk' && level !== 'missing' ? `${word} risk` : word
  return (
    <span className={cn('pill ring-1 ring-inset', style.className, className)}>
      <Icon className="size-3.5" aria-hidden />
      {text}
    </span>
  )
}

/** The TRIAL label and the fixed notice, on every road-risk screen. */
export function TrialNotice({ label, notice, children }: { label: string; notice: string; children?: ReactNode }) {
  return (
    <div className="space-y-1 rounded-lg border border-lane-300 bg-lane-50 p-3 text-sm text-asphalt-800">
      <p className="flex flex-wrap items-center gap-2">
        <span className="pill bg-lane-500 font-semibold tracking-wide text-asphalt-950">{label}</span>
        <span className="font-medium">{notice}</span>
      </p>
      {children && <div className="text-asphalt-600">{children}</div>}
    </div>
  )
}

/** One-line explanation of what the levels mean for this project. */
export function LevelMeaning({ level }: { level: 1 | 2 | null }) {
  if (level === 2) {
    return (
      <p>
        Tested Chicago risk levels: <strong>high</strong> = the riskiest 1% of Chicago roads this week, <strong>medium</strong> = the next 9%,
        all others <strong>low</strong>. Updated every Monday.
      </p>
    )
  }
  if (level === 1) {
    return (
      <p>
        Risk factors only: there is no pothole history here, so roads are compared by their weather and road facts, not by a tested forecast. The
        level shown is the road's highest risk factor.
      </p>
    )
  }
  return null
}

const day = (date: string) => new Date(`${date}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })
const temp = (value: number | null) => (value === null ? '–' : `${Math.round(value)}°`)
const amount = (value: number | null) => (value === null ? '–' : `${formatNumber(value)} mm`)

/** The next 7 days from the National Weather Service, and the recent weather inputs. */
export function WeatherStrip({ weather }: { weather: Weather }) {
  const { outlook, recent } = weather
  return (
    <section aria-label="Weather" className="panel space-y-3 p-4">
      <h3 className="font-medium">Weather</h3>
      {outlook ? (
        <>
          <ol className="grid grid-cols-4 gap-2 text-center text-xs sm:grid-cols-7" aria-label="Next 7 days">
            {outlook.days.map((item) => {
              const freezeThaw = item.max_c !== null && item.min_c !== null && item.max_c > 0 && item.min_c < 0
              return (
                <li key={item.date} className={cn('rounded-lg border p-2', freezeThaw ? 'border-sky-300 bg-sky-50' : 'border-asphalt-100')}>
                  <p className="font-medium text-asphalt-800">{day(item.date)}</p>
                  <p>
                    {temp(item.max_c)} / {temp(item.min_c)}
                  </p>
                  {freezeThaw && (
                    <p className="flex items-center justify-center gap-0.5 font-medium text-sky-800">
                      <Snowflake className="size-3" aria-hidden />
                      <Sun className="size-3" aria-hidden />
                      Freeze-thaw
                    </p>
                  )}
                  {(item.rain_mm ?? 0) > 0 && (
                    <p className="flex items-center justify-center gap-0.5">
                      <CloudRain className="size-3" aria-hidden />
                      {amount(item.rain_mm)}
                    </p>
                  )}
                  {(item.snow_mm ?? 0) > 0 && (
                    <p className="flex items-center justify-center gap-0.5">
                      <Snowflake className="size-3" aria-hidden />
                      {amount(item.snow_mm)}
                    </p>
                  )}
                </li>
              )
            })}
          </ol>
          <p className="text-sm text-asphalt-700">
            Next 7 days: {outlook.freeze_thaw_days} freeze-thaw day{outlook.freeze_thaw_days === 1 ? '' : 's'}, {outlook.frost_days} frost day
            {outlook.frost_days === 1 ? '' : 's'}, {outlook.heavy_rain_days} heavy-rain day{outlook.heavy_rain_days === 1 ? '' : 's'}, snow{' '}
            {formatNumber(outlook.snow_mm)} mm.
          </p>
          <p className="text-xs text-asphalt-500">
            Source: National Weather Service ({outlook.source}), issued{' '}
            {new Date(outlook.issued_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}. "–" means the forecast has no
            value for that day.
          </p>
        </>
      ) : (
        <p className="text-sm text-asphalt-500">The 7-day weather outlook is not available yet. It is fetched every morning.</p>
      )}
      {recent && (
        <div className="space-y-1 border-t border-asphalt-100 pt-3 text-sm">
          <p className="font-medium">Recent weather (up to {new Date(`${recent.as_of}T00:00:00`).toLocaleDateString(undefined, { dateStyle: 'medium' })})</p>
          <ul className="grid gap-1 sm:grid-cols-2">
            {recent.values.map((value) => (
              <li key={value.factor}>
                {value.label}: {value.value === null ? 'not known' : formatNumber(value.value)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

/** Risk factors in two groups: the ones that raise the risk, and background facts. */
export function FactorTable({ factors }: { factors: RiskFactor[] }) {
  const groups: [string, RiskFactor[]][] = [
    ['Risk factors', factors.filter((f) => f.kind === 'risk')],
    ['Background facts', factors.filter((f) => f.kind === 'background')],
  ]
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {groups.map(([title, items]) => (
        <section key={title} className="space-y-2">
          <h4 className="text-sm font-medium">{title}</h4>
          {items.length === 0 ? (
            <p className="text-sm text-asphalt-500">None recorded yet.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {items.map((factor) => (
                <li key={factor.factor} className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    {factor.label}: {factor.value === null ? 'not known' : formatNumber(factor.value)}
                  </span>
                  <LevelBadge level={factor.level} kind="factor" />
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}
