import { useMutation } from '@tanstack/react-query'
import { CircleCheck, ShieldCheck } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router'

import { acceptAgreement } from '@/api/auth'
import { AGREEMENT_PARAGRAPHS } from '@/auth/agreement-text'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { SignOutButton } from '@/components/sign-out-button'
import { Button } from '@/components/ui/button'

export function AgreementDialog({ version }: { version: string }) {
  const auth = useAuth()
  const [remember, setRemember] = useState(false)
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const mutation = useMutation({ mutationFn: () => acceptAgreement(version, remember), onSuccess: (me) => auth.setSignedIn(me) })
  // Focus starts on "I agree", inside the dialog (keyboard and screen readers).
  useEffect(() => dialogRef.current?.querySelector<HTMLButtonElement>('[data-agree]')?.focus(), [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-asphalt-950/60 p-4 backdrop-blur-sm">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={`${titleId}-intro`} className="page-enter flex max-h-[92dvh] w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-black/5">
        <div className="flex items-start gap-4 border-b border-asphalt-100 bg-gradient-to-b from-lane-50 to-white px-6 pt-6 pb-5">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-lane-100 text-asphalt-900" aria-hidden>
            <ShieldCheck className="size-6" />
          </span>
          <div>
            <h1 id={titleId} className="text-xl font-semibold text-asphalt-900">
              GeoInfraLens AI disclaimer
            </h1>
            <p id={`${titleId}-intro`} className="mt-1 text-sm text-asphalt-600">
              Please read these points and agree before you continue.
            </p>
          </div>
        </div>
        <ul className="flex-1 space-y-3 overflow-y-auto px-6 py-5 text-sm leading-relaxed text-asphalt-700">
          {AGREEMENT_PARAGRAPHS.map((text) => (
            <li key={text} className="flex gap-3 rounded-xl bg-asphalt-50 p-3">
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-lane-600" aria-hidden />
              <span>{text}</span>
            </li>
          ))}
          <li className="list-none pt-1">
            <Link to="/about" className="inline-flex items-center gap-1 font-medium text-asphalt-800 underline underline-offset-2">
              Read the full terms of use and privacy
            </Link>
          </li>
        </ul>
        {mutation.isError && (
          <div className="px-6 pb-2">
            <ErrorMessage title="Could not save your answer" error={mutation.error} onRetry={() => mutation.mutate()} />
          </div>
        )}
        <div className="space-y-4 border-t border-asphalt-100 bg-asphalt-50/60 px-6 py-4">
          <div className="flex items-start gap-3 text-sm text-asphalt-700">
            <input
              id={`${titleId}-remember`}
              type="checkbox"
              className="mt-0.5 size-4 cursor-pointer"
              aria-describedby={`${titleId}-remember-hint`}
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            <div>
              <label htmlFor={`${titleId}-remember`} className="cursor-pointer font-medium text-asphalt-800">
                Remember my choice
              </label>
              <p id={`${titleId}-remember-hint`} className="text-xs text-asphalt-500">
                You will not be asked again on this account until the terms change.
              </p>
            </div>
          </div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <SignOutButton />
            <Button data-agree busy={mutation.isPending} onClick={() => mutation.mutate()} className="sm:min-w-32">
              I agree
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
