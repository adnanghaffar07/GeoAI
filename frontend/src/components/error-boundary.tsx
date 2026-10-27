import { Component, type ErrorInfo, type ReactNode } from 'react'

import { logger } from '@/lib/logger'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

/**
 * Last line of defence: if any component crashes while rendering, show a
 * message instead of a blank page. Route-level errors are handled by
 * `RouteErrorPage`; this catches everything else.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    logger.error('The app crashed while showing a page', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children
    return (
      <main className="mx-auto max-w-xl p-8">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="mt-2 text-asphalt-500">This is not your fault. Reloading the page usually fixes it. Anything you already saved is safe.</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-4 rounded-lg bg-asphalt-900 px-4 py-2 text-sm font-medium text-white hover:bg-asphalt-700"
        >
          Reload page
        </button>
      </main>
    )
  }
}
