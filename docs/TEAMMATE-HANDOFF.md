# Quasar teammate handoff: WeatherNext + IBM LinuxONE parcel exposure

> Taking over development? Start with the [complete execution plan](DATATHON-GAP-CLOSURE-PLAN.md), [workboard](DATATHON-WORKBOARD.md) and [rubric audit](DATATHON-DEV-HANDOFF.md). This document retains the earlier exposure implementation snapshot; later modeling and runtime changes supersede its unfinished-producer and display descriptions.

**Handoff snapshot: October 17, 2026. County scope: Okaloosa, Florida, FIPS `12091`.**

**Model status update, October 18 UTC / October 17 Central:** PR #17 added the
[offline modeling pipeline](modeling.md) without trained weights. A subsequent
[real-data training run](modeling-run-v1.md) now provides a locally trained,
exported FEMA mapping proxy that passed the pipeline's promotion gates, plus a
local county assessment for one archived rainfall window. LinuxONE supplied the
prepared inputs; the new model and assessment have not been installed or
activated there. This is not observed-flood validation. Artifacts are ignored
and therefore absent from a repository clone.

The implementation gaps and decisions below are the earlier handoff snapshot,
not the current model status. An observed-report overlay and actual LinuxONE
model benchmark remain unestablished.

## What we are building

Quasar should help someone inspect **which locations deserve closer attention as forecast rainfall changes**, with the supporting inputs and unknowns visible.

The intended pipeline is:

```text
WeatherNext 3 rainfall forecasts
              +
County-validated parcels, terrain and FEMA context
              |
              v
IBM LinuxONE
  Produce documented experimental parcel assessments
  Aggregate complete parcel inventories into H3 summaries
  Serve results through the authenticated backend
              |
              v
Quasar map
  Colored cells -> colored parcels -> index and contributing factors
```

WeatherNext already supplies the trained forecast AI. For this deadline, we agreed that **training a new model on LinuxONE is not required for our chosen implementation**. This is a team scope decision, not a verified statement about the official judging rules.

LinuxONE should perform the exposure computation and serving that the app depends on. The browser applies the color scale; it does not calculate parcel indices or aggregate the real parcel inventory.

The river-gauge prediction experiment in the earlier teammate prompt is a separate idea. This direction is centered on parcel exposure.

## What is implemented locally

| Component | Implemented behavior |
| --- | --- |
| Shared scale | Fixed green/yellow/orange/red color anchors, smooth interpolation and numeric labels |
| Parcel rendering | Colors use the individual parcel assessment; inspection shows its index and factors |
| H3 summaries | Server calculates P90, elevated-index counts and coverage from complete indexed parcel memberships |
| Missing data | Gray/hatching for unknown indices; incomplete cells retain hatching |
| Time changes | Cached parcel geometry and selection persist across scenario/hour changes; previous exposure indices are cleared until matching assessments arrive |
| API | `/api/exposure` provides summaries and bounded parcel assessment lookups |
| LinuxONE proxy | Hosted instances can proxy exposure requests through the existing authenticated LinuxONE connection |
| Data contract | Explicit assessment artifacts are validated against the matching parcel inventory |

**The real-parcel scoring method and the producer of its assessment artifact are not implemented.** This work consumes explicit assessments; it does not invent scores from geometry or turn the existing fictional-site formula into a validated property model.

Until matching assessments are configured, real parcels remain gray/unknown. Their existing `risk_score` and `risk_band` remain null/unknown even when a separate experimental exposure index is supplied.

These are local workspace changes. This handoff does not establish a commit, merge, deployment, configured LinuxONE service, transferred dataset or visual acceptance.

## Color and cell-summary rules

| Index | Label | Color anchor |
| --- | --- | --- |
| 0–34 | Lower relative exposure | Green `#16a34a` at 0 |
| 35–64 | Moderate relative exposure | Yellow `#eab308` at 35 |
| 65–84 | Elevated relative exposure | Orange `#f97316` at 65 |
| 85–100 | Highest relative exposure | Red `#dc2626` at 85 and 100 |
| Unknown | Insufficient data | Gray `#9ca3af`, hatched |

Colors interpolate between anchors. The category boundaries stay fixed at 35, 65 and 85 across hours and zoom levels. Scores can be fractional.

The legend reads **Experimental relative exposure** and **Green does not establish safety.** A score of 80 is not an 80% flood probability.

For each H3 cell:

- Color uses the 90th percentile of eligible parcel indices, linearly interpolated at sorted position `(n - 1) × 0.9`.
- Elevated count includes all indices >=65, including the red band.
- Coverage is eligible parcel count divided by the full indexed parcel membership count.
- Missing records count as unknown, never zero. A valid index of zero remains zero.
- Partial coverage retains hatching. No eligible indices produce a gray/hatched cell.
- Loading more browser pages does not change the cell summary.

