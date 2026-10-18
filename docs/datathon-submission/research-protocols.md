# Remaining research and operation

These protocols cover T14–T20 of the [execution plan](../DATATHON-GAP-CLOSURE-PLAN.md). They are ready to review, not completed experiments. No new cloud forecast acquisition, current-forecast schedule, outcome labels, outreach or user study was performed. Authorized isolated LinuxONE inference and a separate bounded NWS import are recorded in [verified execution](verified-run.md). Assign actual owners before collecting evidence. No domain reviewer, partnership or source availability is invented.

## T14: mapping-proxy weakness

Question: does the poor fully mapped validation group arise from reference/coverage errors, unsupported predictors or a spatially concentrated failure? The committed report records MAE 0.779924 on 60 fully mapped validation parcels. Retrieve the exact dataset, residuals, evaluation and reference-date manifests; run `verify-model-evidence` first. Inventory terrain support, FEMA date/conflict coverage, coastal/open-water context and residual block/group counts. Preserve all zero/partial/full target groups.

Before changing a feature or weight, record the candidate, development/grouped-validation selection rule and subgroup metric. Compare a direct FEMA display, development mean and current model where applicable. Report sample sizes, abstention and equal-block/parcel errors; do not hide a weak group behind overall RMSE. The existing test has been examined: it cannot become untouched by deleting its ledger or recreating the dataset. A redesigned candidate needs genuinely independent evaluation.

Stop if reference/label quality cannot support comparison, or if there is no defensible incremental use over the available FEMA layer. Preserve the old model and report a restriction or negative result. This release's interpretation is restricted to experimental descriptive comparison, with no operational property prioritization. That restriction does not claim the cause of the weakness has been established. The active evaluation and weak subgroup counts were inspected, but raw residuals/native members/training ledger remain absent; independently reproduced failure analysis remains blocked on those specific artifacts.

## T15: observed rainfall-impact experiment

Proposed target for review: independently verified rainfall-driven parcel impact during a forward-six-hour interval. This is a new research product, not a renamed FEMA target. Before acquisition, define impact, episode inclusion, spatial association uncertainty, timing, observation coverage and allowed retrospective/as-issued reference mode with a domain/label reviewer.

