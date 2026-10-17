# Data contract, version 2

## Pilot boundary

Miami-Dade County is fixed to FIPS `12086`, timezone `America/New_York`. API coordinates are WGS84 (EPSG:4326), `[longitude, latitude]`. The fixture loader checks county tags and coordinate validity. **It does not yet perform a county polygon intersection** and must not be used as an external-data import path without that check.

Fixtures contain six invented points. They are not parcels or building footprints. They are deliberately small enough for every teammate to read.

## Property adapter record

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable adapter identifier; demo IDs start `demo-` |
| `label` | string | Display label; do not use real owner names |
| `county_fips` | string | Must be `12086` |
| `longitude`, `latitude` | number | WGS84 point |
| `elevation_m` | number or null | Terrain elevation; real integration must specify vertical datum |
| `fema_zone` | string or null | Illustrative normalized FEMA code; unknown codes remain unknown |
| `waterway_distance_m` | non-negative number or null | Distance to a meaningfully connected waterway |

## Scenario record

`id`, `label`, `valid_from`, `valid_to`, `rainfall_6h_mm`, and `gauge_margin_m`.

Times are ISO 8601 UTC with `Z`; UI formats them in Miami's local time. Each fixture window uses one countywide rainfall and gauge value as an explicit simplification. The rainfall value represents total mm for that six-hour window. Gauge margin is `flood_stage_m - observed_stage_m`, using matching datum and units; negative means above the illustrative stage threshold.

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

The snapshot schema uses `schema_version: 1`, `model: WeatherNext 3`, `county_fips: 12086`, `native_resolution: 0.1 degree`, `statistic: ensemble_mean`, `units: mm_per_hour`, `source_table`, `init_time`, `retrieved_at`, `valid_from`, `valid_to` and `rows`. Rows contain `property_id`, `forecast_time`, `rainfall_1h_mm` and `native_cell_wkt`. The importer converts source meters to mm exactly once in SQL. It sums six hourly **means**, not marginal percentile values.

Hourly timestamps denote the end of each accumulation interval. The six timestamps must be start+1h through start+6h from one initialization. Missing/null steps produce unknown totals; duplicates or out-of-window steps invalidate the import. Each point ID must be in the curated fixture catalog. This is not an import route for arbitrary coordinates or external parcels.

## Browser H3 contract

`QuasarSpatial.aggregate` adds `h3_index`, `property_id`, `risk_band` and `risk_score` to a copy of each site feature. It returns occupied-cell GeoJSON with resolution 7, site/scored/unknown counts, maximum/mean score and a display band. The backend point contract remains independent of H3. All polygons use closed longitude/latitude rings. Unknowns are never zero-filled. Cell shapes may extend beyond the county; they do not establish geographic containment or forecast precision.

## Contract for future real adapters

Do not silently replace fixtures. Add an explicit data mode and source status. Every real adapter must retain source URL/record ID, retrieval time, observation/issue/valid times where relevant, CRS, vertical datum, units, license and transformation steps. Add authoritative county geometry validation, source-age limits, missing/stale states, and tests for outside-county records. Store only normalized county-filtered features in the scoring pipeline. Do not turn a centroid association into a claim of building-level inundation.

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
