# First real-data model run

Completed **October 18, 2026 UTC (October 17 Central)** from PR #17's pipeline.
County scope: **Okaloosa, Florida, FIPS 12091**.

## What exists and where

| Item | Verified state at this checkpoint |
| --- | --- |
| Training/inference code | Added by PR #17; that PR did not contain trained weights |
| Prepared county inputs | Retrieved unchanged from the team's LinuxONE `/srv/quasar/data/`; all 13 transferred files matched remote SHA-256 checksums |
| Trained model | Created locally in the `philadelphia` workspace; five XGBoost members and a dependency-free portable export |
| Evaluation | Passed the unchanged FEMA mapping-proxy promotion gates described below |
| County assessment | Created locally for one six-hour archived forecast window; not the entire replay |
| LinuxONE activation | **Not performed.** The new model and assessment were not uploaded, configured or served |
| Flood-outcome validation | **Not established.** The target is FEMA mapped area, not observed floods |

Cloning the repository gives the code and this report, **not trained weights or
county datasets**. The model artifacts below are deliberately ignored. The server
supplied the prepared inputs; training ran on the Mac, not LinuxONE. No cloud
query, deployment, service restart or shared configuration change occurred.

## Inputs and spatial split

Inputs are the county-validated parcel inventory, `20261017-reconciled` terrain,
FEMA and mapped-stream records, and the authoritative Census county boundary.
The matching `20261018-marseille` inspection artifact was used for assessment.
Original retrieval times, source identifiers, terms, CRS, units and processing
records are preserved in the dataset/evaluation manifests. Parcel inventory
terms require Okaloosa attribution and its as-is, no-survey/no-legal-document
disclaimer. The local transfer receipt is
`data/raw/linuxone-transfer/receipt.json`.

The first real audit exposed one pipeline compatibility bug: the preparer retains
the USGS manifest unit `meters`, while the audit accepted only `m`. The audit now
accepts those two spellings, still rejects feet/unknown units, and preserves the
original manifest bytes. Individual terrain records still require `m` and NAVD88.
All subsequent checks, including actual county polygon containment, passed.

| Dataset partition | Parcel count |
| --- | ---: |
| Full inventory | 113,818 |
| Complete predictors | 112,280 |
| Complete predictors and eligible FEMA target | 112,237 |
| Development after spatial buffer exclusions | 98,358 |
| Validation | 3,165 |
| Untouched test | 7,910 |
| Development parcels excluded by 1 km holdout buffer | 2,804 |
| Unlabeled/ineligible | 1,581 |

Fixed 10 km EPSG:26916 blocks and seed 42 assign 21/4/5 blocks to
development/validation/test. After the buffer, 19 development blocks retain
training parcels. These three partitions have disjoint blocks. Splits are by
blocks, so their parcel counts need not follow 70/15/15 percentages.
Unknown terrain, invalid geometry and incomplete FEMA coverage were not filled.

## Trained model and evaluation

Model version: **`mapped-susceptibility-v1-7673922e5dca`**.

The target is FEMA SFHA fraction of parcel area. Predictors are terrain minimum,
mean, maximum and relief in NAVD88 meters, log parcel area and log distance to
retained mapped streams. FEMA-derived predictors, IDs, coordinates and H3 are
excluded. These are the unchanged PR #17 feature and target definitions.

Five grouped development folds and validation selection chose **depth 4, L2 1,
136 trees per member**. The final ensemble has five members with seeds 42–46,
eta 0.05, row subsampling 0.8 and squared-error loss. Training was limited to three
threads. Versions: Python 3.12.14, XGBoost 3.4.1, NumPy 2.5.4, scikit-learn 1.9.1.

Held-out metrics below use the same 7,792 supported test parcels for every model.
118 test parcels were outside development feature ranges and remain unknown.
Values are errors in **mapped-area fraction**, not flood probabilities or depths.

| Model | Parcel MAE | Parcel RMSE | Equal-block MAE | Equal-block RMSE |
| --- | ---: | ---: | ---: | ---: |
| Five-member ensemble | 0.039631 | 0.115756 | 0.074609 | 0.144684 |
| Development-mean baseline | 0.166738 | 0.233466 | 0.153155 | 0.198298 |
| Standardized ridge baseline | 0.129328 | 0.215976 | 0.182860 | 0.268382 |

