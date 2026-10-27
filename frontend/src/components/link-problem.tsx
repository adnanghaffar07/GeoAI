import { Link } from 'react-router'

import { ErrorMessage } from '@/components/error-message'
import { isApiError } from '@/lib/api-client'

const REASONS: Record<string, string> = {
  expired: 'This link has expired.',
  used: 'This link has already been used.',
  revoked: 'This link was cancelled. A newer link may have been sent.',
  invalid: 'This link is not valid. Check that you copied all of it.',
}

/** Explains why an invitation or reset link cannot be used, and what to do next. */
export function LinkProblem({ error, whatToDo }: { error: unknown; whatToDo: string }) {
  if (isApiError(error) && error.code === 'link_invalid') {
    const reason = (error.details as { reason?: string } | null)?.reason ?? 'invalid'
    return (
      <div role="alert" className="space-y-3 text-sm">
        <p className="font-medium text-asphalt-900">{REASONS[reason] ?? REASONS.invalid}</p>
        <p className="text-asphalt-500">{whatToDo}</p>
        <Link to="/sign-in" className="inline-block link">
          Go to sign in
        </Link>
      </div>
    )
  }
  return <ErrorMessage title="Could not open this link" error={error} />
}
