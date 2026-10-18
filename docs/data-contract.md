# Data contract, version 2

The additive [experimental exposure display contract](exposure-display.md) defines
explicit parcel assessment artifacts, complete-inventory server-side P90 summaries,
coverage, factor explanations and the fixed map scale. Geometry-only risk fields
remain null/unknown; exposure assessments are separate and optional.

## Pilot boundary

Okaloosa County is fixed to FIPS `12091`, timezone `America/Chicago`. API coordinates are WGS84 (EPSG:4326), `[longitude, latitude]`. The fixture loader checks county tags and coordinate validity. **It does not yet perform a county polygon intersection** and must not be used as an external-data import path without that check.

Fixtures contain six invented points. They are not parcels or building footprints. They are deliberately small enough for every teammate to read.

## Property adapter record

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable adapter identifier; demo IDs start `demo-` |
| `label` | string | Display label; do not use real owner names |
| `county_fips` | string | Must be `12091` |
| `longitude`, `latitude` | number | WGS84 point |
| `elevation_m` | number or null | Terrain elevation; real integration must specify vertical datum |
| `fema_zone` | string or null | Illustrative normalized FEMA code; unknown codes remain unknown |
| `waterway_distance_m` | non-negative number or null | Distance to a meaningfully connected waterway |

## Scenario record

`id`, `label`, `valid_from`, `valid_to`, `rainfall_6h_mm`, and `gauge_margin_m`.

Times are ISO 8601 UTC with `Z`; UI formats them in Central time (America/Chicago). Each fixture window uses one countywide rainfall and gauge value as an explicit simplification. The rainfall value represents total mm for that six-hour window. Gauge margin is `flood_stage_m - observed_stage_m`, using matching datum and units; negative means above the illustrative stage threshold.

## Scored GeoJSON

`GET /api/properties?scenario=peak` returns a FeatureCollection with `county_fips`, `mode`, `scenario`, `provenance`, `notice` and `features`. Each Point feature has stable `id`, label, county and `risk`:

```json
{
  "score": null,
  "band": "unknown",
  "factors": [],
  "missing": ["elevation_m"],
  "model_version": "illustrative-baseline-v1",
  "data_status": "incomplete"
}
```

Complete risk outputs contain five factors: `name`, original `value`, `weight`, and weighted score-point `contribution`. Scores are relative demo values, not calibrated probabilities. Preserve nulls in API and UI.

## WeatherNext scenario

`GET /api/properties?scenario=weathernext` is available only when a structurally valid imported snapshot is configured. The response mode is `mixed_forecast_demo`. The collection's `forecast` metadata includes connection/freshness status, exact source table, initialization, retrieval time, validity window, native resolution and statistic. Each point adds `forecast.status`, `rainfall_6h_mm`, `available_hours` and `native_cells_wkt`. Its non-rainfall inputs remain synthetic. Non-null scores report `data_status: mixed_demo`; missing/stale rainfall remains an unknown score.

The snapshot schema uses `schema_version: 1`, `model: WeatherNext 3`, `county_fips: 12091`, `native_resolution: 0.1 degree`, `statistic: ensemble_mean`, `units: mm_per_hour`, `source_table`, `init_time`, `retrieved_at`, `valid_from`, `valid_to` and `rows`. Rows contain `property_id`, `forecast_time`, `rainfall_1h_mm` and `native_cell_wkt`. The importer converts source meters to mm exactly once in SQL. It sums six hourly **means**, not marginal percentile values.

Hourly timestamps denote the end of each accumulation interval. The six timestamps must be start+1h through start+6h from one initialization. Missing/null steps produce unknown totals; duplicates or out-of-window steps invalidate the import. Each point ID must be in the curated fixture catalog. This is not an import route for arbitrary coordinates or external parcels.

## Browser H3 contract

`QuasarSpatial.aggregate` adds `h3_index`, `property_id`, `risk_band` and `risk_score` to a copy of each site feature. It returns occupied-cell GeoJSON with resolution 7, site/scored/unknown counts, maximum/mean score and a display band. The backend point contract remains independent of H3. All polygons use closed longitude/latitude rings. Unknowns are never zero-filled. Cell shapes may extend beyond the county; they do not establish geographic containment or forecast precision.

