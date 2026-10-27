import type { ReactNode } from 'react'

import { BrandName } from '@/components/brand-mark'

/**
 * Frame for the sign-in, invitation and password pages (no menu): an asphalt panel
 * with a dashed centre line on the left, the form on the right. On phones the panel
 * becomes a short band at the top.
 */
export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-canvas lg:flex-row">
      <aside className="relative overflow-hidden bg-asphalt-900 px-6 py-6 text-white lg:flex lg:w-[44%] lg:flex-col lg:justify-between lg:px-14 lg:py-12">
        <CentreLine />
        <div className="relative">
          <BrandName tone="light" />
        </div>
        <div className="relative hidden max-w-md lg:block">
          <p className="text-[2.1rem] leading-[1.15] font-semibold tracking-tight text-white">
            See road and sidewalk problems on the map, and check every one before it counts.
          </p>
          <p className="mt-5 text-base leading-relaxed text-asphalt-200">
            Upload survey photos, review what the AI suggests, and plan inspections for your city.
          </p>
        </div>
        <p className="relative hidden text-sm text-asphalt-300 lg:block">AI suggestions are always confirmed by a person.</p>
      </aside>

      <main className="flex flex-1 items-center justify-center px-4 py-10 sm:px-8">
        <div className="page-enter w-full max-w-[400px]">
          <h1 className="text-[1.75rem] font-semibold tracking-tight">{title}</h1>
          {subtitle && <div className="mt-2 text-[15px] leading-relaxed text-asphalt-500">{subtitle}</div>}
          <div className="mt-8">{children}</div>
        </div>
      </main>
    </div>
  )
}

/** The dashed yellow centre line running down the panel (decorative). */
function CentreLine() {
  return (
    <svg aria-hidden className="pointer-events-none absolute inset-y-0 right-10 hidden h-full w-3 lg:block" preserveAspectRatio="none">
      <line x1="6" y1="0" x2="6" y2="100%" stroke="#f2b705" strokeWidth="6" strokeDasharray="44 30" strokeLinecap="butt" />
    </svg>
  )
}
