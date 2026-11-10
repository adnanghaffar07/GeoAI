import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2 } from 'lucide-react'
import { useState } from 'react'

import { createShareLink, fullLink, listShareLinks, revokeShareLink, shareLinksKey } from '@/api/share-links'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'

/** Managers only: make a secret link to this photo's preview, see the links and cancel them. */
export function SharePhoto({ imageId }: { imageId: string }) {
  const client = useQueryClient()
  const [days, setDays] = useState(7)
  const [made, setMade] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const links = useQuery({ queryKey: shareLinksKey(imageId), queryFn: ({ signal }) => listShareLinks(imageId, signal) })
  const refresh = () => client.invalidateQueries({ queryKey: shareLinksKey(imageId) })
  const create = useMutation({
    mutationFn: () => createShareLink(imageId, days),
    onSuccess: (link) => {
      setMade(link.url ? fullLink(link.url) : null)
      setCopied(false)
      void refresh()
    },
  })
  const revoke = useMutation({ mutationFn: (linkId: string) => revokeShareLink(imageId, linkId), onSuccess: () => void refresh() })
  const active = links.data?.filter((l) => l.state === 'active') ?? []

  return (
    <section aria-label="Share this photo" className="space-y-2 border-t border-asphalt-100 pt-3 text-sm">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col text-xs text-asphalt-600">
          Link works for
          <select className="control mt-1 h-9 py-1 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[1, 7, 30].map((d) => (
              <option key={d} value={d}>
                {d === 1 ? '1 day' : `${d} days`}
              </option>
            ))}
          </select>
        </label>
        <Button variant="secondary" busy={create.isPending} onClick={() => create.mutate()}>
          <Link2 className="size-4" aria-hidden />
          Make a share link
        </Button>
      </div>
      {create.isError && <ErrorMessage error={create.error} />}
      {made && (
        <div className="space-y-1 rounded bg-asphalt-50 p-2">
          <p className="text-xs text-asphalt-600">Anyone with this link can see the photo (no location). Copy it now: it is shown only once.</p>
          <input readOnly aria-label="Share link" className="control h-9 w-full py-1 text-xs" value={made} onFocus={(e) => e.target.select()} />
          <Button
            variant="secondary"
            onClick={() => {
              void navigator.clipboard?.writeText(made).then(() => setCopied(true))
            }}
          >
            {copied ? 'Copied' : 'Copy link'}
          </Button>
        </div>
      )}
      {active.length > 0 && (
        <ul aria-label="Working links" className="space-y-1">
          {active.map((l) => (
            <li key={l.id} className="flex items-center justify-between gap-2 text-xs">
              <span>Ends {new Date(l.expires_at).toLocaleDateString()}</span>
              <Button variant="secondary" busy={revoke.isPending && revoke.variables === l.id} onClick={() => revoke.mutate(l.id)}>
                Cancel link
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
