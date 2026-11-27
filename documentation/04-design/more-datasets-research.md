# More datasets for the counties and Naperville (research, 2026-11-27)

**Why this document exists.** The free report data for the six county areas is nearly used up (see `counties-expansion-data-research.md`). This round looked for *other* data that could improve the project: new inputs for the model, better road condition for Level 1, and new labelled data. It covers DuPage, Will, Kane, Kendall, Grundy, Lake, McHenry, Cook and Naperville, plus sources that cover all of them.

**How it was done.** Web searches on 2026-11-27 (18). Everything below comes from what the search results showed. Items marked **not confirmed** were not opened or tested. No data was downloaded. FHWA's data server and the Cook County map server were down on the same day (see section 3), so those two could not be tested.

**What a new input has to prove.** It is tried on the validation years only. The locked transfer test stays locked. A retrained model needs a fresh pass/fail test on Mondays after 2026-11-24. A high forecast still means "where reports are likely", not "worn road".

---

## 1. Short answer: what I would do, in order

| # | What | Why it helps | Effort | Status |
|---|---|---|---|---|
| 1 | **HPMS from the BTS national download** instead of FHWA's live service | Gives measured roughness, cracking, rutting and traffic on main roads in every county, and does not depend on the broken server | Small to medium (large file) | **Done 2026-11-27** via the data.transportation.gov table (section 8); Level 1 only |
| 2 | **Naperville as the test bench for new inputs** (resurfacing history, street-cut permits) | Naperville is the only area with 3.8 years and 556 requests, so a new input can be validated properly there | Medium | Sources found; machine-readable form **not confirmed** |
| 3 | **Gridded weather** (SNODAS snow depth and melt, hourly multi-sensor rain) | Weather is the main driver of winter potholes; grids cover Kendall, Grundy, McHenry and other places far from a weather station | Medium | Datasets confirmed; archive depth for rain **not confirmed** |
| 4 | **IDOT planned and recent state resurfacing** (open map service) | A road resurfaced recently should have fewer potholes; gives a "recent work" flag on state routes | Small | Service found; licence **not confirmed** |
| 5 | **Start saving live feeds now** (IDOT winter road conditions, Naperville snow map) | Builds a history we do not have today | Small | Layer found; history **not confirmed** |
| 6 | **Ask for pavement ratings** (CMAP, Kane DOT, McHenry DOT) | Segment-level condition for county and town roads | Needs a request | Not started; you decided against records requests for now |

Honest limit: the earlier Cook check found no link between pavement score and where reports appear. Items 1, 4 and 6 mostly improve Level 1 (the risk factors people see), not the tested percentages. Items 2, 3 and 5 are the ones that can plausibly lift the percentages.

---

## 2. By area

### Naperville
- **Open data portal exists** (launched 2017 as part of What Works Cities). The pothole data we already use comes from here. I did not browse the rest of the portal this round, so what else it holds (permits, work orders) is **not confirmed**. <https://www.naperville.il.us/government/open-data/>
- **Resurfacing history.** The city runs yearly programs: street resurfacing (city and Motor Fuel Tax funded), micro-surfacing, crack filling and patching. Descriptions and locations appear in bid notices and an older city map page. Use: a "years since resurfaced" input per road section. The bid sites are commercial with free-view limits, so the clean source would be the city's own program map or a request to Public Works. <https://patch.com/illinois/naperville/city-to-begin-roadway-resurfacing-program>
- **Street-cut permits.** Any utility or contractor work in the street needs a right-of-way permit, and excavation permits are charged a higher fee. Digging up a street is a known cause of later potholes, so permits could become a "recent street cut" input. The city publishes monthly permit reports as PDFs; whether street permits are in the open portal is **not confirmed**. <https://naperville.il.us/services/permits--licenses/right-of-way-permit>
- **Winter operations.** The city has an interactive plow-progress map and sends winter notifications, and it keeps salt domes. No downloadable salt or plow dataset was found. Idea: save the map's data during winter storms to build our own history (item 5). <https://www.naperville.il.us/snowremoval>