## Contract for future real adapters

Do not silently replace fixtures. Add an explicit data mode and source status. Every real adapter must retain source URL/record ID, retrieval time, observation/issue/valid times where relevant, CRS, vertical datum, units, license and transformation steps. Add authoritative county geometry validation, source-age limits, missing/stale states, and tests for outside-county records. Store only normalized county-filtered features in the scoring pipeline. Do not turn a centroid association into a claim of building-level inundation.

## LinuxONE snapshot bridge

The optional IBM-to-Vercel bridge serves only the named normalized snapshots in
[the bridge guide](data-bridge.md). The LinuxONE endpoint requires a bearer token
and an operator-provided HTTPS reverse proxy. Vercel reads snapshots only from
server-side Python code; the token is never returned to the browser. The bridge
preserves each file's source metadata and timestamps, then existing adapter
validation applies the normal county, schema, freshness, and missing-input rules.
An upstream failure is `unavailable`, and does not select synthetic rainfall.
Raw downloads, credentials, and property datasets are outside this contract.

## Isaias 2026 hourly replay (additive contract)

Scenario `isaias-2026` spans 2026-10-09T05:00:00Z through
2026-10-10T05:00:00Z inclusive (25 whole-hour departure times). `at` selects
the departure time; `preset` is `archived`, `plus-5`, or `plus-10`; `mode` is
`archive` or `what_if`. Non-archived presets and road/destination overrides
require what-if mode. UTC is canonical; display timezone is America/Chicago.
Each score uses rainfall intervals ending at at+1h through at+6h from the
latest eligible initialization (not newer than the replay time, at most 12h old).
If supplied, published_at must also be no later than at. Missing publication
times are explicitly initialization-based reconstructions, not as-issued proof.
Archived imports retain real retrieval time, but freshness is evaluated against
the replay clock, never today's date. Current WeatherNext v1 freshness is unchanged.

`GET /api/scenarios` adds replay metadata and source status. Existing scenarios
remain unchanged. `GET /api/properties?scenario=isaias-2026&at=...&preset=archived&mode=archive`
returns the existing scored GeoJSON with `replay` metadata, factor-level
provenance and a six-hour forward validity window. Static site and gauge inputs
remain fictional; incomplete/invalid forecast data is never zero-filled.

`GET /api/timeline?site=demo-001&at=...&preset=archived&mode=archive` returns all
25 hourly risk objects, their rainfall provenance and nullable change from the
preceding score. Nulls are chart gaps. `POST /api/routes` accepts a JSON object
with `site`, `at`, `preset`, `mode`, and optional `roads` / `destinations` maps.
Road states: `open`, `closed`, `unknown`; destination values: booleans. Overrides
are restricted to known IDs (max 100 road and 3 destination overrides; 16KB body).
The equivalent GET endpoint supports selection without overrides. Both return
county, mode, preset, at, source provenance, graph layers, selected route and
unrestricted comparison; statuses distinguish unavailable data from no route.

Historical WeatherNext files use schema_version 2 and kind `historical_forecasts`,
with county/model/grid/statistic/units/table/retrieval metadata and `runs`.
Each run contains init_time, optional published_at, and hourly rows with
property_id, forecast_time, rainfall_1h_mm, native_cell_wkt. All rows must be
curated points, finite nonnegative mm or null, and strictly after initialization.
Duplicates invalidate that run, producing unknown rainfall rather than falling
back to an older run. Source files, checksums and import commands remain local.

Road graph geometry is county-contained EPSG:4326, sourced from Okaloosa street
centerlines. Topology, two-way traversal, 30km/h speeds, access connectors,
restrictions and all three destinations are exercise assumptions, not navigation
or shelter-opening evidence. Whole segments are checked against county rings,
including holes and concavities. No H3 or property score determines passability.

