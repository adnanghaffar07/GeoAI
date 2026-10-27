/**
 * Browser console messages (F12 → Console), all starting with [GeoInfraLens].
 *
 * - While developing (`npm run dev`): every call to the backend, plus info and warnings.
 * - In the released app: only errors (failed loads and saves, crashes), each with its reference
 *   number, so a problem a user reports can be matched to the server log.
 * - In tests: silent.
 * Never pass passwords, link codes or file contents here.
 */

const isTest = import.meta.env.MODE === 'test'
const verbose = import.meta.env.DEV && !isTest
const PREFIX = '%c[GeoInfraLens]'
const STYLE = 'color:#1b2633;background:#f2b705;padding:1px 4px;border-radius:3px;font-weight:600'

/** Hide one-time link codes in addresses (same rule as the server's console). */
const safePath = (path: string) => path.replace(/(\/auth\/(?:invitations|password-resets)\/)[^/?]+/, '$1***')

export const logger = {
  /** One line per call to the backend, e.g. "POST /v1/auth/login → 200 (84 ms)". Development only. */
  request(method: string, path: string, status: number, ms: number, requestId: string | null) {
    if (!verbose) return
    const line = `${method} ${safePath(path)} → ${status || 'no response'} (${Math.round(ms)} ms)`
    const ref = requestId ? ` ref=${requestId}` : ''
    if (status === 0 || status >= 500) console.error(PREFIX, STYLE, line + ref)
    else if (status >= 400 && status !== 401) console.warn(PREFIX, STYLE, line + ref)
    else console.info(PREFIX, STYLE, line)
  },
  info(message: string, ...details: unknown[]) {
    if (verbose) console.info(PREFIX, STYLE, message, ...details)
  },
  warn(message: string, ...details: unknown[]) {
    if (verbose) console.warn(PREFIX, STYLE, message, ...details)
  },
  /** Something failed for the user. Shown in the released app too. */
  error(message: string, ...details: unknown[]) {
    if (!isTest) console.error(PREFIX, STYLE, message, ...details)
  },
}
