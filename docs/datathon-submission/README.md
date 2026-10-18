# Quasar demonstration package

Scope: Okaloosa County, Florida, FIPS `12091`. This package accompanies the implementation of the [PR #26 execution plan](../DATATHON-GAP-CLOSURE-PLAN.md). Team registration, labs, deadline administration and submission were excluded by Isaac for this work. No submission receipt or final recording is claimed.

## Read the package

| File | Purpose |
| --- | --- |
| [Verified execution](verified-run.md) | Fresh county transfer/containment, LinuxONE run, cross-host parity and live API checks |
| [Architecture](architecture.md) | Current code, recorded runs and the separate target-host activation step |
| [Model summary](model-summary.md) | Target, recorded metrics, missing inputs and substantial subgroup weaknesses |
| [Sources and attribution](sources-and-attribution.md) | Checked primary references, dependency versions and unresolved permissions |
| [Contribution record](contribution-record.md) | Preserved commit history, reused code and third-party UI provenance |
| [Problem and comparison](problem-and-comparison.md) | Analyst task, official alternatives and a testable benefit hypothesis |
| [Demo script](demo-script.md) | 175-second recording outline with conditional host wording |
| [Operations runbook](operations.md) | Transfer checks, parity, multiwindow generation, activation candidate and rollback |
| [Acceptance checklist](acceptance.md) | API evidence and Isaac's manual acceptance, kept separate |
| [Research protocols](research-protocols.md) | Remaining experiments, source gaps and decisions that require new evidence |
| [Limitations and claims](limitations.md) | Claims allowed by existing evidence and claims still unsupported |

The [workboard](../DATATHON-WORKBOARD.md) records task status. The starting base was `507de03`, reconciled with `preview` through `d920a8d`; use the feature branch's final commit for a code handoff. The code reference is [draft PR #33](https://github.com/iamisaacberg/Quasar/pull/33), targeting `preview` from [this branch](https://github.com/iamisaacberg/Quasar/tree/iamisaacberg/datathon-rubric-handoff-v1). Intended judge access has not been checked. No `main` update is needed.

## Available locally

The source implements exact-window exposure catalogs, a dry-run replay batch command, transfer integrity checks, all-parcel parity comparison, saved-model evidence verification and a separate optional county NWS importer. Synthetic tests exercise production and selection across all 25 archive positions. Separate [real-data verification](verified-run.md) checked the 25 existing county artifacts, fresh LinuxONE inference/aggregation and full-parcel cross-host parity.

The documented real release comprises 113,818 parcels, the reconciled inputs, Marseille inspection database, a 45-cell archive and model `mapped-susceptibility-v1-7673922e5dca`. Its identities and expected relative paths are in [audit D1](../DATATHON-DEV-HANDOFF.md#d1--recover-and-verify-the-existing-artifacts-p0-incoming-developer--isaacmodel-owner) and [the recorded run](../modeling-run-v1.md). An authorized 91-file transfer now supplies the runtime inputs, active model/evaluation and all 25 assessments in this checkout. Original training dataset/native members/residuals/test ledger remain missing. The active artifact identities differ from the earlier report and are documented separately in [verified execution](verified-run.md). A future clone still requires a separate transfer; only the subsequently authorized Philadelphia path/archive metadata was checked, and its original data folders were missing.

Private logs and receipts belong under `.context/datathon-evidence/`. Raw inputs stay under ignored `data/raw/`, and derived artifacts under ignored `data/processed/`. Publish only reviewed code and summaries consistent with source terms. This implementation performed authorized isolated offline host inference/benchmarking and a bounded current NWS fetch. It changed no running service/configuration, started no deployment or cloud forecast query, and sent no notifications.