## Reports and BI exports (additive contract)

`GET /api/reports?scenario=baseline|heavy-rain|peak|weathernext` returns the shared
analysis report with `generated_at`, scenario, summary, provenance, forecast
metadata and `rows`. Each row includes coordinates, site/scenario keys, relative
score, band, missing input names and available factor contributions. It also
repeats county, mode, input status, window validity, model version, generation
and forecast initialization/import times, source table, statistic and native
resolution. Rainfall is mm per six hours; coordinates are EPSG:4326. The original
property API and scoring are unchanged. Unknown scores have no factor rows.

`scenario=compare` returns only the three synthetic windows, a `scenarios` array
of scenario/summary pairs, and 18 rows (six fictional sites per window). It has
no single scenario/summary. All rows share one generation timestamp. The Python
`compare_scenarios()` helper continues returning a list for notebook callers.

`GET /api/exports?scenario=...&format=csv|geojson|zip` defaults to baseline CSV.
Responses use attachment filenames `quasar-SCENARIO.EXT`, `Cache-Control: no-store`
and the matching CSV, GeoJSON or ZIP MIME type. Invalid county, scenario and
format return JSON errors, not successful attachments. The exports invoke only
local shared analysis; they never query BigQuery, load notebook code or expose
configuration credentials. A missing/invalid WeatherNext snapshot is an error;
a structurally valid stale/incomplete snapshot retains unknown rainfall/scores.

CSV has one row per `(property_id, scenario)`. Numeric nulls are empty cells;
`missing` is semicolon-separated. Text uses CSV quoting and potentially executable
spreadsheet text is prefixed with an apostrophe; negative numeric coordinates
remain numeric. GeoJSON has the same flat fields with JSON nulls and a missing
array. Feature IDs are `property_id:scenario`, so compare features remain unique.
Compare maps repeat point coordinates; filter scenario before mapping.

ZIP includes `sites.csv`, `factors.csv`, `sites.geojson`, `metadata.json` and
`README.txt`. Factors relate on BOTH property_id and scenario, with one row per
available scoring factor. An inner join drops unknown sites, and a flattened
factor join repeats site counts: prefer a relationship or left join with distinct
site/window counts. Metadata lists columns and meanings, units, CRS, timezones,
source terms, transformation notes, scenario summaries and forecast provenance.
All bundle files derive from the same report snapshot. Keep nulls distinct from
zero; score averages exclude unknown sites and an all-unknown average is null.

App reports default to baseline and provide scenario overview, synthetic-window
comparison, and site explanation. Site selection affects only the explanation;
downloads contain all sites in the selected window or comparison. Every report
and export carries synthetic/mixed status and limitations. Printable reports
retain charts, tables, validity/generation/source timestamps and official-guidance
notes; they link to the interactive map rather than capturing a basemap. Print
uses the browser's Print / Save as PDF. BI tools refresh by manual file replacement;
no hosted embedding, automated refresh or native workbook generation is included.


## County grid and parcel browsing

### Persistent inspection (additive)

`GET /api/parcels/manifest` returns county, source mode/URL, dataset and boundary
versions, CRS, retrieval time and geometry freshness. Indexed dataset versions
include the parcel snapshot and cell-index checksums. Live GIS versions expire
at the next UTC day; an ID inventory alone does not version changed shapes.
The browser checks this manifest on entry and after 15 minutes before reuse.
IndexedDB retains validated pages/progress for seven days, up to 100 MiB by LRU;
failed checks preserve cached geometry with an explicit unavailable-source label.
HTTP responses remain private/no-store; the application cache stores no credentials.

`GET /api/parcels/{integer-id}/context?inventory_id=...` and
`GET /api/cells/{h3-id}/summary?inventory_id=...` read the completed inspection
artifact configured by `QUASAR_PARCEL_CONTEXT_DIRECTORY`. Its final manifest,
SQLite checksum, county, parcel snapshot and boundary must match the indexed
inventory. Responses keep `risk_score: null` and `risk_band: unknown`.
Context contains descriptive `inputs`, `forecast_overlaps`, artifact version and
`provenance`. Cell summaries support R4–R7 and count distinct indexed parcel IDs,
with terrain/FEMA coverage counts. Missing artifacts return explicit unavailable
states, never zero coverage. Invalid IDs/scope return 400; source failures 502.
The same server-only parcel authentication/proxy applies to all these endpoints.

