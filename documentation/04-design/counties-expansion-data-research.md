---
title: "Expanding GeoInfraLens AI to eight more counties: open data research"
subtitle: "Prepared 24 November 2026 for the team lead (updated 27 November 2026 after data checks and tests)"
---

# 1. Short answer

- **Roads, weather and cameras are available in all eight counties.** That is enough to switch on **Level 1** (risk factors only) everywhere, with no new data work.
- **Tested levels (Level 2) need pothole reports.** Chicago and Naperville already have them. Since 24 November we added **three more areas with tested levels**, all using public SeeClickFix reports and the same locked transfer test:
    - **Central DuPage** (Lombard, Glen Ellyn, Oak Brook, Wheaton): 631 reports, **passed all 5 checks**. Tested levels are on.
    - **Cook suburbs** (La Grange Park, Elk Grove Village, Schaumburg): 408 reports, **passed all 5 checks**, but the test window is small (about 186 reports), so it is labelled "lower confidence". Tested levels are on.
    - **Cook northwest** (Mount Prospect, Des Plaines, Arlington Heights): 245 reports, **passed all 5 checks**, labelled "lower confidence" (low absolute hit rate, about 0.6 in 100 flagged roads). Switched on in the code; live check on the laptop is still to do.
- **Aurora** publishes a downloadable 311 layer (public domain) with 331 pothole requests over about 17 months (one winter). It was loaded and its locked test passed all 5 checks, labelled "lower confidence" (see section 6 and the status report). Re-check in spring 2027 with a second winter.
- **No usable pothole source was found** for Kendall, Grundy, McHenry, Lake or Will (outside Naperville), or Kane outside Aurora. More than 80 towns and town groups were checked on SeeClickFix, also with other search words. Only public records requests or waiting remain.

# 2. Pothole and 311 reports (the key data for Level 2)

| Place | County | What was found | Status |
|---|---|---|---|
| Chicago | Cook | 311 pothole data since 2011, updated daily | Done (our Chicago model) |
| Naperville | DuPage / Will | City open data, 556 pothole requests since 2023 | Done (tested levels live) |
| **Lombard, Glen Ellyn, Oak Brook, Wheaton** | DuPage | SeeClickFix public reports: 631 (2022: 66, 2023: 96, 2024: 111, 2025: 138, 2026: 167) | **Done 2026-11-25: transfer test passed, tested levels live** |
| **La Grange Park, Elk Grove Village, Schaumburg** | Cook | SeeClickFix public reports: 408 | **Done 2026-11-25: test passed, tested levels live, "lower confidence"** |
| **Mount Prospect, Des Plaines, Arlington Heights** | Cook | SeeClickFix public reports: 245 (about 235 since 2022) | **Done 2026-11-25: test passed, switched on in code, "lower confidence"** |
| **Aurora** | Kane, DuPage, Will, Kendall | myAurora 311 open data layer: 331 pothole requests, 2025-01-31 to 2026-06-24. Public domain, CSV download, daily updates | **Transfer test passed (2026-11-25), lower confidence, one winter. Re-check spring 2027.** |
| **Evanston** | Cook | 311 layer 2013 to 2022 with locations, but no pothole request type | Not usable. Level 1 only. |
| Geneva | Kane | SeeClickFix: 96 reports (22 in 2025, 74 in 2026). St. Charles has only 1 (an earlier count of 99 was an overlapping search box). | Too short for a test. Revisit spring 2027. |
| Joliet, Bolingbrook | Will | SeeClickFix: 12 and 1 reports. Joliet uses VUEWorks CitizenVUE with no public export | No usable data |
| Waukegan | Lake | SeeClickFix: 8 reports. Lake County's open data hub has GIS layers only | No usable data |
| Elgin, St. Charles, Oswego, Yorkville, Morris, McHenry County | Kane, Kendall, Grundy, McHenry | Reports taken by phone or web form or app (Elgin 311, MyCivic 311, county portals for county highways). No public records data found | Ask each town (public records request) |
| County highway departments | all | No open pothole dataset found for any county | Ask each county for reports and repair logs |

**SeeClickFix** has a free public API. Its data licence is CC BY-NC-SA 3.0 US: credit seeclickfix.com, non-commercial use, and contact SeeClickFix before reusing large portions. The project owner decided on 2026-11-24 that this is a non-commercial project and used the data without contacting SeeClickFix first. The app label credits seeclickfix.com and requests are limited to one every 3.2 seconds. If the product ever becomes commercial, this must be revisited. SeeClickFix "closed" dates are often automatic archiving, not repair dates, and report counts rise as app use grows.

# 3. Road maps (centerlines) by county

Every county is covered by **US Census TIGER/Line "All Roads"** (public domain, updated yearly, 2025 files available) and by OpenStreetMap, which our app already uses. County files below are optional extras.

