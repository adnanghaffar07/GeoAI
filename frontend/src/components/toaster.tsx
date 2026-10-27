import { CircleAlert, CircleCheck, Info, X } from 'lucide-react'
import { useSyncExternalStore } from 'react'

import { dismissNotice, getNotices, subscribeNotices, type NoticeKind } from '@/lib/notify'
import { cn } from '@/lib/utils'

const STYLE: Record<NoticeKind, string> = {
  success: 'border-green-200 bg-white text-asphalt-900 [&_svg.kind]:text-green-700',
  error: 'border-red-200 bg-red-50 text-red-900 [&_svg.kind]:text-red-700',
  info: 'border-asphalt-200 bg-white text-asphalt-900 [&_svg.kind]:text-asphalt-600',
}
const ICON = { success: CircleCheck, error: CircleAlert, info: Info }

/** Shows the notices from `notify` at the bottom of the screen; screen readers announce them. */
export function Toaster() {
  const notices = useSyncExternalStore(subscribeNotices, getNotices)
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:items-end">
      {notices.map((notice) => {
        const Icon = ICON[notice.kind]
        return (
          <div
            key={notice.id}
            role={notice.kind === 'error' ? 'alert' : 'status'}
            className={cn('toast-enter pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border p-3 text-sm shadow-lg', STYLE[notice.kind])}
          >
            <Icon className="kind mt-0.5 size-4 shrink-0" aria-hidden />
            <p className="flex-1">{notice.message}</p>
            <button type="button" onClick={() => dismissNotice(notice.id)} className="rounded p-0.5 opacity-60 hover:opacity-100" aria-label="Close message">
              <X className="size-4" aria-hidden />
            </button>
          </div>
        )
      })}
    </div>
  )
}