Offline preparation copies verified descriptive records and computes positive-area
native forecast overlaps in EPSG:26916, keeping native IDs, geometry and overlap
fractions. Multiple cells remain separate. Browser rainfall comes only from the
selected scenario's existing `weather_cells`, matched by native ID and geometry;
stale/missing values stay null. Synthetic exercise rainfall is never assigned to
real parcels. No runtime GIS dependency, cloud query or score calculation is added.

`GET /api/county` returns a WGS84 GeoJSON collection with the single authoritative
Census TIGERweb `GEOID=12091` boundary, source URL, retrieval time, CRS, units,
license and processing notes. It is cached in memory for the UTC day. The browser
fills all intersecting county cells at H3 resolutions 4, 5, 6 and 7, including
coastal slivers and islands. Hexagons can extend beyond the dashed county outline.
Zoom thresholds are 6.75, 8.5 and 10.75, matching TrialSmiles. No site-derived
score exists for unoccupied cells; their score stays null. In rainfall mode the
grid is neutral and is not a forecast layer.

`GET /api/parcels?ring=<JSON closed lon/lat R7 ring>&offset=0` queries the fixed
Okaloosa parcel GIS layer for intersecting polygons. Only `OBJECTID`
and geometry are requested; owner, address and mailing fields are excluded. Every
complete polygon is checked against the authoritative county geometry, including
edges, concavities and holes. Boundary-crossing polygons are excluded rather
than represented as wholly inside the county. This is an intersection inventory,
so a parcel can appear in adjacent cells. It is not a count of homes or units.

Responses contain `features`, `status: ready`, `source_total` (raw GIS matches),
`checked_count`, page-local `excluded_count`, `next_offset` (null on completion),
and `inventory_id`. Continue with the returned offset and inventory ID until
null; there is no UI row cap. A changed ID inventory or incomplete source page
fails explicitly. Each page has at most 100 source records. IDs are cached for
five minutes in a bounded in-memory cache; each worker may reacquire them.
County validation is authoritative geometry validation, not trust in a supplied
FIPS or an envelope. Page/source failures are HTTP 502 with `status: unavailable`,
never successful empty inventories. Bad requests and non-pilot FIPS are HTTP 400.
The browser retains completed late pages in cache without changing the current
selection, labels partial loads and offers retry. Only a completed load claims
all source matches were checked. Lists show 50 searchable rows per page without
limiting the complete inventory.

Parcel properties are `parcel_id`, `county_fips: 12091`,
`risk_score: null`, and `risk_band: unknown`. Metadata includes source/terms URLs,
retrieval/inventory/boundary retrieval times, CRS `EPSG:4326`, degrees, license
notes and processing steps. No forecast, terrain, FEMA or gauge joins are implied.
Raw/derived research downloads stay in ignored `data/raw/` / `data/processed/`.
Server runtime reads remain read-only. The browser persists public geometry and
pagination in IndexedDB under the bounded inspection cache policy above.

Separate offline descriptive-input artifacts are defined in
[parcel input preparation](parcel-inputs.md). Their terrain/FEMA/reference-distance
fields enter the opt-in inspection endpoints above, separately from geometry, and
never enter the scoring pipeline. A complete artifact requires
its final manifest; every research record retains null risk scores and explicit
coverage/unknown states.


## Okaloosa county weather (schema 3)

County snapshots have `schema_version: 3`, county FIPS `12091`, kind `current_county_forecasts` or `historical_county_forecasts`, source table/model, native resolution/statistic/units, actual retrieval time, county geometry, `native_cells` and initialization-grouped `runs`. Each native cell retains ID, original WKT and GeoJSON geometry. IDs are SHA-256 of source WKT. Hourly rows reference the cell ID in `property_id`; `rainfall_1h_mm` is null or a nonnegative finite number. Duplicate cell/hour/run rows invalidate the snapshot. Current snapshots additionally carry `init_time`, `valid_from` and `valid_to`; historical ones carry the Central-time replay bounds.

