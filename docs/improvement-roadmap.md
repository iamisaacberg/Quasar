# Improvement roadmap and research plan

## How to use this plan

This is a proposed backlog based on the reviewed code and project records, not a delivery commitment or a claim that the work has been implemented. It prioritizes trustworthy inputs and evaluation before additional predictive claims. Scope remains Okaloosa County, FIPS `12091`.

Priorities describe dependencies: **P0** resolves inconsistencies in the current demonstration; **P1** makes real inputs reproducible and usable; **P2** evaluates models and extends evidence; **P3** addresses a broader service only if explicitly in scope. The team should assign an owner and one reviewable outcome per task.

## P0 — Make status and validation consistent

These tasks can improve the present application without waiting for model training.

| Gap visible in the reviewed code | Proposed change | Acceptance evidence |
| --- | --- | --- |
| `notifications.preview()` rejects `weathernext` by name, while replay also exists; the UI hides previews outside synthetic mode | Use an explicit synthetic-scenario allowlist in the backend | Direct API tests reject current forecast and replay scenarios; ordinary synthetic previews still return zero sent |
| The acquisition manifest embeds status statements saying WeatherNext is unconfigured and no replay event is selected | Generate source-specific status from measured acquisition results; separate acquisition history from app runtime readiness | A new manifest no longer contradicts configured integrations or claim checks it did not perform |
| DEM metadata text combines EPSG:4326 and NAD83 labels, and catalog search uses a bounding box | Inspect actual raster/vendor CRS and datum; record correct references and candidate-search versus county-mask steps | A documented transformation with accurate horizontal/vertical references and a county coverage check |
| `/health` always reports process `ok` and default demo mode | Add a separate readiness/source-status summary while retaining a simple process probe | Missing, invalid, stale, and ready sources are distinguishable without treating an outage as a healthy feed |
| Forecast/replay/graph validation has different depth; WKT receives only a prefix check and advisory metadata gets limited validation | Define validation expectations per artifact and validate metadata consistency, IDs, timestamps, and geometry at the appropriate boundary | Malformed-artifact tests return explicit unavailable/invalid states rather than misleading values or uncontrolled exceptions |
| Browser replay selection is coordinated, but separate requests can read different file versions during import replacement | Add artifact version/checksum IDs and verify response agreement, or serve one consolidated replay snapshot | A replacement during a request sequence cannot mix source versions in one displayed selection |
| Some architecture/source notes predate new replay and acquisition paths | Reconcile status descriptions and attach dates to checkpoints | Docs distinguish implemented code, recorded acquisition, currently configured data, and validated results |

These are source-review observations. They have not been reproduced through a live service as part of this documentation task. Keep repairs in focused changes with behavior tests.

## P1 — Build a defensible real site dataset

### County geometry and asset inventory

Create a minimal-field adapter for permitted county parcels and/or building footprints. Choose whether an analysis unit is a parcel, building, or another site, and document how multipart assets and boundary crossings are handled. Avoid treating a centroid as the complete footprint.

Validate external geometry against the authoritative county polygon. Preserve holes, boundary cases, and excluded-record reasons. Keep source identifiers and an auditable mapping to normalized asset IDs. Remove owner/mailing fields before producing the modeling dataset.

**Completion evidence:** a source-term review, reproducible command, county-filtered inventory, rejection summary, schema, and small permitted fixture covering inside/outside/boundary cases. A FIPS-only filter or rectangular crop does not satisfy this milestone.

### Terrain, FEMA, and connected waterways

Normalize elevation rasters after verifying horizontal CRS, vertical datum, units, NoData, tile coverage, and acquisition dates. Decide whether the feature represents a point sample, footprint summary, surrounding terrain, relative local height, or floor elevation. Those quantities have different meanings.

