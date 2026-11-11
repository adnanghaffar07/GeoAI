import { ChevronDown, type LucideIcon } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface DropdownCardProps {
  title: string
  subtitle?: string
  icon?: LucideIcon
  number?: number
  badges?: string[]
  startOpen?: boolean
  children: ReactNode
}

/** A click-to-open card (About page, Data storage guide): icon or step number, title, optional subtitle and badges. */
export function DropdownCard({ title, subtitle, icon: Icon, number, badges, startOpen = false, children }: DropdownCardProps) {
  const [open, setOpen] = useState(startOpen)
  const id = useId()
  return (
    <div
      className={cn(
        'overflow-hidden rounded-2xl border bg-white transition-all duration-200',
        open ? 'border-asphalt-200 shadow-md ring-1 ring-lane-400/60' : 'border-asphalt-100 shadow-sm hover:-translate-y-0.5 hover:shadow-md',
      )}
    >
      <h3>
        <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((value) => !value)} className="flex w-full items-center gap-4 px-5 py-4 text-left">
          {number !== undefined ? (
            <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-bold transition', open ? 'bg-asphalt-900 text-white' : 'bg-lane-400 text-asphalt-900')} aria-hidden>
              {number}
            </span>
          ) : (
            Icon && (
              <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl transition', open ? 'bg-asphalt-900 text-white' : 'bg-asphalt-50 text-asphalt-700')} aria-hidden>
                <Icon className="size-5" />
              </span>
            )
          )}
          <span className="min-w-0 flex-1">
            <span className="block font-semibold text-asphalt-900">{title}</span>
            {subtitle && <span className="mt-0.5 block text-sm font-normal text-asphalt-500">{subtitle}</span>}
            {badges && badges.length > 0 && (
              <span className="mt-2 flex flex-wrap gap-1.5">
                {badges.map((badge) => (
                  <span key={badge} className="rounded-full bg-asphalt-50 px-2.5 py-0.5 text-xs font-medium text-asphalt-600 ring-1 ring-asphalt-100">
                    {badge}
                  </span>
                ))}
              </span>
            )}
          </span>
          <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-full transition', open ? 'bg-lane-400 text-asphalt-900' : 'bg-asphalt-50 text-asphalt-500')} aria-hidden>
            <ChevronDown className={cn('size-4 transition-transform duration-200', open && 'rotate-180')} />
          </span>
        </button>
      </h3>
      <div id={id} hidden={!open} className="border-t border-asphalt-100 bg-asphalt-50/40 px-5 py-4 text-sm leading-relaxed text-asphalt-700">
        {children}
      </div>
    </div>
  )
}
