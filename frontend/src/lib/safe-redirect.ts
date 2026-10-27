/** Only allow redirects inside this app (never to another website, e.g. "//evil.example"). */
export function safeNextPath(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}
