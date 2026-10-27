import { cn } from '@/lib/utils'

/** The app's mark: a stretch of asphalt with a yellow dashed centre line. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn('size-8 shrink-0', className)}>
      <rect width="32" height="32" rx="8" fill="#1b2633" />
      <path d="M16 4v24" stroke="#f2b705" strokeWidth="3.2" strokeDasharray="5 4" strokeLinecap="round" />
    </svg>
  )
}

/** Mark plus product name. `tone` sets the name's colour for dark or light backgrounds. */
export function BrandName({ tone = 'dark' }: { tone?: 'dark' | 'light' }) {
  return (
    <span className="flex items-center gap-2.5">
      <BrandMark className={tone === 'light' ? 'ring-1 ring-white/15 rounded-lg' : undefined} />
      <span className={cn('text-[17px] font-bold tracking-tight', tone === 'light' ? 'text-white' : 'text-asphalt-900')}>
        GeoInfraLens AI
      </span>
    </span>
  )
}
