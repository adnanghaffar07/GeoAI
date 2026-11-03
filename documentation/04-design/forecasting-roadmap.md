# Road Damage Forecasting: Roadmap (V2 research track)

**Status:** **Approved (CR-005) 2026-10-28. F0 ground rules approved and frozen 2026-10-28. F1 complete for Chicago 2026-10-29** (owner's load 2026-10-28; counts in `07-ml/dataset-card-chicago-forecast.md`). Cook County pavement condition added for checking only (PI-23). **F1b (static layers) complete 2026-10-29. F2 complete 2026-10-29: locked test PARTIAL; B1 (logistic regression) chosen for the app** (`07-ml/model-card-forecast-chicago.md`). **Any-area pipeline complete 2026-10-30** (`04-design/forecasting-any-area-plan.md`: Chicago same results; Naperville Level 1 trial). **Next: F4.** Alert decisions taken 2026-10-28 (§7.6). Not part of version 1 (`03-requirements/requirements.md` §11 lists "comparing the same road over time" as later work).
**Source:** `Geo_Infra_Lens_AI_Orange_Deck_Adnan_Ghaffar.pdf` (this folder): "Predicting road damage before it happens", Chicago suburbs (Naperville, Aurora, Oswego). Data sources checked on the web on 2026-10-27.

## In plain words

Version 1 **finds damage that is already there** (photos → AI suggestion → reviewer). The forecasting track adds the question from the deck: **"Which roads are likely to be damaged next, and where should we inspect first?"**

It learns from four kinds of information: **weather** (freeze–thaw, rain, snow, heat), **road condition** (existing cracks, age, repairs), **map data** (elevation, drainage, flood zones, soil) and **traffic**. For every road section it gives a **risk estimate for the next 30–90 days**, with the reasons. It never says damage is certain. People decide where to inspect, and what they find is recorded, which is how the forecast is checked and improved.

---

## 1. Goal and research questions (from the deck)

| # | Question | How we will answer it |
|---|----------|-----------------------|
| RQ1 | Can AI predict which roads are more likely to deteriorate after extreme weather? | Compare the model with simple baselines on past winters it never saw (§5). |
| RQ2 | Can we measure how reliable the predictions are? | Precision of the top-ranked sections, recall, calibration, and confidence ranges, reported per area and season (§5). |
| RQ3 | Can cities inspect more efficiently without overlooking serious damage? | Field pilot: inspections planned from the forecast vs the usual way, counting damage found per inspection and damage missed (§6, phase F5). |

## 2. Rules that carry over from version 1

- A forecast is a **risk estimate**, never a finding and never a severity. Screens say "higher risk", not "damaged".
- Every score shows **why** (its inputs and their contributions) and which **data dates** and **model version** it used.
- Missing inputs are **flagged**, never guessed (same rule as inspection priority).
- Forecasts and their inputs are **kept**; nothing is overwritten (history for checking later).
- The model goes through the same steps as P8: pass marks agreed **before** training, a locked test period, a TRIAL label until it passes.

## 3. Data sources (checked 2026-10-27)

| Source | Free? | Updates | What we use | Limits |
|--------|-------|---------|-------------|--------|
| NOAA GHCN-Daily (weather stations) | Yes, public domain | Daily | Max/min temperature, rain, snow, snow depth → freeze–thaw cycles, heavy-rain days | Station points; each road section uses its nearest station(s) |
| Open-Meteo historical weather | Free for **non-commercial** use only | Daily, hourly history from 1940 | Gap-filling, hourly detail, forecasts for early warnings | Commercial use needs a paid plan; prefer NOAA |
| City of Chicago 311 "Pot Holes Reported" (2011–2018) and 311 Service Requests (Dec 2018 onward) | Yes, public | Regularly | **Dated, located damage reports**: the outcome the proof of concept learns from | Chicago only; reports reflect where people complain, not all damage |
| FHWA HPMS public release (Illinois) | Public | Yearly; public file found is 2018 | Roughness (IRI), condition rating, traffic (AADT, trucks) on major roads | Major roads only; old snapshot |
| IDOT Condition Rating Survey | Report public; raw data availability unconfirmed | Yearly (half the state each year) | Pavement condition 1–9 on state and some local major roads | Not ordinary city streets |
| IDOT traffic counts (AADT) | Public online | Yearly | Traffic per section | Thin on local streets |
| OpenStreetMap roads | Yes (ODbL: credit + share-alike) | Continuous | Road network, names, categories, splitting into sections | Data quality varies |
| USGS 3DEP elevation | Yes | Rarely | Slope, low points where water collects | — |
| FEMA National Flood Hazard Layer | Public | Rarely | Flood zones | Large downloads by county |
| USDA SSURGO soils | Yes | Rarely | Soil drainage class under the road | — |
| **City pavement ratings and repair history** (Naperville, Aurora, Oswego) | **Not public** | Every 1–3 years | The key outcome and condition data for the suburbs | Needs a data agreement with each city (or the academic partner) |
| **GeoInfraLens itself** | Ours | Continuous | Verified findings (existing damage), inspection outcomes (did damage appear?) | Grows as the app is used; becomes the best ground truth |

Not confirmed yet: whether IDOT's road download includes the condition field, exact licence wording for IDOT/FEMA/Chicago data, and whether a newer HPMS public file exists.

## 4. How the forecast works

**Unit:** a road **section** (about 100 m of one street, from OpenStreetMap) and a **week**.

**What we predict (target, to be agreed in F0):** "Will new damage be reported or verified on this section within the next 30 / 60 / 90 days?"
- Proof of concept (Chicago): a new 311 pothole report within 30 days.
- Suburbs and the app: a verified finding or an inspection outcome "damage found".

**Inputs (features) per section and week:**

| Group | Examples |
|-------|----------|
| Weather (changes daily) | freeze–thaw cycles in the last 7 / 30 days, total rain and snow, heavy-rain days, extreme-heat days, days since last freeze |
| Road condition | condition rating or roughness (where available), verified cracks and potholes from GeoInfraLens, years since last repair (city data) |
| Road use | traffic per day, share of trucks, road category |
| Place | slope, low point, flood zone, soil drainage |
| History | damage reports on this and neighbouring sections in past winters |

**Models, simplest first:**
1. **Rule baseline:** freeze–thaw cycles × existing condition. Easy to explain; the bar to beat.
2. **Logistic regression:** a transparent statistical baseline.
3. **Gradient boosting (LightGBM)** with calibrated probabilities: the main candidate. It runs on a normal computer (no GPU) and gives per-section factor contributions for the "why" breakdown.

## 5. How it is tested (decided before training, like P8)

- **Time split:** train on earlier winters, test on a later winter the model never saw (e.g. train 2015–2022, validate 2023, test 2024–2025).
- **Place split:** also test on an area left out of training (does it work in a new place?).
- **Measures:** precision of the top 10 / top 5% sections ("of the sections we would send crews to, how many really got damage?"), recall (how much damage the top 20% covers), PR-AUC, calibration (does "30% risk" happen about 30% of the time?), all with counts and confidence ranges.
- **Compared against:** the rule baseline, "inspect the worst-rated roads first", and random choice.
- **Pass marks:** PLACEHOLDER until the partner agrees them (same process as PI-17), frozen before training.

## 6. Roadmap

| Phase | What happens | Rough time | Gate (must be true to move on) |
|-------|--------------|-----------|--------------------------------|
| **F0 Ground rules** | Agree the target, forecast horizon (30/60/90 days), study area, section length, measures and pass marks; check every data licence; contact the cities and the academic partner | 1 week | Owner approves the plan (CR-005); licences recorded |
| **F1 Data pipeline** | Load OpenStreetMap road sections for the study area into PostGIS; daily NOAA weather; static layers (elevation, flood, soil, traffic, HPMS); Chicago 311 history; dataset card | 2–3 weeks | Counts reconcile; dataset card written; nothing from the test period touched |
| **F2 Proof of concept (Chicago)** | Build the section-by-week table; train the three models; run the locked test once; write the report | 2–4 weeks | Model beats the baselines by the agreed margin, with honest limits written down |
| **F3 Suburbs** | Get Naperville / Aurora / Oswego condition and repair data (agreement); adapt and retrain; test on held-out time and place | Depends on the cities (weeks to months) | Pass marks met on suburban data, or a documented "partial pass" decision |
| **F4 App integration** | Tables, daily jobs, API and screens (section 7), including **automatic in-app alerts for project managers** (§7.5); labelled **TRIAL FORECAST** until approved | 2–3 weeks (+ about 3–5 days for alerts) | Automated tests pass; owner tests the screens; permissions checked |
| **F5 Field pilot** | One winter season (Dec–Mar): crews inspect forecast top sections; outcomes recorded in the app; compare with usual practice (RQ3) | One season | Results report; partner feedback |
| **F6 Sign-off** | Model card, limitations, handover notes | 1 week | Owner and partner sign-off |

**Overall:** about **6–8 weeks** for F0–F2 (free data only), **2–3 weeks** for F4, while F3 and F5 depend on the cities and the winter season. Working in parallel with version 1 testing (P9) is possible because F0–F2 do not touch the app.

## 7. Integration into the GeoInfraLens app (phase F4)

The forecast sits next to the existing priority list: version 1 ranks **known** damage; the forecast ranks **roads to watch**. Both feed the same inspection workflow.

### 7.1 Database (new tables, add-only migration)

| Table | Holds |
|-------|-------|
| `road_sections` | Organization, project, OpenStreetMap way id, name, road category, line geometry (EPSG:4326), length, source, source date, licence |
| `weather_stations`, `weather_daily` | Station location; daily max/min temperature, rain, snow, source and download date |
| `section_features` | Section, date, the input values used, and the data versions they came from |
| `risk_runs` | Model version, run date, horizon (30/60/90 days), status, input data dates |
| `risk_scores` | Run, section, risk (0–1), risk band (low / medium / high), top factors with their contributions, missing inputs |
| `inspections.risk_score_id` (new optional column) | Links an inspection planned from a forecast to the score that suggested it, so its outcome checks the forecast |

### 7.2 Background jobs (Celery, scheduled)

- **Every morning:** download yesterday's weather (NOAA), recompute weather inputs, run the forecast for every project that has forecasting switched on.
- **Weekly / yearly:** refresh static layers (roads, traffic, condition data).
- **Retraining** happens outside the app (`ml/forecasting/`) after each winter, and a new model version goes through the same test-and-approve steps. The app accepts only a model file whose fingerprint matches the tested one (like the trial detector).

### 7.3 API (new, under `/api/v1`)

| Request | Who | What |
|---------|-----|------|
| `GET /projects/{id}/risk?horizon=30` | `risk.view` (new key: managers, reviewers, viewers) | Road sections with risk band, factors, run date, model version |
| `GET /road-sections/{id}/risk-history` | `risk.view` | Past scores for one section, with what inspections found |
| `POST /projects/{id}/risk-runs` | `risk.configure` (managers) | Run the forecast again now |
| `GET /projects/{id}/weather-summary?days=30` | `risk.view` | Freeze–thaw cycles, rain and snow for the project area |

### 7.4 Screens

- **New project tab "Road risk"** (or a section of Priority): map with road sections coloured by risk band, always with a word and icon (never colour alone); list "Inspect first" with the top sections and plain reasons, e.g. "6 freeze–thaw cycles in 14 days + existing cracks + 18,000 vehicles a day"; a weather strip for the last 30 days; **Plan inspection** opens the existing inspection flow.
- **Home "What to do next":** after a freeze–thaw spell or storm, e.g. "Freeze–thaw alert: 8 road sections in Mission District are at higher risk → See them".
- **Reports:** forecast CSV / GeoJSON export, labelled as estimates.
- **Settings:** switch forecasting on per project; choose the horizon.

### 7.5 Automatic alerts (decided by the owner, 2026-10-28)

The system tells people by itself when it finds something important; nobody has to open the forecast page and look.

**Decisions for now (owner, 2026-10-28):**

| Question | Decision now | Later (not planned yet) |
|----------|--------------|-------------------------|
| Who receives alerts | **Project managers only**, for the projects they manage (org admins see them when they open a project they manage) | Reviewers, inspectors, viewers |
| How | **In the app only**: a notification bell with a count, a notifications list, and an item in Home "What to do next" | Email (needs an email provider, which would also send invitation links); SMS **not wanted** for now |
| Which alerts | All forecast alerts below (no filtering by level yet) | Per-person settings (choose levels, projects, quiet hours) |

**When an alert is created** (checked automatically after every daily forecast run):

| Alert | Rule (starting values, configurable and documented like the priority weights) |
|-------|-------------------------------------------------------------------------------|
| Section turns high risk | A road section moves from low/medium into **high** |
| Sharp jump | Risk rises by **25 points or more** since the previous run |
| Weather coming to weak roads | The weather forecast shows freeze–thaw cycles or heavy rain in the next 7 days on sections already at medium or high risk |
| Data problem | The daily weather download or forecast run failed, or inputs are missing for many sections (so nobody trusts an old forecast without knowing) |

- **One alert per event and project**, listing all affected sections, not one alert per section; the same event is not repeated while it is still open.
- Alerts are **kept** (history) and marked read/unread per person; they never expire silently.

**What every alert contains (all measures and details):**
1. Title and project, e.g. "Freeze–thaw warning: 8 road sections at high risk".
2. **When**: the weather event and its dates, with the weather source and when it was issued.
3. **Each affected road section**: name and stretch, risk (next 30 days) with its range, previous risk, and the **main reasons with their contributions** (e.g. "4 freeze–thaw cycles coming +31%, existing cracks verified 2026-10-02 +18%, 18,000 vehicles/day +12%, condition 4/9 +9%"), plus any **missing inputs**.
4. **Suggested action** (e.g. "inspect before Friday") with buttons **Open on map** and **Plan inspections** (existing inspection flow).
5. **Model and data**: model version and its TRIAL label, data dates for weather, condition and traffic.
6. The fixed wording: "Risk estimate, not a confirmed defect."

**What it adds to the app (phase F4):**

| Part | Addition |
|------|----------|
| Database | `alerts` (project, type, title, details as JSON: sections, values, factors, sources, model version, run id; created_at; open/closed) and `alert_reads` (alert, user, read_at). Add-only migration |
| Background | After the daily forecast run (Celery Beat schedule), a step applies the alert rules and writes alerts; failures create a "data problem" alert |
| Permission | New key `alert.view`: **project_manager** only (org admin through their manager role). Other roles get nothing |
| API | `GET /notifications` (alerts for my managed projects, unread count), `POST /notifications/{id}/read`, `GET /projects/{id}/alerts` |
| Screens | Bell with unread count in the top bar / menu (managers only); notifications list; alert detail page with the section table, reasons, sources and buttons; Home "What to do next" item for new alerts |

**Stack for alerts:** nothing new beyond the forecasting track itself: Celery Beat (comes with Celery) for the schedule, PostgreSQL for alerts, FastAPI for the API, React for the bell and pages. No email or SMS service is needed for this decision.

### 7.6 Optional link to the priority score

Later, "forecast risk" can become an extra, configurable input to the inspection priority score (with a placeholder weight and the usual breakdown). It stays separate at first so each can be judged on its own.

## 7.7 Two levels for any project area (decided 2026-10-29)

The owner wants forecasting information for **whatever area a project manager selects**, anywhere in the US.

| Level | Where | What the manager sees | Built from |
|-------|-------|-----------------------|------------|
| **1. Risk factors** | Any project area in the US | Freeze–thaw and heavy rain (past and forecast), dips where water collects, slope, flood zones, road type; traffic and bus routes where a state/city publishes them (else "missing") | Free national data only: NOAA weather, NWS forecasts, OpenStreetMap roads, USGS elevation, FEMA flood zones (USDA soil where useful), fetched automatically for the project polygon |
| **2. Tested forecast** | Cities with pothole or repair history (Chicago first) | "Chance of a new pothole in the next 30 days" per road section, with measured accuracy | A model trained and locked-tested per city (as in F2) |

Rules:
- Level 1 is shown as **risk factors, never as a percentage chance**, because without local history its accuracy cannot be tested (project rule: never invent model capabilities). Labelled TRIAL.
- An area moves from Level 1 to Level 2 when it has enough dated history: city 311/repair data, or **GeoInfraLens's own verified findings** after 1–2 seasons of inspections there, and passes its own locked test.
- Traffic and bus data are not national; missing is shown as missing.

Rough effort after F2 passes: make the pipeline area-generic (~1 week); Level 1 in the app as part of F4 (~3–4 weeks); each extra Level 2 city ~1–2 weeks at first, then a few days.

## 8. Feedback loop (how it gets better)

Every inspection planned from a forecast records its outcome (damage found or not, severity by the reviewer). Those outcomes become labelled data: precision of the top sections is measured monthly, and the model is retrained after each winter. This is also the evidence for RQ2 and RQ3.

## 9. Cost

- Data: free (NOAA, OpenStreetMap, USGS, FEMA, USDA, Chicago, HPMS). Open-Meteo only if the use is non-commercial, otherwise paid.
- Computing: a normal computer or free Colab; no GPU needed.
- Possible paid items: pavement surveys if the cities have no usable records (quoted per mile); always-on hosting for the daily jobs (part of P10 anyway).

## 10. Risks and how we handle them

| Risk | Handling |
|------|----------|
| No damage history for the suburbs | Start with Chicago; ask the cities early (F0); use app inspection outcomes as they grow |
| 311 reports reflect who complains, not where damage is | Compare by neighbourhood; prefer verified inspections; report this limit |
| Few weather stations | Nearest-station and gap-filling; report station distance |
| One unusual winter skews the model | Test across several winters; report per season |
| People treat the forecast as certain | Wording ("higher risk"), confidence ranges, TRIAL label, inspections still decided by people |
| Data licences (ODbL share-alike, unclear IDOT/FEMA terms) | Record source, date and licence for every layer (F0) |

## 11. Decisions taken

| Date | Decision |
|------|----------|
| 2026-10-28 | Alerts: project managers only, in the app only (bell, list, Home), all alert types; no SMS; email later if wanted (§7.5) |
| 2026-10-28 | CR-005 approved: the track starts with F0 (ground rules, `04-design/forecasting-f0-ground-rules.md`) |

## 12. Decisions still needed before starting

1. Approve starting the forecasting track (CR-005), alongside or after P9.
2. Target and horizon: "new damage within 30 days" first, then 60 / 90?
3. Study area: Chicago proof of concept first, then Naperville, Aurora and Oswego?
4. Who contacts the cities and the academic partner for pavement and repair data?
5. Pass marks (with the partner), agreed before training.