The importer selects native cells by county intersection; cells can extend beyond the county. The runtime associates the six fictional points locally using source polygon coverage and rejects ambiguous overlapping assignments. It exposes native rainfall as additive `weather_cells` GeoJSON on property collections, with per-cell availability and six-hour mm. Score records remain six fictional sites; county parcels stay unscored. H3 grids do not substitute for native forecast polygons. Existing schemas 1/2 remain supported for the configured county. Miami-Dade FIPS 12086 files are rejected.

## Retained current-forecast playback (additive)

### Source-only Data tab

`GET /api/data/weather` reads the configured schema-3 current county snapshot
without assigning rainfall to fictional sites or computing scores. It returns
`county_fips`, `timezone`, `units` (`mm / 6h`), `generated_at`, `status`,
`default_index` and `frames`. Each frame has `at`, `valid_to` and `rows`, with
`native_cell_id`, `rainfall_6h_mm`, `available_hours` and per-cell `status`.
Successful imports retain `init_time`, `retrieved_at`, `source_table`,
`native_resolution`, `statistic` and `expires_at`. Freshness and retained-window
rules match map playback, including the original snapshot expiry. Null/missing
hours stay unavailable; valid zero stays zero. Missing imports, bridge errors,
invalid data and legacy six-site imports produce explicit states with no frames.
No cloud query, property join or scoring is performed.

The existing parcel manifest adds optional `parcel_count` for indexed inventories.
It must be a nonnegative integer or null. Older remote manifests may omit it;
the UI displays unknown rather than zero. Live GIS browsing has no countywide
verified count. Counts reflect county-validated parcel geometry, not homes or
flood-risk coverage. Existing authentication and county checks still apply.

The Data tab CSV contains all native cells in the selected window, independently
of search/status filters, with source/validity metadata and explicit units.
Unknown rainfall is blank. Charts count input availability; mean rainfall is an
unweighted mean of available native cells, not an area-weighted county estimate.
Fictional scenario reports and their existing exports retain their own labels.

### Map playback

`GET /api/weather/timeline` reads one configured WeatherNext snapshot. It never
queries BigQuery or starts an import. The response has `county_fips`, `timezone`,
`units` (`mm / 6h`), `status`, `default_index`, and `frames`. Each frame has `at`
(UTC whole-hour window start) and `collection` with the existing scored map
FeatureCollection structure, including native `weather_cells`. The default
properties/report endpoints retain their original six-hour window and behavior.

Schema-3 current county imports provide one frame per hourly start from the
initialization through the last retained hour minus six hours. Thus 18 retained
hours yield 13 starts. Interior missing/null hours produce unavailable values;
duplicates or invalid rows invalidate the timeline. Legacy six-hour imports
provide a single frame. A missing snapshot returns `not_configured`; bridge
failure returns `unavailable`; invalid input returns `invalid`. Those responses
have no frames and a message. `ready`, `incomplete`, and `stale` snapshots retain
per-frame/per-cell states rather than treating missing rainfall as zero.

County responses also preserve `init_time`, `retrieved_at`, `source_table`,
`native_resolution`, `statistic`, `expires_at`, and a notice. `default_index`
selects the imported window start. `expires_at` is the earliest original window
expiry, initialization plus 12 hours, or retrieval plus two hours. Every request
uses real time for freshness, independent of the selected frame. Once the original
snapshot is stale, all frames remain stale/unscored even if their validity extends
into the future. Playback requests refresh this local endpoint; source metadata
and all frames in each response come from the same loaded snapshot.

Search geocodes are temporary map locations, validated against the authoritative
county polygon. They do not enter property datasets, scores, exports or storage.
The browser sends queries directly to Mapbox using only the public `pk.` token.
