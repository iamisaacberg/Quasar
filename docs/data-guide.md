# Data guide: inputs, provenance, and quality

## Scope and evidence

Quasar uses six hand-authored fictional points in Okaloosa County. They are exercise sites, not real homes, cadastral parcels, or building footprints. All operational dates below are configuration or recorded project checkpoints unless explicitly described otherwise.

This guide explains how data is used in the reviewed implementation. [data-contract.md](data-contract.md) defines exact record and response fields; [data-sources.md](data-sources.md) lists source identifiers and acquisition history. Existing project notes report downloads and a forecast import on October 17, 2026. Those historical notes have not been refreshed by a new network or cloud check as part of this documentation work.

## Data families and current use

| Family | Current role | Status boundary |
| --- | --- | --- |
| Fictional site catalog | Six points, labels, invented elevation/FEMA/waterway attributes | Committed fixture; one elevation is intentionally null |
| Synthetic weather windows | Countywide exercise rainfall and gauge margin | Three committed fictional windows; no observations |
| Current WeatherNext rainfall | Optional six-hour forecast for the six site coordinates | Explicit local import; all other score factors remain fictional |
| Historical WeatherNext rainfall | Optional runs for hourly replay | Separate archive; missing runs/hours remain unknown; availability must be checked locally |
| Census county boundary | Authoritative geometry for acquisition and road checks | Acquisition code exists; does not automatically validate the ordinary fixture pipeline |
| County parcels/buildings | Proposed real site inventory and geometry | County-validated parcel geometry loads on R7 selection; separate offline input joins do not change app scoring; building joins remain unavailable |
| FEMA NFHL | Offline mapped-zone intersections | Separate research joins retain zones/subtypes, dates and coverage; no app scoring join is implemented |
| USGS 3DEP | Research terrain input | Offline pixel coverage and parcel terrain summaries; no runtime terrain sampling or building elevation model |
| USGS monitoring locations | County-filtered station metadata | Locations are not water-level observations or gauge-to-site relationships |
| NWS active alerts | Optional point-fetch client | CLI client exists; dashboard endpoint deliberately reports `not_connected` |
| NHC advisory text | Optional storm context in replay | Local preparation extracts original issue times; not local flood verification |
| County street centerlines | Source geometry for a curated exercise graph | Traversal, speeds, connectors, closures, and destinations remain simulated |

An acquired file, an integrated feature, and a validated model input are separate milestones.

The **Data** tab now reads current county-native forecast cells directly, rather
than the fictional-site reporting pipeline. It shows retained six-hour windows,
native-cell input status, rainfall and source metadata, plus the indexed parcel
count when available from the verified inventory manifest. Empty/stale sources
remain unavailable; it never substitutes exercise rainfall. Its cell-average
rainfall excludes unavailable cells and is not area-weighted county rainfall.
Parcel counts establish geometry coverage only; terrain/FEMA/gauge coverage and
parcel flood scores are not inferred. Reports & exports continue to describe
their explicitly labeled fictional/mixed demonstrations.

## The committed fixtures

`quasar/fixtures/properties.json` contains six sites: Destin, Fort Walton Beach, Niceville, Crestview, Laurel Hill, and a missing-terrain exercise site in Shalimar. The names locate the exercise conceptually; they do not identify actual parcels or owners. Stable identifiers run from `demo-001` through `demo-006`.

| Input | Unit or representation | Interpretation in this starter |
| --- | --- | --- |
| `longitude`, `latitude` | Decimal degrees, WGS84 | API/GeoJSON uses `[longitude, latitude]` |
| `county_fips` | Text `12091` | Required county identity |
| `elevation_m` | Meters or null | Fictional terrain value; no surveyed building-floor elevation |
| `fema_zone` | Zone code or null | Fictional simplified mapping category |
| `waterway_distance_m` | Nonnegative meters or null | Fictional proximity; no drainage connectivity model |
| `rainfall_6h_mm` | Millimeters per six-hour window | Synthetic scenario total or complete imported hourly sum |
| `gauge_margin_m` | Meters | Flood-stage threshold minus stage, with matching units/datum required for real use |

The scenario fixture supplies these exercise conditions:

