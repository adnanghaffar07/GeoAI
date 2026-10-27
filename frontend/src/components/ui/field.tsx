import { Eye, EyeOff } from 'lucide-react'
import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

interface FieldProps {
  label: string
  error?: string
  hint?: ReactNode
}

function FieldMessage({ id, error, hint }: { id: string; error?: string; hint?: ReactNode }) {
  if (error) {
    return (
      <p id={id} className="mt-1.5 text-sm text-red-700">
        {error}
      </p>
    )
  }
  return hint ? (
    <p id={id} className="mt-1.5 text-sm text-asphalt-500">
      {hint}
    </p>
  ) : null
}

/** A labelled text input with its error shown right below it. */
export const TextField = forwardRef<HTMLInputElement, FieldProps & InputHTMLAttributes<HTMLInputElement>>(
  function TextField({ label, error, hint, className, ...props }, ref) {
    const id = useId()
    const messageId = `${id}-message`
    return (
      <div className={className}>
        <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-asphalt-800">
          {label}
        </label>
        <input
          id={id}
          ref={ref}
          aria-invalid={error ? true : undefined}
          aria-describedby={error || hint ? messageId : undefined}
          className="control"
          {...props}
        />
        <FieldMessage id={messageId} error={error} hint={hint} />
      </div>
    )
  },
)

/** A password input with an eye button that shows or hides what was typed. */
export const PasswordField = forwardRef<HTMLInputElement, FieldProps & Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>>(
  function PasswordField({ label, error, hint, className, ...props }, ref) {
    const id = useId()
    const messageId = `${id}-message`
    const [visible, setVisible] = useState(false)
    const Icon = visible ? EyeOff : Eye
    return (
      <div className={className}>
        <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-asphalt-800">
          {label}
        </label>
        <div className="relative">
          <input
            id={id}
            ref={ref}
            type={visible ? 'text' : 'password'}
            aria-invalid={error ? true : undefined}
            aria-describedby={error || hint ? messageId : undefined}
            className="control pr-11"
            {...props}
          />
          <button
            type="button"
            onClick={() => setVisible((value) => !value)}
            aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
            aria-pressed={visible}
            className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-asphalt-500 transition-colors hover:text-asphalt-900"
          >
            <Icon className="size-[18px]" aria-hidden />
          </button>
        </div>
        <FieldMessage id={messageId} error={error} hint={hint} />
      </div>
    )
  },
)

export const SelectField = forwardRef<HTMLSelectElement, FieldProps & SelectHTMLAttributes<HTMLSelectElement>>(
  function SelectField({ label, error, className, children, ...props }, ref) {
    const id = useId()
    return (
      <div className={className}>
        <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-asphalt-800">
          {label}
        </label>
        <select id={id} ref={ref} aria-invalid={error ? true : undefined} className={cn('control', 'pr-8')} {...props}>
          {children}
        </select>
        {error && <p className="mt-1.5 text-sm text-red-700">{error}</p>}
      </div>
    )
  },
)
