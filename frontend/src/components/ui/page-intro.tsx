import type { ReactNode } from 'react'

interface PageIntroProps {
  title: string
  /** One plain sentence: what this page is for. */
  children?: ReactNode
  /** The page's main buttons (e.g. "Upload photos"). */
  actions?: ReactNode
}

/** Heading at the top of a page: its name, what it is for, and its main action. */
export function PageIntro({ title, children, actions }: PageIntroProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0 max-w-3xl">
        <h2 className="text-lg font-semibold">{title}</h2>
        {children && <p className="mt-1 text-sm text-asphalt-500">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  children?: ReactNode
  action?: ReactNode
}

/** Shown instead of an empty list: says why it is empty and what to do next. */
export function EmptyState({ icon, title, children, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center rounded-xl border-2 border-dashed border-asphalt-200 bg-white/70 px-6 py-10 text-center">
      {icon && <div className="mb-3 text-asphalt-300 [&>svg]:size-9">{icon}</div>}
      <p className="font-medium text-asphalt-800">{title}</p>
      {children && <p className="mt-1 max-w-md text-sm text-asphalt-500">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