| County | County's own open road data | Access | Note |
|---|---|---|---|
| **Cook** | Cook Central maps portal and Socrata data catalog. "Highway Jurisdiction" covers the 557 miles the county highway department looks after. | Download (shapefile, KML) | Chicago has its own data. Suburbs rely on county and state files. |
| **DuPage** | Open data hub: Road Type Centerline and Pavement Centerline | Download or map service | One older service says "current as of 2009 aerial photography". Check which layer is current. |
| **Will** | GIS Division vector data page | Download after accepting a click-through "Open Geo-Spatial Data" licence | Read the licence before using. |
| **Kane** | GIS department; open hub not confirmed. Kane DOT publishes a county highway map (PDF). | Unclear | Use TIGER or OpenStreetMap unless the hub is confirmed. |
| **Kendall** | Open GeoData site (parcels, zoning, contours, OpenStreetMap-based routes) | Download and feature service | No authoritative road centerline listed. |
| **Grundy** | County GIS data is sold by fee schedule. Web map services are for display. | Paid | Use TIGER or OpenStreetMap. |
| **Lake** | Open data hub: Street Centerlines (emergency-call standard) and Edge of Pavement | Download (many formats) | The best county road data of the eight. |
| **McHenry** | GIS data on written request. Government and non-profit data sharing needs a signed agreement. | By request | No open download found. Use TIGER or OpenStreetMap. |

# 4. Cameras

- The **Illinois DOT Gateway** camera list gives location, direction, picture link and picture age. Our app already uses it, with a **15 km** search outside the project area.
- The Gateway network also carries pictures from county and tollway traffic centers (DuPage, Cook and the Illinois Tollway are listed; Will is listed as planned).
- So **new projects in these counties get cameras automatically**. I could not count cameras per county from here. I expect fewer in Kendall and Grundy than in the Chicago-area counties.

# 5. Other useful data

- **IDOT pavement condition ratings** (Condition Rating Survey). Published yearly by jurisdiction, with Fair, Poor and similar bands. Interstates yearly, other roads every two years. A published analysis of Cook County used it for state, local and toll roads. It could become a road-condition input for Level 1.
- **IDOT crash data** is not an open download. It is available by request or through a safety portal that needs approval. Not recommended for now.

# 6. Plan and status

1. **Level 1 everywhere first.** Create a test project in one town per county and confirm roads, weather and cameras appear. No new data needed. *Open.*
2. **Data checks.** *Done for Aurora, Evanston, the DuPage and Cook SeeClickFix towns, Geneva, Joliet, Waukegan and more (section 8 and 9).*
3. **Locked transfer test where there is enough data.** *Done: Central DuPage passed, Cook suburbs passed, Cook northwest passed, Aurora passed (all lower confidence except DuPage). Geneva, Highland Park / Lake Forest and a second Aurora check wait until spring 2027.*
4. **Public records requests** for pothole reports to the larger towns and county highway departments (Joliet, Elgin, Oswego, Yorkville, Morris, McHenry County and others). *Not sent: the project owner chose not to use public records requests for now.*
5. **Test IDOT pavement ratings** as an extra road-condition input. *Open.*

# 7. Sources

- Cook County highway jurisdiction data: smartchicagocollaborative.org/new-cook-county-data-cook-county-highway-jurisdiction
- Cook County road condition analysis: civicfed.org/blog/tale-three-cook-counties-geographic-disparities-road-conditions
- DuPage open data: gisdata-dupage.opendata.arcgis.com
- Will County GIS data: willcounty.gov/County-Offices/Administration/GIS-Division/Data
- Kane County GIS: kanecountyil.gov/Pages/gis.aspx
- Kendall County Open GeoData: geodata.kendallcountyil.gov
- Grundy County GIS data request: grundycountyil.gov/services/gis/gis_data_request.php
- Lake County street centerlines: catalog.data.gov/dataset/street-centerlines
- McHenry County GIS: mchenrycountyil.gov/departments/geographic-information-system-gis
- Census TIGER/Line roads: catalog.data.gov (search "TIGER/Line Shapefile, Current, County ... All Roads")
- Aurora 311 portal: aurora.il.us/News-articles/City-Launches-myAurora-311-Open-Data-Portal
- Aurora 311 data hub: myaurora-311-cityofaurora.hub.arcgis.com
- Evanston 311 dataset: geo.btaa.org/catalog/46a3790e057a413e83103abf0e50a816_0
- Gateway camera locations: geo.btaa.org/catalog/8a885da23dfb46caaa1827ad920fb5b1_0
- IDOT condition ratings: idot.illinois.gov/transportation-system/network-overview/highway-system/reports.html
- IDOT crash data: idot.illinois.gov/transportation-system/safety/Illinois-Roadway-Crash-Data
- SeeClickFix API: dev.seeclickfix.com
- Joliet service requests: joliet.gov/our-city/i-want-to/report-3101
- Oswego MyCivic 311: patch.com/illinois/oswego/mycivic-311-replaces-oswego-click-n-fix
- Lake County open data hub: data-lakecountyil.opendata.arcgis.com

