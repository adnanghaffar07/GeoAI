// Adds DOM matchers such as toBeInTheDocument() to Vitest.
import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Remove each test's rendered screen so tests never see each other's output.
afterEach(() => cleanup())

// Charts (Recharts) measure their box with ResizeObserver, which jsdom does not have.
// Report a fixed size so charts render in tests.
class TestResizeObserver {
  private readonly callback: ResizeObserverCallback
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }
  observe(target: Element) {
    const rect = { width: 600, height: 300, top: 0, left: 0, right: 600, bottom: 300, x: 0, y: 0, toJSON: () => ({}) }
    this.callback([{ target, contentRect: rect } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= TestResizeObserver as unknown as typeof ResizeObserver
