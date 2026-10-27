import { isRouteErrorResponse, Link, useRouteError } from 'react-router'

import { BrandName } from '@/components/brand-mark'
import { logger } from '@/lib/logger'

/** After an update, an open tab may ask for page files that no longer exist; reloading fetches the new ones. */
function isOutdatedApp(error: unknown): boolean {
  const text = error instanceof Error ? error.message : String(error)
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported module|Loading chunk/i.test(text)
}

/** Shown by the router when a page fails to load or crashes. */
export function RouteErrorPage() {
  const error = useRouteError()
  const outdated = isOutdatedApp(error)
  logger.error(outdated ? 'Page files changed (app was updated); asking the user to reload' : 'A page crashed', error)

  let title = 'Something went wrong on this page'
  let message = 'This is not your fault. Reloading the page usually fixes it. If it keeps happening, tell your administrator what you were doing.'
  if (outdated) {
    title = 'The app has been updated'
    message = 'Reload the page to get the latest version. Nothing you saved is lost.'
  } else if (isRouteErrorResponse(error) && error.status === 404) {
    title = 'Page not found'
    message = 'The address may be mistyped, or the page has moved.'
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <div className="w-full max-w-md panel p-6 text-center">
        <div className="mb-5 flex justify-center">
          <BrandName />
        </div>
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="mt-2 text-sm text-asphalt-500">{message}</p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <button type="button" onClick={() => window.location.reload()} className="btn btn-accent">
            Reload page
          </button>
          <Link to="/" className="btn btn-secondary" reloadDocument>
            Go to Home
          </Link>
        </div>
      </div>
    </main>
  )
}
