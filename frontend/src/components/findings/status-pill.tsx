import { REVIEW_STATUS_LABELS } from '@/api/findings'
import { STATUS_STYLES } from '@/lib/findings'
import { cn } from '@/lib/utils'

export function StatusPill({ status, className }: { status: string; className?: string }) {
  return <span className={cn('pill', STATUS_STYLES[status], className)}>{REVIEW_STATUS_LABELS[status] ?? status}</span>
}
