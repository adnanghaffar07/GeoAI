# Whole road: make it always work (2026-11-17)

**Problem.** OpenStreetMap keeps one road as many short pieces, and the place search returns one. "Whole road" collected the rest with an Overpass search `way(around:5000,lat,lon)["highway"]["name"="X"]`. The `around` search over 5 km makes the servers check thousands of roads, so all three timed out on the live site.

**Chain** (each step is tried only if the one before fails; the screen names the source used)

| Step | Where it runs | What |
|------|---------------|------|
| 1. Fast search | server (`services/whole_road.py`) | Tag first, inside a box: `way["highway"]["name"="X"](s,w,n,e)`, also by route number (`ref`) and by the found piece's own name and route numbers. Box = twice the radius (default about 10 km). All three servers are asked at the same time (threads); the first good answer wins; 20 s limit. A "runtime error" note in a 200 answer counts as a failure |
| 2. Nominatim backup | browser (`lib/whole-road.ts`) | `q`, `dedupe=0`, `limit=40`, `viewbox` + `bounded=1`, `polygon_geojson=1`, `extratags=1`, `format=jsonv2`. Keeps the LineString results whose name (or route number) matches; short and long spellings and directions match ("N Washington St" = "Washington Street") |
| 3. Our own database | server | Road sections loaded for forecasting (`forecast_sections`: Chicago, Naperville) inside the box, matched by name or `road_ref` |
| Road between two points | browser | The route from the free OSRM demo router (`overview=full&geometries=geojson`), thinned to 5,000 points, then a strip through `area-from-place`. The map tool shows A and B pins |
| Find all parts by name | browser + server | The same chain, for a typed name and a chosen extent: town limits (Overpass `is_in` + administrative area that contains the point), the map view, or within 5 / 10 / 20 km |

**Rules kept:** nothing is saved by these requests; no e-mail in any request; free services only; long roads are thinned to the shape limit before the strip is made; a map view larger than 0.6 degrees is refused with advice.

**Tests.** Backend `tests/test_geo.py`: tag-first box query; map view, 20 km and town extents; refused requests; first good server wins; all servers failing names each one; database backup (spellings, route numbers, far roads, 404 vs 503); thinning. Frontend `lib/whole-road.test.ts` (names, Nominatim backup, chain order, OSRM) and `pages/project-form-page.test.tsx` (backup used, database used, all fail, Find all parts by name, Road between two points). All use stand-in answers.

**Status.** Built 2026-11-17. Frontend type check and backend format and lint pass in the agent's workspace; the test runs and the live try are the owner's (`backend-tests`, `frontend-tests`, `start-local`).

## Update 2026-11-17 (after the first hand test)

Liberty Street (Naperville) showed gaps. The server log showed why: all three Overpass servers failed (502, 504, ReadTimeout), so the backup place search answered, and Nominatim returns at most 40 results, so the road was cut at exactly 40 parts.

Changes:
- **Tiled backup.** When the place search returns a full 40, the box is cut into four tiles and each is asked in turn (one request a second, Nominatim's rule). The parts are joined and repeated parts count once.
- **Partial warning.** If a tile is still full, or the town limits are used (no box to cut), the screen says the source may have left parts out and suggests "Road between two points".
- **More servers.** `overpass.kumi.systems` and `overpass.openstreetmap.fr` were added to the three Overpass servers (not tested from the build workspace: a server that fails is simply skipped).
- Not done yet: save a found road in our own database for next time; stop early when two servers have already failed with a server error.