### DuPage
- **County GIS**: pavement centerline (older layers say aerial 2009 or 2013) and Road Type Centerline (2024). Roads, not condition. <https://geo.btaa.org/catalog/42d5d1dffdfa47aab02e06a35f88bf40_0>
- **County Division of Transportation** publishes yearly construction programs listing county-highway resurfacing (for example 2023). Names and limits are in web pages, not a data layer. <https://www.dupageco.org/dot/construction/index.php>
- **County right-of-way permits** exist for county highways only. No open dataset found. <https://www.dupagecounty.gov/government/departments/transportation/doing_business/permits/construction_permits.php>
- Towns publish their own pavement studies, for example Clarendon Hills (PASER ratings and a five-year resurfacing plan, 2021). Useful but PDF. <https://www.clarendonhills.us/DocumentCenter/View/2079/2021-Pavement-Study>

### Will
- **Construction Projects Interactive Map** from the county GIS Division, updated through the year, plus yearly schedules (reconstruction, resurfacing, intersections). County highways only. Whether the map has a download is **not confirmed**. <https://willcounty.gov/County-Offices/Administration/County-Executive/Press-Releases/will-county-launches-interactive-map-for-monitoring-2023-road-construction>
- **Romeoville** keeps a five-year crack-sealing and resurfacing plan, with a van-based pavement survey every five to six years and a live list of in-house resurfacing jobs. <https://romeoville.org/232/Road-Updates>
- Earlier finding stays: the Will GIS data page needs a click-through licence. Report data is thin outside Naperville and Aurora.

### Kane
- **Kane DOT pavement dashboard** shows Condition Rating Survey values for about 300 route miles of county highways, in bands from Excellent to Poor. This is the most useful county-level condition source found. Whether it can be downloaded or only viewed is **not confirmed**. <https://kdot.kanecountyil.gov/Pages/Dashboard/Pavement.aspx>
- A county bid describes collecting pavement condition index, roughness (IRI) and images for the whole county network, so segment-level data exists inside the county. <https://www.bidnetdirect.com/public/supplier/solicitations/statewide/443663203521/abstract>
- Yearly resurfacing and asphalt-rejuvenator programs are announced in the press. <https://www.shawlocal.com/kane-county-chronicle/2026/06/01/kane-county-road-resurfacing-work-begins-june-1-what-to-expect/>
- IDOT hosts public plan sets for Aurora resurfacing jobs (for example Molitor and Diehl Roads). These give exact limits of recent work in Aurora, but as PDFs. <https://apps1.dot.illinois.gov/eplan/desenv/011626/007-61L56/PLANS/PL-61L56-007.pdf>

### Kendall
- **Highway Department five-year program** (2025 to 2029), a PDF list of pavement preservation and projects. <https://kendallcountyil.gov/home/showpublisheddocument/587/638621831424970000>
- **Yorkville** runs a pavement management program that rates every road and reports resurfacing since 2019. The ratings themselves are not public data as far as I found. <https://shawlocal.com/kendall-county-now/2025/03/21/yorkville-prepares-for-46-million-in-roadway-repair-projects>
- Nothing new on report history (still about 27 reports county-wide).

### Grundy
- **Not searched again this round.** The earlier check found no pothole data and paid GIS data only. Gridded weather (item 3) and HPMS (item 1) are the only new things that would reach Grundy.

### Lake
- **Edge of Pavement** layer, traced from March and April 2018 aerial photos, with a pavement type code; downloads in CSV, GeoJSON, shapefile and others. This is road surface shape and type, not condition. <https://catalog.data.gov/dataset/edge-of-pavement-0433a>
- Street centerlines follow the NG911 specification (earlier finding). No pavement condition or resurfacing data found.

### McHenry
- **Division of Transportation** publishes a five-year program every year, each with a section on condition evaluation and GIS pavement management. It maintains 525 miles of county road. The county put out a request for a pavement condition survey in 2018. The ratings sit in the county's own GIS, not in an open layer. <https://mchenrycountyil.gov/departments/transportation/sections/maintenance-department>
- **City of McHenry** has a full pavement condition index report (2019, made with CMAP) with PAVER. PDF. <https://www.cmap.illinois.gov/documents/10180/1112751/Final_Report_McHenry.pdf/54ba75ee-0fb4-7f94-d61c-fa41094148ae>

