import type { ButtonHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

/** Look of a button. `accent` (yellow) is for the one main action on a page. */
export type ButtonVariant = 'primary' | 'accent' | 'secondary' | 'danger' | 'ghost'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  busy?: boolean
}

/** Standard button. `busy` disables it and shows a spinner. Styles live in index.css (`.btn-*`). */
export function Button({ variant = 'primary', busy = false, className, children, disabled, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      {...props}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cn('btn', `btn-${variant}`, className)}
    >
      {busy && <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  )
}
