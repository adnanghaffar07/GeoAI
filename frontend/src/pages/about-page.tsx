import {
  Accessibility,
  ArrowUpRight,
  Briefcase,
  Building2,
  Camera,
  CircleCheck,
  CircleHelp,
  Clock,
  Database,
  FileText,
  Globe,
  HardDrive,
  Headset,
  Keyboard,
  ListChecks,
  Mail,
  MapPin,
  MessageCircle,
  Palette,
  Phone,
  Play,
  ScanSearch,
  Search,
  ShieldCheck,
  Table2,
  UserCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, Navigate } from 'react-router'

import { useAuth } from '@/auth/auth-context'
import { AGREEMENT_PARAGRAPHS } from '@/auth/agreement-text'
import { BrandName } from '@/components/brand-mark'
import { DropdownCard as Dropdown } from '@/components/ui/dropdown-card'
import { cn } from '@/lib/utils'

/** About page (team lead plan, Phase 1, tl-phase1-design.md §3): readable without signing in. */

/** Step by step: how to use the app, in the order the work is done. Lines starting "- " are shown as a list. */
const STEPS: [string, string[]][] = [
  ['Sign in and agree', [
    'Open GeoInfraLens AI and sign in with the email and password your organization gave you. If you forgot your password, ask your administrator for a password reset link.',
    'Each time you sign in, a short disclaimer appears. Read it and click "I agree" to open the app, or "Sign out" if you do not agree. Nothing in the app can be opened before you agree.',
  ]],
  ['Open or create a project', [
    'A project is one survey area, for example a neighbourhood, a set of streets or a whole town. Open it from Projects in the menu.',
    'Managers create a new project with "New project":',
    '- Give it a name and choose which kinds of road problems it records.',
    '- Mark the area: search a road, address or area by name (or paste coordinates), draw it on the map, or upload a map file. A searched road becomes a strip of the width you choose; an address becomes a circle of about 150 m.',
    '- Save. The area can be changed later in the project\'s Settings.',
  ]],
  ['Add your team', [
    'Managers open the project\'s Settings, then Team, and add people from the organization with one role each:',
    '- Project manager: runs the project, plans inspections, shares photos, switches road risk on.',
    '- Field collector: takes and uploads photos and records inspection results.',
    '- Technical reviewer: checks every AI suggestion and decides whether it is a real problem.',
    '- Viewer: looks at verified results, maps and reports, and changes nothing.',
  ]],
  ['Upload road photos', [
    'In the project, open Photos, then Upload, and choose one or many photos. Tick the box confirming you may share them, then upload.',
    '- Use clear daylight photos, with the phone\'s location (GPS) switched on, so each photo lands on the map by itself.',
    '- A photo without a location can still be checked; place it on the map by hand from the photo\'s page. Problems already found on it then appear on the map too.',
    '- Sending the same file twice is safe: it is kept once.',
  ]],
  ['Send photos to the AI check', [
    'On the Photos tab, the app shows how many new photos are waiting. Send them to the AI check with one button and wait until it says finished (usually seconds per photo).',
    'The AI marks possible potholes, cracks and worn pavement with a box on the photo. These are suggestions only: nothing counts until a person has checked it.',
  ]],
  ['Review every suggestion', [
    'Reviewers open Findings (or Review) and go through the suggestions one by one. For each one:',
    '- Verify it (choose the type and how serious it is), reject it, or ask for a field check.',
    '- Correct the type, severity or location if the AI got it wrong; the original AI answer is always kept.',
    'Only verified problems count in the priority list, the reports and the home page. Every decision is saved in the finding\'s history.',
  ]],
  ['See the photos and problems on the map', [
    '- Findings: every problem on a map and in a list; click one to see its photo and details.',
    '- Photo map: every analysed photo as a pin, coloured by its most serious problem; click a pin to see the photo with all its boxes.',
    '- Roads: only the roads, coloured by risk, speed limit, road type, weather or traffic; choose an area to list just those roads.',
    '- Cameras: Illinois DOT traffic cameras in the project area; "Take snapshot" saves a picture as a project photo.',
    'Managers can make a share link to one photo for someone without an account. It shows only the photo (no location), ends after 1 to 30 days and can be cancelled at any time.',
  ]],
  ['Decide what to fix first', [
    'The Priority tab ranks verified problems by how serious they are, the type of road and nearby places such as schools. Each score shows how it was worked out.',
    'Plan an inspection for a colleague with a due date. They see it under My inspections, visit the place and record what they found (with a note or a photo).',
  ]],
  ['Make a report', [
    'Open Reports, then "Make a new report", choose the filters and a format:',
    '- CSV for spreadsheets (Excel, Google Sheets).',
    '- GeoJSON for map software (QGIS, ArcGIS).',
    '- PDF to print or send.',
    'Reports contain verified problems by default and state which AI model and settings were used.',
  ]],
  ['Use road risk (optional)', [
    'A manager switches it on in the project\'s Settings, then Road risk. Set-up takes a few minutes to an hour, depending on the area.',
    'The Road risk tab then lists the roads most likely to need attention in the next 30 days (high, medium, low), with plain reasons such as recent pothole reports, freeze-thaw weather or road condition, plus the weather outlook and alerts.',
    '- Inside Chicago and Naperville the levels are tested against each city\'s own pothole reports.',
    '- Elsewhere the app shows risk factors (weather, road type, condition) for every road.',
    'Plan an inspection from any road, and (if switched on) ask the assistant questions such as "Which roads should we inspect first?".',
  ]],
]