### Cook
- **Cook County Highway Jurisdiction** (shapefile or KML) shows which roads the county highway department maintains; the department looks after 1,620 lane miles in the suburbs. Useful as a "who maintains this road" input. <https://smartchicagocollaborative.org/new-cook-county-data-cook-county-highway-jurisdiction>
- **Pavement Condition Index map service** exists but was down on 2026-11-27 (section 3).
- **Civic Federation analysis** of IDOT ratings across Cook (state, local and toll roads) shows what the state data looks like; the toll roads rate best. Useful to read, not a data source. <https://civicfed.org/blog/tale-three-cook-counties-geographic-disparities-road-conditions>
- **Claims.** The county takes vehicle-damage claims for potholes on county roads through its Risk Management office. Not an open dataset, and probably not obtainable. <https://www.cookcountyil.gov/service/problem-reporting>

---

## 3. Sources that cover every area

**HPMS (measured roughness, cracking, rutting, traffic).**
- FHWA's live service lists Illinois for 2020 and 2022 to 2025, but on 2026-11-27 every data request failed for every state tested, so the problem is on FHWA's side (our own check, three runs).
- Our earlier note "HPMS not published for Illinois" looks wrong: FHWA's 2023 national tables count 13,794 miles of urban federal-aid road in Illinois with measured roughness, and 5,128 of them above the poor limit. <https://www.fhwa.dot.gov/policyinformation/statistics/2023/pdf/hm47i.pdf>
- **Alternative route:** the US DOT Bureau of Transportation Statistics publishes HPMS 2023 (BETA) as a downloadable file geodatabase with one feature class per state. The catalogue lists a public-domain (CC0) licence but also says "non-public" access, which it does not explain. The download page offers geodatabase, shapefile, GeoPackage, CSV and GeoJSON. <https://catalog.data.gov/dataset/beta-highway-performance-monitoring-system-2023>
- HPMS covers main roads only. Residential streets, where most reports come from, are mostly not measured.

**IDOT.**
- **Condition Rating Survey**: scale 1 (failed) to 9 (new), state highways, non-interstate roads on a two-year cycle. Public output is summary reports (FY2022 and FY2025 exist). <https://idot.illinois.gov/transportation-system/network-overview/highway-system/maps.html>
- **Segment-level data exists.** CMAP says it obtained a special version of IDOT's roadway database with roughness and condition. So a data request is the route. <https://www.cmap.illinois.gov/mobility/explore/sources>
- **Multi-Year Program and Annual Highway Improvement Program**: an open ArcGIS service (up to 2,000 records per request) and Excel project lists by district and county. Gives planned and recent state resurfacing. <https://services2.arcgis.com/aIrBD8yn1TDTEXoz/ArcGIS/rest/services/Annual_Highway_Improvement_Program/FeatureServer>
- **Winter Road Conditions** layer on IDOT's open data portal (live). Whether any history is kept is **not confirmed**. <https://geo.btaa.org/catalog/4120fe1943d9414bba20756391aa13d9_2>
- IDOT right-of-way and utility permits are for state roads only; no open permit data found. <https://idot.illinois.gov/doing-business/permit-and-sales-marketplace/utility-permits.html>

**Gridded weather.**
- **SNODAS** (NOAA): daily 1 km snow depth, snow water equivalent, snowfall and snowpack temperature from 2003, free from the National Snow and Ice Data Center. Caution from its own documentation: it is not suited to snowfall totals for specific places, so use it for snow cover and melt, not exact snowfall. <https://www.nohrsc.noaa.gov/archived_data/instructions.html>
- **Stage IV / MRMS precipitation**: hourly radar-plus-gauge rain estimates on a national grid, available for download from NOAA. How far back the free archive goes was **not confirmed**. <https://water.noaa.gov/about/precipitation-data-access>
- Why it matters: the current weather input comes from nearby stations. Gridded data fills the gap in Kendall, Grundy, McHenry and the western edges of Kane and Will.

