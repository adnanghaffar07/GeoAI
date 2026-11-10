import {
  Accessibility,
  ChevronDown,
  CircleCheck,
  CircleHelp,
  Clock,
  Database,
  FileText,
  HardDrive,
  Keyboard,
  ListChecks,
  Palette,
  ScanSearch,
  Search,
  ShieldCheck,
  Table2,
  UserCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/auth-context'
import { AGREEMENT_PARAGRAPHS } from '@/auth/agreement-text'
import { BrandName } from '@/components/brand-mark'
import { cn } from '@/lib/utils'

/** About page (team lead plan, Phase 1, tl-phase1-design.md §3): readable without signing in. */

/** Step by step: how to use the app, in the order the work is done. */
const STEPS: [string, string][] = [
  ['Sign in and agree', 'Sign in with the account your organization gave you. Each time you sign in, you are asked to read the disclaimer and click "I agree" before the app opens.'],
  ['Open or create a project', 'A project is one area of roads, for example a neighbourhood. Open it from Projects. Managers can create a new project and draw its area on the map.'],
  ['Add your team', 'Managers open the project\'s Settings, then Team, and add people with a role: field collector (takes photos), technical reviewer (checks the AI), viewer (looks only) or manager.'],
  ['Upload road photos', 'In the project, open Photos, then Upload. Choose clear daylight photos with the phone\'s location (GPS) switched on. A photo without a location can still be reviewed; you can place it on the map by hand.'],
  ['Send photos to the AI check', 'On the Photos tab, send the new photos to the AI check and wait until it has finished. The AI marks possible potholes and cracks with a box. These are suggestions only.'],
  ['Review every suggestion', 'Reviewers open Findings and check each suggestion: verify it, reject it, change the type or severity, or ask for a field check. Only verified problems count in the priority list and reports.'],
  ['See the photos and problems on the map', 'The Findings tab shows every problem on a map and in a list. The Photo map tab shows every analysed photo as a pin; click a pin to see the photo with all its problem boxes. Managers can make a share link to a photo for someone without an account (it ends after 1 to 30 days and can be cancelled).'],
  ['Decide what to fix first', 'The Priority tab ranks verified problems by severity, type of road and nearby places such as schools. Plan an inspection for a colleague with a due date; they record the result under My inspections.'],
  ['Make a report', 'Open Reports, then "Make a new report", and choose CSV (for spreadsheets), GeoJSON (for map software) or PDF. Reports say which AI model and settings were used.'],
  ['Use road risk (optional)', 'A manager switches it on in the project\'s Settings, then Road risk. The Road risk tab then lists the roads most likely to need attention soon, with plain reasons, weather alerts and road details such as the speed limit. You can plan an inspection from any road and ask the assistant questions.'],
]

/** Where each kind of data is kept. */
const STORAGE: [string, string][] = [
  ['Photos (the original file and a smaller copy for screens)', 'In your organization\'s file storage. By default this is the private storage of the server that runs the app. An organization administrator can switch to the organization\'s own storage instead (an S3-type service such as Amazon S3, Cloudflare R2, Wasabi, or MinIO running on the organization\'s own computer or server) in Settings, then Data storage. New files go there from then on; files saved earlier stay where they were and can still be opened.'],
  ['How files are protected', 'Every file is encrypted (AES-256-GCM) before it is saved, wherever it is saved, so the storage company cannot read it. The key to your own storage is also kept encrypted. Each file is shown only after a sign-in and permission check.'],
  ['Findings, reviews, inspections, accounts and history', 'In the app\'s database (PostgreSQL) on the server that runs the app. Every change is kept in the history, which managers can see in the project\'s Settings, then History.'],
  ['Photo locations', 'The location saved with each photo (from its GPS, or placed by hand). It is the camera position, so it is approximate. Share links never include it.'],
  ['Road-risk data', 'Public data only (city pothole reports where published, weather, roads, elevation, flood zones, road condition), kept in a separate database on the same server. None of your photos or findings are added to it.'],
  ['Where can I check this for my organization?', 'Open Settings, then Data storage (organization administrators can change it there), or My account, which shows "Where your data is stored".'],
  ['Withdrawing a photo', 'Managers can withdraw a photo, and field collectors can withdraw their own photos before the AI check. A withdrawn photo is hidden from the photo list and the photo map, and any share link to it stops working.'],
]

const FAQ: [string, string][] = [
  ['What does GeoInfraLens AI do?', 'It helps a city find road damage. Field staff upload road photos, an AI marks possible potholes and cracks, a reviewer confirms each one, and the results show on a map, in a priority list and in reports. A separate road-risk view shows which roads are more likely to get potholes soon.'],
  ['Is the AI always right?', 'No. AI results can be wrong or incomplete. Every AI suggestion is checked by a person before it counts, and you should always confirm on site before acting.'],
  ['What do the colours and levels mean?', 'High, medium and low are shown in words as well as colours. On road risk, "high" means the road is among the roads most likely to need attention soon, compared with the others in the area. It is not a confirmed defect.'],
  ['Who can see my photos?', 'Only people in your organization who have access to the project, according to their role, and people a manager sends a share link to (until the link ends or is cancelled).'],
  ['Why is a photo not on the map?', 'The photo had no location. You can still review it; add the location by hand or retake the photo with location switched on.'],
  ['How is the priority worked out?', 'From the severity confirmed by the reviewer, the type of road and nearby places such as schools. The weights are set by your organization and shown next to every score.'],
  ['Where does road-risk information come from?', 'From free public data: city pothole reports where published, weather (NOAA and the National Weather Service), measured road condition and traffic (Federal Highway Administration), roads, speed limits and lanes (OpenStreetMap), elevation (USGS) and flood zones (FEMA).'],
  ['Where do the traffic camera pictures come from?', 'From the Illinois Department of Transportation\'s Gateway traffic cameras (shared under the Creative Commons Attribution-ShareAlike 2.0 licence). Viewing them stores nothing. "Take snapshot" saves that one picture (about 70 KB) as a project photo in your organization\'s storage, credited to IDOT, so it can go to the AI check like any upload.'],
  ['Why does a road say "Not on the map" for its speed limit?', 'Road details come from OpenStreetMap, and not every road has them there. The app never guesses a missing value. Always check the signs on site.'],
  ['What road problems can the AI find, and how serious are they?', 'Potholes, surface cracking and pavement deterioration. Field staff can also add observations by hand, for example on a sidewalk. When a reviewer verifies a problem, they give it a severity level (for example low, medium or high) from your organization\'s severity scale.'],
  ['How long is my data kept?', 'Nothing is deleted automatically. Photos (including withdrawn ones), findings (including rejected ones), reports and the history are all kept until your organization confirms how long it must keep them; those rules will then be set with you, and every change is recorded in the history.'],
  ['How do I report a mistake?', 'Open the finding and correct it, or tell your organization\'s administrator. Every change is kept in the history.'],
]

const TABS = ['FAQ', 'Terms of use', 'Accessibility', 'Privacy'] as const
type Tab = (typeof TABS)[number]

const TAB_INFO: Record<Tab, { icon: LucideIcon; text: string }> = {
  FAQ: { icon: CircleHelp, text: 'How to use the app, where your data is kept, and common questions' },
  'Terms of use': { icon: FileText, text: 'The rules for using GeoInfraLens AI' },
  Accessibility: { icon: Accessibility, text: 'How the app works for everyone' },
  Privacy: { icon: ShieldCheck, text: 'What we store, where, and who can see it' },
}

export function AboutPage() {
  const auth = useAuth()
  const [tab, setTab] = useState<Tab>('FAQ')
  const info = TAB_INFO[tab]
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="border-b border-asphalt-100 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <BrandName />
          <Link to={auth.me ? '/' : '/sign-in'} className="btn btn-secondary">
            {auth.me ? 'Back to the app' : 'Sign in'}
          </Link>
        </div>
      </header>
      <div className="bg-asphalt-900 text-white">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">About GeoInfraLens AI</h1>
          <p className="mt-2 max-w-2xl text-asphalt-200">Road damage from photos, checked by people, shown on a map: here is how it works, the rules, and how we look after your data.</p>
        </div>
      </div>
      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[15rem_1fr]">
        <div role="tablist" aria-label="About" aria-orientation="vertical" className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
          {TABS.map((name) => {
            const Icon = TAB_INFO[name].icon
            return (
              <button
                key={name}
                type="button"
                role="tab"
                id={`tab-${name}`}
                aria-selected={tab === name}
                aria-controls="about-panel"
                onClick={() => setTab(name)}
                className={cn(
                  'flex shrink-0 items-center gap-3 rounded-xl px-4 py-3 text-left text-sm font-medium transition',
                  tab === name ? 'bg-white text-asphalt-900 shadow-sm ring-1 ring-asphalt-200' : 'text-asphalt-600 hover:bg-white/70',
                )}
              >
                <Icon className={cn('size-5', tab === name ? 'text-asphalt-900' : 'text-asphalt-400')} aria-hidden />
                {name}
              </button>
            )
          })}
        </div>
        <section id="about-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="min-w-0 space-y-6">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-full bg-lane-400 text-asphalt-900" aria-hidden>
              <info.icon className="size-5" />
            </span>
            <div>
              <h2 className="text-xl font-semibold text-asphalt-900">{tab}</h2>
              <p className="text-sm text-asphalt-500">{info.text}</p>
            </div>
          </div>
          {tab === 'FAQ' && <FaqPanel />}
          {tab === 'Terms of use' && <TermsPanel />}
          {tab === 'Accessibility' && <AccessibilityPanel />}
          {tab === 'Privacy' && <PrivacyPanel />}
        </section>
      </main>
    </div>
  )
}