/** Where each kind of data is kept. */
const STORAGE: [string, string[]][] = [
  ['Photos (the original file and a smaller copy for screens)', [
    'Every photo you upload is kept twice: the original file, exactly as taken, and a smaller copy for fast screens and share links.',
    'They are kept in your organization\'s file storage. By default this is the private storage of the server that runs GeoInfraLens AI.',
    'An organization administrator can switch to your organization\'s own storage instead in Settings, then Data storage: a cloud account in your name (for example Backblaze B2, Amazon S3, Cloudflare R2, Wasabi or Google Cloud), your own server, or a computer in your office running MinIO. New files go there from then on; files saved earlier stay where they were and still open.',
  ]],
  ['How files are protected', [
    '- Every file is encrypted (AES-256-GCM) before it is saved, wherever it is saved, so the storage company cannot read it.',
    '- The key to your own storage is also kept encrypted and is never shown again after saving.',
    '- A photo is only shown after a sign-in and a check that the person may see that project.',
    '- Passwords are never stored, only a secure fingerprint of them.',
  ]],
  ['Findings, reviews, inspections, accounts and history', [
    'Text and numbers (the problems found, review decisions, inspections, reports, accounts and settings) are kept in the app\'s database (PostgreSQL) on the server that runs the app.',
    'Every change is kept in a history that cannot be edited. Managers see it in the project\'s Settings, then History: who did what, and when.',
  ]],
  ['Photo locations', [
    'Each photo keeps the location saved by the phone (GPS), or the point placed by hand. It is where the camera was, so it is approximate (usually within 5 to 20 metres).',
    'A reviewer can correct a problem\'s location; the original is always kept. Share links never include any location.',
  ]],
  ['Road-risk data', [
    'Road risk uses public data only: city pothole reports where they are published, daily weather (NOAA) and forecasts (National Weather Service), roads and speed limits (OpenStreetMap), road condition and traffic (Federal Highway Administration), elevation (USGS) and flood zones (FEMA).',
    'It is kept in a separate database on the same server. None of your photos or findings are added to it.',
  ]],
  ['Where can I check this for my organization?', [
    'Open Settings, then Data storage: it shows where files are kept, when the storage was last checked and how files are protected. Administrators can change it there and follow a step-by-step guide.',
    'Everyone can also see "Where your data is stored" on My account.',
  ]],
  ['Withdrawing a photo', [
    'Managers can withdraw any photo; field collectors can withdraw their own photos before the AI check.',
    'A withdrawn photo is hidden from the photo list and the photo map, and any share link to it stops working. It is not erased: it stays in the history.',
  ]],
]