Join FEMA zones using geometry and retain effective dates, mapping status, subtypes, and units/datum for any base flood elevation. Keep regulatory mapping distinct from a dynamic forecast. Build waterway features using a documented drainage relationship where possible; straight-line distance alone does not establish hydraulic connection.

**Completion evidence:** traceable site-feature tables, source versions, join coverage/missingness reports, known-case review, and tests for NoData, mismatched references, geometry overlap, and unsupported FEMA classes. Continue labeling mixed demonstrations while required features remain fictional.

### Gauge observations and local water conditions

The acquired USGS records identify stations. The next step is to select hydrologically relevant stations, acquire actual timestamped measurements, and define their connection to sites or catchments. Record measurement quality, units, vertical reference, flood-stage definition, sensor age, and outages.

Evaluate whether canal operations, coastal water level, tides, surge, antecedent wetness, drainage capacity, and other locally relevant factors belong in the research question. These are candidate inputs to investigate, not factors whose predictive value is established here.

**Completion evidence:** documented station selection and association, observation provenance, stale/missing behavior, compatible stage thresholds, and domain review. The current fixed 1.2 m margin in forecast/replay modes must not be described as observed water level.

## P1 — Make forecast imports reproducible at useful coverage

Retain explicit import commands, dry-run defaults, and byte caps. Extend beyond the six curated coordinates only after real assets pass county validation. Estimate query size before expanding coverage and preserve native cell associations so repeated sites can reuse source values without pretending the grid became finer.

Introduce a consistent artifact manifest with schema/model versions, row counts, source/table ID, initialization, validity, publication timing when known, retrieval time, checksum, units, spatial coverage, and transformation command. Preserve validated normalized snapshots when a refresh fails and expose failure separately from the last usable artifact.

Review freshness policies against actual source update/publication behavior and the intended exercise. Do not widen thresholds merely to keep a green status. Any future scheduling should be a deliberate design change with bounded cost, observability, and explicit operational ownership.

**Completion evidence:** reproducible imports across selected windows, measured dry-run/actual bytes and latency, duplicate/boundary handling, per-site completeness, source-status reporting, and a failure/recovery demonstration. Cloud entitlement alone is insufficient.

## P1 — Connect official alerts with honest coverage

Extend the existing point client with documented county/zone/polygon matching, expiration handling, caching, bounded retries/backoff, pagination, and source-age reporting. Define separate states for connected with active alerts, connected with no matching alerts, stale cached alerts, upstream error, and not connected.

Keep official messages identifiable as source material and distinct from Quasar's heuristic results. A nonmatching alert response is not an assertion that a site has no flood hazard.

**Completion evidence:** representative matching and expiration cases, pagination/outage tests, preserved issue/effective/expiration/retrieval times, and a UI that cannot turn an unavailable feed into an all-clear.

## P2 — Establish historical truth before model evaluation

The current reconstruction can replay archived **forecasts**. It does not contain an observed local flood-outcome dataset. NHC text supplies storm context; it does not label which Okaloosa assets flooded or which roads were passable.

For the selected event, document its relevance to the county and acquire independent outcomes with spatial/time coverage and quality limitations. Potential research targets include a documented inundation extent, measured water level, or a verified impact label. A road-closure record and a building-flood record are different outcomes and need different tasks.

Reconstruct what was knowable at each decision time. Preserve model initialization, forecast publication, source observation, retrieval, and outcome times. Exclude future information from predictor features. Where publication timing cannot be established, retain the initialization-based label and qualify any lead-time analysis.

**Completion evidence:** an event/source inventory, a reproducible replay manifest, time-aligned predictor/outcome tables, documented exclusions, and a clear account of what is observed versus reconstructed. A compelling replay animation alone is insufficient.

## P2 — Evaluate the heuristic and any trained model

### Define the prediction task

Choose one target with units and a time horizon before selecting an algorithm. Examples are classification of a documented impact within a window or estimation of a measured level at a gauge. These are candidate experiments, not current capabilities. A 0–100 relative score is not automatically a suitable target or probability.