function Card({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-asphalt-100 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-lg bg-asphalt-50 text-asphalt-700" aria-hidden>
          <Icon className="size-5" />
        </span>
        <h3 className="font-semibold text-asphalt-900">{title}</h3>
      </div>
      <div className="mt-3 space-y-2 text-sm leading-relaxed text-asphalt-600">{children}</div>
    </div>
  )
}

function TermsPanel() {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border-l-4 border-lane-500 bg-white p-5 shadow-sm">
        <h3 className="font-semibold text-asphalt-900">Disclaimer</h3>
        <ul className="mt-3 space-y-3 text-sm leading-relaxed text-asphalt-700">
          {AGREEMENT_PARAGRAPHS.map((text) => (
            <li key={text} className="flex gap-3">
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-lane-600" aria-hidden />
              <span>{text}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Acceptable use" icon={UserCheck}>
          <p>Use the application only for your organization's road work.</p>
          <p>Upload only photos you are allowed to share, avoid photographing people where possible, and keep your password private.</p>
        </Card>
        <Card title="AI results are estimates" icon={ScanSearch}>
          <p>Every AI suggestion is checked by a person before it counts. Always confirm on site before acting.</p>
          <p>Exported reports state which AI model and settings were used.</p>
        </Card>
      </div>
    </div>
  )
}

function AccessibilityPanel() {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-asphalt-100">
        <p className="text-asphalt-800">We aim to meet the Web Content Accessibility Guidelines (WCAG) 2.1 level AA.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Checked automatically" icon={ListChecks}>
          <p>Every main screen is checked automatically for labels, roles, names and headings.</p>
        </Card>
        <Card title="Works with the keyboard" icon={Keyboard}>
          <p>Everything can be done with the keyboard: Tab to move, Enter or Space to choose, Esc to close a window.</p>
        </Card>
        <Card title="Never colour alone" icon={Palette}>
          <p>Levels and states are always written in words, never shown by colour alone.</p>
        </Card>
        <Card title="Tables and easy navigation" icon={Table2}>
          <p>Every chart can also be read as a table, and every page has Back and a breadcrumb.</p>
        </Card>
      </div>
      <div className="rounded-2xl bg-asphalt-50 p-5 text-sm leading-relaxed text-asphalt-700">
        <p>Known limits: map areas are easiest to use with a mouse or touch; the same information is always also in a list.</p>
        <p className="mt-2">If something is hard to use, tell your organization's administrator so it can be fixed.</p>
      </div>
    </div>
  )
}

function PrivacyPanel() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="What we store" icon={Database}>
        <p>What the application needs: your name, email and role; the photos you upload with their date and location; AI results, review decisions, inspections and reports; and a history of changes.</p>
      </Card>
      <Card title="Where it is kept" icon={HardDrive}>
        <p>Photos are kept in the storage chosen by your organization (ours, or your own space), encrypted (AES-256-GCM). Passwords are stored only as secure hashes.</p>
      </Card>
      <Card title="Who can see it" icon={Users}>
        <p>Only people with access to the project, after a permission check, and people a manager sends a share link to (photo only, no location, until the link ends).</p>
      </Card>
      <Card title="How long it is kept" icon={Clock}>
        <p>Your organization decides how long photos and results are kept. Nothing is deleted automatically until it confirms its rules.</p>
        <p>Road-risk information comes from public data and contains no personal information.</p>
      </Card>
    </div>
  )
}

