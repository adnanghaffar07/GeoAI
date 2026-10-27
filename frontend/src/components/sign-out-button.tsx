import { useMutation } from '@tanstack/react-query'
import { LogOut } from 'lucide-react'
import { useNavigate } from 'react-router'

import { signOut } from '@/api/auth'
import { useAuth } from '@/auth/auth-context'
import { Button } from '@/components/ui/button'
import { isApiError } from '@/lib/api-client'

/** `compact`: an icon-only button for the dark menu. */
export function SignOutButton({ className, compact = false }: { className?: string; compact?: boolean }) {
  const auth = useAuth()
  const navigate = useNavigate()
  const mutation = useMutation({
    mutationFn: signOut,
    onSettled: (_data, error) => {
      // A 401 means the session had already ended; either way, leave the app.
      if (!error || (isApiError(error) && error.status === 401)) {
        auth.clearSession()
        void navigate('/sign-in', { replace: true })
      }
    },
  })

  return (
    <div className={className}>
      {compact ? (
        <button
          type="button"
          aria-label="Sign out"
          title="Sign out"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
          className="rounded-lg p-2 text-asphalt-300 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-50"
        >
          <LogOut className="size-[18px]" aria-hidden />
        </button>
      ) : (
        <Button variant="secondary" busy={mutation.isPending} onClick={() => mutation.mutate()}>
          Sign out
        </Button>
      )}
      {mutation.isError && !(isApiError(mutation.error) && mutation.error.status === 401) && (
        <p role="alert" className={compact ? 'sr-only' : 'mt-2 text-sm text-red-700'}>
          Could not sign out. Check your connection and try again.
        </p>
      )}
    </div>
  )
}
