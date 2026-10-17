# Mechanisms and implementation reference

## Runtime structure

One Python process serves a fixed set of static assets and JSON/download endpoints. It uses `ThreadingHTTPServer` and standard-library modules, with no third-party Python runtime dependencies. An optional read-only SQLite store holds county parcel geometry and H3 memberships. There is no scoring database, background queue, scheduler, or message provider.

```text
Committed fictional sites + synthetic windows
                       |
Explicit imports       |        Optional historical preparation
  BigQuery CLI         |          NHC context + county roads
       |               |                    |
  Local forecast / historical JSON          Local JSON graph/context
       |               |                    |
       +----> adapters + pipeline <---- replay / routing
                       |
               scoring.score
                       |
             GeoJSON + shared analysis
                  /             \
       Python HTTP API       CLI / optional notebooks
             |
  React shell + JavaScript controllers
       /             |                \
  Mapbox / H3    Timeline / routes     Reports / exports
```

Imports and source preparation are deliberate commands. Browser requests read local artifacts; they never run BigQuery or public-data acquisition. Mapbox's SDK, style, and tiles are separate browser network dependencies.

## Source ownership map

| Component | Primary implementation | Responsibility |
| --- | --- | --- |
| Fixed scope and local settings | `quasar/config.py` | County, timezone, model version, non-executing `.env` loader, public Mapbox settings |
| Scoring | `quasar/scoring.py` | Required inputs, normalization, contributions, bands, null behavior |
| Main pipeline | `quasar/pipeline.py` | Fixture loading, scenario selection, mixed forecast association, GeoJSON, sorting |
| Current forecast adapter | `quasar/adapters/weathernext.py` | Query construction, capped CLI import, schema and freshness checks |
| Historical import/replay | `quasar/adapters/historical.py`, `quasar/replay.py` | Archived runs, temporal selection, forward windows, timeline, provenance |
| County geometry | `quasar/geometry.py` | Point/line containment and approximate geodesic lengths |
| Routing | `quasar/routing.py` | Graph validation, route search, simulated conditions, overrides |
| HTTP server and launchers | `quasar/server.py`, `quasar/__main__.py`, `quasar/wifi.py` | Explicit routes, JSON validation, localhost service, optional team HTTPS gate |
| Shared analysis and exports | `quasar/analysis.py`, `quasar/exports.py` | Report rows, summaries, serialization, BI bundle |
| Notification simulation | `quasar/notifications.py` | Opt-in checks and in-memory preview text with `sent_count: 0` |
| NWS point adapter | `quasar/adapters/nws.py` | Explicit official point query, raw response, retrieval time, propagated errors |
| React UI | `frontend/` | Application shell, dashboard markup, reports, styling |
| Browser controllers | `quasar/static/app.js`, `replay.js`, `spatial.js` | Data loading, map layers, selection, timeline controls, H3 aggregation |
| Acquisition | `scripts/acquire_local_data.py`, `scripts/prepare_isaias.py` | Research downloads, manifests, advisory extraction, graph curation |

The [data contract](data-contract.md) governs fields. This guide explains how those fields are produced.

## Scoring mechanism

The model identifier is `illustrative-baseline-v1`. No training procedure produces its weights; they are demonstration parameters.

For a value `x`, define `clamp(x) = max(0, min(1, x))`.

| Factor | Normalized value | Weight | Maximum points |
| --- | --- | --- | --- |
| Six-hour rainfall | `clamp(rainfall_6h_mm / 120)` | 0.35 | 35 |
| Terrain elevation | `clamp((10 - elevation_m) / 10)` | 0.20 | 20 |
| FEMA category | Zone lookup below | 0.20 | 20 |
| Waterway distance | `clamp(1 - waterway_distance_m / 1000)` | 0.10 | 10 |
| Gauge margin | `clamp((1 - gauge_margin_m) / 1.5)` | 0.15 | 15 |

The zone lookup is V/VE → 1.0; A/AE/AH/AO → 0.8; X → 0.2. Other codes are unknown. It does not distinguish FEMA X subtypes or fully represent regulatory mapping.

Each contribution is `round(normalized_value * weight * 100, 3)`. The score is the sum of those rounded contributions, rounded to one decimal. The band uses that final score:

| Final score | Band |
| --- | --- |
| Below 35 | `lower_relative` |
| 35 to below 65 | `moderate` |
| 65 or above | `elevated` |
| Missing required factor or unsupported zone | `unknown`, score null |

Numeric inputs must be finite numbers; booleans are rejected. Rainfall and waterway distance cannot be negative. Negative elevation and gauge margin are allowed by the score function and clamped through their formulas. Numeric strings are not scoring inputs, even though the current forecast adapter can normalize numeric rainfall strings before scoring.

