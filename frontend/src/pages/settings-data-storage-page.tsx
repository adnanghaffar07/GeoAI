import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cloud, HardDrive, LockKeyhole, Server } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { dataStorageQueryKeys, getDataStorage, saveDataStorage, type DataStorage, type DataStorageInput } from '@/api/data-storage'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { PasswordField, TextField } from '@/components/ui/field'
import { SkeletonRows } from '@/components/ui/loading-screen'

const when = (time: string | null) => (time ? new Date(time).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')

/** Read-only summary: where and how the files are kept (also on My account). */
export function DataStorageSummary({ storage }: { storage: DataStorage }) {
  const Icon = storage.kind === 's3' ? Cloud : HardDrive
  return (
    <dl className="panel grid grid-cols-[10rem_1fr] gap-y-2 p-4 text-sm">
      <dt className="text-asphalt-500">Where</dt>
      <dd className="flex items-center gap-2">
        <Icon className="size-4 text-asphalt-500" aria-hidden />
        {storage.place}
        {storage.location_note && <span className="text-asphalt-500">({storage.location_note})</span>}
      </dd>
      {storage.kind === 's3' && (
        <>
          <dt className="text-asphalt-500">Storage</dt>
          <dd>
            {storage.endpoint} · {storage.bucket}
            {storage.prefix && ` / ${storage.prefix}`}
          </dd>
          <dt className="text-asphalt-500">Last checked</dt>
          <dd>{when(storage.verified_at)}</dd>
        </>
      )}
      <dt className="text-asphalt-500">How</dt>
      <dd className="flex items-center gap-2">
        <LockKeyhole className="size-4 text-emerald-700" aria-hidden />
        Encrypted ({storage.encryption}); shown only to people with access, after a permission check
      </dd>
    </dl>
  )
}

/** Settings → Data storage (team lead plan, Phase 2). Organization admins choose where files are kept. */
export function SettingsDataStoragePage() {
  const { currentMembership } = useAuth()
  const orgId = currentMembership?.organization_id ?? ''
  const query = useQuery({ queryKey: dataStorageQueryKeys.one(orgId), queryFn: ({ signal }) => getDataStorage(orgId, signal), enabled: Boolean(orgId) })
  return (
    <section className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-[1.75rem] font-semibold tracking-tight">Data storage</h1>
        <p className="mt-1 text-asphalt-500">Where your organization's photos, reports and inspection pictures are kept, and how.</p>
      </header>
      {query.isPending && <SkeletonRows rows={3} />}
      {query.isError && <ErrorMessage title="Could not load the storage settings" error={query.error} onRetry={() => void query.refetch()} />}
      {query.isSuccess && (
        <>
          <DataStorageSummary storage={query.data} />
          {query.data.can_edit && <StorageForm orgId={orgId} current={query.data} />}
        </>
      )}
    </section>
  )
}

function StorageForm({ orgId, current }: { orgId: string; current: DataStorage }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState(current.kind)
  const [form, setForm] = useState({
    endpoint: current.endpoint ?? '',
    bucket: current.bucket ?? '',
    region: current.region ?? '',
    prefix: current.prefix ?? '',
    access_key_id: current.access_key_id ?? '',
    secret_key: '',
    location_note: current.location_note ?? '',
  })
  const save = useMutation({
    mutationFn: (body: DataStorageInput) => saveDataStorage(orgId, body),
    onSuccess: (data) => {
      queryClient.setQueryData(dataStorageQueryKeys.one(orgId), data)
      setForm((old) => ({ ...old, secret_key: '' }))
    },
    meta: { success: 'Storage saved. New files are kept there from now on.' },
  })
  const set = (name: keyof typeof form) => (event: { target: { value: string } }) => setForm((old) => ({ ...old, [name]: event.target.value }))
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(kind === 'app' ? { kind, location_note: form.location_note } : { kind, ...form })
  }
  const choices = [
    { value: 'app', icon: HardDrive, title: 'GeoInfraLens AI storage', text: 'Kept for you, encrypted. Nothing to set up.' },
    { value: 's3', icon: Server, title: 'Your own storage', text: 'Your cloud account (Amazon S3, Wasabi, Backblaze B2, Cloudflare R2) or your own computer or server running MinIO.' },
  ] as const

  return (
    <form onSubmit={submit} className="panel space-y-4 p-4">
      <fieldset className="space-y-2">
        <legend className="font-medium">Where should new files be kept?</legend>
        {choices.map((choice) => (
          <label key={choice.value} className="flex cursor-pointer items-start gap-3 rounded-xl border border-asphalt-200 p-3 has-[:checked]:border-asphalt-900">
            <input type="radio" name="kind" value={choice.value} checked={kind === choice.value} onChange={() => setKind(choice.value)} className="mt-1" />
            <choice.icon className="mt-0.5 size-5 shrink-0 text-asphalt-600" aria-hidden />
            <span>
              <span className="block font-medium">{choice.title}</span>
              <span className="block text-sm text-asphalt-600">{choice.text}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {kind === 's3' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField label="Storage address" placeholder="https://s3.us-east-1.amazonaws.com" value={form.endpoint} onChange={set('endpoint')} hint="For your own computer: its secure https address." />
          <TextField label="Bucket name" value={form.bucket} onChange={set('bucket')} />
          <TextField label="Region (optional)" placeholder="us-east-1" value={form.region} onChange={set('region')} />
          <TextField label="Folder in the bucket (optional)" value={form.prefix} onChange={set('prefix')} />
          <TextField label="Access key" value={form.access_key_id} onChange={set('access_key_id')} hint="Give it access to this bucket only." />
          <PasswordField
            label="Secret key"
            value={form.secret_key}
            onChange={set('secret_key')}
            hint={current.has_secret ? 'Saved. Leave empty to keep it.' : 'Kept encrypted; never shown again.'}
          />
        </div>
      )}
      <TextField label="Note (optional)" placeholder="For example: City IT office server" value={form.location_note} onChange={set('location_note')} />
      {save.isError && <ErrorMessage title="Could not save" error={save.error} />}
      <p className="text-sm text-asphalt-600">
        We test the storage first (write, read and delete a small file); nothing changes if the test fails. Files already saved stay readable.
        With your own computer, it must be on and online for photos to open and be checked.
      </p>
      <Button type="submit" busy={save.isPending}>
        {kind === 's3' ? 'Test and save' : 'Save'}
      </Button>
    </form>
  )
}
