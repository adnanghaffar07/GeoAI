import { ShieldCheck } from 'lucide-react'

/**
 * S18 Retention. Automatic deletion stays off until the customer confirms how long photos,
 * findings and reports must be kept (partner input PI-13). Nothing is ever deleted now.
 */
export function SettingsRetentionPage() {
  return (
    <section className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">Data retention</h1>
        <p className="mt-1 text-asphalt-500">How long photos, findings, reports and the history are kept before they are deleted.</p>
      </header>
      <div className="panel flex gap-3 p-4 text-sm">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-emerald-700" aria-hidden />
        <div className="space-y-2">
          <p className="font-medium">Nothing is deleted automatically until your organization confirms how long to keep things.</p>
          <p className="text-asphalt-600">
            Everything is kept for now, including withdrawn photos, rejected findings, reports and the history. Once your organization
            confirms its rules, they will be set here. Every change will need to be confirmed and will be recorded in the history.
          </p>
        </div>
      </div>
    </section>
  )
}