/** FAQ tab: the steps as numbered cards, then searchable questions that open one by one. */
function FaqPanel() {
  const [query, setQuery] = useState('')
  const words = query.trim().toLowerCase()
  const match = ([q, a]: [string, string]) => !words || `${q} ${a}`.toLowerCase().includes(words)
  const storage = STORAGE.filter(match)
  const questions = FAQ.filter(match)
  return (
    <div className="space-y-8">
      {!words && (
        <section aria-labelledby="faq-steps" className="space-y-3">
          <h2 id="faq-steps" className="text-lg font-semibold">
            How to use the app, step by step
          </h2>
          <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {STEPS.map(([step, text], index) => (
              <li key={step} className="flex gap-3 rounded-xl border border-asphalt-100 bg-white p-4 shadow-sm">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-lane-400 text-sm font-bold text-asphalt-900" aria-hidden>
                  {index + 1}
                </span>
                <div>
                  <h3 className="font-semibold text-asphalt-900">{step}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-asphalt-600">{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
      <label className="relative block">
        <span className="sr-only">Search the questions</span>
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-asphalt-400" aria-hidden />
        <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search the questions, e.g. storage, cameras, speed limit" className="control h-11 w-full pl-9" />
      </label>
      {storage.length > 0 && <QuestionGroup title="Where your data is stored" items={storage} open={Boolean(words)} />}
      {questions.length > 0 && <QuestionGroup title="Questions" items={questions} open={Boolean(words)} />}
      {words && storage.length === 0 && questions.length === 0 && <p className="text-asphalt-600">No question matches "{query}".</p>}
    </div>
  )
}

function QuestionGroup({ title, items, open }: { title: string; items: [string, string][]; open: boolean }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="divide-y divide-asphalt-100 overflow-hidden rounded-xl border border-asphalt-100 bg-white">
        {items.map(([question, answer]) => (
          <Question key={`${question}-${open}`} question={question} answer={answer} startOpen={open} />
        ))}
      </div>
    </section>
  )
}

function Question({ question, answer, startOpen }: { question: string; answer: string; startOpen: boolean }) {
  const [open, setOpen] = useState(startOpen)
  const id = useId()
  return (
    <div>
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left font-medium text-asphalt-900 hover:bg-asphalt-50"
        >
          {question}
          <ChevronDown className={cn('size-4 shrink-0 text-asphalt-500 transition-transform', open && 'rotate-180')} aria-hidden />
        </button>
      </h3>
      <div id={id} hidden={!open} className="px-4 pb-4 text-sm leading-relaxed text-asphalt-600">
        {answer}
      </div>
    </div>
  )
}