Freeze a versioned baseline and a dataset snapshot. Split development and evaluation by event/time and, where relevant, location. Randomly splitting adjacent hours from the same storm can leak shared conditions across the split. If only one suitable event exists, state that limitation and avoid broad generalization claims.

### Measure the right things

| Evaluation question | Candidate evidence | Interpretation limit |
| --- | --- | --- |
| Does the system have enough data? | Completeness, staleness, and scoring coverage by site/time/source | Coverage is not predictive skill |
| Does a binary classifier identify documented impacts? | Precision, recall, confusion matrix, precision-recall curve, alert burden | Requires trustworthy positive/negative labels and a declared threshold |
| Are probabilities trustworthy, if a probability model is introduced? | Reliability/calibration assessment and Brier score | Current heuristic cannot be evaluated as a calibrated probability without a defined mapping |
| Does a numeric prediction match a measurement? | MAE/RMSE and residuals by event/location | Only meaningful for a defined numeric target and units |
| Are high-priority sites ranked usefully? | Ranking or top-k capture against independent outcomes | Does not establish depth or probability accuracy |
| How early can a result be available? | Lead time measured from documented data availability | Initialization time alone may overstate available warning time |
| How stable are results? | Event-level variation, uncertainty intervals, missingness and feature sensitivity | Small samples may prevent reliable uncertainty estimates |

Select a subset appropriate to the target; this table is a research menu, not an implemented evaluation suite. Report both false negatives and false positives. Count unknown outputs separately so abstaining on difficult cases cannot inflate apparent performance.

### Compare and document

Compare the unchanged heuristic with simple defensible baselines before adding complexity. Test feature groups separately to learn whether terrain, regulatory zones, gauge association, or weather adds useful information. Evaluate candidate coastal/drainage features against held-out outcomes rather than adding them because they sound relevant.

If training a model, keep shared feature and inference code in `quasar/`, and preserve training data/version, target, split strategy, feature availability, preprocessing, hyperparameters, random seeds, evaluation results, limitations, and intended use. Check Linux `s390x` support before adding compiled packages to the runtime.

**Completion evidence:** a reproducible evaluation report with held-out results and limitations. No numerical performance targets are prescribed here; the team must choose defensible targets after assessing data and intended use. Until then, keep the heuristic labeled unvalidated.

## P2 — Improve routing evidence and realism

Keep the existing routing exercise usable while treating real routing as a separate evidence problem. A future graph would need directionality, turn restrictions, usable connectivity, access rules, and verified destination information. Flood-related restrictions require road-specific observations or a separately validated passability method; a site score or H3 color is not enough.

Document time-varying conditions if travel is modeled across multiple hours, and account for closures or destination changes during the trip. Define behavior for uncertain segments, stale restrictions, inaccessible destinations, and disconnected graphs.

**Completion evidence:** sourced graph semantics and restriction timestamps, destination status provenance, reviewed route cases, and evaluation against known conditions. Maintain exercise labels until those requirements are met; current two-way topology and uniform speed are not navigation evidence.

## P2 — Improve explanation, accessibility, and analysis workflows

Expose source freshness and missing reasons alongside score summaries and map colors. Test whether readers can distinguish a real forecast from synthetic terrain, a hazard zone from a forecast, a site from an H3 cell, and an unknown result from low exposure.

Review keyboard access, focus behavior, contrast, screen-reader announcements, chart tables, reduced motion, and print layout. Use Isaac's visual review for the rendered interface. Keep the list/report fallback useful when maps fail. Preserve unknowns in every download and avoid countywide labels for six-point summaries.

For notebooks, assign one owner per experiment, import shared functions, record findings in markdown, and commit clean source without saved outputs/execution counts. Promote reusable transformations into Python modules so app and notebook results cannot diverge.

