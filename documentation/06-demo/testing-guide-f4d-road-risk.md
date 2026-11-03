# Testing Guide: Road Risk (F4b to F4d)

Written 2026-11-02 for the owner. Follow the parts in order: **A** start everything, **B** switch to local
settings, **C** test each new thing on the laptop, **D** switch back to live-demo settings, **E** Cloudflare
tunnel, **F** push to GitHub (this updates the live demo). Tick each box as you go. If anything looks wrong,
take a screenshot and send it to Claude with the step number.

All commands are typed in **PowerShell** opened in the project folder
(`C:\Users\Developer2025\Desktop\GeoInfraLens AI`: in File Explorer, open the folder, click the address bar,
type `powershell`, press Enter).

---

## A + B. Start everything for testing on the laptop

1. [ ] Open **Docker Desktop** and wait until it says **Engine running**.
2. [ ] Double-click **`scripts\start-local.bat`**. It saves a copy of `.env` once (`.env.backup-live-demo`),
   switches `.env` to local settings, starts Docker
   (`db`, `queue`, `api`, `worker`, `beat`), brings the database up to date, and starts the screens.
3. [ ] Keep that window open. Open **http://localhost:5173** and sign in as the organization admin.

## C. Test each new thing

### C1. A Chicago project and switching road risk on
1. [ ] **New project** → in "Find a street, neighborhood or city" type `Wicker Park, Chicago` → Search →
   keep the area small (about 1-2 km²) → choose a finding type → Create.
2. [ ] Open the project. There is **no "Road risk" tab yet** (it appears only when road risk is on).
3. [ ] **Settings → Road risk**. Check: status **Off**, the text about 500 km², "Who can see road risk" shows
   Project managers (always, greyed), Technical reviewers ☑, Viewers ☑, Field collectors ☐.
4. [ ] Click **Switch on**. Status becomes **Setting up…**. Reload the page every minute or two.
   For Chicago this takes a few minutes. Expected: **On and ready**, and a line like "1,234 road sections;
   tested Chicago levels."
   - If it says **Set-up failed**, copy the reason shown and send it to Claude. **Try again** retries.
5. [ ] Click **Update now**. The first time this fetches all new Chicago 311 reports since late September and
   the weather, then works out the levels: allow **10-30 minutes**. You can keep testing other parts meanwhile.

### C2. The Road risk tab (after the update has finished)
1. [ ] A **Road risk** tab now appears between Priority and Reports.
2. [ ] At the top: yellow **TRIAL FORECAST** label and "Risk estimate, not a confirmed defect.", the
   sentence about high = riskiest 1% of Chicago roads this week, and "Levels of Monday …".
3. [ ] Counts: **High / Medium / Low** with numbers. Most roads in a small area are usually **Low** (high is only
   the top 1% of all Chicago roads), so 0 high is normal for a quiet area.
4. [ ] **Weather**: 7 day boxes (max/min °C), freeze-thaw days marked, rain/snow when forecast, and the source
   "National Weather Service … issued …". A "–" means no value for that day.
5. [ ] **Map**: the survey area and its roads; high = thick red line, medium = dashed orange, low = thin grey;
   the key below the map explains them in words. Click a road → its page opens.
6. [ ] **Inspect first** list: numbered roads, each with a level word and icon, road type and length, up to
   3 reasons in plain words (e.g. "Pothole reports here, last 12 months: 4"), and a note when some inputs are
   not known. **No percentage anywhere in the list.**
7. [ ] The **Show** filter (High / Medium / Low / All roads) changes the list.
8. [ ] **Download CSV** and **Download GeoJSON**: files download; the CSV starts with lines beginning `#`
   (TRIAL FORECAST, the notice, the dates). Open the CSV in Excel.

### C3. One road's page
1. [ ] Click **Open** on a road. Check: name and level, "number N on this project's Inspect first list",
   the TRIAL label, Main reasons, **Risk factors** and **Background facts** with a level word each,
   "Week by week" (one week for now), "Inspections of this road: None yet", and a small map of the road.

### C4. Plan and record a road inspection
1. [ ] On the road page (or in the list) click **Plan inspection** → choose a person and a date →
   **Plan inspection**. A message "Inspection planned." appears.
2. [ ] The road page now shows the inspection, and **Plan inspection** is gone (one open inspection per road).
3. [ ] Click **View inspection** → **Mark inspected** → then **Mark resolved** without a note: it must ask for
   a note or a photo. Type a note → **Mark resolved**.
4. [ ] **Reopen** → give a reason, person and date → the old one stays as "Reopened" and a new one is planned.
5. [ ] **Settings → History**: you see "inspection.planned", "inspection.resolved", "forecast.enabled" and
   similar entries.

### C5. Who can see road risk (needs two more accounts)
Use **Team** to invite people if you have no test accounts: one **viewer** and one **field collector**, both
added to this project in **Settings → Team**. Use a private/incognito window for the second person.
1. [ ] Sign in as the **viewer**: the **Road risk** tab is there; there is **no "Road risk" in Settings**;
   there is **no Plan inspection** button.
2. [ ] Sign in as the **field collector**: **no Road risk tab** (hidden by default).
3. [ ] As the manager: **Settings → Road risk** → tick **Field collectors** → **Save who can see it**.
   The field collector (reload) now sees the tab. Untick **Viewers** and save: the viewer (reload) no longer
   sees it.
4. [ ] As the manager, plan a road inspection with the **field collector** as the person. The field collector
   sees it in **My inspections** with a **Road** tag, can open it with **Record result**, and can mark it
   inspected/resolved.
5. [ ] Put the ticks back to the default (Technical reviewers and Viewers) when done.