const FAQ: [string, string[]][] = [
  ['What does GeoInfraLens AI do?', [
    'It helps a city find and fix road damage faster:',
    '- Field staff upload road photos (or take snapshots from traffic cameras).',
    '- An AI marks possible potholes, cracks and worn pavement on each photo.',
    '- A reviewer confirms each one, so only checked problems count.',
    '- Results show on a map, in a priority list and in reports you can download.',
    'A separate road-risk view shows which roads are likely to need attention in the next 30 days, using weather, road condition and past pothole reports.',
  ]],
  ['Is the AI always right?', [
    'No. AI results can be wrong (a shadow marked as a pothole) or incomplete (a crack it did not see), especially in poor light or on roads unlike the ones it learned from.',
    'Every AI suggestion is checked by a person before it counts. Always confirm on site before sending a crew or making a decision.',
    'Photos taken in your own area help the AI improve; ask your administrator if you can share some.',
  ]],
  ['What do the colours and levels mean?', [
    'Levels are always written in words as well as colours, so nobody depends on colour alone.',
    '- Findings: green means verified by a reviewer; amber means an AI suggestion waiting for review.',
    '- Road risk: "high" means the road is among the top 1% most likely to get new pothole reports in the next 30 days compared with the others in the area; "medium" the next 9%; "low" the rest.',
    'A high level is a reason to inspect first. It is not a confirmed defect.',
  ]],
  ['Who can see my photos?', [
    '- People in your organization who have access to the project, according to their role. Viewers see verified problems only, never unchecked AI suggestions.',
    '- People a manager sends a share link to: only that one photo, without its location, until the link ends or is cancelled.',
    'Nobody outside your organization can browse your projects, and every photo is shown only after a permission check.',
  ]],
  ['Why is a photo not on the map?', [
    'The photo had no location, usually because location (GPS) was switched off for the camera, or the photo was sent through a messaging app that removes it.',
    'You can still review it. To put it on the map, open the photo and place its location by hand; its problems then appear on the map too. Next time, switch location on before taking photos.',
  ]],
  ['How is the priority worked out?', [
    'Each verified problem gets a score from:',
    '- How serious it is, as chosen by the reviewer.',
    '- The type of road (a main road counts more than a quiet street).',
    '- Nearby places such as schools and hospitals.',
    'Your organization sets how much each part counts, and the breakdown is shown next to every score, so the ranking can always be explained.',
  ]],
  ['Where does road-risk information come from?', [
    'Only from free, public data:',
    '- City pothole reports where published (for example Chicago and Naperville).',
    '- Daily weather from NOAA and the outlook from the National Weather Service: freeze-thaw days, frost, rain and snow.',
    '- Roads, speed limits and lanes from OpenStreetMap.',
    '- Measured road condition and traffic from the Federal Highway Administration.',
    '- Elevation (USGS) and flood zones (FEMA).',
    'Each road page names its sources and how recent they are.',
  ]],
  ['Where do the traffic camera pictures come from?', [
    'From the Illinois Department of Transportation\'s Gateway traffic cameras, shared under the Creative Commons Attribution-ShareAlike 2.0 licence. The Cameras tab shows the cameras inside your project area with their latest picture, refreshed by IDOT every few minutes.',
    'Viewing them stores nothing. "Take snapshot" saves that one picture (about 70 KB) as a project photo in your organization\'s storage, credited to IDOT, so it can go to the AI check like any upload.',
  ]],
  ['Why does a road say "Not on the map" for its speed limit?', [
    'Road details (speed limit, lanes, surface, one-way) come from OpenStreetMap, which volunteers keep up to date. Not every road has every detail there yet.',
    'The app never guesses a missing value. Always check the signs on site.',
  ]],
  ['What road problems can the AI find, and how serious are they?', [
    '- Potholes',
    '- Surface cracking (single cracks and networks of cracks)',
    '- Pavement deterioration (worn, crumbling or patched surface)',
    'Field staff can also add observations by hand, for example on a sidewalk. When a reviewer verifies a problem, they give it a severity level (for example low, medium or high) from your organization\'s severity scale.',
  ]],
  ['How long is my data kept?', [
    'Nothing is deleted automatically. Photos (including withdrawn ones), findings (including rejected ones), reports and the history are all kept until your organization confirms how long it must keep them.',
    'Those rules will then be set together with you, and every change is recorded in the history. A project deleted by an administrator disappears from the app but is not erased.',
  ]],
  ['How do I report a mistake?', [
    'If a finding is wrong, open it and correct the type, severity or location, or reject it. If you are not allowed to, tell a reviewer or your organization\'s administrator.',
    'For anything else, use the Contact us tab. Every change is kept in the history, so nothing is lost.',
  ]],
]