H3 memberships use intersecting parcel polygons. A parcel may belong to several cells; adding cell parcel counts does not produce a distinct county total. H3 does not improve WeatherNext's native forecast resolution.

## Inputs and their limits

WeatherNext county snapshots and the parcel terrain/FEMA preparation are documented in [integrations](integrations.md) and [parcel input preparation](parcel-inputs.md). Verify the actual files, manifests and checksums on the machine doing the work; the repository's recorded preparation is not proof that ignored artifacts exist on every teammate's computer.

Use the reconciled research inputs when available. Preserve terrain coverage, FEMA conflicts and unmapped portions. Mean sea-level elevation is not the same as elevation relative to surrounding drainage, and neither is building-floor elevation.

The scoring owner still needs to define and document the index: input fields, units, transformations, weights, fixed thresholds, missing-data behavior and limitations. Do not fill missing gauge, terrain or drainage values just to produce a colored parcel. Do not claim the resulting formula is trained AI or calibrated flood risk.

### Observed flood evidence

An inspection of NOAA's 2018–2025 bulk event files found **19 county-coded flash-flood records across 12 episodes** for Okaloosa. Several describe flooded intersections or road closures. This is a filtered archive count, not a complete inventory of flooding or a set of county-boundary-validated parcel outcomes. [NOAA bulk archive](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/).

These records can support a separately dated historical evidence layer after geographic validation. They do not provide parcel flood boundaries or confirmed non-flooded examples. An absent report does not mean no flooding. The USGS high-water-mark API returned HTTP 403 during investigation; its county inventory remains unverified.

No observed-report overlay or flood-outcome training pipeline was added in this implementation. Do not describe an older reported closure as active during the October 2026 forecast reconstruction.

## Required assessment artifact

Set the following on LinuxONE using the actual prepared artifact paths:

```dotenv
QUASAR_PARCEL_DATABASE=/absolute/path/to/quasar-parcels.sqlite3
QUASAR_EXPOSURE_FILE=/absolute/path/to/exposure.json
# Configure QUASAR_PARCEL_API_TOKEN privately: at least 32 characters.
```

The JSON contract below is **synthetic format documentation**. It is not a real parcel assessment and must not be presented as one.

```json
{
  "schema_version": 1,
  "county_fips": "12091",
  "run_id": "synthetic-format-example",
  "method_version": "synthetic-method-example",
  "inventory_id": "matching-source-provenance-output-sha256",
  "windows": [
    {
      "valid_from": "2026-10-09T05:00:00Z",
      "valid_to": "2026-10-09T11:00:00Z",
      "computed_at": "2026-10-17T12:00:00Z",
      "parcels": [
        {
          "parcel_id": 1,
          "score": 70,
          "factors": [
            {"name": "synthetic_factor", "value": "synthetic example", "contribution": 70}
          ],
          "missing": []
        },
        {
          "parcel_id": 2,
          "score": null,
          "factors": [],
          "missing": ["terrain"]
        }
      ]
    }
  ]
}
```

The producer must satisfy these rules:

1. `inventory_id` matches `source_provenance.output_sha256` in the parcel SQLite metadata. All assessment parcel IDs must exist in that inventory.
2. Each window is exactly six hours and exactly matches the selected app forecast window. All timestamps include a timezone; use UTC.
3. Known indices are finite numbers from 0 to 100, with no missing inputs. Named, nonnegative factor contributions sum to the index within 0.11 points for rounding.
4. Unknown inputs produce a null index. Omitted parcel records also remain unknown.
5. Duplicate IDs/windows, incorrect county/inventory or invalid values invalidate the artifact.
6. Publish files atomically. The current implementation limits the assessment artifact to 128 MiB.

Current-mode results expire at the end of the window or two hours after computation. Future computation timestamps are invalid. Replay accepts deliberate historical windows without applying today's age cutoff. The producer remains responsible for the validity and provenance of its source inputs; these checks do not validate a scoring method.

The UI does not apply real parcel assessments to synthetic or what-if exercise modes.

## API and hosted connection

Summary request:

```text
GET /api/exposure?from=2026-10-09T05:00:00Z&to=2026-10-09T11:00:00Z&mode=replay&resolution=7
```

Supported resolutions are 4–7. The response identifies the run, method, inventory, window and actual aggregation architecture. Each entry in `cells` includes `p90_score`, `parcel_count`, `scored_count`, `unknown_count`, `coverage`, `incomplete` and `elevated_count`.