### C6. Overview card and the automatic jobs
1. [ ] **Overview** tab: a **Road risk** card with the TRIAL label, High and Medium counts, and **See road risk**.
2. [ ] Automatic jobs (nothing to click): the scheduler checks every hour. Tomorrow after 06:00 Chicago time
   the weather and outlook update by themselves; next Monday after 07:00 the levels update. Check
   **Settings → Road risk → Last updates** on those days.

### C7. Switch off
1. [ ] **Settings → Road risk → Switch off**: the Road risk tab disappears; results are kept. Switch on again
   to bring it back (Chicago set-up runs again, a few minutes).

### C8. A project outside Chicago (optional)
1. [ ] New project in `Naperville, Illinois` (small area) → Settings → Road risk → Switch on.
   Set-up downloads roads, elevation, flood zones and weather for the area: allow **10-60 minutes**.
2. [ ] When ready: the top of the tab says **"Risk factors only: there is no pothole history here…"**; roads
   are ordered by their risk factors; rows show "Main risk factors" (e.g. "Freeze-thaw days, last 14 days
   (high)") instead of reasons; no weekly history. See the note at the end about what this means.
3. [ ] A project larger than 500 km² shows **Area too large** and is not set up.

### C9. Alerts (F4e)
1. [ ] As a project manager: the left menu has **Alerts** with a bell (and a yellow number when there are
   unread alerts). Viewers and field collectors do not see it.
2. [ ] **Alerts** page: alerts newest first; unread ones have a yellow edge and bold title; **Mark all as read**
   clears the number.
3. [ ] Open an alert: TRIAL label and notice, **When**, **Source** (National Weather Service), **Suggested
   action**, the roads with level and reasons, **Open** and **Plan inspection**. Opening it marks it read.
4. [ ] **Home → What to do next** shows unread alerts first with **See the roads**.
5. [ ] **Road risk** tab shows an **Open alerts** box at the top (managers only).
6. [ ] Real alerts appear only when a rule applies: a road turns high (from the second Monday), 3+ freeze-thaw
   days or a 25 mm rain day in the 7-day forecast, or a data problem (a failed job, or the laptop off for more
   than 2 days). An empty Alerts page today is normal.

## Sign-off (F4f)

| Part | Result (OK / problem) | Note |
|---|---|---|
| A-B start locally | | |
| C1 switch on (Chicago) | | |
| C2 Road risk tab | | |
| C3 road page | | |
| C4 road inspection | | |
| C5 who can see road risk | | |
| C6 overview card, automatic jobs | | |
| C7 switch off | | |
| C8 outside Chicago (optional) | | |
| C9 alerts | | |
| D-F live demo and push | | |

Signed off by: ____________  Date: ____________

## D + E. Live demo and the Cloudflare tunnel

1. [ ] Close the `start-local` window (this stops the local screens; Docker keeps running).
2. [ ] Double-click **`scripts\start-live.bat`**. It switches `.env` back to the live-demo settings, restarts
   the app, starts the Cloudflare tunnel in the background, writes the new tunnel address into
   `frontend\vercel.json`, checks `/api/health`, and prints the git commands.
3. [ ] The tunnel keeps running in the background while the computer is on. To stop it:
   `Stop-Process -Name cloudflared` in PowerShell.

## F. Push to GitHub (updates the live demo)

In the project folder:
1. [ ] `git status`. Check that the list does **not** contain `.env`, `_backups`, `.dump` files or `data/`
   folders (they are ignored on purpose). If you see any of them, stop and ask Claude.
2. [ ] `git add -A`
3. [ ] `git commit -m "Road-risk forecasting: background jobs, API, permissions and Road risk screens (F4b-F4d)"`
4. [ ] `git push origin development`
5. [ ] Wait 1-3 minutes, then open **https://geo-ai-liart.vercel.app**, sign in, and repeat a short check:
   C2 (Road risk tab) and C3 (one road). If the site cannot sign in, the tunnel address in `vercel.json` is
   probably wrong or the tunnel window was closed: repeat E and push again.

---

## Note: does it work for an area other than Chicago?

**Yes, anywhere in the United States, but only as "risk factors", not as a tested forecast.**

| | Chicago (Level 2) | Other US areas (Level 1) |
|---|---|---|
| What you get | Weekly **tested** levels: high = riskiest 1% of Chicago roads, medium = next 9% | **Risk factors** per road: freeze-thaw days, frost days, snow, bus routes (risk group), plus background facts: heavy rain, low spots, slope, flood zone, traffic (Illinois only) |
| How roads are ordered | By the model's ranking | By how many risk factors are high, then medium |
| Reasons | Top 3 reasons from the model | The risk factors that are high or medium |
| Tested? | Yes: on 15 never-used months, about 32% better than the simple rule | **No**: there is no pothole history to test against |
| Weather outlook, map, downloads, road inspections | Yes | Yes |
| Week-by-week history | Yes | No |

**In what sense it "works" outside Chicago:** it tells you which roads have the **conditions** linked to
potholes (many freeze-thaw cycles, frost, snow, buses, low spots that hold water, flood zones). The cut-offs
for high/medium come from Chicago's data, so "high freeze-thaw" means "high compared with Chicago winters".
It does **not** say how likely a pothole is, and it has not been checked against real potholes in that area.

**Limits:** United States only (the weather and map sources are US services); project areas up to 500 km²;
traffic counts only in Illinois (elsewhere traffic shows as "not known"); the first set-up downloads data and
can take up to an hour. To get tested levels for another city, that city's pothole/311 history is needed
(see partner inputs PI-20, PI-21).
