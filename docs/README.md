# Quasar documentation

Quasar displays Okaloosa County parcels, prepared terrain/FEMA reference inputs,
and imported native forecast rainfall. The application has no fictional-site or
synthetic fallback; real parcel scores remain unknown without separate matching
assessments. Start with the [current runtime contract](data-contract.md) and
[activation checklist](real-data-rollout.md). Older explanatory guides retain
clearly marked offline research context.

These guides describe the code and existing project records reviewed on **October 17, 2026**, including local work in progress. They do not certify a deployed build, current source availability, current snapshot freshness, historical accuracy, or IBM Z execution. Runtime status must be checked separately.

## Read by topic

| Document | What it answers |
| --- | --- |
| [App premise](app-premise.md) | What problem does Quasar explore, who is it for, and what can the current demonstration establish? |
| [Data guide](data-guide.md) | Which inputs exist, which are fictional, how are sources associated with sites, and how are quality and provenance preserved? |
| [Mechanisms](mechanisms.md) | How do scoring, import, replay, routing, the browser, reports, exports, and APIs work? |
| [Improvement roadmap](improvement-roadmap.md) | What should improve, why, in what order, and what evidence would count as completion? |

Start with the premise for a project introduction. Read the data guide before interpreting any score. Use mechanisms when changing code. Use the roadmap when assigning the next experiment or implementation task.

## Existing technical references

The guides explain the whole application; the following files retain the detailed contracts and task instructions.

| Reference | Purpose |
| --- | --- |
| [Root README](../README.md) | Local setup, demonstration walkthrough, commands, and project overview |
| [Teammate exposure handoff](TEAMMATE-HANDOFF.md) | WeatherNext/LinuxONE direction, implemented display, required assessment artifact and remaining integration work |
| [Exposure display contract](exposure-display.md) | Optional assessment artifacts, fixed palette, complete-inventory P90 summaries and exposure API |
| [Architecture](architecture.md) | Runtime structure, scoring baseline, browser aggregation, and portability boundaries |
| [Data contract](data-contract.md) | Record fields, API payloads, forecast schemas, replay additions, and export semantics |
| [Source catalog](data-sources.md) | Source identifiers, access history, acquisition checkpoints, and pending integrations |
| [Parcel input preparation](parcel-inputs.md) | Optional local GIS environment, elevation coverage and unscored FEMA/mapped-waterway joins |
| [Integration setup](integrations.md) | Mapbox, WeatherNext, H3, and the recorded October 17 forecast import |
| [LinuxONE data bridge](data-bridge.md) | Authenticated reads of normalized snapshots from IBM LinuxONE into the Vercel API |
| [Isaias exercise](isaias-demo.md) | Replay preparation, archive versus what-if behavior, and routing walkthrough |
| [Notebook workflow](../notebooks/README.md) | Optional research environment, shared functions, notebook ownership, and clean source files |
| [Team workflow](../CONTRIBUTING.md) | Ownership, focused changes, review, and pull requests into `preview` |
| [Agent instructions](../AGENTS.md) | County scope, data handling, development checks, and authorization boundaries |

## Common tasks

| Task | Follow |
| --- | --- |
| Run the county source-data app | [Run locally](../README.md#run-locally) |
| Configure the map or import current rainfall | [Integration setup](integrations.md) |
| Prepare historical context and exercise roads | [Local replay preparation](isaias-demo.md#local-data-preparation) |
| Understand a displayed score | [Scoring mechanism](mechanisms.md#scoring-mechanism) |
| Work in Power BI or Tableau | [Reports and downloads contract](data-contract.md#reports-and-downloads) |
| Explore data in a notebook | [Notebook workflow](../notebooks/README.md) |
| Select the next engineering task | [Improvement roadmap](improvement-roadmap.md) |

## Reading results correctly

- A score is relative demonstration output, with no flood-depth or calibrated probability meaning. A lower relative score is not a safety determination.
- Unknown inputs remain unknown. A blank score, a stale forecast, unavailable road data, and a disconnected alert feed have different meanings.
- Imported rainfall does not validate fictional site attributes. Native weather cells, H3 display cells, and site geometry serve different purposes.
- Downloaded research files do not establish completed normalization, integration, or evaluation.
- Historical forecast reconstruction does not establish observed flooding or exactly what was publicly available at the time unless publication timing is documented.
- Simulated routes and notification previews are retired from the application. Follow official NWS and local emergency guidance for real decisions.

## Maintaining these docs

Update field and API changes in [data-contract.md](data-contract.md) alongside code. Update the explanatory guides when behavior changes, and move roadmap items to completed only when their acceptance evidence exists. Record source checks with dates; keep changing local status in runtime responses or acquisition manifests instead of describing an old snapshot as live.

Documentation changes alone do not require a data download, cloud query, running service, or deployment.
