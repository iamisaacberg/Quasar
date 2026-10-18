# Mechanisms and implementation reference

This is the current county application. Detailed payloads are in [data-contract.md](data-contract.md); [architecture.md](architecture.md) and [operations](datathon-submission/operations.md) distinguish code, artifacts and host proof.

## Runtime structure

`quasar.server` serves explicit API/static routes. React/Tailwind source in `frontend/` compiles into committed `quasar/static/ui/`. Standard-library Python is sufficient to serve the app and run portable inference. Optional GIS/ML and notebooks stay separate. Source reads use configured snapshots/read-only SQLite or authenticated LinuxONE proxies; serving never imports cloud data, trains or produces an assessment.

## Source ownership map

| Code | Responsibility |
| --- | --- |
| `adapters/county_weather.py`, `replay.py`, `forecast_timeline.py` | Validate native forecasts, eligible initializations and exact hourly frames |
| `parcels.py`, `parcel_context.py`, `inspection_prepare.py` | County inventory, indexed geometry, verified prepared descriptive inputs/overlaps |
| `modeling/dataset.py`, `training.py`, `portable.py` | Audited research data, spatial splits, gated local training and standard-library inference |
| `modeling/production.py`, `replay_batch.py` | Explicit single-window/batch production and resource reports |
| `exposure.py`, `exposure_catalog.py` | Validated exact-window assessments, complete-inventory H3 summaries and bounded immutable selection |
| `modeling/evidence.py` | Existing-bundle hashes, model metric/identity replay and all-parcel cross-host parity |
| `bridge.py` | Allowlisted authenticated snapshot reads, bounded network requests and explicit source failures |
| `adapters/county_alerts.py` | Explicit optional current NWS import and saved-message lifecycle; excluded from archive |
| `static/app.js`, `spatial.js`, `inspection.js`, `map-ui.js` | Source/layer/selection state, geometry cache, coverage and stale-response protection |
| `source_exports.py` | Selected source-rainfall Reports and CSV/GeoJSON/BI exports |

## Scoring mechanism

The active optional real-parcel path first predicts FEMA mapped-area fraction from six terrain/area/mapped-stream predictors, then calculates `100 * susceptibility * rainfall_mm / (rainfall_mm + 50)`. The second step is an uncalibrated deterministic interaction, not another trained model. See [modeling](modeling.md) and the [model summary](datathon-submission/model-summary.md) for features, held-out metrics, weak groups and limitations.

Unknown terrain, invalid geometry/coverage, unsupported feature ranges and incomplete/stale rainfall cannot yield a known assessment. Factors are nonnegative index contributions that sum to the index; signed model path attributions are separate and are not physical causes. Five-member spread is not a confidence interval. No output is depth, flood probability or a safety determination.

The earlier arbitrary five-factor fixture score remains in `scoring.py` for offline research only. It is not copied onto county parcels, and its synthetic endpoints stay retired.

## Forecast import and local reads

An explicit county importer retains native geometry, initialization/publication/validity/retrieval, hourly rainfall units and source hash. Six-hour windows require six unique complete hours from one eligible run; no zero filling or mixing. [Current/replay freshness](data-guide.md#current-weathernext-path) and publication limitations remain distinct. A bridge outage does not fall back to fictional sources. New cloud queries remain dry-run/capped explicit commands.

## Replay and timeline

The archive exposes 25 starts from October 9 midnight through October 10 midnight Central. The final forward window requires six additional hours. Map/Data/Reports share selected rainfall time. Selection changes invalidate prior exposure indices; late summary/parcel responses cannot repaint a new selection. Geometry may remain cached while time-dependent scores are cleared.

Legacy single-file assessments still work. A configured catalog instead selects exact mode/window and enforces inventory/model/forecast/file identity beneath an explicit artifact root. No missing hour substitutes a prior score. Batch production writes a new release, records genuine gaps and publishes an atomic catalog marker after validation. Cached summaries do not retain full parcel maps across windows. The [verified execution checkpoint](datathon-submission/verified-run.md) records actual host measurements; broader load/recovery remains open.

## Browser map and H3

Mapbox GL JS 3.33.0 uses a public token; H3 JS 4.3.0 is vendored with notices. Native forecasts retain their actual resolution. County-clipped H3 rainfall uses maximum complete overlaps; exposure uses complete-inventory P90 and explicit coverage. Unknown interiors are transparent. P90 excludes unknown values but coverage includes those parcels. Overlapping membership counts cannot be summed into unique county totals.

## Reports and exports

Reports and downloads use source rainfall for the selected frame. They do not export a fabricated county risk dataset or model-result report. Browser printing is a user action, not a server PDF generator. Export labels retain reconstruction, native resolution, validity and missing values. See the [report/download contract](data-contract.md#reports-and-downloads).

## Notifications and official alerts

Notification previews and simulated routing are retired application features; their HTTP routes return 410. No contact collection or messages are sent. The optional current county NWS command is separate from fictional point research and from model scores. Serving reads a saved short-lived snapshot, never fetching NWS on a request. Source failures, partial pagination, stale data, fresh empty results and disconnection remain distinct. The archive never shows present-day messages.

## Configuration and build

Use [README](../README.md), [.env.example](../.env.example), [bridge setup](data-bridge.md) and [operations](datathon-submission/operations.md). The hosted application is public; source tokens stay on servers. The optional laptop Wi-Fi passphrase gate is separate. Never put secret credentials in `VITE_` settings or browser configuration. Rebuild committed assets after changing frontend source. Do not restart shared services/deploy from a successful local build alone.

## Verification boundaries

Run required Python/npm checks and optional ML/GIS tests for research changes. Regression fixtures cover missing/stale/wrong-time and authentication behavior. Actual source/model artifacts, LinuxONE execution/parity/latency, Isaac's rendered review and independent research validation require separate evidence. The [acceptance checklist](datathon-submission/acceptance.md), [claim ledger](datathon-submission/limitations.md) and [workboard](DATATHON-WORKBOARD.md) retain those boundaries.