**Completion evidence:** documented review cases, resolved usability findings, accessible alternatives, consistent report/API values, and reproducible notebook execution. Automated controller tests do not establish visual quality or reader understanding.

## P2 — Demonstrate IBM Z and measure scale

Run the actual dependency set, required checks, and a representative application workload on the authorized LinuxONE/IBM Z environment. Verify the base image, `s390x` availability, permissions for mounted snapshots, and actual execution. Container portability intent and x86 CI are separate evidence.

Measure real-site ingestion, forecast association, scoring, report/export generation, and browser response at increasing dataset sizes. The current implementation reads JSON files and rebuilds report/timeline data; it has not demonstrated countywide scale. Profile first, then consider indexed artifact storage, bounded caches, pagination, or server-side aggregation where measurements justify them.

Keep cloud querying separate from serving. If preprocessing runs elsewhere, transfer credential-free normalized artifacts with checksums. Do not place Google credentials in the browser or image.

**Completion evidence:** target-host run record, versions, required check results, representative request results, resource/latency measurements, and documented remaining limits. Access to the team's host requires explicit authorization.

## P3 — Consider a broader service only when authorized

The local server and optional shared Wi-Fi password gate are appropriate to a controlled demonstration. Broader hosting would require a suitable application server, individual access control, HTTPS operations, request limits, logging/monitoring, artifact/version management, recovery procedures, and a clear source-refresh owner. Database and worker choices should follow measured requirements.

Real notifications are a separate scope decision. They would require explicitly authorized contact collection, persistent consent, unsubscribe, deduplication, delivery credentials, provider behavior, retry handling, auditability, and reviewed message policy. The present datathon flow remains simulation-only.

**Completion evidence:** an approved service scope and operational runbook, followed by the authorized implementation and verification. This roadmap does not authorize deployments, infrastructure changes, real messages, or contact collection.

## Suggested sequence and team handoffs

| Milestone | Suggested lead area | Reviewable output | Depends on |
| --- | --- | --- | --- |
| Consistent demonstration state | App/integration | Focused validation and status fixes, updated contracts/docs | Current source review |
| County asset foundation | Data/GIS | Minimal, permitted inventory with containment and missingness evidence | Source terms and analysis-unit decision |
| Real feature pipeline | Data/GIS + modeling | Reproducible terrain/FEMA/gauge/weather features with provenance | County asset foundation |
| Historical benchmark | Research/modeling | Time-aligned predictors and independent outcomes | Suitable event/outcome access |
| Baseline evaluation | Modeling | Versioned held-out results and limitations | Historical benchmark |
| Clear presentation | Frontend + reviewers | Source-aware map/reports, accessibility and visual review | Stable contracts and representative results |
| IBM Z demonstration | Integration | Actual target-host run and measured limits | Authorized host access and dependency review |
| Broader service | Team/product owner | Explicit scope, service design, and operational evidence | Demonstrated need, validation, and authorization |

These are suggested responsibilities, not assigned people. Coordinate shared contract/API changes before implementation. Notebook research and target-host preparation can proceed alongside compatible work, while reusing stable Python interfaces.

For each task, capture the question, current gap, owner, inputs/output contract, source status, failure behavior, acceptance evidence, and remaining limitations. Keep changes on feature branches and use reviewed pull requests into `preview`.

## Questions to settle before expanding scope

- Is the next demonstration focused on exposure explanation, historical forecast reconstruction, or route restriction exercises?
- Which real analysis unit and independent outcome can the team actually obtain and legally use?
- Can source publication timing be recovered, or must historical results remain initialization-based?
- Which local water processes need domain review before choosing more features?
- What amount of coverage, latency, and uncertainty is sufficient for the declared research task?
- What target-host access and review ownership are available for the IBM Z demonstration?

Use the [premise](app-premise.md) to keep the product claim narrow, the [data guide](data-guide.md) to preserve evidence, and [mechanisms](mechanisms.md) to locate the implementation.
