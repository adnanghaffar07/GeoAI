/**
 * Short notices at the bottom of the screen ("Saved", "Could not save…").
 * A tiny store (no extra library): `notify.success(...)` from anywhere, `<Toaster />` shows them.
 */

export type NoticeKind = 'success' | 'error' | 'info'

export interface Notice {
  id: number
  kind: NoticeKind
  message: string
}

const SHOW_MS: Record<NoticeKind, number> = { success: 4000, info: 6000, error: 8000 }
const MAX_SHOWN = 3

let notices: Notice[] = []
let nextId = 1
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

export function dismissNotice(id: number): void {
  notices = notices.filter((notice) => notice.id !== id)
  emit()
}

function push(kind: NoticeKind, message: string): void {
  // The same message twice in a row (e.g. two failed saves) is shown once.
  if (notices.some((notice) => notice.message === message)) return
  const id = nextId++
  notices = [...notices, { id, kind, message }].slice(-MAX_SHOWN)
  emit()
  setTimeout(() => dismissNotice(id), SHOW_MS[kind])
}

export const notify = {
  success: (message: string) => push('success', message),
  error: (message: string) => push('error', message),
  info: (message: string) => push('info', message),
}

export function subscribeNotices(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getNotices(): Notice[] {
  return notices
}
