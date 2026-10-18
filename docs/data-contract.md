# Application data contract

Optional promoted mapping-proxy model metadata, forecast provenance and signed
raw-model diagnostics extend schema-1 assessments additively; see
[the exposure additions](exposure-display.md#optional-modeling-fields-schema-1-additive)
and [offline modeling](modeling.md). Legacy assessment factors and unknown semantics
remain unchanged; signed attribution is separate from nonnegative index factors.

Only Okaloosa County FIPS `12091` is supported. Source initialization, validity,
retrieval time, native resolution and units remain part of every forecast view.
Unknown is distinct from zero. All application data comes from county sources;
o public endpoint substitutes fictional sites or invented inputs.

## Native forecast map and playback

`GET /api/weather/timeline?source=current|archive` reads one configured schema-3
county snapshot. Defaults to `archive`. The application exposes only the Isaias archive; explicit
`source=current` API reads remain supported for offline integration compatibility. Other selectors, presets and what-if
parameters are rejected. Missing, invalid, disconnected and legacy site-only
imports return explicit status, a message and no frames.

The response contains `county_fips`, `source`, `timezone`, `units` (`mm / 6h`),
`status`, `default_index`, source metadata and `frames`. Each frame contains `at`
and `collection`. The collection has no site features (`features: []`), mode
`county_forecast` or `county_archive`, a scenario validity window, `forecast`
metadata, and native polygon GeoJSON in `weather_cells`. It contains no fixture
scores, terrain, gauge margins or synthetic rainfall increments.

Current imports yield one forward six-hour frame per retained hourly start.
Eighteen retained hours yield 13 frames. Expiry is the earliest original validity
end, initialization plus 12 hours, or retrieval plus two hours. Real-time expiry
applies to every frame, including later slider positions. Stale frames retain
geometry/metadata with null rainfall. Missing/null hours remain incomplete;
duplicate, negative and invalid inputs fail validation. Valid zero stays zero.

Archive imports yield 25 positions from October 9 midnight through October 10
midnight Central. They use archived forecasts available at each reconstruction
clock, retaining per-cell initialization and publication constraints where known.
They are not historical rainfall observations and never use what-if additions.

`GET /api/data/weather?source=archive` projects this shared archive pipeline into native-cell
rows for the Data tab, without geometry or scoring. Frames contain `at`,
`valid_to`, and rows with `native_cell_id`, `rainfall_6h_mm`, `available_hours`
and `status`, retaining the selected initialization per frame and cell. Existing county/inventory checks remain in force.

## Reports and downloads

`GET /api/reports?source=current|archive&frame=N` returns source metadata, status,
selected frame index, available `windows`, source collection and native-cell rows.
The default source is `archive`. Frame defaults to
the imported default. No available source yields no rows or collection.
`GET /api/exports` accepts the same selectors plus `format=csv|geojson|zip`.
CSV retains source/validity metadata and units; unknown rain is blank. GeoJSON
retains native cell geometry. ZIP contains both formats and provenance JSON.
All formats are based on one loaded snapshot. Unsupported selectors fail with
400; unavailable sources cannot produce a replacement download.

## Retired application endpoints

`/api/scenarios`, `/api/properties`, `/api/timeline`, `/api/routes`,
`/api/replay/context`, and POST `/api/notifications/preview` return 410.
Offline research adapters and synthetic test fixtures are separate from the
application contract. `/health` and `/api/config` identify `county_sources`.
Health status alone does not establish data readiness.

## Public application, private source credentials

The hosted app, source tables, reports and downloads are public. No team password,
sign-in form or session cookie is required. Only the application route/asset
allowlist is served; raw databases, source files, `.env` and workspace files are
not public. LinuxONE snapshot and parcel endpoints still require server-to-server
authentication. No Google, bridge or parcel credential is sent to browsers.

## Authenticated LinuxONE reads

Vercel reads allowlisted snapshots at `/bridge/v1/snapshots/*` with the private
bridge token and parcel APIs with `X-Quasar-Parcel-Token`. Secrets stay server-side.
Errors never cause fallback to a different dataset. See `real-data-rollout.md`
for service/proxy activation and artifact checks.

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
fractions. Multiple cells remain separate. Parcel inspection rainfall comes only from the
selected scenario's existing `weather_cells`, matched by native ID and geometry;
stale/missing values stay null. Synthetic exercise rainfall is never assigned to
real parcels. No runtime GIS dependency, cloud query or score calculation is added.

`GET /api/county` returns a WGS84 GeoJSON collection with the single authoritative
Census TIGERweb `GEOID=12091` boundary, source URL, retrieval time, CRS, units,
license and processing notes. It is cached in memory for the UTC day. The browser
fills all intersecting county cells at H3 resolutions 4, 5, 6 and 7, including
coastal slivers and islands. Displayed hexagons and the selected-cell outline are clipped to the authoritative
county polygon, retaining holes and islands. H3 IDs and parcel membership remain unchanged.
Zoom thresholds are 6.75, 8.5 and 10.75, matching TrialSmiles. No site-derived
score exists for unoccupied cells; their score stays null.

In rainfall mode the H3 grid is the only weather surface. A browser geometry join
intersects each clipped hex with the imported native forecast polygons. Boundary-only
contacts are excluded. The hex color is the **maximum** overlapping six-hour
forecast, only when the geometry is fully covered and every overlapping native cell
has a finite, nonnegative, ready value. Otherwise the fill remains transparent.
The inspector retains the individual native values, their range, initialization,
import time, source resolution and units. It requires no prepared parcel artifact.
Geometry joins are cached per grid and native ID/geometry signature; every hour
reads new rainfall, and a failed source reload clears colors. Native square outlines
are not drawn. H3 does not increase forecast resolution, and the color is neither
an area-weighted mean nor a parcel estimate. The browser uses the pure-JavaScript
`polygon-clipping` library bundled in committed UI assets; Python/GIS runtime
requirements are unchanged. Existing API payloads and exports retain native geometry.

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

The server-only parcel proxy forwards the validated R7 `ring`, `cell`, `offset`
and optional `inventory_id` together. The indexed host applies the same request
validation before reading stored memberships; omitting the ring rejects the
request before any parcel page is read. A replacement inventory invalidates
in-flight and displayed inspection inputs. A selected parcel is relinked only
after its ID appears in the replacement geometry page; otherwise the inspector
returns to the cell until a parcel is selected from that inventory.

Separate offline descriptive-input artifacts are defined in
[parcel input preparation](parcel-inputs.md). Their terrain/FEMA/reference-distance
fields enter the opt-in inspection endpoints above, separately from geometry.
The optional [offline modeling pipeline](modeling.md) consumes verified descriptive
inputs separately; inspection endpoints do not calculate scores. A complete artifact
requires its final manifest; every research record retains null risk scores and explicit
coverage/unknown states.


## Okaloosa county weather (schema 3)

County snapshots have `schema_version: 3`, county FIPS `12091`, kind `current_county_forecasts` or `historical_county_forecasts`, source table/model, native resolution/statistic/units, actual retrieval time, county geometry, `native_cells` and initialization-grouped `runs`. Each native cell retains ID, original WKT and GeoJSON geometry. IDs are SHA-256 of source WKT. Hourly rows reference the cell ID in `property_id`; `rainfall_1h_mm` is null or a nonnegative finite number. Duplicate cell/hour/run rows invalidate the snapshot. Current snapshots additionally carry `init_time`, `valid_from` and `valid_to`; historical ones carry the Central-time replay bounds.

The importer selects native cells by authoritative county intersection; cells can
extend beyond the boundary. Application views consume native-cell rainfall only,
without associating fictional sites. County parcels remain unscored unless a
separate matching exposure assessment exists. H3 does not replace native forecast
polygons. Application forecast endpoints require schema 3; schemas 1/2 remain
available only in offline research adapters. FIPS 12086 inputs are rejected.
