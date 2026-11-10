import { useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/auth-context'
import { AGREEMENT_PARAGRAPHS } from '@/auth/agreement-text'
import { BrandName } from '@/components/brand-mark'
import { cn } from '@/lib/utils'

/** About page (team lead plan, Phase 1, tl-phase1-design.md §3): readable without signing in. */

/** Step by step: how to use the app, in the order the work is done. */
const STEPS: [string, string][] = [
  ['Sign in and agree', 'Sign in with the account your organization gave you. The first time (and when the terms change) you are asked to read the disclaimer and click "I agree". Tick "Remember my choice" so you are not asked again on this account.'],
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

export function AboutPage() {
  const auth = useAuth()
  const [tab, setTab] = useState<Tab>('FAQ')
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <BrandName />
        <Link to={auth.me ? '/' : '/sign-in'} className="btn btn-secondary">
          {auth.me ? 'Back to the app' : 'Sign in'}
        </Link>
      </div>
      <h1 className="text-[1.75rem] font-semibold tracking-tight">About GeoInfraLens AI</h1>
      <div role="tablist" aria-label="About" className="flex flex-wrap gap-2">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            id={`tab-${name}`}
            aria-selected={tab === name}
            aria-controls="about-panel"
            onClick={() => setTab(name)}
            className={cn('rounded-full px-4 py-1.5 text-sm font-medium', tab === name ? 'bg-asphalt-900 text-white' : 'bg-asphalt-100 text-asphalt-800 hover:bg-asphalt-200')}
          >
            {name}
          </button>
        ))}
      </div>
      <section id="about-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="panel space-y-4 p-5 text-asphalt-800">
        {tab === 'FAQ' && (
          <>
            <h2 className="text-lg font-semibold">How to use the app, step by step</h2>
            <ol className="list-decimal space-y-3 pl-5">
              {STEPS.map(([step, text]) => (
                <li key={step}>
                  <h3 className="font-semibold">{step}</h3>
                  <p className="text-asphalt-700">{text}</p>
                </li>
              ))}
            </ol>
            <h2 className="pt-2 text-lg font-semibold">Where your data is stored</h2>
            {STORAGE.map(([question, answer]) => (
              <div key={question}>
                <h3 className="font-semibold">{question}</h3>
                <p className="text-asphalt-700">{answer}</p>
              </div>
            ))}
            <h2 className="pt-2 text-lg font-semibold">Questions</h2>
            {FAQ.map(([question, answer]) => (
              <div key={question}>
                <h3 className="font-semibold">{question}</h3>
                <p className="text-asphalt-700">{answer}</p>
              </div>
            ))}
          </>
        )}
        {tab === 'Terms of use' && (
          <>
            {AGREEMENT_PARAGRAPHS.map((text) => (
              <p key={text}>{text}</p>
            ))}
            <h2 className="font-semibold">Acceptable use</h2>
            <p>Use the application only for your organization's road work. Upload only photos you are allowed to share, avoid photographing people where possible, and keep your password private.</p>
            <p className="text-sm text-asphalt-600">AI results are estimates. Exported reports state which AI model and settings were used.</p>
          </>
        )}
        {tab === 'Accessibility' && (
          <>
            <p>We aim to meet the Web Content Accessibility Guidelines (WCAG) 2.1 level AA.</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Every main screen is checked automatically for labels, roles, names and headings.</li>
              <li>Everything can be done with the keyboard: Tab to move, Enter or Space to choose, Esc to close a window.</li>
              <li>Levels and states are always written in words, never shown by colour alone.</li>
              <li>Every chart can also be read as a table, and every page has Back and a breadcrumb.</li>
            </ul>
            <p>Known limits: map areas are easiest to use with a mouse or touch; the same information is always also in a list.</p>
            <p>If something is hard to use, tell your organization's administrator so it can be fixed.</p>
          </>
        )}
        {tab === 'Privacy' && (
          <>
            <p>We store what the application needs: your name, email and role; the photos you upload with their date and location; AI results, review decisions, inspections and reports; and a history of changes.</p>
            <p>Photos are kept in the storage chosen by your organization and are shown only to people with access to the project, after a permission check. Passwords are stored only as secure hashes.</p>
            <p>Your organization decides how long photos and results are kept. Road-risk information comes from public data and contains no personal information.</p>
          </>
        )}
      </section>
    </main>
  )
}
