import { useMutation } from '@tanstack/react-query'
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-asphalt-950/70 p-4">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} className="page-enter w-full max-w-2xl rounded-2xl bg-white shadow-2xl">
        <h1 id={titleId} className="border-t-4 border-lane-500 px-6 pt-5 text-2xl font-semibold text-asphalt-900">
          GeoInfraLens AI disclaimer
        </h1>
        <div className="max-h-[55dvh] space-y-3 overflow-y-auto px-6 py-4 text-asphalt-700">
          {AGREEMENT_PARAGRAPHS.map((text) => (
            <p key={text}>{text}</p>
          ))}
          <p>
            <Link to="/about" className="underline">
              Read the full terms of use and privacy
            </Link>
          </p>
        </div>
        {mutation.isError && (
          <div className="px-6">
            <ErrorMessage title="Could not save your answer" error={mutation.error} onRetry={() => mutation.mutate()} />
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-asphalt-100 px-6 py-4">
          <label className="flex items-center gap-2 text-sm text-asphalt-700">
            <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
            Remember my choice
          </label>
          <div className="flex items-center gap-2">
            <SignOutButton />
            <Button data-agree busy={mutation.isPending} onClick={() => mutation.mutate()}>
              I agree
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