Any missing required factor returns no score and an empty factor list. The code does not renormalize remaining weights or calculate a partial score. Missing factor names survive in `risk.missing`.

### Worked fictional example

For `demo-001` in the `peak` fixture: rainfall is 115 mm, elevation 1.2 m, zone AE, waterway distance 90 m, and gauge margin -0.2 m.

| Factor | Contribution, points |
| --- | --- |
| Rainfall | 33.542 |
| Elevation | 17.600 |
| FEMA | 16.000 |
| Waterway distance | 9.100 |
| Gauge margin | 12.000 |
| Sum before final rounding | 88.242 |

The resulting illustrative score is **88.2**, band `elevated`. This is a calculation from invented fixture values. It is not 88.2% flood probability, a water depth, or validation of the chosen weights.

The model does not represent drainage connectivity, rainfall-runoff dynamics, canal controls, tides, surge, soil saturation, building floors, or interactions between these factors. Contributions explain the arithmetic; they do not establish physical causation.

## Scenario and GeoJSON pipeline

`pipeline.collection()` defaults to `baseline`. It loads the chosen scenario and fictional catalog, checks fixed county identity and valid WGS84 coordinates, assembles required inputs, and calls `score()` for each site. Features sort by descending score with unknowns last.

For `weathernext`, the adapter's per-site rainfall replaces only the rainfall factor. Gauge margin is fixed at 1.2 m; other site factors are unchanged. Complete risk objects are marked `mixed_demo`, while the collection is `mixed_forecast_demo`.

For `isaias-2026`, the pipeline delegates to `replay.collection()`, which still calls the same scoring function. Replay-only parameters on ordinary scenarios are rejected. County checks in the fixture path validate tags and coordinate ranges, rather than county polygon containment.

## Forecast import and local reads

The current importer generates parameterized SQL and invokes the authenticated `bq` CLI through a subprocess. It validates the expected precipitation table name, project/location identifiers, whole-hour window, and positive byte cap. It defaults to a dry run with a 1,000,000,000-byte cap. `--execute` authorizes that invocation to query and save a snapshot; `--print-query` prints SQL without authentication or cloud calls.

Current imports select one initialization and six hourly means for six coordinates. Historical imports select multiple initializations and normalize them into a separate run archive. Both use local JSON and atomic replacement for their normalized output, so validation failure does not replace a previously usable normalized snapshot.