const TABS = ['FAQ', 'Terms of use', 'Accessibility', 'Privacy', 'Contact us'] as const
type Tab = (typeof TABS)[number]

const TAB_INFO: Record<Tab, { icon: LucideIcon; text: string }> = {
  FAQ: { icon: CircleHelp, text: 'How to use the app, where your data is kept, and common questions' },
  'Terms of use': { icon: FileText, text: 'The rules for using GeoInfraLens AI' },
  Accessibility: { icon: Accessibility, text: 'How the app works for everyone' },
  Privacy: { icon: ShieldCheck, text: 'What we store, where, and who can see it' },
  'Contact us': { icon: Headset, text: 'Call, write, visit or follow CodeAutomation.ai, the team behind GeoInfraLens AI' },
}

/** `embedded`: shown inside the signed-in app (menu "About", /help), so the sidebar stays; the public
 * page (/about) is for people who are not signed in. */
export function AboutPage({ embedded = false }: { embedded?: boolean }) {
  const auth = useAuth()
  const [tab, setTab] = useState<Tab>('FAQ')
  const info = TAB_INFO[tab]
  if (!embedded && auth.me && !auth.me.agreement_required) return <Navigate to="/help" replace />
  const Main = embedded ? 'div' : 'main' // inside the app, the app's own <main> already holds the page
  return (
    <div className={embedded ? 'w-full space-y-6' : 'min-h-dvh bg-canvas'}>
      {!embedded && (
      <header className="border-b border-asphalt-100 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <BrandName />
          <Link to={auth.me ? '/' : '/sign-in'} className="btn btn-secondary">
            {auth.me ? 'Back to the app' : 'Sign in'}
          </Link>
        </div>
      </header>
      )}
      <div className={cn('bg-asphalt-900 text-white', embedded && 'rounded-2xl shadow-sm')}>
        <div className={cn('mx-auto px-4 sm:px-6', embedded ? 'py-8' : 'max-w-6xl py-10')}>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">About GeoInfraLens AI</h1>
          <p className="mt-2 max-w-2xl text-asphalt-200">Road damage from photos, checked by people, shown on a map: here is how it works, the rules, and how we look after your data.</p>
        </div>
      </div>
      <Main className={cn('grid gap-6 lg:grid-cols-[15rem_1fr]', !embedded && 'mx-auto max-w-6xl px-4 py-8 sm:px-6')}>
        <div role="tablist" aria-label="About" aria-orientation="vertical" className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
          {TABS.map((name) => {
            const Icon = TAB_INFO[name].icon
            return (
              <button
                key={name}
                type="button"
                role="tab"
                id={`tab-${name.replace(/\s+/g, '-')}`}
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
        <section id="about-panel" role="tabpanel" aria-labelledby={`tab-${tab.replace(/\s+/g, '-')}`} className="min-w-0 space-y-6">
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
          {tab === 'Contact us' && <ContactPanel />}
        </section>
      </Main>
    </div>
  )
}

function DropdownList({ children }: { children: ReactNode }) {
  return <div className="space-y-3">{children}</div>
}

function SectionTitle({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <h2 id={id} className="flex items-center gap-2 text-lg font-semibold text-asphalt-900">
      <span className="h-5 w-1.5 rounded-full bg-lane-400" aria-hidden />
      {children}
    </h2>
  )
}

function TermsPanel() {
  return (
    <DropdownList>
      <Dropdown title="Disclaimer" icon={ShieldCheck} startOpen>
        <ul className="space-y-3">
          {AGREEMENT_PARAGRAPHS.map((text) => (
            <li key={text} className="flex gap-3">
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-lane-600" aria-hidden />
              <span>{text}</span>
            </li>
          ))}
        </ul>
      </Dropdown>
      <Dropdown title="Who may use the application" icon={Users}>
        <Answer
          lines={[
            'GeoInfraLens AI is for the staff and partners of organizations that have an account, invited by their organization\'s administrator. Each person signs in with their own account; accounts must not be shared.',
            'Your organization decides who may use it and with which role, and can remove access at any time.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Acceptable use" icon={UserCheck}>
        <Answer
          lines={[
            'Use the application only for your organization\'s road and infrastructure work. In particular:',
            '- Upload only photos you are allowed to share, taken where it is safe and legal to do so.',
            '- Avoid photographing people, faces and number plates where possible; retake the photo if they are clearly visible.',
            '- Keep your password private and sign out on shared computers.',
            '- Do not try to reach projects, photos or data you have not been given access to, or to disturb the service.',
            'Share links are for passing one photo to people outside the app; send them only to people who should see it.',
          ]}
        />
      </Dropdown>
      <Dropdown title="AI results and road-risk levels are estimates" icon={ScanSearch}>
        <Answer
          lines={[
            'The AI suggests possible road problems and the road-risk view estimates which roads may need attention soon. Both can be wrong or incomplete.',
            '- Every AI suggestion is checked by a reviewer before it counts.',
            '- Road-risk levels compare roads with each other; they are not a confirmed defect or a promise that damage will or will not appear.',
            '- Always confirm on site before acting. Decisions remain the responsibility of your organization.',
            'Exported reports state which AI model and settings were used, so results can be traced.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Your content and third-party data" icon={FileText}>
        <Answer
          lines={[
            'Photos and data your organization adds remain your organization\'s. They are used only to provide the service to you and, with your organization\'s agreement, to test and improve the AI for your area.',
            'Maps, weather, road and camera data come from public sources (for example OpenStreetMap, NOAA, the National Weather Service and the Illinois Department of Transportation) under their own terms; each is credited where it is shown.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Changes to these terms" icon={Clock}>
        <Answer
          lines={[
            'When these terms change, everyone sees the new version when they next sign in and is asked to agree again. Each agreement is recorded with its date.',
          ]}
        />
      </Dropdown>
    </DropdownList>
  )
}

function AccessibilityPanel() {
  return (
    <DropdownList>
      <Dropdown title="Our standard" icon={Accessibility} startOpen>
        <p>We aim to meet the Web Content Accessibility Guidelines (WCAG) 2.1 level AA.</p>
        <p className="mt-2">This means the application should be usable with a keyboard, with a screen reader, at large text sizes and on small screens, and that information is never given by colour alone.</p>
      </Dropdown>
      <Dropdown title="Checked automatically" icon={ListChecks}>
        <Answer
          lines={[
            'Every main screen is checked automatically, each time the application is changed, for:',
            '- Labels on every field and button, so screen readers can name them.',
            '- Correct roles and headings, so pages can be navigated by heading.',
            '- Text contrast, so text is readable.',
            'A change that breaks one of these checks is not released.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Works with the keyboard" icon={Keyboard}>
        <Answer
          lines={[
            'Everything can be done without a mouse:',
            '- Tab and Shift+Tab move between links, buttons and fields; the one in focus is always clearly outlined.',
            '- Enter or Space chooses; arrow keys move within lists and options.',
            '- Esc closes a window, and focus returns to where you were.',
            '- The review screen has keyboard shortcuts, shown on the screen, which are off while you type.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Never colour alone" icon={Palette}>
        <Answer
          lines={[
            'Levels and states are always written in words (for example "High", "Verified", "Not on the map"), with colour as an extra hint only.',
            'Map lines and pins have a key in words, and every map item can also be found in a list.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Tables and easy navigation" icon={Table2}>
        <Answer
          lines={[
            '- Every chart can also be read as a table.',
            '- Every page has a Back button and a breadcrumb showing where you are.',
            '- Pages work at 200% zoom and on phones.',
            '- Messages say in plain words what happened and what to do next.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Known limits and feedback" icon={CircleHelp}>
        <Answer
          lines={[
            'Drawing an area on the map is easiest with a mouse or touch; you can search an area by name or upload a map file instead. Everything shown on a map is also available in a list.',
            'Traffic camera pictures come from IDOT and have no text description beyond the camera\'s location.',
            'If something is hard to use, tell your organization\'s administrator or use the Contact us tab, so it can be fixed.',
          ]}
        />
      </Dropdown>
    </DropdownList>
  )
}

function PrivacyPanel() {
  return (
    <DropdownList>
      <Dropdown title="What we store" icon={Database} startOpen>
        <Answer
          lines={[
            'Only what the application needs to work:',
            '- About you: your name, email address, role and when you signed in.',
            '- Your work: the photos you upload with their date and location, AI results, review decisions, inspections and reports.',
            '- A history of changes: who did what, and when.',
            'We do not track you across other websites and do not sell or share personal data for advertising.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Where it is kept and how it is protected" icon={HardDrive}>
        <Answer
          lines={[
            'Photos are kept in the storage chosen by your organization: ours, or your organization\'s own space (a cloud account, its own server or an office computer). Every file is encrypted (AES-256-GCM) before it is saved.',
            'Text and numbers are kept in the application\'s database. Passwords are stored only as secure fingerprints, never as text. Connections use secure https.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Who can see it" icon={Users}>
        <Answer
          lines={[
            '- People in your organization with access to the project, according to their role, after a permission check on every request.',
            '- People a manager sends a share link to: one photo only, without its location, until the link ends or is cancelled.',
            '- The GeoInfraLens AI team, only to keep the service running or when your organization asks for help.',
          ]}
        />
      </Dropdown>
      <Dropdown title="How long it is kept" icon={Clock}>
        <Answer
          lines={[
            'Your organization decides how long photos and results are kept. Nothing is deleted automatically until it confirms its rules.',
            'If your organization stops using the service, it can ask for its data to be returned or erased.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Public data and road risk" icon={ShieldCheck}>
        <Answer
          lines={[
            'Road-risk information comes from public data (city pothole reports, weather, roads, road condition, elevation, flood zones). When pothole reports are loaded, only their date, type, status and location are kept: no names, addresses or comments.',
          ]}
        />
      </Dropdown>
      <Dropdown title="Your questions and requests" icon={Mail}>
        <Answer
          lines={[
            'To see, correct or remove personal data about you, ask your organization\'s administrator, or contact us (Contact us tab). Corrections are recorded in the history.',
          ]}
        />
      </Dropdown>
    </DropdownList>
  )
}

/** An answer: paragraphs, and lines starting "- " shown together as a list. */
function Answer({ lines }: { lines: string[] }) {
  const blocks: (string | string[])[] = []
  for (const line of lines) {
    if (line.startsWith('- ')) {
      const last = blocks[blocks.length - 1]
      if (Array.isArray(last)) last.push(line.slice(2))
      else blocks.push([line.slice(2)])
    } else blocks.push(line)
  }
  return (
    <div className="space-y-2">
      {blocks.map((block, index) =>
        Array.isArray(block) ? (
          <ul key={index} className="list-disc space-y-1 pl-5">
            {block.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p key={index}>{block}</p>
        ),
      )}
    </div>
  )
}

/** FAQ tab: search, then the steps and the questions, each opening on click. */
function FaqPanel() {
  const [query, setQuery] = useState('')
  const words = query.trim().toLowerCase()
  const match = ([q, a]: [string, string[]]) => !words || `${q} ${a.join(' ')}`.toLowerCase().includes(words)
  const storage = STORAGE.filter(match)
  const questions = FAQ.filter(match)
  const open = Boolean(words)
  return (
    <div className="space-y-8">
      <label className="relative block">
        <span className="sr-only">Search the questions</span>
        <Search className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-asphalt-400" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search the questions, e.g. storage, cameras, speed limit"
          className="h-12 w-full rounded-2xl border border-asphalt-100 bg-white pr-4 pl-12 text-sm shadow-sm outline-none focus:border-asphalt-300 focus:ring-2 focus:ring-lane-400"
        />
      </label>
      {!words && (
        <section aria-labelledby="faq-steps" className="space-y-3">
          <SectionTitle id="faq-steps">How to use the app, step by step</SectionTitle>
          <DropdownList>
            {STEPS.map(([step, text], index) => (
              <Dropdown key={step} title={step} number={index + 1}>
                <Answer lines={text} />
              </Dropdown>
            ))}
          </DropdownList>
        </section>
      )}
      {storage.length > 0 && (
        <section className="space-y-3">
          <SectionTitle>Where your data is stored</SectionTitle>
          <DropdownList>
            {storage.map(([question, answer]) => (
              <Dropdown key={`${question}-${open}`} title={question} icon={HardDrive} startOpen={open}>
                <Answer lines={answer} />
              </Dropdown>
            ))}
          </DropdownList>
        </section>
      )}
      {questions.length > 0 && (
        <section className="space-y-3">
          <SectionTitle>Questions</SectionTitle>
          <DropdownList>
            {questions.map(([question, answer]) => (
              <Dropdown key={`${question}-${open}`} title={question} icon={CircleHelp} startOpen={open}>
                <Answer lines={answer} />
              </Dropdown>
            ))}
          </DropdownList>
        </section>
      )}
      {words && storage.length === 0 && questions.length === 0 && (
        <p className="rounded-2xl bg-white p-6 text-center text-asphalt-600 shadow-sm">No question matches "{query}".</p>
      )}
    </div>
  )
}

/** Contact details of CodeAutomation.ai (owner, 2026-11-11). Legal team: added when the team lead sends it. */
const CONTACTS = [
  { icon: Phone, title: 'Call us', value: '+1 850 558 4691', href: 'tel:+18505584691' },
  { icon: Mail, title: 'Email us', value: 'info@codeautomation.ai', href: 'mailto:info@codeautomation.ai' },
  { icon: MapPin, title: 'Visit us', value: '50 S Main Street, Suite 200, Office 233, Naperville, IL 60540, USA', href: 'https://share.google/l9C5ReYnl5Jgl5PMG' },
] as const

const SOCIAL = [
  { name: 'LinkedIn', handle: 'codeautomationai', href: 'https://www.linkedin.com/company/codeautomationai/', icon: Briefcase, color: '#0A66C2' },
  { name: 'Facebook', handle: 'Codeautomationai', href: 'https://www.facebook.com/Codeautomationai/', icon: Users, color: '#1877F2' },
  { name: 'Instagram', handle: '@codeautomation.ai', href: 'https://www.instagram.com/codeautomation.ai/', icon: Camera, color: '#C13584' },
  { name: 'X (Twitter)', handle: '@codeautomation', href: 'https://twitter.com/codeautomation', icon: MessageCircle, color: '#111827' },
  { name: 'YouTube', handle: '@codeautomation-ai', href: 'https://www.youtube.com/@codeautomation-ai', icon: Play, color: '#D10000' },
  { name: 'Website', handle: 'codeautomation.ai', href: 'https://codeautomation.ai/', icon: Globe, color: '#1b2633' },
] as const

function ContactPanel() {
  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-3">
        {CONTACTS.map(({ icon: Icon, title, value, href }) => (
          <a
            key={title}
            href={href}
            {...(href.startsWith('http') ? { target: '_blank', rel: 'noreferrer' } : {})}
            className="group flex flex-col gap-3 rounded-2xl border border-asphalt-100 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <span className="flex size-11 items-center justify-center rounded-xl bg-lane-400 text-asphalt-900" aria-hidden>
              <Icon className="size-5" />
            </span>
            <span className="text-xs font-semibold tracking-wide text-asphalt-500 uppercase">{title}</span>
            <span className="font-medium text-asphalt-900 group-hover:underline">{value}</span>
          </a>
        ))}
      </div>

      <section aria-labelledby="follow-us" className="space-y-3">
        <h3 id="follow-us" className="text-lg font-semibold text-asphalt-900">
          Follow us
        </h3>
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {SOCIAL.map(({ name, handle, href, icon: Icon, color }) => (
            <li key={name}>
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                aria-label={`${name}: ${handle} (opens in a new tab)`}
                className="group flex items-center gap-4 rounded-2xl border border-asphalt-100 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
              >
                <span className="flex size-12 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: color }} aria-hidden>
                  <Icon className="size-6" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-asphalt-900">{name}</span>
                  <span className="block truncate text-sm text-asphalt-500">{handle}</span>
                </span>
                <ArrowUpRight className="size-5 shrink-0 text-asphalt-400 transition group-hover:text-asphalt-900" aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-wrap items-center gap-4 rounded-2xl bg-asphalt-900 p-6 text-white">
        <span className="flex size-12 items-center justify-center rounded-xl bg-white/10" aria-hidden>
          <Building2 className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">GeoInfraLens AI is built by CodeAutomation.ai</p>
          <p className="text-sm text-asphalt-200">Custom software and AI development, Naperville, Illinois.</p>
        </div>
        <a href="https://codeautomation.ai/" target="_blank" rel="noreferrer" className="btn bg-lane-400 text-asphalt-900 hover:bg-lane-300">
          Visit our website
        </a>
      </div>
    </div>
  )
}
