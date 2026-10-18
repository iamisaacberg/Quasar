# Architecture and implementation status

Quasar is an Okaloosa County source-data application (FIPS `12091`). The [current architecture visual](datathon-submission/architecture.md) separates implemented code, recorded local training, the active directory release, fresh isolated LinuxONE inference and optional catalog verification. The [runtime contract](data-contract.md) defines fields and failure states.

## Runtime path

Explicit county preparation and WeatherNext import create validated snapshots and manifests. Local optional XGBoost training exports a dependency-free portable FEMA mapping proxy. Explicit offline assessment production combines its output with six complete native forecast hours. Immutable single-window artifacts can be selected by an optional exact-window catalog. The inventory host computes complete-inventory H3 P90 summaries; hosted Vercel instances proxy its authenticated HTTPS API. The browser receives only a public Mapbox token.

Python serves the API and committed React/Tailwind assets. The server/container needs no ML/GIS, Jupyter or Node runtime. The optional ML/GIS environment stays local. Training, inference, aggregation, serving and browser display are separate proof steps. The [recorded first run](modeling-run-v1.md) proves local training and one local assessment; the separate [verified execution checkpoint](datathon-submission/verified-run.md) now records fresh LinuxONE inference/cross-host parity and bounded checks of the already active API.

## Geometry, weather and exposure

County parcels require authoritative boundary validation; prepared inputs preserve source geometry, units/datum, coverage and identities. A parcel inventory is not a set of flood outcomes. H3 covers county intersections and may include the same parcel in more than one cell. Summing cell membership counts does not give a unique county total.

The default map is the October 9 archive with 25 hourly starts and a forward-six-hour window. Native WeatherNext rainfall stays at 0.1-degree resolution. H3 rainfall displays the maximum overlapping native value where coverage is complete. H3 exposure displays P90 across scored parcel members, with every member retained in the coverage denominator. Unknown scores stay transparent; they are never zero-filled or interpreted as safety. Reports/export remain source-rainfall products.

Model artifacts retain per-window forecast/model provenance. The optional catalog is bounded and resolves only listed files beneath an explicit server-side artifact root, verifies content hashes, and rejects mismatched inventory/model/source/window identities. It cannot fall back to a prior hour or single-file configuration. One decoded artifact and eight small summary cache entries bound retained data across hour changes; actual target-host measurements are recorded in the [verified execution checkpoint](datathon-submission/verified-run.md), separately from local fixture checks.

## Access and failure states

The hosted app is public. Source APIs require server-only tokens and read-only input access; hosted proxy failures remain unavailable. Snapshot fetching never refreshes data or produces assessments. The optional Wi-Fi launcher has its own local passphrase gate; it is not the hosted access flow. A Dockerfile is packaging code, not evidence of a real s390x container run.

The current NWS county importer is an optional explicit command. Its saved snapshot has bounded pagination, lifecycle handling and short expiry. The current-alert API is separate; the archive remains disconnected. No serving request fetches NWS or BigQuery. Empty, partial, invalid, stale and disconnected mean different things.

## Retired research paths

Fictional sites, illustrative five-factor scoring, what-if rainfall, simulated routes and notification previews survive only in offline modules/test fixtures. Their old HTTP routes return 410. They are not current UI features, observed property risk, road passability or message delivery. Optional notebooks import shared analysis functions and remain outside runtime.

Use the [operations runbook](datathon-submission/operations.md) for artifact verification, actual-host inference/parity, candidate activation and rollback. Current forecasts, scheduling, broader monitoring, observed-outcome research and user adoption still require the evidence in [research protocols](datathon-submission/research-protocols.md). No deployment, service restart or shared infrastructure change is implied by passing local checks.
