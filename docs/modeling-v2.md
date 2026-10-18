# V2 datathon exposure-model experiment

V2 builds on the existing FEMA mapping proxy. Its six predictors, squared-error
XGBoost family, five-member ensemble, portable tree format, county FIPS `12091`,
and six-hour exposure horizon remain the same. It is the intended next demo
model **only if its frozen engineering gates pass**. V1 is an archived comparison
baseline, not a fallback when v2 fails or is unavailable. The running service is
not changed by this implementation or by a local training command.

## Scientific purpose

The learned component estimates FEMA SFHA fraction from terrain, area and stream
distance. Its defensible task is reconstruction of mapped susceptibility from
those independent predictors. Where actual FEMA coverage is available, that
coverage remains the reference: learning an approximation does not by itself add
flood-prediction value. Feature ablations and simple predictive baselines test
whether the learned approximation contributes useful mapping information.

The exposure layer still uses `100 * susceptibility * rain_mm / (rain_mm + 50)`.
The constant is uncalibrated. A fraction of .2 caps this index at 20 regardless of
rain; zero rain gives zero even though surge or upstream flooding may exist.
No index is depth, probability, a safety determination or official guidance.
Reference-versus-model comparisons and sensitivity runs are not flood validation.
Current terrain/FEMA reference retrievals do not establish what was known before
the replay. Missing forecast publication times remain initialization-based
reconstructions; no demonstrated warning lead time follows from this experiment.

## Frozen experiment and artifact handoff

The implementation freezes `mapping-proxy-nested-spatial-v2` in
`quasar/modeling/v2.py`; every run writes the full protocol and its hash before
training. Changes to that protocol require a new reviewed experiment, not an
after-the-fact adjustment to gates.

Required private bundle:

- County parcel SQLite and adjacent manifest; reconciled inputs directory;
  authoritative county boundary; inspection SQLite/manifest; existing archive.
- Original dataset SQLite/manifest, test ledger, model/native member files,
  evaluation, residuals and split assignments when available.
- Expected hashes and source manifests retaining retrieval, terms, CRS, units
  and processing. Keep raw and processed data under their ignored directories.

`review` distinguishes missing artifacts from invalid artifacts. A missing
original test ledger or native member is an evidence gap, never fabricated.
Dataset serialization IDs from separate runs must remain distinct. Reconstruction
from existing inputs must record source checksums, split assignments and counts;
it must not claim to recover a different serialized database or absent ledger.

The research pool contains only the original development and validation rows.
Original test rows are filtered out by SQL before their JSON is loaded. The old
test ledger, if present, is hashed and preserved. A separate exclusive
`v2-experiment.json` reserves one controlled experiment. A failed/interrupted run
does not automatically release that reservation or allow another tuning attempt.

## Evaluation and retraining

- Five outer geographic folds; three inner tuning folds; existing 10 km blocks
  in EPSG:26916. Each split removes fit parcels within 1 km of actual held-out
  parcel polygons. Insufficient blocks/support is an explicit failure.
- Candidate sample weights balance zero/partial/full mapped targets. Calculate
  `min(5, n / (nonempty_groups * group_count))` on each fit subset, then normalize
  to mean one. Held-out targets never determine fit weights.
- Six configurations: depths 2/3/4, L2 1/10; learning rate .05, at most 400 trees,
  early stopping 40, subsampling .8, three threads. Candidate selection uses mean
  zero/partial/full MAE; unweighted selection uses RMSE. Median inner best rounds
  determines the refit size; ties prefer fewer rounds, lower depth, then L2.
- Refit mean, standardized ridge and unweighted XGBoost inside every outer fold.
  Final candidate and outer ensembles use seeds 42–46. Terrain-only and
  stream-distance-only ablations use the candidate settings selected inside each
  outer training set, without separately tuning ablations. Combined uses all six
  features, including parcel area.
- All comparators use common, explicitly reported feature support. Out-of-range
  parcels stay unknown. Report pooled and per-fold parcel/equal-block errors,
  zero/partial/full support and errors, out-of-fold references/predictions,
  per-block residuals, and a geographic residual SVG.

All gates must pass: at least 10% lower macro subgroup and fully mapped MAE than
unweighted XGBoost; at most 5% worse parcel/equal-block RMSE; at least 10% lower
RMSE than mean and ridge under both weighting schemes; at least 90% feature
support; and portable/native error <=1e-6 on >=10,000 distinct eligible rows.
The report identifies cross-validation on existing research data, not a fresh
untouched external test. These engineering thresholds do not establish flood
accuracy, statistical sufficiency or calibrated uncertainty.

## Explicit local commands

Use the optional pinned research environment from `modeling.md`. On the checked
Mac, set `DYLD_LIBRARY_PATH` to that environment's `sklearn/.dylibs` directory for
XGBoost's existing OpenMP dependency. No native ML/GIS dependency is added to the
app/container.