| Scenario | UTC window | Rainfall, mm / 6h | Gauge margin, m |
| --- | --- | --- | --- |
| `baseline` | Oct 17, 2026 12:00–18:00 | 15 | 1.2 |
| `heavy-rain` | Oct 17 18:00–Oct 18 00:00 | 70 | 0.4 |
| `peak` | Oct 18 00:00–06:00 | 115 | -0.2 |

These are a fixed fictional clock. Their dates do not make them current weather. Negative gauge margin represents an invented stage above the exercise threshold.

## Data modes

| Collection `mode` | Rainfall | Other scoring inputs | Meaning |
| --- | --- | --- | --- |
| `synthetic_demo` | Fixture | Fixture | Fully synthetic exercise |
| `mixed_forecast_demo` | Current imported forecast | Fictional; gauge margin fixed at 1.2 m | Mixed demonstration with current-forecast freshness rules |
| `historical_mixed_demo` | Eligible archived forecast, when available | Fictional; gauge margin fixed at 1.2 m | Historical forecast reconstruction |
| `what_if_exercise` | Archived rainfall plus selected synthetic increment, when complete | Fictional | Controlled exercise; may also include simulated road/destination overrides |

Risk-level `data_status` answers a different question: complete fixture inputs report `synthetic`; complete mixed inputs report `mixed_demo`; an unscorable record reports `incomplete`. Forecast and routing statuses add their own reasons. Do not infer source freshness from a non-null site score alone.

The fixed gauge margin in imported modes is an exercise assumption, not a gauge reading.

## Current WeatherNext path

`quasar/adapters/weathernext.py` constructs an explicit BigQuery query for one initialization and six hourly intervals. It joins each curated coordinate to the **original forecast polygon** with `ST_COVERS`, selects hourly ensemble-mean precipitation, and converts meters to millimeters once in SQL.

The normalized version-1 snapshot retains source table, model, county, initialization, import time, six-hour validity, statistic, native resolution, units, original cell geometry, and hourly rows. The six hour-ending timestamps must be `window_start + 1h` through `window_start + 6h`.

For example, six synthetic hourly means of 2.5 mm sum to 15 mm for the six-hour window. If an hour is absent or null, the total is unknown. This arithmetic example is not an observed forecast import.

### Structure and completeness

- Only the six curated IDs are accepted; this importer is not an arbitrary-coordinate or external-property intake.
- Duplicate site/hour rows and hours outside the selected window invalidate the snapshot. Boundary overlaps must not be double-counted.
- Rainfall must be finite and nonnegative or explicitly null. Booleans and non-finite values are rejected.
- Native cell text must be supplied as polygon/multipolygon WKT. The current validator checks its type prefix; this is not full geometry parsing or independent verification of a point-cell join.
- The source grid is `0.1 degree`; the statistic is `ensemble_mean`; stored hourly units are `mm_per_hour`.

Summing hourly means produces a mean accumulation for the window. Summing hourly p90 values would not establish a six-hour p90. That would require the corresponding ensemble trajectories and a separate calculation.

### Freshness

| Condition | Effect |
| --- | --- |
| Initialization age greater than 12 hours | Stale; rainfall becomes null |
| Import age greater than 2 hours | Stale; rainfall becomes null |
| Window end at or before the current clock | Stale; rainfall becomes null |
| Missing/null hourly input | Site incomplete unless the snapshot is already stale |
| Wrong schema, units, IDs, duplicate rows, or malformed metadata | Invalid snapshot |
| No configured path | `not_configured` |

Initialization/retrieval times more than five minutes in the future are rejected, and retrieval cannot precede initialization. These are implemented starter policies, not validated meteorological operating thresholds.

A structurally valid stale/incomplete snapshot can still appear as a selectable scenario and preserve provenance. Its unavailable rainfall is not scored and does not silently fall back to fixture rain. A missing or invalid snapshot is not usable as the WeatherNext scenario.

## Historical forecast path

The separate historical importer writes schema version 2, kind `historical_forecasts`, with a list of runs. It queries the configured replay period, six-hourly initializations starting at the preceding six-hour UTC boundary, and each run's first 18 hourly intervals. It retains actual retrieval time and native cells; this is separate from the current snapshot.

At replay hour `t`, the code chooses the latest run initialized by `t`. If `published_at` exists, it must also be no later than `t`. The run must be no more than 12 hours old at replay time, and it must supply all six interval endings `t+1h` through `t+6h` for that site.

