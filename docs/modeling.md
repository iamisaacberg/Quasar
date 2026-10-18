# Offline parcel modeling

These commands prepare, train, evaluate, export and score an experimental FEMA
mapping proxy. PR #17 supplied the pipeline without trained weights. The
[first real-data run](modeling-run-v1.md), completed October 18, 2026 UTC
(October 17 Central), trained and exported a model locally from verified
LinuxONE inputs and passed the unchanged promotion gates. The subsequent
[LinuxONE activation](real-data-rollout.md#exposure-activation) serves all 25
archive positions using the host's checksum-matched staged model and evaluation.
That activated model stays in place. The straight-line ensemble added here is a
second scorer for the same exported trees, retained as a manual fallback; it does
not replace the current one or introduce separately trained weights.
Ignored datasets and trained artifacts are
not included in a repository clone. This mapping-proxy evaluation does not
establish observed-flood accuracy or actual LinuxONE performance.

Quasar learns patterns in FEMA mapped hazard areas from parcel
terrain and mapped stream proximity, then combines that estimate with six-hour
forecast rainfall to prioritize closer inspection. The resulting exposure index
is experimental. Prediction of actual flooding requires verified storm
observations and independent evaluation. The method omits storm surge, drainage
capacity, floor elevation, and observed water levels. Official NWS and local
guidance remain the authority for emergency decisions. Notification features
remain simulations.

Authoritative terrain manifests record elevation units as `meters` (NAVD88).
Parcel records use `m`. Area is square meters and mapped-stream distance is
meters before `log1p`. Audit accepts either manifest spelling and rejects other units.

**Training and promotion are run results, not a property of this source file.**
Check `evaluation.json` before describing a model as promoted.
Ignored county datasets are absent from this workspace. Synthetic tests do not
establish flood accuracy, county coverage, visual acceptance or LinuxONE execution.
County scope is Okaloosa, FIPS `12091`.

## Method

Stage 1 targets the fraction of parcel area mapped as FEMA Special Flood Hazard
Area. It measures agreement with regulatory mapping, not observed floods. Labels
require complete FEMA coverage without conflicting flags. Partial/unmapped areas
are unknown, and a zero mapped fraction does not establish safety.

The six ordered predictors are terrain minimum, mean, maximum and relief (NAVD88
meters), `log1p(parcel area m²)` and `log1p(distance to retained mapped streams m)`.
FEMA fields/derivatives, IDs, coordinates, H3, invented gauges and demo scores are
excluded. Terrain requires complete polygon statistics; separate point samples
never fill gaps. Mapped-stream distance retains incomplete coastal/lake/canal
coverage warnings and does not establish hydraulic connectivity.

Preparation verifies manifests, database/input hashes, inventory identity, units
(the manifest accepts `m` or the preparer's USGS spelling `meters`),
datum and actual polygon containment in the authoritative county geometry. It
assigns representative points to fixed 10 km EPSG:26916 squares, ordered by SHA256
of `42:<block>`, with cumulative 70/85% boundaries for development/validation/test.
At least ten occupied labeled blocks are required. Development polygons within
1 km of validation/test polygons are excluded; all missing/buffered rows remain
recorded. Five development blocks are required for grouped cross-validation.

Six XGBoost candidates use depths 2/3/4 × L2 regularization 1/10, squared-error
loss, eta .05, row subsampling .8, seed 42 and at most 400 trees. Five grouped
development folds select median best tree count (early stopping patience 40).
Validation RMSE selects configuration; ties prefer fewer trees, shallower depth,
then smaller L2. Five replicas use seeds 42–46. Average each member's clipped
`[0,1]` prediction. Population standard deviation describes model instability,
**not a confidence interval**. Constant-mean and standardized ridge (alpha 1)
baselines fit development only.

Reports include parcel/equal-block MAE and RMSE, zero/partial/full-target errors,
coverage, exclusions, source references/terms, parameters, versions, spatial
residual SVG and EPSG:26916 point table. An exclusive dataset-level
`test-evaluation.json` reservation prevents another training run using the same
test labels. Interrupted reservations are intentionally not automatically removed.
Do not recreate datasets to tune against test results.

Promotion requires >=10% lower test RMSE than both baselines under both weighting
schemes, >=90% test feature support, and native/portable error <=`1e-6` on 10,000
distinct development rows. Small experiments still produce unpromoted research
reports. Test support/out-of-range abstentions are always reported.

## Setup and local research

```sh
uv venv --python 3.12 .context/model-venv
uv pip install --python .context/model-venv/bin/python -r requirements-modeling.txt
```

Pinned ML/GIS dependencies stay outside the app/container. The checked Mac ARM
wheels exist; the checked versions do not publish s390x wheels. macOS XGBoost
needs OpenMP. Workspace verification used scikit-learn's bundled library without
changing system packages:

```sh
export DYLD_LIBRARY_PATH="$PWD/.context/model-venv/lib/python3.12/site-packages/sklearn/.dylibs"
```

The paths below are examples, not assertions that these artifacts exist. No
command downloads source data, queries BigQuery, configures a service or deploys.

```sh
python3 -m quasar.modeling audit \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/reconciled \
  --boundary data/raw/census_okaloosa_county.geojson

.context/model-venv/bin/python -m quasar.modeling prepare \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --output data/processed/okaloosa/modeling/dataset-v1

.context/model-venv/bin/python -m quasar.modeling train \
  --dataset data/processed/okaloosa/modeling/dataset-v1 \
  --output data/processed/okaloosa/modeling/experiment-v1

python3 -m quasar.modeling export \
  --experiment data/processed/okaloosa/modeling/experiment-v1 \
  --output data/processed/okaloosa/modeling/portable-model.json
```

Preparation writes `dataset.sqlite3` and a final `manifest.json`. Experiments write
five native saved JSON models, portable `model.json`, `evaluation.json`,
`MODEL_CARD.md` and spatial residual artifacts. Keep them under ignored
`data/processed/`; commit code/docs/synthetic fixtures only. No pickle is loaded.

Portable inference supports five numeric scalar regression ensembles with at most
400 bounded, acyclic trees per member and the exact feature schema. Both input
values and thresholds use XGBoost float32 comparison semantics. Signed tree-path
changes plus the baseline sum to raw susceptibility; clipping/ensemble averaging
are separate. Attributions are not SHAP values or physical causes. Standard-library
server inference imports no ML/GIS packages.

Two scorers read those same trees. `predict` is the current tree walk and remains
the scorer for the activated model and assessment production. `predict_compiled`
emits one straight-line function with the same comparisons and sums. It is a
manual fallback path for county-scale runtime, and bias edits still apply on each
call. Production continues to call `predict`; there is no automatic substitution
for missing inputs, stale forecasts or failed provenance checks. Both scorers
preserve unknown inputs. Revalidate a model after editing its trees before scoring
again. The compiled cache retains only the most recently used complete model and
is cleared by validation.

## Assessment production and benchmark

Use an inspection artifact prepared against the exact supplied forecast snapshot.
It verifies positive-area overlaps; overlapping native cells are rejected.
New snapshots require compatible inspection preparation. Rainfall requires full
parcel coverage (fraction sum within `1e-6` of one), unique cells and six complete
hourly values from one eligible initialization. Missing coverage is never filled
or renormalized. Current freshness preserves original snapshot expiry, init +12h
and retrieval +2h. Replay preserves decision/publication time and reconstruction
limitations. Inputs outside development feature ranges remain unknown.

The policy `susceptibility-rainfall-stress-v1` uses:

```text
rainfall_stress = rainfall_6h_mm / (rainfall_6h_mm + 50)
exposure_index = 100 * learned_susceptibility * rainfall_stress
```

The 50 mm constant is an uncalibrated visualization rule. A zero-rain index does
not rule out surge or other flooding. One nonnegative interaction factor accounts
for the final index; signed model attribution is separate. The result is not
flood depth, probability or safety guidance.

On LinuxONE, use system Python, with no ML/GIS installation:

```sh
python3 -m quasar.modeling assess \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --inspection data/processed/okaloosa/inspection/run-v1 \
  --model data/processed/okaloosa/modeling/portable-model.json \
  --evaluation data/processed/okaloosa/modeling/experiment-v1/evaluation.json \
  --weather data/processed/weathernext.json \
  --from 2026-10-17T20:00:00Z --mode current \
  --output data/processed/okaloosa/modeling/exposure-window-v1.json

python3 -m quasar.modeling benchmark \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --artifact data/processed/okaloosa/modeling/exposure-window-v1.json \
  --output data/processed/okaloosa/modeling/benchmark-v1.json
```

The timestamp is an example; choose an actually valid retained window. Only
promoted, checksum-matched, inventory/boundary-compatible models can produce
assessments. Production uses 256-row batches, one worker and an atomic new file,
limited to 128 MiB. Failures do not publish partial results or overwrite the old
artifact. Explicitly configure `QUASAR_EXPOSURE_FILE` after review; rollback
restores the previous artifact or unsets configuration to return to unknown.
No request starts training, production or cloud queries.

Host budget: **3 vCPUs, 8 GB RAM, 50 GB disk**. Training is local and bounded to
three threads. Production requires >=1 GiB free disk. Production plus R4–R7
aggregation targets <300 seconds and <2 GiB peak RSS. Benchmark results record
architecture, Python, wall time, peak RSS, artifact bytes/hash and disk free.
Local runs do not establish actual LinuxONE/full-county performance. No host
access or real county benchmark was performed in this implementation.

## Conditional observed-outcome research

`validate-outcomes` and `train-outcomes` take `--dataset`, `--observations`,
`--inspection`, `--weather <snapshot> [...]`, and (`train-outcomes`) `--output`.
They never fetch observations. Use a new output directory.

Observation JSON contains schema 1, county/inventory/boundary identities and
`records`. Required record fields:

- `parcel_id`, `episode_id`, decision `at`, and `label`: verified 0/1 or null.
- `association_verified: true`, `observed_coverage: true`,
  `mechanism: rainfall_driven`, nonnegative `spatial_uncertainty_m`.
- `source_id`, `source_url`, `source_retrieved_at`, `labeling_policy`,
  `coverage_evidence`, `observation_from`, `observation_to`, `forecast_sha256`.
- `reference_mode`: `as_issued` plus `reference_available_at <= at`, or
  `current_reference_retrospective`, which cannot establish as-issued lead time.

Source association/coverage declarations need source/human review; schema validation
cannot verify a real flood. Observations belong to the next six hours. Negatives
require explicit coverage of the entire window; absent/ambiguous/unverified records
are excluded, never negatives. Forecast hashes must match supplied inspection-verified
snapshots. Predictors are the six static features plus validated forecast six-hour
rainfall, first-three-hour rainfall and peak hourly rainfall accumulation, all in
mm. Future reference information is rejected. Missing publication times remain
initialization-based reconstructions, not proven as-issued predictions.

Readiness requires >=10 independent episodes, >=200 positive and >=200 negative
examples. The latest three episodes are the test set, each requiring both classes.
The preceding 20% (rounded up) form validation; earlier episodes form development.
A separate spatial holdout reserves every fifth sorted occupied block across all
episodes, excluding those blocks from training/tuning. At least five spatial blocks
and both classes in each remaining partition are required.

Compare standardized logistic regression (C=1) with six boosted classifiers:
depth 2/3/4 × L2 1/10, 200 trees, eta .05, subsampling .8, seed 42, three threads.
Validation average precision selects the tree configuration. Reports include
precision/recall at .5, average precision, false alarms/missed impacts, per-storm
results, event/spatial holdouts and exclusions. The separate outcome test ledger
prevents automatic test reuse. Save native classifier JSON, logistic coefficients,
split assignments and evaluation. Stage 2 remains research-only and never
automatically replaces Stage 1; readiness counts are not statistical sufficiency.

## Verification

Run the required Python suite, npm installation, check and test commands. Run
modeling tests inside the optional environment for native export, full training,
conditional outcome experiments and actual GIS containment. The 10,000-row
synthetic parity test checks numerical fidelity, not real model performance or
the real experiment promotion gate. Isaac reviews rendered visuals.
