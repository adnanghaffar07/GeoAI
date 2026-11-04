import axe from 'axe-core'
import { expect } from 'vitest'

/**
 * P9.4: automatic accessibility check (axe-core, WCAG 2.1 A and AA rules).
 *
 * Two rules are left out because the test browser (jsdom) cannot check them: colour contrast (no real
 * colours or layout) and "region" (screens are tested without the app frame that has the landmarks).
 * Contrast is checked by hand in the keyboard walk-through (p9-results.md).
 */
export async function expectNoAccessibilityProblems(container: Element) {
  const result = await axe.run(container, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    resultTypes: ['violations'],
  })
  const problems = result.violations.map(
    (v) => `${v.id}: ${v.help}\n  ${v.nodes.map((n) => n.target.join(' ')).join('\n  ')}`,
  )
  expect(problems, problems.join('\n')).toEqual([])
}