**Waze for Cities.**
- Free for public agencies; two-way sharing of incident and road-closure data. The feed is not a public API: an agency applies and is given access. <https://www.waze.com/discuss/t/waze-for-cities/377967>
- In April 2026 Waymo and Waze started a pilot that adds Waymo-detected potholes to the same free platform, in five launch markets (not Chicago). <https://techcrunch.com/2026/04/09/waymo-robotaxis-are-tracking-potholes-and-sharing-that-data-with-waze-users>
- For us this is a partnership idea, not a dataset: a client city that joins Waze for Cities could feed its pothole reports into the app.

**CMAP.**
- Pavement management plans for 44 municipalities and one county (2018 to 2021) with pavement condition index per street. Mostly PDF reports. <https://metroplanning.org/rough-roads-ahead-if-we-cant-maintain-what-weve-got-should-we-be-building-more/>

---

## 4. Not worth doing

- **More SeeClickFix scans.** Done and exhausted (section 11 of the counties document).
- **Cook County PCI as a model input right now.** Server down, and the earlier check found no link to report risk.
- **Scraping commercial bid sites** (ConstructConnect and similar). They limit free views and the terms are unclear.
- **FHWA national tables.** State totals only, no use per road.
- **Waymo pothole data.** Only in five other cities.

---

## 5. Open questions (not confirmed)

1. ~~Does the BTS HPMS download contain Illinois with roughness and cracking filled in?~~ Answered: yes, through the data.transportation.gov table (section 8).
2. Is Naperville's open portal carrying street permits or pavement data (it was not browsed this round)?
3. Can the Kane DOT dashboard data be downloaded, or only viewed?
4. Does IDOT keep any history of the winter road conditions layer? What licence applies to its open layers?
5. How far back does the free rain archive go for Illinois?
6. Does Will County's construction map have a data download?

---

## 6. Proposed next steps

| Step | Who | Size |
|---|---|---|
| Check the BTS HPMS download for Illinois (fields filled, file size) | Claude writes a laptop check, you run it | Small |
| Browse the Naperville portal for permit, pavement and work-order data | Claude (web) | Small |
| Try SNODAS and the rain grid as extra weather inputs on Chicago validation years, then Naperville | Claude builds, you run | Medium |
| Add "recent resurfacing" and "recent street cut" inputs for Naperville from the city's program list and permit reports | Claude and you (needs the city's lists) | Medium |
| Save IDOT winter road conditions and Naperville's plow map during storms | Scheduled task | Small |
| Ask CMAP, Kane DOT and McHenry DOT for segment-level pavement ratings | You decide (not a records request, but still a request) | Waiting time |

---

## 7. Sources