```sh
MODEL_DATASET=data/processed/okaloosa/modeling/dataset-recovered
MODEL_DATABASE=data/processed/okaloosa/linuxone/quasar-parcels.sqlite3
MODEL_INPUTS=data/processed/okaloosa/parcel-inputs/20261017-reconciled
MODEL_BOUNDARY=data/raw/census_okaloosa_county.geojson
MODEL_INSPECTION=data/processed/okaloosa/parcel-inspection/20261018-marseille
MODEL_WEATHER=data/processed/isaias-2026.json
MODEL_RUN=data/processed/okaloosa/modeling/experiment-v2

python -m quasar.modeling train-v2 --dataset "$MODEL_DATASET" \
  --database "$MODEL_DATABASE" --inputs "$MODEL_INPUTS" \
  --boundary "$MODEL_BOUNDARY" --inspection "$MODEL_INSPECTION" \
  --output "$MODEL_RUN"

python -m quasar.modeling review --dataset "$MODEL_DATASET" \
  --experiment "$MODEL_RUN" --database "$MODEL_DATABASE" \
  --inputs "$MODEL_INPUTS" --boundary "$MODEL_BOUNDARY" \
  --inspection "$MODEL_INSPECTION" --weather "$MODEL_WEATHER" \
  --research-sensitivity --output data/processed/okaloosa/modeling/review-v2
```

Use new output paths. Exit 2 means incomplete evidence, research-only results, or
unavailable inputs, rather than a qualified model. `review --output <new-dir>`
alone produces a missing-bundle inventory. The research sensitivity option can
analyze rejected candidates: it writes summary comparisons for the non-test pool,
not serveable assessment artifacts. It computes static predictions once and
evaluates all 25 existing replay positions at constants 25/50/100 mm, recording
band distributions, top-decile overlap, tie-aware rank correlation, zero-rain
behavior, caps, reference gaps, and source status. Missing references are excluded
from paired comparisons, never replaced by zero.

Only after qualification:

```sh
python -m quasar.modeling assess-replay --database "$MODEL_DATABASE" \
  --inputs "$MODEL_INPUTS" --boundary "$MODEL_BOUNDARY" \
  --inspection "$MODEL_INSPECTION" --weather "$MODEL_WEATHER" \
  --model "$MODEL_RUN/model.json" --evaluation "$MODEL_RUN/evaluation.json" \
  --output data/processed/okaloosa/modeling/replay-v2
```

This prepares one exact assessment per UTC start from October 9 05:00 through
October 10 05:00, each looking forward six hours, plus production/aggregation
benchmarks. A final manifest is written only after all 25 complete. Repeat
`review` with `--assessments <directory>` to validate matching lineage, forecast,
inventory, exact windows and R4–R7 summaries. A partial directory is not an
activated or complete replay.

## API, UI and runtime handoff

V2 assessments carry model SHA-256, training dataset ID, evaluation SHA-256,
evaluation protocol and summary mapping errors. Producer validation recomputes
the frozen acceptance gates rather than trusting `promoted: true`. Existing
schema-1 legacy artifacts remain readable. Known parcel diagnostics add actual
FEMA mapped fraction (null for incomplete reference), separate from estimated
fraction and forecast rainfall. Existing calculation details display this
evidence and the uncalibrated formula without changing the layout.

Before any authorized activation, the runtime owner must verify transferred
hashes, execute the actual portable model on LinuxONE, benchmark full-county
production/aggregation, and compare the same parcel/window through the source
API and app. Set `QUASAR_EXPOSURE_REQUIRED_MODEL_VERSION` to the exact reviewed
v2 identity and point the source to its prepared directory. An unavailable or
mismatched v2 stays unavailable; no v1 or synthetic substitute is selected.
Activating paths, restarting services, changing Vercel, deploying and visual
acceptance are separate steps requiring their normal authorization/review.

## Observation and teammate evidence

The [completed experiment and observation inventory](modeling-run-v2.md) records
the failed gates and obtained sources. Historical Okaloosa storms were explicitly
authorized in addition to the selected replay. Acquisition is a separate command:

```sh
python scripts/acquire_model_observations.py \
  --boundary data/raw/census_okaloosa_county.geojson \
  --raw data/raw/model-observations \
  --output data/processed/okaloosa/model-observations-reviewed --historical
```

Use a new output directory. Verified raw-download caches can be reused; their
original retrieval times and hashes are retained. The derived manifest records
normalization time, source receipts, units, datum, errors and county containment.
Source redistribution terms still require review. The command collects station
measurements and reported events; it creates zero verified parcel labels and
does not fit an observed-outcome model or query WeatherNext.

Time-box public-source discovery to two hours and the selected Okaloosa replay.
NOAA county/zone reports and USGS high-water marks/event sensors are candidates
for source review, not automatic parcel labels. Preserve observation timing,
spatial uncertainty, rainfall/surge mechanism, publication availability and
coverage. No report is not a covered negative. Unavailable/unpublished data
remain explicit. No new WeatherNext acquisition is needed for this experiment.

The teammate handoff should answer, with the generated report open: what is
learned; the exact source/weight identities; comparative and weakest-subgroup
results; what the rainfall rule changes; which observations are missing; and
whether LinuxONE inference, API integration and activation were actually shown.
Never describe an unsuccessful retrain as an improvement.
