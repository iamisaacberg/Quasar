# Quasar demonstration package

Scope: Okaloosa County, Florida, FIPS `12091`. This package accompanies the implementation of the [PR #26 execution plan](../DATATHON-GAP-CLOSURE-PLAN.md). Team registration, labs, deadline administration and submission were excluded by Isaac for this work. No submission receipt or final recording is claimed.

## Read the package

| File | Purpose |
| --- | --- |
| [Architecture](architecture.md) | Current code, recorded runs and the separate target-host activation step |
| [Model summary](model-summary.md) | Target, recorded metrics, missing inputs and substantial subgroup weaknesses |
| [Sources and attribution](sources-and-attribution.md) | Checked primary references, dependency versions and unresolved permissions |
| [Problem and comparison](problem-and-comparison.md) | Analyst task, official alternatives and a testable benefit hypothesis |
| [Demo script](demo-script.md) | 175-second recording outline with conditional host wording |
| [Operations runbook](operations.md) | Transfer checks, parity, multiwindow generation, activation candidate and rollback |
| [Acceptance checklist](acceptance.md) | API evidence and Isaac's manual acceptance, kept separate |
| [Research protocols](research-protocols.md) | Remaining experiments, source gaps and decisions that require new evidence |
| [Limitations and claims](limitations.md) | Claims allowed by existing evidence and claims still unsupported |

The [workboard](../DATATHON-WORKBOARD.md) records task status. The base reviewed for this implementation is `507de03`; use the feature branch's final commit for a code handoff. The code reference is [this branch](https://github.com/iamisaacberg/Quasar/tree/iamisaacberg/datathon-rubric-handoff-v1), which requires a separate authorized push before it contains this local work. Judge access has not been checked. No `main` update is needed.

## Available locally

The source implements exact-window exposure catalogs, a dry-run replay batch command, transfer integrity checks, all-parcel parity comparison, saved-model evidence verification and a separate optional county NWS importer. Synthetic tests exercise production and selection across all 25 archive positions. These are software checks, not 25 real county artifacts or a target-host benchmark.

The documented real release comprises 113,818 parcels, the reconciled inputs, Marseille inspection database, a 45-cell archive and model `mapped-susceptibility-v1-7673922e5dca`. Its identities and expected relative paths are in [audit D1](../DATATHON-DEV-HANDOFF.md#d1--recover-and-verify-the-existing-artifacts-p0-incoming-developer--isaacmodel-owner) and [the recorded run](../modeling-run-v1.md). Those ignored files are absent in this checkout. Documentation supplies locations and identities; it does not transfer bytes. Do not access another workspace or reacquire weather/retrain to replace the missing bundle.

Private logs and receipts belong under `.context/datathon-evidence/`. Raw inputs stay under ignored `data/raw/`, and derived artifacts under ignored `data/processed/`. Publish only reviewed code and summaries consistent with source terms. No app service, cloud query, deployment, shared configuration, host inference or notification delivery was started by this implementation.