- Naperville open data: <https://www.naperville.il.us/government/open-data/>
- Naperville right-of-way permit: <https://naperville.il.us/services/permits--licenses/right-of-way-permit>
- Naperville snow removal: <https://www.naperville.il.us/snowremoval>
- DuPage Road Type Centerline: <https://geo.btaa.org/catalog/42d5d1dffdfa47aab02e06a35f88bf40_0>
- DuPage DOT construction program: <https://www.dupageco.org/dot/construction/index.php>
- Will County construction map: <https://willcounty.gov/County-Offices/Administration/County-Executive/Press-Releases/will-county-launches-interactive-map-for-monitoring-2023-road-construction>
- Romeoville road updates: <https://romeoville.org/232/Road-Updates>
- Kane DOT pavement dashboard: <https://kdot.kanecountyil.gov/Pages/Dashboard/Pavement.aspx>
- Kane County pavement data bid: <https://www.bidnetdirect.com/public/supplier/solicitations/statewide/443663203521/abstract>
- Kendall highway program: <https://kendallcountyil.gov/home/showpublisheddocument/587/638621831424970000>
- Yorkville repair projects: <https://shawlocal.com/kendall-county-now/2025/03/21/yorkville-prepares-for-46-million-in-roadway-repair-projects>
- Lake County Edge of Pavement: <https://catalog.data.gov/dataset/edge-of-pavement-0433a>
- McHenry County maintenance: <https://mchenrycountyil.gov/departments/transportation/sections/maintenance-department>
- City of McHenry pavement report: <https://www.cmap.illinois.gov/documents/10180/1112751/Final_Report_McHenry.pdf/54ba75ee-0fb4-7f94-d61c-fa41094148ae>
- Cook highway jurisdiction: <https://smartchicagocollaborative.org/new-cook-county-data-cook-county-highway-jurisdiction>
- Cook County problem reporting: <https://www.cookcountyil.gov/service/problem-reporting>
- Civic Federation: <https://civicfed.org/blog/tale-three-cook-counties-geographic-disparities-road-conditions>
- BTS HPMS 2023 (BETA): <https://catalog.data.gov/dataset/beta-highway-performance-monitoring-system-2023>
- FHWA Table HM-47i 2023: <https://www.fhwa.dot.gov/policyinformation/statistics/2023/pdf/hm47i.pdf>
- IDOT highway system maps and reports: <https://idot.illinois.gov/transportation-system/network-overview/highway-system/maps.html>
- IDOT Annual Highway Improvement Program service: <https://services2.arcgis.com/aIrBD8yn1TDTEXoz/ArcGIS/rest/services/Annual_Highway_Improvement_Program/FeatureServer>
- IDOT winter road conditions: <https://geo.btaa.org/catalog/4120fe1943d9414bba20756391aa13d9_2>
- IDOT utility permits: <https://idot.illinois.gov/doing-business/permit-and-sales-marketplace/utility-permits.html>
- CMAP mobility data sources: <https://www.cmap.illinois.gov/mobility/explore/sources>
- CMAP pavement plans (Metropolitan Planning Council): <https://metroplanning.org/rough-roads-ahead-if-we-cant-maintain-what-weve-got-should-we-be-building-more/>
- SNODAS archive instructions: <https://www.nohrsc.noaa.gov/archived_data/instructions.html>
- NOAA precipitation data access: <https://water.noaa.gov/about/precipitation-data-access>
- Waze for Cities: <https://www.waze.com/discuss/t/waze-for-cities/377967>
- Waymo and Waze pothole pilot: <https://techcrunch.com/2026/04/09/waymo-robotaxis-are-tracking-potholes-and-sharing-that-data-with-waze-users>

---

## 8. HPMS table check passed (2026-11-27)

`scripts\hpms-table-check.bat` (12 steps, all OK) tested FHWA's table "HPMS Spatial All Sections - 2024" on data.transportation.gov (public domain, Socrata id `42um-tgh5`, data year 2024).

- **Illinois: 445,757 road pieces.** Roughness (IRI) and cracking are filled in on 111,298 of them, rutting on 93,169, traffic (AADT) on 174,585, trucks on about 116,000, surface type on 111,374.
- **A DuPage-sized box holds 12,657 pieces.** Most are local streets with only basic fields; the measured values are on the main roads.
- **The earlier note "HPMS not published for Illinois" is wrong** (it was FHWA's map server, not the data).
- **Built:** `download.py` tries FHWA's map services first and falls back to this table (`download_hpms_table`; config `hpms.table` in `config/sources.yaml`). Three new tests in `tests/test_forecast_download.py`; 96 forecasting tests pass on the laptop.

---

## 9. Result: HPMS loaded for every area (2026-11-27)

FHWA's map service was still down, so every run used the data.transportation.gov table (data year 2024). The model does not read these columns, so the locked tests are unchanged; only Level 1 risk factors change.

| Area | HPMS pieces | Road sections matched |
|---|---|---|
| Naperville | 1,209 | 2,584 |
| Central DuPage | 2,119 | 2,411 |
| Cook suburbs | 6,329 | 2,648 |
| Cook northwest | 2,453 | 3,092 |
| Aurora | 1,708 | 2,712 |
| Chicago | 13,636 | 21,511 |

**Naperville fill rates** (of 1,209 pieces): roughness 787, cracking 708, rutting 492, traffic 1,209, surface type 787.

**Resurfacing fields are too thin.** Only 142 of 1,209 Naperville pieces (12%) have `year_last_improvement` or `last_overlay_thickness`. Most years are 1958 to 1997; about 12 are 2016 or later. A "years since resurfaced" input from HPMS is dropped. It would need the city's own yearly resurfacing lists (section 2, Naperville).

**Still to do:** in the app, Settings > Road risk > Update now; retry `scripts\road-condition-check.bat` later for the Cook pavement and FHWA map services.