# 8. Update 2026-11-24: data checks run on the laptop (scripts\archive-data-checks\county-data-check*.bat, moved 2026-11-27)

**Aurora (Kane, DuPage, Will, Kendall)**

- City 311 layer: 23,248 requests, 2025-01-03 to 2026-06-25. "Pothole" request type: **331** (2025 = 205, 2026 to June = 126). All 331 have a location, but only to a street block (map points rounded to about 100 m).
- Busiest months: March (59) and April (58).
- Verdict: **too thin for the locked transfer test** (18 months; Naperville had 3.8 years and 556 requests). Ask the city for older records or wait for more winters.
- Note: several "Aurora" layers found by search belong to Aurora, Colorado. Ignore them.

**Evanston (Cook)**

- 311 layer (ArcGIS): 230,622 requests, 2013-12-30 to 2022-02-24, with latitude and longitude.
- **No pothole request type.** The road-related titles are street signs, street lights, snow removal, street sweeping, manhole covers, bike lane maintenance and flooding. Potholes are not in the data under any title with "pothole", "pavement" or "road".
- Verdict: **not usable for tested levels.** Level 1 only.

# 9. Update 2026-11-25: new areas built, tested and switched on

**Central DuPage: Lombard, Glen Ellyn, Oak Brook, Wheaton (DuPage)**

- 631 SeeClickFix pothole reports after removing duplicates (2022: 66, 2023: 96, 2024: 111, 2025: 138, 2026: 167). 94 weekly test dates (2025-01-06 to 2026-10-19) on 10,160 road sections.
- Locked transfer test of the Chicago model (`forecast-chicago-0.2`): **PASS, all 5 checks.** Top-1% hit rate 1.59% against 0.84% for an average section (ratio 1.89); PR-AUC ratio 2.03; winter ratio 1.78; top-10% recall 0.335 against 0.156; Brier score 0.0019 against 0.0069.
- Tested levels are switched on, labelled with the source (seeclickfix.com). The pass marks are still placeholders until the owner approves final marks (PI-20).

**Cook suburbs: La Grange Park, Elk Grove Village, Schaumburg (Cook)**

- 408 SeeClickFix reports after removing duplicates (14 more fall outside the area).
- Locked transfer test: **PASS, all 5 checks.** Precision ratio 2.12 (0.0191 against 0.0090); PR-AUC ratio 1.79; winter ratio 2.44; top-10% recall 0.444.
- Only about 186 reports fall in the test window and some weeks have none (possibly gaps in the data), so the level is labelled **"lower confidence"**.

**Aurora (Kane, DuPage, Will, Kendall): re-checked and loaded at Level 1**

- The city's myAurora 311 hub publishes a request-level layer: public domain (citation appreciated), CSV and GeoJSON download, updated daily. 331 pothole requests, 2025-01-31 to 2026-06-24, one winter.
- Loaded into its own area (12,788 road sections, all 331 requests inside the city). **The transfer test is not run:** about 80 reports would fall in the test window and the test can only be run once. Re-check in spring 2027, when a second winter should bring roughly 600 or more reports.
- *Superseded later on 2026-11-25: the Aurora test was run and passed all 5 checks (lower confidence, one winter), and Aurora is in the tested areas. See sections 1 and 6.*

**Other towns searched on 2026-11-25 (no usable public data):** Elgin, St. Charles, Joliet (VUEWorks CitizenVUE), Oswego (MyCivic 311), Yorkville, Morris, Lake County (GIS hub only), McHenry County (county-highway report portal only). Only public records requests or waiting remain for these.

**Limits to keep in mind**

- SeeClickFix licence: see section 2. Non-commercial decision by the owner; the contact-first email was not sent.
- SeeClickFix report counts rise with app adoption, and its "closed" date is often automatic archiving, not a repair date.
- All pass marks are placeholders until PI-20.
- The tested levels apply to roads inside these areas only; roads in the other counties get Level 1 (risk factors).

# 10. Update 2026-11-25: Kendall and Grundy checked

