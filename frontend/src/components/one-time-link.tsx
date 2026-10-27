import { useState } from 'react'

import { Button } from '@/components/ui/button'

/**
 * Shows an invite or reset link once, with a Copy button (FR-54, FR-55).
 * The server never shows the link again, so the admin is told to copy it now.
 */
export function OneTimeLink({ title, url, note, onDone }: { title: string; url: string; note: string; onDone: () => void }) {
  const [copied, setCopied] = useState<'no' | 'yes' | 'failed'>('no')

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied('yes')
    } catch {
      setCopied('failed') // clipboard can be blocked; the text box can still be copied by hand
    }
  }

  return (
    <div role="status" className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm">
      <p className="font-medium text-green-900">{title}</p>
      <p className="mt-1 text-green-800">{note}</p>
      <div className="mt-3 flex gap-2">
        <input
          readOnly
          value={url}
          aria-label="Link"
          onFocus={(event) => event.currentTarget.select()}
          className="min-w-0 flex-1 rounded-lg border border-green-300 bg-white px-2 py-1.5 font-mono text-xs"
        />
        <Button variant="secondary" onClick={() => void copy()}>
          {copied === 'yes' ? 'Copied' : 'Copy'}
        </Button>
      </div>
      {copied === 'failed' && <p className="mt-2 text-red-700">Copy was blocked by the browser. Select the link and copy it by hand.</p>}
      <Button variant="ghost" className="mt-2" onClick={onDone}>
        Done
      </Button>
    </div>
  )
}