| Unchanged promotion gate | Result |
| --- | --- |
| At least 10% lower test RMSE than both baselines, both weighting schemes | Passed: improvements 50.42% / 46.40% parcel-weighted and 27.04% / 46.09% equal-block, versus mean / ridge respectively |
| At least 90% test feature support | Passed: 98.5082% (7,792 of 7,910) |
| Native/portable parity on at least 10,000 distinct development parcels, error at most 1e-6 | Passed: 10,000 real parcels; maximum absolute difference 3.1861144e-7 |

`promoted: true` means **eligible under these experimental pipeline gates**. It
does not mean deployed, independently validated against floods, or approved for
safety decisions. Test evaluation occurred once; its dataset ledger is retained.
Do not recreate this dataset to tune against the reported test results.

Overall errors conceal important variation. Test MAE is 0.012002 on 6,567
zero-target parcels, 0.172181 on 1,015 partial-target parcels, and 0.262964 on
210 fully mapped parcels. The selected candidate's validation MAE on its 60
fully mapped parcels was 0.779924. These spatial/subgroup weaknesses remain in
the report; the overall gate pass does not remove them.

## Local assessment and timing

One assessment covers **2026-10-09 05:00–11:00 UTC**, or **00:00–06:00 Central**,
using the saved archive and its eligible 00:00 UTC initialization. Rainfall is a
forecast reconstruction, not an observation or proven as-issued publication.
The unchanged interaction is `100 * susceptibility * rain_mm / (rain_mm + 50)`.
The 50 mm constant is uncalibrated; a zero-rain result cannot rule out surge.

All **113,818** parcels are represented: **112,120** scored and **1,698** unknown.
The unknown set includes 1,538 parcels without complete terrain and 160 outside
training ranges; overlapping geometry/rainfall failure reasons are retained.
The JSON artifact is 73,259,210 bytes. Local production took 43.14 seconds;
production plus R4–R7 aggregation took **45.23 seconds**, with approximately
**393.2 MiB** peak RSS. This is Mac ARM64 evidence, **not an s390x benchmark**.

## Local artifacts and identity

All paths are relative to the workspace root and stay out of Git:

- `data/processed/okaloosa/modeling/dataset-v1/`: prepared SQLite, manifest and single-test ledger.
- `data/processed/okaloosa/modeling/experiment-v1/`: five saved native members, portable `model.json`, `evaluation.json`, `MODEL_CARD.md`, spatial residual JSON and SVG.
- `data/processed/okaloosa/modeling/portable-model-v1.json`: verified re-export for standard-library inference.
- `data/processed/okaloosa/modeling/exposure-replay-20261009T050000Z.json`: single-window county assessment and adjacent production benchmark.
- `data/processed/okaloosa/modeling/benchmark-local-v1.json`: local production plus aggregation report.

SHA-256 identifiers:

```text
Inventory: 0d8bf9c244cbae678108bbc8149d80c60db30f60824e24cd49435f2b93b4fd5a
Boundary:  03d0eb4232382046cf1bc85c77c3fd7b7178bb0ac9af8dafdc8c1de09c3b00f4
Dataset:   447374887feed64c7d11918aca14fff9715fedaf4eebdda48ed5cde98ba93f87
Model:     c3896f84e4593bbe20af909aade20edf7d46e43459b79e7aa79d5dc13188457f
Assessment:4c2283d716eaedd53c3f0f6d2c16224452f4b9f4ce317c08ee07921853f8b2c7
```

Verification reconciled artifact/native-model/dataset/ledger hashes, all split
counts, disjoint split blocks, supported and unknown test IDs, and recomputed
parcel/equal-block RMSE from saved residuals. Re-export exactly matched the
evaluated portable model. The required Python suite passed 193 tests with eight
optional skips; the isolated modeling environment passed all 193. npm clean
installation, type/syntax checks, 65 JavaScript tests and whitespace checks passed.

## Remaining boundaries

Activation would require explicitly transferring reviewed artifacts, verifying
inventory and forecast compatibility on LinuxONE, benchmarking there, and
configuring the intended assessment window. That work is not part of this
completed local training checkpoint. The single assessment cannot populate every
hour of the replay. Current stale forecasts remain stale.

Verified observed flood episodes and negatives with observation coverage remain
absent; the conditional outcome model has not been trained. FEMA reference dates,
incomplete coastal/lake/canal hydrography, missing floor heights and missing
hydraulic connectivity limit interpretation. No score is flood depth, flood
probability, an evacuation instruction or a guarantee of safety.
