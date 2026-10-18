# Data guide: inputs, provenance, and quality

Only Okaloosa County, Florida (FIPS `12091`) is supported. The current app uses imported native forecast rainfall and county-validated parcel geometry with optional prepared inputs and matching exposure artifacts. A source record, a model estimate and an observed flood are different evidence.

## Data families and current use

| Family | Use | Evidence boundary |
| --- | --- | --- |
| Authoritative Census county polygon | Validate actual parcel containment; clip display cells | A supplied FIPS tag or bounding box is insufficient |
| County parcels | Minimal geometry/inventory and indexed H3 memberships | Geometry is not floor height, observed impact or risk |
| Terrain/FEMA/retained streams | Prepared descriptive parcel context and optional model inputs/target | Preserve source dates, missing coverage, vertical datum and mapping limitations |
| WeatherNext schema-3 snapshot | Native 0.1-degree hourly ensemble mean, complete six-hour windows | Forecast reconstruction is not observed rainfall or proven as-issued publication |
| Portable FEMA mapping proxy | Experimental mapped-area fraction and rainfall interaction | Not trained on observed flood outcomes; weak subgroups remain visible |
| Immutable assessment/catalog | Exact method/inventory/model/forecast/window results | Missing or invalid match means unknown, never a prior hour's score |
| Optional saved current NWS snapshot | Official county-query messages in separate current API | Never on the archive; disconnected/stale/partial/error do not mean no hazard |
| Fictional fixtures and old routing/notification modules | Offline research/regression only | Retired public HTTP routes return 410; never substituted into the app |

## Scope and evidence

The [recorded first model run](modeling-run-v1.md) lists 113,818 parcels, a trained model and one assessment. The [activation record](real-data-rollout.md) describes earlier LinuxONE county-context serving. An authorized runtime transfer and fresh host checks are now recorded in [verified execution](datathon-submission/verified-run.md). The [model summary](datathon-submission/model-summary.md) distinguishes metrics checked against the active evaluation from missing raw residual/ledger verification.

## Current WeatherNext path

Imports are explicit commands, dry-run by default with a scan cap and budget accounting. Access entitlement is separate from a successful connection. No app or notebook request automatically queries cloud data. Native cell IDs/geometry, source table, initialization/publication when known, validity, retrieval, resolution, units and processing remain attached.

Each forward-six-hour sum needs six distinct valid hourly values from one eligible initialization. Missing, null, negative, duplicate or stale inputs cannot become zero. Valid zero rainfall remains zero. Current freshness includes initialization age at most 12 hours, import age at most two hours and a valid window that has not ended. These project policies do not establish operational meteorological adequacy. Current forecasts remain absent from controls until a complete fresh input/assessment path is reviewed.

## Historical forecast path

The archive spans 25 hourly starts from October 9 midnight through October 10 midnight Central (05:00 UTC endpoints). Each start looks forward six hours; the final window ends October 10 at 11:00 UTC. Selected runs must supply those required hours without mixing initializations. Missing/stale replay inputs stay unknown, using the deliberate replay clock rather than today's age cutoff. Original import/source records are preserved. Unknown publication time means initialization-based reconstruction, not proven warning lead time.

The batch command plans this actual timeline and publishes each eligible assessment separately. Its coverage report records genuine source gaps. Catalog code and synthetic tests are separate from the now completed [verification of 25 existing real windows](datathon-submission/verified-run.md). New acquisition to fill gaps requires an explicitly selected window/budget; the importer does not manufacture missing hours.

## Geographic scales and joins

County polygon, parcel footprint, prepared terrain statistics, native weather cell and H3 display cell have distinct scales. Parcel rainfall requires verified positive-area native overlaps summing to full coverage within tolerance. Missing overlaps are not renormalized. A new snapshot must match the inspection artifact's exact source hash, not merely repeat cell IDs.

H3 rainfall is the maximum overlapping native rainfall where complete. H3 exposure is P90 over known parcel indices, while coverage includes all indexed members. Parcels may belong to multiple H3 cells; summed cell memberships are not unique county totals. H3 does not improve native weather resolution, infer building terrain or map inundation.

## Provenance and local storage

Retain source ID/URL, retrieval, license, horizontal/vertical CRS/datum, units, processing and content identities. Raw inputs stay under ignored `data/raw/`; derived databases/models/assessments under ignored `data/processed/`. Private transfer, host and review receipts stay in `.context/`. A public code checkout omits these files. Preserve source ownership terms and disclaimers; do not include raw property data or credentials in Git.

The [operations runbook](datathon-submission/operations.md) covers producer-supplied file hashes, semantic input auditing, saved-metric verification and cross-host parity. Inventory identity is not automatically the SQLite byte checksum. Synthetic tests establish software behavior only. No unknown, low index, empty message list or model promotion gate establishes safety.