- **Kendall: Level 1 only.** SeeClickFix shows 27 pothole reports in the whole county for 2012 to 2026 (Oswego 8, none after 2022; Yorkville 1; Montgomery 1; Plano, Sandwich, Minooka 0). Oswego (MyCivic 311) and Yorkville (Report a Concern) publish no data. County GIS has no pothole layer. Only an informal request to Oswego for a MyCivic export could change this (not sent).
- **Grundy: Level 1 only.** SeeClickFix shows 0 pothole reports in the whole county (Morris, Channahon, Coal City/Diamond, Braidwood, Dwight, Minooka all 0). Morris takes reports by phone only. Minooka has a report portal with no export and 0 SeeClickFix reports. County GIS data is sold with no pothole layer.
- Details: `kendall-grundy-data-check.md`.

# 11. Update 2026-11-26 and 27: more towns, new search words, new area

**Scan 1: 48 more towns on SeeClickFix (DuPage, Cook, Will, Kane).** Strong and already covered: Wheaton (about 33 a year), Glen Ellyn (about 63), Elk Grove Village (about 25), Schaumburg (about 20). New and usable: **Mount Prospect** (210 reports, about 32 a year since 2020), **Des Plaines** (80) and Arlington Heights (39). Too small: Addison, Hinsdale, Glendale Heights (10 to 15 each). Evanston stopped around 2019. All the Will towns checked (Plainfield, Romeoville, Lockport, Crest Hill, Shorewood, Frankfort, Mokena, New Lenox, Lemont) have 0 to 1 report, Elgin 2, Hampshire/Gilberts 0.

**New area: Cook northwest (Mount Prospect, Des Plaines, Arlington Heights).**

- 245 SeeClickFix pothole reports after removing duplicates; 12,994 road sections; weather from Palwaukee, O'Hare and Barrington. Config `ml/forecasting/config/areas/cook_northwest.yaml`, prepared with `scripts/cook-northwest-prepare.bat`.
- Locked transfer test of `forecast-chicago-0.2` (Mondays 2022-01-03 to 2026-10-19, 251): **PASS, all 5 checks.** Top-1% precision 0.0058 against 0.0010 for the simple rule (ratio 5.8); PR-AUC ratio 3.3; winter ratio 8.7; top-10% recall 0.371 against 0.140; Brier 0.0004 against 0.0055.
- Caveat: the ratios look large because the simple rule scored very poorly here. Only about 0.6 in 100 flagged roads got a report in 30 days, and the Brier check mostly tests calibration at a tiny base rate. Pass marks are placeholders (PI-20).
- App: `COOK_NORTHWEST` added to `TESTED_AREAS`; the label says "lower confidence" and credits seeclickfix.com. Backend tests and the live check on the laptop are still to do.

**Scan 2: other search words.** Reports filed as "pavement", "road damage", "street repair" or "sinkhole" were tested in 36 town groups (Lake, McHenry, Will, Kane, Kendall, Grundy, Cook, DuPage). A sample of titles showed that "street repair" is mostly sidewalk and curb repairs, water-utility asphalt repairs and street lights (Geneva, Algonquin, Highland Park), not potholes. The plain "pothole" search was already the right one. **No new area came out of this.** The scan also fixed two counts: St. Charles has 1 pothole report (not 99, which were Geneva's), and Algonquin / Lake in the Hills has 222 "pothole" reports but only 24 since 2024.

**No-history experiment (Chicago validation year).** The Chicago model without local report history reached only about 2.3 times chance at the top 1%, with no better probabilities than the average, so areas without reports stay at Level 1. Details: `forecasting-f5-no-history-plan.md`.

**Other sources searched, no usable public pothole history:** CMAP pavement condition data (2018 survey and pavement plans for 44 municipalities, mostly PDFs, road wear not pothole history; the earlier Cook check found no link between wear and reports), county road department report portals (McHenry, Lake, Will), Lake County and Des Plaines open data portals, town request forms (St. Charles, Highland Park, Deerfield, Antioch, Crystal Lake). Mapillary street photos were considered and dropped by the owner.

**Where this leaves the six areas.** DuPage and Will, Kane, Cook: partly complete. Kendall, Grundy, Lake and McHenry: Level 1 only. Retest in spring 2027: Geneva, Highland Park / Lake Forest, Aurora (second winter). The SeeClickFix route is used up; the remaining routes are waiting or asking towns (not chosen by the owner for now).

## 12. Road-condition data check (2026-11-27)
- IDOT's Condition Rating Survey covers state highways only and is published as summary PDFs; segment data exists (CMAP got a special IRIS copy) but is not openly downloadable. CMAP's local pavement plans (44 municipalities, 2018-2021) are PDFs.
- FHWA lists Illinois HPMS services for 2020 and 2022-2025, so the earlier note "not published for Illinois" may have been an outage. On 2026-11-27 (three runs of `scripts\road-condition-check.bat`) FHWA's data server returned "connection attempt failed" for every state tested (Illinois, Indiana, Wisconsin), and both Cook County pavement servers returned server errors. Result: not decided; repeat the check later.
- Any use is Level 1 only (road wear showed no link to report risk).
