import { isApiError } from '@/lib/api-client'

interface ErrorMessageProps {
  error: unknown
  title?: string
  onRetry?: () => void
}

interface FieldProblem {
  field: string
  message: string
}

/** Field problems from the server's validation errors, in readable form. */
function fieldProblems(details: unknown): FieldProblem[] {
  if (typeof details !== 'object' || details === null || !('fields' in details)) return []
  const fields = (details as { fields: unknown }).fields
  if (!Array.isArray(fields)) return []
  return fields
    .filter((item): item is FieldProblem => typeof item?.field === 'string' && typeof item?.message === 'string')
    .map((item) => ({
      field: item.field.replace(/^(body|query|path)\.?/, '').replaceAll('_', ' '),
      message: item.message.replace(/^Value error, /, ''),
    }))
}

/** Shows a user-safe error message, with the request ID when there is one (for support). */
export function ErrorMessage({ error, title = 'Something went wrong', onRetry }: ErrorMessageProps) {
  const message = isApiError(error)
    ? error.message
    : 'An unexpected error occurred. Please try again.'
  const requestId = isApiError(error) ? error.requestId : null
  const problems = isApiError(error) ? fieldProblems(error.details) : []

  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-medium">{title}</p>
      <p className="mt-1">{message}</p>
      {problems.length > 0 && (
        <ul className="mt-2 list-disc space-y-0.5 pl-5">
          {problems.map((problem, index) => (
            <li key={index}>
              {problem.field && <span className="font-medium">{problem.field}: </span>}
              {problem.message}
            </li>
          ))}
        </ul>
      )}
      {requestId && <p className="mt-2 text-xs text-red-700">If you contact support, quote this reference: {requestId}</p>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-lg border border-red-300 bg-white px-3 py-1.5 font-medium hover:bg-red-100"
        >
          Try again
        </button>
      )}
    </div>
  )
}
