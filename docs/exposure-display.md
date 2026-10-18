# Experimental relative exposure display

The map uses fixed green/yellow/orange/red anchors for experimental exposure
indices. It is not a trained parcel flood model, flood probability, depth, or
safety assessment. **Green does not establish safety.** Existing real-parcel
`risk_score` and `risk_band` remain null/unknown.

| Index | Label | Color anchor |
| --- | --- | --- |
| 0–34 | Lower relative exposure | Green `#16a34a` at 0 |
| 35–64 | Moderate relative exposure | Yellow `#eab308` at 35 |
| 65–84 | Elevated relative exposure | Orange `#f97316` at 65 |
| 85–100 | Highest relative exposure | Red `#dc2626` at 85 and 100 |
| Unknown | Insufficient data | Transparent interior; thin outline |

Colors interpolate in RGB between fixed anchors. Labels change at 35, 65 and
85, including fractional indices. Hour and zoom never renormalize the scale.
The source of truth is `quasar/static/exposure-scale.json`, supplied through
`/api/config`. Numeric indices, explanations and a gradient legend accompany color.

## Explicit assessments

Geometry-only databases contain no exposure assessments. Set
`QUASAR_EXPOSURE_FILE` and `QUASAR_PARCEL_DATABASE` on LinuxONE to consume explicit
results from a separately documented scoring method. Existing parcel API
authentication also protects `/api/exposure`; set `QUASAR_PARCEL_API_TOKEN` to
32+ characters. Never expose that token to the browser.

For hourly playback, configure `QUASAR_EXPOSURE_DIRECTORY` **instead of**
`QUASAR_EXPOSURE_FILE`. Store one existing schema-1 assessment per UTC start,
named `YYYYMMDDTHHMMSSZ.json` (for example `20261009T050000Z.json`). Each file
retains its own forecast provenance and 128 MiB limit. The API reads only the
exact requested whole-hour file and still verifies its internal window,
inventory, model diagnostics and freshness. Missing hours stay unavailable;
there is no nearest-hour substitution. Setting both sources is an explicit
configuration error. The authenticated proxy and browser API are unchanged.

The October 9 Central replay needs 25 six-hour assessments starting hourly from
`2026-10-09T05:00:00Z` through `2026-10-10T05:00:00Z`, inclusive. Run the existing
`python3 -m quasar.modeling assess` command for each start with `--mode replay`
and `--output <directory>/<UTC-start>.json`, using the same verified model,
evaluation, inputs, inspection and archive paths. Benchmark the results before
activation. Generate into a new ignored directory; configure that directory on
the inventory host only after generation and verification complete. A single
73 MB county assessment cannot populate the full replay, and combining 25 into
one file would exceed the serving limit. Do not retrain to activate existing weights.

If the inspector says the exposure service is **not configured**, this is a
service-level gap, not proof that the selected parcel lacks terrain or FEMA data.
Check the assessment source and `QUASAR_PARCEL_DATABASE` on the inventory host.
`QUASAR_PARCEL_CONTEXT_DIRECTORY` supplies descriptive inputs only. Once the
configured service is active, **Refresh parcels** requests fresh assessments.
Parcel-level missing reasons are meaningful only after a matching run is served.

The original display change adds no scoring formula or training dataset. Optional
[offline modeling](modeling.md) can produce FEMA mapping proxy assessments after
promotion gates pass, separately from any validated flood predictor. Missing assessments stay unknown
with transparent interiors. Fictional sites are not served by the application.

Schema 1 example (**synthetic format documentation**, not real parcel data):

```json
{
  "schema_version": 1,
  "county_fips": "12091",
  "run_id": "synthetic-format-example",
  "method_version": "synthetic-method-example",
  "inventory_id": "matching-source-provenance-output-sha256",
  "windows": [{
    "valid_from": "2026-10-09T05:00:00Z",
    "valid_to": "2026-10-09T11:00:00Z",
    "computed_at": "2026-10-17T12:00:00Z",
    "parcels": [{
      "parcel_id": 1,
      "score": 70,
      "factors": [{"name": "synthetic_factor", "value": "synthetic example", "contribution": 70}],
      "missing": []
    }]
  }]
}
```

