# Verified execution checkpoint

Verified October 18, 2026 UTC / October 17 Central. Scope: Okaloosa County, FIPS `12091`. Isaac authorized artifact transfer and offline LinuxONE inference/benchmarking. No service configuration, restart, deployment, new forecast acquisition or retraining was performed in this work.

## Source and artifact identities

The feature branch was reconciled with `preview` at `d920a8d` (through PR #30). The isolated target-host run used runtime archive revision `f40e1b0`; subsequent local changes affect the optional NWS importer/docs, not its model arithmetic. The pre-existing active release remained `/opt/quasar/releases/edmonton-exposure-20261018`, using `QUASAR_EXPOSURE_DIRECTORY`. The new optional catalog does not replace that configuration.

An authorized transfer copied **91 existing files**: county runtime inputs/manifests, saved archive, active portable model/evaluation, 25 assessments, benchmarks and receipts. Every file matched the source host's recorded SHA-256. No raw data or weights are committed.

| Identity | SHA-256 / identifier |
| --- | --- |
| Inventory | `0d8bf9c244cbae678108bbc8149d80c60db30f60824e24cd49435f2b93b4fd5a` |
| Authoritative boundary | `03d0eb4232382046cf1bc85c77c3fd7b7178bb0ac9af8dafdc8c1de09c3b00f4` |
| Active model | `5fbfe10500f05e1b5fbd16ebc622b52596489aa19aea479ab063cf872d0535a7` |
| Active evaluation | `eae3f735b38e10a3876f19aa7632dced8aa74645767746ea3ecbf38e93be9967` |
| Active training dataset ID | `8ab0884720f21ce9fe492b8c1aabe317e28850f82857ab0dff880a3a1c057179` |
| Fresh LinuxONE assessment | `a707ebbd0760c293df188ee0a40671a32077332a5e194060398142b5e8cfe274` |
| Matching fresh Mac assessment | `95b9bbc999c046d599e4e27297e9e0484a5852df6998ef7f4b46364fede5456e` |

The active model retains version `mapped-susceptibility-v1-7673922e5dca`. Its byte hash/dataset ID differ from the [earlier local training report](../modeling-run-v1.md). Preserve both records; do not substitute one identity into the other. Model/evaluation identities match each other and the current inventory/boundary audit. Original dataset, native members, residuals and the retained test ledger were not on the staged host. Isaac also authorized copying the documented two original folders, but the Philadelphia workspace path no longer exists and its archived context contains neither folder. No source files were copied, training rerun or ledger changed. A backup is required for independent training-lineage/arithmetic verification.

## Actual county checks and inference

The input/inspection audit passed for **113,818 parcels**. A separate Shapely check tested the actual valid parcel polygons against the authoritative county polygon: **113,803 covered valid polygons, zero outside, 15 invalid/empty geometries retained as unknown**. This checks geometry containment, not flood outcomes.

Fresh standard-library inference on actual **LinuxONE `s390x`, Python 3.12.3, three logical CPUs**, covered October 9, 2026, 05:00–11:00 UTC. It produced **112,120 scored and 1,698 unknown** assessments. Overlapping missing-reason categories must not be added as unique parcel totals.

| Measurement | Actual result |
| --- | ---: |
| Production | 85.37 seconds |
| R4–R7 aggregation | 4.29 seconds |
| Production plus aggregation | **89.66 seconds** |
| Peak process RSS | **292,741,120 bytes (279.18 MiB)** |
| Free target disk after production | 32,282,394,624 bytes |
| Unique parcel comparison against fresh Mac run | **113,818 compared, zero mismatches** |

The Mac run used the same transferred inputs/model and took 42.85 seconds for production. Full-parcel cross-host comparison preserved known/unknown status, missing reasons and exact method/source/window identity, with fixed absolute tolerances of `1e-6` for model details and `1e-5` for rounded score/factors. The fresh LinuxONE result also matched the previously activated first-hour assessment across every parcel. Run IDs/computation timestamps legitimately differ.

## Replay and API checks

All **25 existing real six-hour assessments** were validated against their producer hashes, active model/forecast/inventory and full parcel counts, with R4–R7 summaries. A local catalog exercised the first/middle/last hour, a return to the first hour and an unsupported hour. The local verification took 43.24 seconds and 772.42 MiB peak RSS; that is Mac evidence. The new catalog remains an unactivated candidate. The same validation/switching on actual LinuxONE passed in **101.98 seconds at 586,162,176 bytes (559.01 MiB) peak RSS**, with the identical catalog hash `2112e81ca957cbd5a168a92618c2d63635cb1710578349ba0de220f87c0f85f6`. The service remained active on its original directory release.

Seven bounded read-only public API requests verified the existing app path: first/middle/last archive summaries were ready and reported `s390x`/the active model; a matching-run lookup returned scored parcel **19144** and unknown parcel **1001** with `complete_terrain_required`; an unsupported hour returned `unavailable`; an obsolete run returned `changed`; the direct source rejected an unauthenticated read with **401**. Successful summary/parcel requests took approximately 2.77–3.14 seconds in this small declared sample. This is not a load test, p95 estimate or rendered review.

The optional county NWS importer successfully fetched the canonical official county endpoint at **2026-10-18T03:42:57Z** after an initial redirect failure was reproduced and fixed. The saved snapshot expires after 120 seconds and becomes stale; no refresh job or current-alert UI was activated. Source text/lifecycle and retrieval remain saved privately. The archive stays disconnected from present-day alerts. No empty response is an all-clear.

## Remaining evidence

Isaac's rendered/accessibility acceptance, an actual recovery test, source/UI sharing permissions, original training reproducibility artifacts, a recording/rehearsal, independent observed outcomes and actual user/domain research remain open. Team/lab/deadline/submission administration was excluded. Core/research/JavaScript checks are recorded in the [workboard](../DATATHON-WORKBOARD.md); private logs, hashes, actual commands and outputs are indexed under `.context/datathon-evidence/`. No flood depth, probability, property safety or observed-flood validation is established.
