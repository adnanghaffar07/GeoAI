import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, Cloud, Clock, Computer, Database, HardDrive, Info, LockKeyhole, MapPin, Server, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { dataStorageQueryKeys, getDataStorage, saveDataStorage, type DataStorage, type DataStorageInput } from '@/api/data-storage'
import { useAuth } from '@/auth/auth-context'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { DropdownCard } from '@/components/ui/dropdown-card'
import { PasswordField, TextField } from '@/components/ui/field'
import { SkeletonRows } from '@/components/ui/loading-screen'
import { cn } from '@/lib/utils'

const when = (time: string | null) => (time ? new Date(time).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')

/** Read-only summary: where and how the files are kept (also on My account). */
export function DataStorageSummary({ storage }: { storage: DataStorage }) {
  const own = storage.kind === 's3'
  const items = [
    { icon: own ? Cloud : HardDrive, label: 'Where', value: storage.place + (storage.location_note ? ` (${storage.location_note})` : '') },
    ...(own
      ? [
          { icon: MapPin, label: 'Storage', value: `${storage.endpoint} · ${storage.bucket}${storage.prefix ? ` / ${storage.prefix}` : ''}` },
          { icon: Clock, label: 'Last checked', value: when(storage.verified_at) },
        ]
      : []),
    { icon: LockKeyhole, label: 'How', value: `Encrypted (${storage.encryption}); shown only to people with access, after a permission check` },
  ]
  return (
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(({ icon: Icon, label, value }) => (
        <div key={label} className="rounded-2xl border border-asphalt-100 bg-white p-4 shadow-sm">
          <dt className="flex items-center gap-3 text-xs font-semibold tracking-wide text-asphalt-500 uppercase">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-lane-400 text-asphalt-900" aria-hidden>
              <Icon className="size-5" />
            </span>
            {label}
          </dt>
          <dd className="mt-2 text-sm font-medium break-words text-asphalt-900">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function SettingsDataStoragePage() {
  const { currentMembership } = useAuth()
  const orgId = currentMembership?.organization_id ?? ''
  const query = useQuery({ queryKey: dataStorageQueryKeys.one(orgId), queryFn: ({ signal }) => getDataStorage(orgId, signal), enabled: Boolean(orgId) })
  return (
    <section className="w-full space-y-6">
      <header className="flex flex-wrap items-center gap-4 rounded-2xl bg-asphalt-900 p-6 text-white shadow-sm">
        <span className="flex size-12 items-center justify-center rounded-xl bg-lane-400 text-asphalt-900" aria-hidden>
          <Database className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Data storage</h1>
          <p className="mt-1 text-asphalt-200">Where your organization's photos, reports and inspection pictures are kept, and how they are protected.</p>
        </div>
      </header>
      {query.isPending && <SkeletonRows rows={3} />}
      {query.isError && <ErrorMessage title="Could not load the storage settings" error={query.error} onRetry={() => void query.refetch()} />}
      {query.isSuccess && (
        <>
          <DataStorageSummary storage={query.data} />
          {query.data.can_edit && (
            <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
              <div className="space-y-4 xl:sticky xl:top-4">
                <StorageForm orgId={orgId} current={query.data} />
              </div>
              <StorageGuide />
            </div>
          )}
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
    <form onSubmit={submit} className="space-y-5 rounded-2xl border border-asphalt-100 bg-white p-5 shadow-sm">
      <fieldset className="space-y-3">
        <legend className="text-lg font-semibold text-asphalt-900">Where should new files be kept?</legend>
        {choices.map((choice) => (
          <label
            key={choice.value}
            className={cn(
              'flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition',
              kind === choice.value ? 'border-asphalt-900 bg-lane-50 ring-1 ring-asphalt-900' : 'border-asphalt-100 hover:bg-asphalt-50',
            )}
          >
            <input type="radio" name="kind" value={choice.value} checked={kind === choice.value} onChange={() => setKind(choice.value)} className="mt-3" />
            <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', kind === choice.value ? 'bg-asphalt-900 text-white' : 'bg-asphalt-50 text-asphalt-700')} aria-hidden>
              <choice.icon className="size-5" />
            </span>
            <span>
              <span className="block font-semibold text-asphalt-900">{choice.title}</span>
              <span className="block text-sm text-asphalt-600">{choice.text}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {kind === 's3' && (
        <div className="grid gap-3 rounded-2xl bg-asphalt-50/60 p-4 sm:grid-cols-2">
          <TextField label="Storage address" placeholder="https://s3.us-west-004.backblazeb2.com" value={form.endpoint} onChange={set('endpoint')} hint="Starts with https://" />
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
      <p className="flex gap-2 rounded-xl bg-lane-50 p-3 text-sm text-asphalt-700">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-asphalt-700" aria-hidden />
        <span>We test the storage first (write, read and delete a small file); nothing changes if the test fails. Files already saved stay readable.</span>
      </p>
      <Button type="submit" busy={save.isPending} className="w-full sm:w-auto">
        {kind === 's3' ? 'Test and save' : 'Save'}
      </Button>
    </form>
  )
}

/** The simple, step-by-step guide for administrators who are not technical (owner request 2026-11-10):
 * four ways to keep photos in your own space; each ends with the same "connect it here" part. */
type Part = { title: string; time: string; steps: string[] }
type Way = { key: string; title: string; best: string; needs: string; parts: Part[]; connect: string[] }

const CONNECT_END = [
  'Click "Test and save". We put a tiny test file in your storage, read it back and remove it. When you see "Storage saved", you are done. If you see a red message, fix that box and try again: nothing changes until it works.',
  'Upload one road photo to any project and open it here: it looks exactly as before. In your storage you will see new files with strange names: that is correct, they are locked and only GeoInfraLens AI can open them.',
]

const WAYS: Way[] = [
  {
    key: 'cloud',
    title: 'A free storage account in your name',
    best: 'Easiest. Best if you have no IT person.',
    needs: 'An email address and 15 minutes. Free for the first 10 GB (about 50,000 road photos).',
    parts: [
      { title: 'Make your free storage account', time: 'about 5 minutes', steps: ['Open a new browser tab and go to backblaze.com.', 'Click "Sign Up" at the top right and choose "B2 Cloud Storage".', "Type your organization's email address, choose a password, and click \"Create Account\".", 'Open the email from Backblaze and click the link in it to confirm your address.'] },
      { title: 'Make your storage box (Backblaze calls it a "bucket")', time: 'about 2 minutes', steps: ['On the left, click "Buckets", then "Create a Bucket".', 'Give it a name with your city in it, for example cityname-road-photos (small letters, numbers and dashes only).', 'Where it asks "Files in Bucket are", choose "Private". This keeps your box closed to the internet.', 'Click "Create a Bucket". Find the line "Endpoint" (for example s3.us-west-004.backblazeb2.com) and write it down.'] },
      { title: 'Make a key for GeoInfraLens AI', time: 'about 3 minutes', steps: ['On the left, click "Application Keys", then "Add a New Application Key".', 'Name it geoinfralens. Under "Allow access to Bucket(s)", choose your box (not "All").', 'Under "Type of Access", choose "Read and Write", then click "Create New Key".', 'Backblaze shows "keyID" and "applicationKey" only once. Copy both into a note for a moment and keep them private, like a password.'] },
    ],
    connect: ['Storage address: type https:// and then the Endpoint, for example https://s3.us-west-004.backblazeb2.com', 'Bucket name: the name of your box. Region: the middle part of the Endpoint, for example us-west-004.', 'Access key: the keyID. Secret key: the applicationKey.'],
  },
  {
    key: 'pc',
    title: 'Your own computer (PC)',
    best: 'Photos stay on a computer in your office.',
    needs: 'A Windows computer that stays switched on all the time, with enough free disk space, and about 30 minutes. If the computer is off, new uploads stop until it is back on.',
    parts: [
      { title: 'Get the free storage program (MinIO)', time: 'about 5 minutes', steps: ['On that computer, open this address in the browser: dl.min.io/server/minio/release/windows-amd64/minio.exe . The file minio.exe downloads.', 'Make a folder C:\\MinIO and move minio.exe into it.', 'Make a second folder where the photos will be kept, for example C:\\RoadPhotos.'] },
      { title: 'Start the storage program', time: 'about 5 minutes', steps: ['Open the folder C:\\MinIO. Click the address bar at the top of the window, type powershell and press Enter. A blue window opens.', 'Copy these three lines into the blue window, change the password to your own long password, and press Enter after each line:', '$env:MINIO_ROOT_USER = "cityadmin"', '$env:MINIO_ROOT_PASSWORD = "choose-a-long-password"', '.\\minio.exe server C:\\RoadPhotos --console-address ":9001"', 'Leave this blue window open. (Your IT person can later make it start by itself when the computer starts.)'] },
      { title: 'Make your storage box and a key', time: 'about 5 minutes', steps: ['In the browser on that computer, open localhost:9001 and sign in with "cityadmin" and your password.', 'Click "Buckets", then "Create Bucket". Name it road-photos and click "Create Bucket".', 'Click "Access Keys", then "Create access key", then "Create". Copy the "Access Key" and the "Secret Key" into a note for a moment.'] },
      { title: 'Give it a safe internet address', time: 'about 10 minutes', steps: ['Our server must be able to reach your computer through a safe (https) address. The free way is Cloudflare Tunnel.', 'In the browser, search for "cloudflared download Windows", open the Cloudflare page and download cloudflared for Windows. Save it in C:\\MinIO as cloudflared.exe.', 'Open a second blue window in C:\\MinIO (as in Part 2) and type: .\\cloudflared.exe tunnel --url http://localhost:9000 and press Enter.', 'After a few seconds it shows an address like https://some-words.trycloudflare.com. Copy it. Leave this window open too.', 'Note: this quick address changes when the computer restarts; you then type the new one here again. For an address that never changes, ask an IT person to make a "named tunnel" with your own web address.'] },
    ],
    connect: ['Storage address: the https address from Part 4, for example https://some-words.trycloudflare.com', 'Bucket name: road-photos. Region: us-east-1.', 'Access key and Secret key: the two values from Part 3.'],
  },
  {
    key: 'server',
    title: 'Your own server (with your IT team)',
    best: 'Best for city offices with an IT department or a network drive (NAS).',
    needs: 'Your IT person, about 1 hour of their time.',
    parts: [
      { title: 'Ask your IT team to prepare the storage', time: 'IT: about 1 hour', steps: ['Send them this sentence: "Please set up S3-compatible storage for GeoInfraLens AI, for example MinIO on one of our servers or the S3 feature of our network drive (NAS), with a private bucket, a key with read and write access to that bucket only, and a secure https address that the GeoInfraLens AI server can reach from the internet."', 'If they ask for more detail, they can use the technical guide that came with GeoInfraLens AI (guide-client-own-storage).'] },
      { title: 'Get five things back from them', time: 'a few minutes', steps: ['1. The storage address (it starts with https://)', '2. The bucket name', '3. The region (if they have none, use us-east-1)', '4. The access key', '5. The secret key'] },
    ],
    connect: ['Type the five things from your IT team into the matching boxes.', 'Note: write "Our own server" (or the server name) so everyone knows where the photos are.'],
  },
  {
    key: 'existing',
    title: 'A cloud account you already have',
    best: 'If your organization already uses Amazon, Cloudflare, Wasabi or Google Cloud.',
    needs: 'Access to that account, about 15 minutes.',
    parts: [
      { title: 'Make a private storage box and a key', time: 'about 10 minutes', steps: ['In your cloud account, create a new private storage box ("bucket") only for GeoInfraLens AI.', 'Create a key that may read and write files in that box only, and copy both parts of the key.', 'Amazon S3: address https://s3.<region>.amazonaws.com, region for example us-east-2 (make the key as an IAM user).', 'Cloudflare R2: address https://<your account number>.r2.cloudflarestorage.com, region auto (R2 → Manage API tokens → Object Read & Write).', 'Wasabi: address https://s3.<region>.wasabisys.com, region for example us-east-1.', 'Google Cloud Storage: address https://storage.googleapis.com, region auto (Settings → Interoperability → create an HMAC key).'] },
    ],
    connect: ['Storage address and region: as listed for your cloud in Part 1.', 'Bucket name: your new box. Access key and Secret key: the two parts of the key.'],
  },
]

const HELP: [string, string][] = [
  ['It says the address must start with https://', 'Type https:// in front of the address.'],
  ['It says the storage could not be reached', 'Check that the address is typed exactly. For your own computer: is it switched on, with both windows open? Then try again in a few minutes.'],
  ['It says access was refused', 'The keys were copied wrongly, or the key is for another box. Make a new key and paste it again.'],
  ['It says the bucket was not found', 'Check the bucket name: small letters, exactly as you made it.'],
]

const WAY_ICONS: Record<string, typeof Cloud> = { cloud: Cloud, pc: Computer, server: Server, existing: Database }
const WAY_BADGES: Record<string, string[]> = {
  cloud: ['About 15 minutes', 'Free up to 10 GB', 'Easiest'],
  pc: ['About 30 minutes', 'Free', 'Computer must stay on'],
  server: ['IT: about 1 hour', 'Uses your own server'],
  existing: ['About 15 minutes', 'Your current cloud plan'],
}

function StorageGuide() {
  return (
    <div className="space-y-6">
      <section aria-labelledby="ways-title" className="space-y-3">
        <div>
          <h2 id="ways-title" className="flex items-center gap-2 text-lg font-semibold text-asphalt-900">
            <span className="h-5 w-1.5 rounded-full bg-lane-400" aria-hidden />
            Four ways to keep your photos in your own space
          </h2>
          <p className="mt-1 text-sm text-asphalt-600">
            Our app keeps running on our server; only the files go to your space, locked (encrypted) before they leave. Pick the way that suits you and click it for the steps.
          </p>
        </div>
        {WAYS.map((way, wayIndex) => {
          const parts: Part[] = [
            ...way.parts,
            { title: 'Connect it here', time: 'about 3 minutes', steps: ['On the left, choose "Your own storage".', ...way.connect, 'Note (optional): anything that helps you remember where the photos are.', ...CONNECT_END] },
          ]
          return (
            <DropdownCard key={way.key} title={`${wayIndex + 1}. ${way.title}`} subtitle={way.best} icon={WAY_ICONS[way.key]} badges={WAY_BADGES[way.key]}>
              <p className="mb-4 flex gap-2 rounded-xl bg-lane-50 p-3">
                <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>
                  <span className="font-semibold text-asphalt-900">What you need: </span>
                  {way.needs}
                </span>
              </p>
              <ol className="space-y-4">
                {parts.map((part, index) => (
                  <li key={part.title} className="rounded-xl border border-asphalt-100 bg-white p-4">
                    <h4 className="flex items-center gap-3 font-semibold text-asphalt-900">
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-lane-400 text-xs font-bold" aria-hidden>
                        {index + 1}
                      </span>
                      <span>
                        Part {index + 1}: {part.title} <span className="font-normal text-asphalt-500">({part.time})</span>
                      </span>
                    </h4>
                    <ul className="mt-3 space-y-1.5 pl-10">
                      {part.steps.map((step) =>
                        step.startsWith('$env') || step.startsWith('.\\') ? (
                          <li key={step}>
                            <code className="block rounded-lg bg-asphalt-900 px-3 py-2 font-mono text-xs break-all text-white">{step}</code>
                          </li>
                        ) : (
                          <li key={step} className="list-disc">
                            {step}
                          </li>
                        ),
                      )}
                    </ul>
                  </li>
                ))}
              </ol>
            </DropdownCard>
          )
        })}
      </section>
      <section aria-labelledby="more-title" className="space-y-3">
        <h2 id="more-title" className="flex items-center gap-2 text-lg font-semibold text-asphalt-900">
          <span className="h-5 w-1.5 rounded-full bg-lane-400" aria-hidden />
          Good to know
        </h2>
        <DropdownCard title="Before and after you switch" icon={Info}>
          <ul className="list-disc space-y-1 pl-5">
            <li>Photos saved before you switch stay with us and still open normally. Only new photos go to your storage.</li>
            <li>Do not delete files in your storage by hand, and do not delete the key: the photos would then be missing here.</li>
            <li>To switch back: on the left, choose "GeoInfraLens AI storage" and click "Save".</li>
          </ul>
        </DropdownCard>
        <DropdownCard title="If something goes wrong" icon={CircleAlert}>
          <dl className="divide-y divide-asphalt-100 rounded-xl border border-asphalt-100 bg-white">
            {HELP.map(([problem, fix]) => (
              <div key={problem} className="grid gap-1 p-3 sm:grid-cols-2">
                <dt className="font-medium text-asphalt-900">{problem}</dt>
                <dd>{fix}</dd>
              </div>
            ))}
          </dl>
        </DropdownCard>
      </section>
    </div>
  )
}