Parcel lookup:

```text
GET /api/exposure?from=2026-10-09T05:00:00Z&to=2026-10-09T11:00:00Z&mode=replay&parcel_ids=1,2&run_id=<summary-run-id>
```

Parcel IDs above are examples. Request at most 100 distinct IDs. A changed run returns `status: changed` with no assessments. The UI also checks that the assessment inventory matches the displayed geometry inventory.

On the hosted web application, reuse these server-only settings:

```dotenv
QUASAR_LINUXONE_API_URL=https://your-linuxone-origin.example
# Configure QUASAR_LINUXONE_API_TOKEN privately to match the parcel API token.
```

The origin must be HTTPS without a path. The reverse proxy must forward `/api/exposure` with the existing `X-Quasar-Parcel-Token` header. The web host forwards the request to LinuxONE; it does not calculate a replacement summary after a bridge failure.

Keep Google credentials, bridge tokens and server credentials out of the browser, Git and screenshots. Only Mapbox's public `pk.` token belongs in the browser. See the [LinuxONE bridge guide](data-bridge.md) for existing infrastructure context. This change does not configure that infrastructure.

## Remaining work and suggested ownership

| Owner role | Next deliverable | Completion evidence |
| --- | --- | --- |
| Data / scoring | Define a defensible experimental method and produce matching assessment windows from verified inputs | Versioned method notes, manifests, complete factor contributions and explicit unknowns |
| IBM / integration | Run assessment production and aggregation on the authorized LinuxONE host; connect the existing backend bridge | Actual `s390x` output, execution log, API response and matching run/inventory IDs |
| Frontend / Isaac | Inspect colors, gradient, hatching, numeric labels and hour changes in the actual app | Isaac's visual acceptance and checks that unavailable data stays unknown |
| Presenter | Record the complete forecast-to-parcel-to-LinuxONE walkthrough | Demonstrated app output tied to the actual target-host run |

The scoring method is the main unfinished dependency. Do not substitute fabricated parcel indices or quietly copy fictional-site scores onto real parcels.

## Verification and demo

The latest local integration checks recorded **148 Python tests run, with 2 skipped, and 76 passing JavaScript tests**. `npm ci --ignore-scripts`, `npm run check`, `npm run build` and `git diff --check` also passed. Test fixtures are synthetic; these results establish software behavior, not flood accuracy, rendered visual acceptance or LinuxONE execution.

Run the required checks after integration changes:

```sh
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
npm test
npm run build
git diff --check
```

Commit regenerated UI assets alongside frontend source when handing off code. Raw data, SQLite files, credentials and assessment artifacts stay ignored. A Git handoff alone does not transfer them.

Suggested demo sequence, once the remaining inputs and host are verified:

1. Select a complete forecast window and show its WeatherNext initialization, validity and native resolution.
2. Inspect a cell's P90, elevated-index count and full-inventory coverage.
3. Open a real parcel and explain its index and contributing factors.
4. Change the hour; verify the displayed indices belong to the new window.
5. Show an unknown parcel or incomplete cell and its hatching.
6. Show the actual LinuxONE architecture, computation evidence and matching API run ID. Measure timing; do not invent performance or acceleration claims.

Presenter wording:

> WeatherNext supplies the trained AI rainfall forecast. IBM LinuxONE combines it with local parcel context and serves experimental exposure assessments. Quasar shows the indices, the evidence behind them and where the data is incomplete.

Use that wording only after the corresponding assessment producer and LinuxONE connection have been demonstrated. Until then, describe those parts as the intended pipeline.

Follow official NWS and local emergency guidance. This demonstration supplies no evacuation order, safe route, delivery guarantee or property-level flood probability.

## Code and reference map

| File | Purpose |
| --- | --- |
| [`quasar/exposure.py`](../quasar/exposure.py) | Artifact validation, complete-inventory aggregation and LinuxONE proxy |
| [`quasar/static/exposure-scale.json`](../quasar/static/exposure-scale.json) | Shared thresholds, labels and color anchors |
| [`quasar/static/spatial.js`](../quasar/static/spatial.js) | Map color expressions and assignment of server results |
| [`quasar/static/app.js`](../quasar/static/app.js) | Requests, parcel/cell inspection and stale-selection protection |
| [`frontend/dashboard.tsx`](../frontend/dashboard.tsx) | Legend source; build output is under `quasar/static/ui/` |
| [Exposure display contract](exposure-display.md) | Detailed artifact and API behavior |
| [Data contract](data-contract.md) | Existing shared contracts and optional exposure addition |

Keep work on feature branches and target `preview` for an explicitly requested PR handoff. Do not deploy or push to `main` without authorization.
