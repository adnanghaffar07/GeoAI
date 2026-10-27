/** Full-page loading state (never a blank page). */
export function LoadingScreen({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex min-h-[50vh] items-center justify-center gap-3 text-sm text-asphalt-500">
      <span className="size-4 animate-spin rounded-full border-2 border-asphalt-300 border-t-transparent" aria-hidden />
      {label}
    </div>
  )
}

/** Grey placeholder rows used while a list loads. */
export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-2">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-10 animate-pulse rounded-lg bg-asphalt-100" />
      ))}
    </div>
  )
}