Candidate discovery: [NOAA Storm Events](https://www.ncei.noaa.gov/access/storm-events-database/), county incident/road-closure records and verified field/high-water evidence where actually accessible. A county incident is not automatically a parcel label; absence of a report is not a negative. Negative labels require observation coverage across the entire interval. Ambiguous associations remain unknown. Preserve source IDs, retrieval, terms, county containment, forecast/inspection hashes and publication/reference availability.

Use the existing `validate-outcomes` gate: at least ten independent episodes, 200 positives, 200 negatives and the implemented temporal/spatial/class support requirements. These minimums do not establish statistical adequacy. If they fail, publish an insufficiency report and stop before training; never weaken the gates. If eligible, preregister logistic and boosted baselines, feature/threshold selection on development/validation only, independent temporal/spatial holdouts, precision/recall, average precision, missed impacts/false alarms, coverage/abstention and per-group counts. Probability claims additionally require calibration/reliability and proper scoring evaluation. No such labels or outcome model are present here.

## T16: physical-input inventory

| Candidate | Question / primary discovery source | Required alignment before deriving features |
| --- | --- | --- |
| Floor heights | Is a reviewed local building-elevation source available? County owner/source access unresolved | Building/parcel association, actual measured elevation, vertical datum, date and terms; no inferred floor heights |
| Relative terrain/drainage | [USGS 3DEP](https://www.usgs.gov/3d-elevation-program) and retained county drainage records | Polygon coverage, horizontal/vertical datum, units and a reviewed physical derivation; absolute DEM alone is insufficient |
| Drainage infrastructure/connectivity | [County stormwater reference](https://myokaloosa.com/pw/stormwater); inventory access unresolved | Actual topology/capacity, dates/coverage/terms; a line layer is not a hydraulic model |
| Channels, lakes and canals | Retained county hydrography and [USGS NHD reference](https://www.usgs.gov/national-hydrography/national-hydrography-dataset) | Source-specific types, gaps, positive geometry and actual connectivity; do not claim complete coverage |
| Tide/surge context | Source/experiment selection requires coastal/domain review | Common vertical datum, physical mechanism and availability at decision time; rainfall cannot rule out surge |
| Measured gauges | [USGS water-data discovery](https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items) | Actual time series, station/variable/units/datum, quality flags and defensible parcel linkage; station coordinates alone fail |

For each source, retain retrieval, license, CRS, units, dates, actual geographic/temporal coverage, decision-time availability and missingness. Acquire only after selecting a supported question. Keep transformations in `quasar/` with geographic/unit/time tests. Evaluate incremental value under T14/T15's holdout rules. Do not subtract incompatible BFE/DEM heights, invent drainage/floor context or interpret an inventory as a depth model.

## T17: current forecasts and lead time

The selected scope remains the saved October 9 replay. A new date/window and allowed scan budget are required before acquisition. Existing county import commands remain explicit and dry-run by default; no request starts a query. Obtain a dry-run byte estimate, cap and query-budget reservation before execution. Preserve source init/publication/validity/import/resolution/units, reject duplicate/null/missing hours, and match inspection geometry/hash to the exact snapshot.

Publish a coherent snapshot and matching assessment/catalog release. Test source switch, stale expiry while open, failed partial import, out-of-order responses and delayed publication. Keep archive controls intact. Do not introduce a current selector until the complete data path is reviewed. No auto-refresh job is configured. Any later job needs an owner, lock, source-based schedule, cost cap, timeout, bounded retry, failure reporting and authorization for shared infrastructure changes.

Measure actual source availability → import → production → API latency over repeated coherent runs. If publication time is unavailable, report initialization-based latency rather than warning lead time. Stop on exhausted budget, incoherent identities, unavailable source or missing operation scope. Existing entitlement and one successful fetch are not ongoing reliability.

## T18: official alerts

County import/interpretation and an explicit current API are implemented and fixture-tested; see [operations](operations.md#optional-current-official-alerts). The documented county UGC query avoids guessing a single forecast-zone relationship. A bounded live canonical county fetch succeeded and its original response/lifecycle was retained. The snapshot deliberately expires after 120 seconds. Separate current UI acceptance and any operated refresh remain open. The archive never displays present-day alerts. No hazard/safety conclusion is drawn from an empty, stale, partial or disconnected feed.

## T19: operation, recovery and adoption

Before an operational scope is proposed, name owners for inputs, credentials, source terms, releases, model versions, incidents, backups and feedback. Define freshness, API response, availability, retention and recovery objectives from actual user needs. Their numeric values remain unresolved, not invented targets. Monitor source age/coverage, coherent artifact IDs, job success, API failures/latency, memory/disk and certificate/config health through reviewed redacted logs.

Exercise restore from retained immutable releases, failed import, artifact/catalog rollback and unavailable upstream in a designated authorized environment. Record observed recovery time and restored identities; backup existence is insufficient. Concurrency testing needs an agreed host cap and stop criteria. Use [the acceptance checklist](acceptance.md) for Isaac's review and [the comparison protocol](problem-and-comparison.md) for willing reviewers. No pilot, reviewer response or restored service was measured here. Real contacts, subscriptions, notifications and navigation remain outside scope.

## T20: differentiation experiment

Test one precise question: does displaying explicit unknown coverage reduce unsupported low-risk interpretations during the analyst task? Freeze two comparable task versions and score correct source/time/unknown interpretation, task completion, errors and time. Alternate order across willing reviewers; report every result, small-sample limitations and failures. Use the official-source workflow as the comparison; do not claim those tools lack features without verification.

Separately, use full-parcel cross-host parity and measured resource cost to assess portable inference. Numerical fidelity, human understanding, prediction quality and county-scale resource use are distinct outcomes. A conventional model plus integrations is the current contribution; no claim of novel AI architecture, measured community impact or award qualification is substantiated. Stop or narrow claims when either data or user evidence is insufficient.