Publication timing is not supplied by the importer. Its default label is therefore **initialization-based archive reconstruction**. Initialization describes model state time; it does not prove the forecast had already been published or received. Later retrieval does not retroactively establish availability.

An invalid selected run yields unknown rainfall; the code does not hide the problem by falling back to an older run. Today's clock does not make a deliberate historical archive stale. A `loaded` archive describes accepted metadata, while individual selected runs can still be stale, invalid, incomplete, or unavailable.

What-if presets add 5 or 10 mm to **each of six valid hourly values**, increasing a complete six-hour total by 30 or 60 mm. They do not fill gaps. Their effects remain synthetic.

## Geographic scales and joins

Three spatial objects must remain distinct:

1. **County polygon:** establishes whether an asset or whole road segment is in scope.
2. **Native forecast cell:** establishes which source precipitation value was associated with a site.
3. **H3 grid at resolutions 4–7:** covers the county for browsing; R7 selection loads real parcels. Optional matching assessments supply server-side parcel P90 exposure summaries, separate from fictional-site summaries.

Neither a bounding box nor a matching FIPS tag proves county containment. Ordinary fixture loading checks tags and coordinate validity, not polygon containment. The road subsystem separately checks full line containment, including holes and concavities. Future external site adapters must add authoritative boundary checks before scoring.

H3 cells may cross the county border. The browsing grid covers all county-intersecting cells. Fictional-site summaries exclude unknown scores and report unknown counts separately. Optional parcel exposure summaries use complete indexed memberships for coverage and exclude unknown indices from P90; absent assessments remain unknown. Geometry-only parcel risk fields remain null. See the [exposure display contract](exposure-display.md). A small display cell does not create a finer forecast or a building-level terrain estimate.

DEM catalog searches in the acquisition script use the county's bounding box to find candidate tiles. Downloading those tiles alone does not establish exact county masking, terrain coverage at every asset, or correct vertical reference. The separate [parcel input preparer](parcel-inputs.md) now checks those properties and records missing coverage; it does not change the app fixtures. Verify raster metadata before transformation. The source raster CRS is retained; inspect its XML before reprojection. NAD83 geographic coordinates use EPSG:4269, not EPSG:4326.

## Provenance and local storage

| Path | Contents | Handling |
| --- | --- | --- |
| `quasar/fixtures/` | Small fictional source inputs | Committed and visibly labeled |
| `data/raw/` | Original downloads, query rows, source metadata | Ignored; retain source identity and checksums |
| `data/processed/source_manifest.json` | Acquisition inventory and processing notes | Ignored; inspect alongside source files |
| `data/processed/weathernext.json` | Default current forecast snapshot | Ignored; configure explicitly |
| `data/processed/isaias-2026.json` | Default historical forecast archive | Ignored; separate from current forecast |
| `data/processed/isaias-advisories.json` | Prepared NHC context | Ignored; retain original issue time and source link |
| `data/processed/evacuation-network.json` | Curated county-contained exercise graph | Ignored; contains source and simulation assumptions |

For real adapters, retain source URL/identifier, retrieval time, issue/observation/validity times as applicable, coordinate reference system, vertical datum, units, license/terms, transformation steps, checksums, and quality flags. Record data availability time separately when reconstructing past decisions.

The acquisition manifest contains some hard-coded historical status text about WeatherNext and event selection. Treat it as the output of that acquisition path, not a global integration-status authority. Existing source notes also require reconciliation as components evolve; see the [roadmap](improvement-roadmap.md#p0--make-status-and-validation-consistent).

Do not commit raw property datasets, credentials, real opt-ins, or server details. A later real site adapter should use the minimum permitted asset fields and omit owner/mailing details.

The countywide preparation pipeline acquires minimal parcel geometry, validates full containment in Census Okaloosa, indexes overlapping H3 R4–R7 cells and builds SQLite. The new source inventory contains 114,009 polygons, of which 113,818 are fully county-contained and 191 are excluded. Parcel scores remain unknown. Inspect ignored manifests for hashes, timestamps, source terms and CRS; see [source catalog](data-sources.md).

County weather snapshots additionally support schema 3 with native polygons and hourly runs. See [integration guide](integrations.md). Legacy schema 1/2 six-site formats remain readable only for the configured county.