The current loader checks its configured file and recalculates freshness when read. Replay reads its own file against a historical clock. Neither mechanism runs an automatic refresh. See the [data guide](data-guide.md#current-weathernext-path) for exact completeness/freshness rules and [integration setup](integrations.md) for commands.

## Replay and timeline

Selection accepts a whole UTC hour from `2026-10-07T00:00:00Z` through `2026-10-11T00:00:00Z`. Presets are `archived`, `plus-5`, and `plus-10`; modes are `archive` and `what_if`. Synthetic increments require `what_if`.

For each hour, replay selects an eligible run, obtains the next six hourly values, and scores the selected site using fictional static inputs and gauge margin. Timeline output includes all 97 hours, each risk object, rainfall provenance, and change from the previous score. A change is null if either the current or preceding score is null; chart gaps are retained.

The browser requests property scores, a selected-site timeline, and route output together. A request counter prevents an older response from overwriting a newer selection, and timestamp checks prevent different replay hours from being committed together. This coordinates browser selection; it is not a transaction across local files if an importer replaces them between server requests.

Playback advances at most one hour per second as requests complete and stops at the last hour. Reset restores hour zero, archive mode, archived rainfall, and empty overrides. The browser filters prepared NHC advisories by original issue time relative to the selected hour.

## Routing mechanism

`routing.validate_graph()` checks county/version, provenance, node positions, edge identity/endpoints, complete line containment, connectivity declarations for the six sites, and three exercise destinations. `geometry.line_covered()` splits line segments at county-ring intersections and checks the resulting intervals, catching paths that leave a concave polygon or cross a hole despite having inside endpoints.

The graph contains sourced road shapes and explicitly classified simulated access lines. Runtime graph reads are cached using resolved file path, modification time, and size. A missing/invalid graph returns `network_unavailable`.

The search uses Dijkstra's algorithm: expand the least costly known path until the reachable graph has been explored. Edges are treated as two-way and traversed at 30 km/h. Path ordering uses travel time, distance, and stable edge IDs; destination ties use destination ID. With uniform speed, minimizing modeled time also minimizes modeled distance. Closed and unknown segments are excluded.

| Mode/phase | Road and destination assumptions |
| --- | --- |
| Archive | Roads unknown and destinations unavailable; no historical route is asserted |
| What-if, hours 0–23 | Segments assumed open and exercise destinations available |
| What-if, hour 24 onward | Attempts to close a baseline road segment that has an alternative path |
| What-if, hour 48 onward | Also makes the original baseline destination unavailable |
| What-if, hour 72 onward | Closes every segment |

Manual what-if overrides apply after those phase defaults, so an explicit override can reopen a segment or destination. Overrides accept up to 100 known road IDs and three known destination IDs; unknown roads/destinations are rejected. Road states are `open`, `closed`, or `unknown`; destination availability must be boolean.

The response includes the constrained route, unrestricted comparison, network/destination layers, excluded roads, and change indicators. Status distinguishes `ready`, `no_route`, `network_unavailable`, and `historical_conditions_unavailable`. `no_route` describes the supplied exercise graph and restrictions; it is not proof that no real-world escape route exists.

Restrictions apply at departure time. The model does not predict changing conditions during travel, traffic, turns, one-way rules, capacity, shelter eligibility, or water passability. Site scores and H3 cells never set road closure states.

## Browser map and H3

React provides the shell and dashboard markup; the existing JavaScript controller loads data and manages Mapbox. `spatial.js` assigns site coordinates to H3 resolution 7 and returns a copied point collection plus occupied-cell summaries. The county browsing layer fills every cell intersecting the authoritative Census boundary at zoom-dependent resolutions 4–7. All cell resolutions open the adapted TrialSmiles summary panel; a separate action zooms to the next level. R7 loads all intersecting county-validated parcel polygons in pages with persistent browser caching, resumable progress and a searchable list of 50 rows per page. Optional verified inspection inputs and native forecast overlaps populate descriptive context; overall scores remain unknown. A parcel opens its detail panel; close/back preserve the cell context. Real parcels remain unscored, and the rainfall browsing grid stays neutral. See the county/parcel API contract in `data-contract.md`.

Cell properties include site count, scored count, unknown count, maximum score, and mean score. Unknowns are excluded from numeric statistics. Maximum score determines the displayed band, so a mean does not hide a high-scoring sample. An all-unknown cell has null statistics and an unknown band.

H3 boundaries are closed GeoJSON rings in longitude/latitude order. H3's indexing call receives latitude/longitude, so that conversion is explicit. Cells are not county-clipped, flood extents, continuous hazard surfaces, or weather downscaling.

Without a working map token, SDK, WebGL, or tiles, tabular site details remain the intended fallback. Reports also work without a Mapbox token. Map SDK resources still depend on browser network access.

## Reports and exports

`analysis.scenario_report()` calls the application collection and flattens site results with source metadata. `analysis.report('compare')` creates a single generation timestamp across the three synthetic windows. The notebook helper `compare_scenarios()` retains its list-of-rows interface.

Reports support `baseline`, `heavy-rain`, `peak`, `weathernext`, and `compare`; they do **not** support `isaias-2026`. The report view offers scenario overview, synthetic comparison, and site explanation. Selecting a site changes the explanation, while downloads retain every site in the selected scenario/comparison.

`exports.export()` serializes one report snapshot as CSV, GeoJSON, or ZIP. CSV quotes text, preserves numeric blanks, and prefixes potentially executable spreadsheet strings with an apostrophe. GeoJSON preserves JSON nulls and uses `property_id:scenario` feature IDs. ZIP includes site rows, available factor rows, GeoJSON, metadata, and import instructions.

The UI uses browser printing for PDF output. Exports do not execute notebooks, query the cloud, send messages, or produce native Power BI/Tableau workbooks. Detailed joins, units, and null policies are in the [export contract](data-contract.md#reports-and-bi-exports-additive-contract).

## Notifications and official alerts

The preview function requires literal `opt_in=true`, 1–100 string site IDs, and channel `email` or `sms` (default `email`). It deduplicates IDs and creates text only for elevated scores. Results remain in memory with `mode: simulation`, `delivery_status: simulated_only`, and `sent_count: 0`.

The UI offers previews only in `synthetic_demo`. The backend specifically rejects `weathernext`, but currently lacks a synthetic-scenario allowlist; direct replay requests need an explicit exclusion. This is a documented implementation gap, not permission to use previews with imported data.

The dashboard's official-alert endpoint returns `not_connected` and an empty list with a warning that this is not an all-clear. Separately, the CLI NWS client requests active alerts for one curated point with an identifying user agent, timeout, response-size limit, raw GeoJSON, and retrieval time. It propagates failures and rejects unhandled pagination. It lacks the coverage/freshness handling needed for a countywide feed.

## API reference

| Method and path | Parameters/defaults | Result |
| --- | --- | --- |
| GET `/health` | Optional county scope | Process `ok`, fixed county, default demo mode; no upstream-readiness proof |
| GET `/api/config` | Optional county scope | Notices, timezone, public Mapbox settings, H3 resolution |
| GET `/api/scenarios` | Optional county scope | Three fixtures, historical descriptor, optional structurally valid current forecast |
| GET `/api/properties` | `scenario=baseline`; replay accepts `at`, `preset`, `mode` | Scored GeoJSON with mode/provenance |
| GET `/api/weather/status` | None | Current snapshot metadata/status without internal per-site records |
| GET `/api/timeline` | Required `site`; optional replay selection | 97-hour selected-site timeline |
| GET `/api/routes` | Required `site`; optional replay selection | Exercise route/status without override maps |
| POST `/api/routes` | Required JSON `site`; optional `at`, `preset`, `mode`, `roads`, `destinations` | Exercise route with validated overrides |
| GET `/api/replay/context` | None | Prepared advisory metadata or `not_imported` |
| GET `/api/reports` | `scenario=baseline` | Shared report; supports `compare` |
| GET `/api/exports` | `scenario=baseline`, `format=csv` | CSV, GeoJSON, or ZIP attachment |
| GET `/api/official-alerts` | None | Explicit disconnected status |
| POST `/api/notifications/preview` | JSON with site IDs, opt-in, channel, scenario | In-memory simulation |

GET requests reject duplicate query parameters and any supplied `county_fips` other than `12091`. Unknown routes return 404. Validated value errors return JSON 400 responses. POST bodies must be JSON objects with content type `application/json` and length 1–16,384 bytes; wrong type returns 415 and invalid length returns 413. Unsupported methods are not a general API extension point.

JSON responses and downloads use `Cache-Control: no-store`; JSON serialization rejects NaN. Static assets are allowlisted, so arbitrary repository files and `.env` are not served. There is no versioned public API guarantee or comprehensive production exception/observability layer.

## Configuration and build

| Setting | Default or rule |
| --- | --- |
| `MAPBOX_PUBLIC_TOKEN` | Empty; only whitespace-free `pk.` values accepted; deliberately browser-visible |
| `MAPBOX_STYLE` | `mapbox://styles/mapbox/light-v11`; requires a Mapbox style URL |
| `QUASAR_WEATHERNEXT_FILE` | Unconfigured unless explicitly set |
| `QUASAR_REPLAY_FILE` | `data/processed/isaias-2026.json` |
| `QUASAR_ROUTES_FILE` | `data/processed/evacuation-network.json` |
| `QUASAR_WIFI_PASSWORD` | Optional launcher input; otherwise interactive prompt |
| `SHADCNBLOCKS_API_KEY` | Development registry access; not returned by app configuration |

The startup loader reads literal `KEY=VALUE` lines from `.env`; it performs no shell expansion. Existing environment variables take precedence. Direct helper calls do not automatically load `.env`; use the documented entry points or configure their environment explicitly.

The default launcher binds `127.0.0.1:8000`. The Wi-Fi launcher detects the macOS Wi-Fi address or accepts an explicit IPv4 address. It uses HTTPS and a shared passphrase entered on the Quasar team access page. A signed, HTTP-only session cookie gates every route. The password must have at least 12 non-padding characters, at most 256 total characters, and no newline/NUL. It generates a temporary local certificate, prints a fingerprint for comparison, and removes temporary certificate/key files on normal exit. This shared gate is temporary team access, with no individual accounts or audit trail.

Vite compiles `frontend/main.tsx` into committed `quasar/static/ui/app-shell.js` and CSS. The Python container serves those assets without Node or Jupyter. Its image uses Python 3.12 slim and UID/GID 10001. Running a container on x86 does not verify the image, dependency choices, or service on Linux `s390x`.

## Verification boundaries

The repository contains tests for scoring/unknowns, forecast validation, replay selection, county holes/concavities, routing, API errors, exports, HTTPS gating, browser controller behavior, reports, and H3. These use synthetic inputs and mocks; they are software checks, not observed-outcome model evaluation or visual acceptance.

Before proposing a merge, the repository requires:

```sh
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
npm test
```

Frontend source changes also need `npm run build` and review of generated assets; CI checks they are current. Notebook changes follow the [clean/execute workflow](../notebooks/README.md#clean-reproducible-notebook-commits). The existence of those tests does not imply they ran during a documentation update. Isaac reviews visual and print layout.

For future work, use the [roadmap](improvement-roadmap.md); for project scope, read the [premise](app-premise.md).