Indices must be finite numbers from 0 to 100. Known indices require no missing
inputs and named, nonnegative contributions summing to the index within 0.11
points (rounding tolerance). Missing inputs require null indices. Omitted records
also remain unknown. Duplicate IDs/windows, out-of-inventory IDs, wrong county,
inventory mismatch and invalid values invalidate the artifact. Windows are
exactly six hours; timestamps require timezones. Files are limited to 128 MiB,
read-only and cached by file version. Publish atomically.

## Complete-inventory summaries

`GET /api/exposure?from=<UTC>&to=<UTC>&mode=current|replay&resolution=4|5|6|7`
returns summaries keyed by indexed H3 cell. Every parcel in the database cell
membership contributes to coverage; absent assessments are unknown. Client
pagination never changes a cell's color.

- Color value: linear-interpolated P90 at sorted position `(n-1)*0.9`, using
  eligible indices. Zero is valid; no eligible indices produce null.
- Coverage: scored / full parcel count. Incomplete coverage is reported in inspection details.
- Elevated count: number of parcel indices >=65, including highest indices.
- Unoccupied or unassessed cells have transparent interiors and thin outlines.
- Memberships use intersecting polygons: a parcel can occur in several cells.
  Do not sum cell counts as a distinct county parcel count.

`parcel_ids=<comma-separated IDs>` returns up to 100 assessments instead of cell
summaries. Supply the summary's `run_id`; a changed run returns `status: changed`
without indices. Responses include method/run/inventory identity, forecast
window, computation time, scale version and actual aggregation host architecture.

Current results expire at window end or after two hours since computation.
Future computation timestamps are invalid. Replay permits deliberate past
windows without today's freshness cutoff. Missing exact windows and invalid or
stale artifacts return explicit status without indices. Retired synthetic and what-if application routes cannot consume these artifacts.

## LinuxONE and hosted behavior

Run aggregation on the actual LinuxONE host. With `QUASAR_LINUXONE_API_URL` and
`QUASAR_LINUXONE_API_TOKEN` set, the web host proxies `/api/exposure` through
authenticated HTTPS. It never recomputes a local substitute when that service
fails. Forward `/api/exposure` through the existing parcel reverse proxy with
the same authentication header. This code does not modify infrastructure.

`aggregation_architecture` records the actual summary host. Local synthetic tests
do not establish IBM Z execution, configured real assessments or visual acceptance.
Changing scenario/hour retains cached parcel geometry and the selected cell/parcel
while clearing previous exposure indices until matching assessments arrive. Late
responses cannot repopulate closed or superseded selections.

## Optional modeling fields (schema 1, additive)

Legacy artifacts remain supported. Model artifacts add validated `model_metadata`
(schema/version, proxy target, policy, promoted flag, model hash and notice) and
`forecast_provenance` (init/publication/import/valid/expiry times, source table/hash,
native resolution/statistic/units, mode and availability basis). These fields pass
through local and authenticated proxy responses. Current source expiry invalidates
server results and browser colors; recomputation cannot extend source validity.

Known model records require `model_details`: susceptibility, raw susceptibility,
six-hour rainfall mm, rainfall stress, ensemble instability, raw baseline and six
signed tree-path attributions. Validators check finite values/ranges, policy
arithmetic and baseline plus attribution sum. One nonnegative
`susceptibility_rainfall_interaction` factor accounts for the final index; signed
model explanations remain separate. Invalid diagnostics fail closed. Parcel
inspection labels the mapping proxy, visualization rule, instability and source
times explicitly. None of these values establish flood depth, probability,
confidence intervals or safety.
