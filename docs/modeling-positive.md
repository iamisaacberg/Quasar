# FEMA-overlapping parcels only: revised experiment

**Current decision:** the user subsequently removed ridge-baseline promotion
requirements. The exact same trained weights qualify under the explicitly
amended v4 decision policy below; the original v3 failed-gate record is preserved.

The user requested exclusion of zero-mapped parcels after reviewing v2 results.
This is a new experiment, `mapping-proxy-positive-nested-spatial-v3`, retaining
the completed v2 protocol, weights, evaluation and ledger as historical evidence.
The same original dataset is read without modification; a separate
`v3-positive-experiment.json` reserves one run. No original test targets are read.

## Scope and scientific meaning

Include only original development/validation parcels with verified FEMA SFHA
overlap **strictly greater than zero**. Zero overlap is not a missing label, and
missing/incomplete reference coverage is not zero. The original research pool
has 20,626 eligible parcels across 22 original blocks: 16,268 partially and 4,358 fully overlapping parcels;
80,897 zero-overlap parcels are excluded. `population.json` records exact included
and excluded IDs, parent dataset ID and a checksum bound to the evaluation.

This estimates mapped-area fraction **conditional on already knowing a property
overlaps FEMA's hazard area**. It cannot discover flood-prone properties outside
that map. Cohort selection uses the known reference to define eligibility; FEMA
values still never enter the six predictor columns. All comparisons and support
denominators refer only to this positive-overlap population. Better metrics on
this narrower population cannot establish an improvement over countywide v2 or
the served v1. This decision follows inspection of earlier research results;
the revised cross-validation is not a fresh untouched test.

Assessment production for this model requires verified positive FEMA overlap.
Confirmed zero overlap produces an excluded/unscored result; unknown or
incomplete overlap produces an unknown/unscored result. Neither becomes zero
exposure or low risk. Those properties remain in the county map/input inventory
and in complete-inventory H3 coverage denominators. Model identity, evaluation
and API metadata explicitly carry `inference_population: positive_fema_overlap`.
Inference always retains six predictors, native/portable parity checks, and the
six-hour rainfall formula with the unchanged, uncalibrated 50 mm constant.

## Protocol frozen before the new run

Reuse the [v2 geographic and tuning procedure](modeling-v2.md): five outer and
three inner folds on the existing 10 km blocks, 1 km polygon buffer exclusions,
the same depth/L2 grid, learning rate, stopping limit and five ensemble seeds.
Every comparator is refit within each outer training fold. Candidate weights
balance **partial and full** groups using training rows only, with the same cap
of five before mean-one normalization. Candidate selection and early stopping
use the mean of partial/full MAE. The zero subgroup has no support and no error
estimate; it is not assigned an artificial error of zero.

Retain the numerical gates without loosening them: candidate macro (now the two
eligible subgroups) and fully mapped MAE must each improve at least 10% versus
the same-cohort unweighted model; parcel/equal-block RMSE may worsen at most 5%;
candidate must beat refit mean/ridge RMSE by at least 10% under both weightings;
eligible-population support must be at least 90%; native/portable maximum error
must be at most 1e-6 on at least 10,000 distinct eligible parcels. Report all
folds, exclusions, subgroup errors, support and all failed gates. A failed run
remains research-only; there is no activation or gate revision based on results.

## Explicit local command

Use the existing pinned optional research environment and downloaded sources:

```sh
DYLD_LIBRARY_PATH="$PWD/.context/model-venv/lib/python3.12/site-packages/sklearn/.dylibs" \
.context/model-venv/bin/python -m quasar.modeling train-positive \
  --dataset data/processed/okaloosa/modeling/dataset-recovered \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/20261017-reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --inspection data/processed/okaloosa/parcel-inspection/20261018-marseille \
  --output data/processed/okaloosa/modeling/experiment-v3-positive
```

Use a new output path. The exclusive ledger prevents repeating this experiment
on the original research dataset. Serving starts no training or downloads. An
eligible model still requires separately reviewed, authorized runtime activation.

## Completed run: October 18, 2026 UTC

The single revised experiment completed in **170.87 seconds**. It excluded all
80,897 zero-overlap research parcels and fit/evaluated the 20,626 eligible parcels.
SHA checks confirmed the original dataset, its manifest, previous v2 ledger,
v2 protocol, weights and evaluation were unchanged. Exact membership is retained
in `population.json`; no zero-overlap parcel appears in the revised fold fits,
held-out populations or out-of-fold prediction file.

| Identity | Value |
| --- | --- |
| Model version | `mapped-susceptibility-v3-positive-df72d7de944e` |
| Model SHA-256 | `d8862984236312666892f1a3963d5545cddd64d9b721febf5c142cab6afc141c` |
| Evaluation SHA-256 | `52ccb66f7a697da92e58b6f4262c6e5eb510bebf98cc04af4ec6452325ded909` |
| Protocol SHA-256 | `f257e83d83c6fdc9891ac133d08f63248f0db36660297a675f02e521f6a931e5` |
| Parent dataset ID | `447374887feed64c7d11918aca14fff9715fedaf4eebdda48ed5cde98ba93f87` |

All following errors measure mapped-area fractions within the eligible cohort.
Parentheses give minimum–maximum across geographic folds, not confidence
intervals. The comparisons use the same revised population and supported rows;
they cannot be compared directly with the countywide v2 aggregate metrics.

| Method | Parcel RMSE (fold range) | Equal-block RMSE (fold range) | Mean partial/full MAE (fold range) |
| --- | ---: | ---: | ---: |
| Balanced candidate | .307587 (.245845–.405791) | .306970 (.245845–.405791) | .217378 (.164885–.411113) |
| Unweighted XGBoost | .313439 (.255960–.419251) | .323693 (.242501–.419251) | .246473 (.168137–.427763) |
| Refit mean | .378346 (.356381–.417526) | .429372 (.356381–.453106) | .366430 (.333427–.375093) |
| Standardized ridge | .337640 (.308093–.385050) | .288639 (.241539–.385050) | .312660 (.275696–.339476) |
| Terrain alone | .306334 (.241215–.375052) | .297465 (.241215–.365654) | .199418 (.137331–.336242) |
| Stream distance alone | .407194 (.384077–.450411) | .456290 (.384077–.476706) | .340938 (.312096–.358215) |

| Method | Partial MAE (fold range) | Fully mapped MAE (fold range) |
| --- | ---: | ---: |
| Balanced candidate | .248325 (.205392–.319551) | .186431 (.062227–.502675) |
| Unweighted XGBoost | .245763 (.201497–.341683) | .247182 (.103154–.527762) |
| Refit mean | .330799 (.302562–.390855) | .402061 (.358545–.440904) |
| Ridge | .278359 (.220948–.336619) | .346960 (.292388–.394950) |
| Terrain alone | .247738 (.204820–.318236) | .151097 (.054949–.398147) |
| Stream distance alone | .361032 (.331989–.426844) | .320844 (.250420–.365336) |

Candidate average partial/full MAE improved **11.80%**, fully mapped MAE improved
**24.58%**, and parcel/equal-block RMSE both improved versus same-cohort
unweighted XGBoost. Partial MAE increased slightly. Terrain alone had lower
aggregate errors than the combined candidate under these shared settings;
added decision value from stream distance/area is not established.

**Original v3 decision was research-only.** The two ridge-comparison gates failed:
parcel RMSE improved only **8.90%**, below the required 10%, and equal-block RMSE
was **6.35% worse** than ridge. All other frozen gates passed. This initial
decision used the frozen v3 policy; the subsequent user-authorized amendment
below preserves that original record. This is a useful subgroup result,
not uniform superiority over simpler models.

Eligible-population feature support was **91.85%**: 15,011 of 16,268 partial and
3,934 of 4,358 fully mapped parcels were supported out of fold. The remaining
1,681 eligible parcels remained unknown. The excluded zero-overlap parcels are
outside this denominator, not successful predictions. Fold support varied from
79.48% to 100%; the aggregate gate does not guarantee adequate support in each
geographic fold. Exact exclusions and per-block residuals remain in the evidence.

| Fold | Eligible held out | Supported | Partial supported | Fully mapped supported |
| --- | ---: | ---: | ---: | ---: |
| 0 | 7,820 | 6,215 | 4,879 | 1,336 |
| 1 | 4,588 | 4,542 | 2,951 | 1,591 |
| 2 | 3,770 | 3,770 | 3,472 | 298 |
| 3 | 2,219 | 2,198 | 1,887 | 311 |
| 4 | 2,229 | 2,220 | 1,822 | 398 |

Native/portable parity passed on 10,000 distinct eligible parcels with maximum
absolute error **5.634e-7**. A read-only, in-memory LinuxONE check also evaluated
10,000 eligible parcels on actual **s390x**, with platform difference **0.0**,
12.024 seconds for inference, and peak RSS 27,246,592 bytes. The inference module
SHA was `587bc8c879c8e45b7053b3d59370d45766d3fed51ca2b42ef8650ffa362b9aea`.
This demonstrates candidate inference, not activation, full-county production,
current API integration or visual acceptance. No model was activated in this run.

The source audit and native re-export/model lineage review passed. All 25 archive
positions have conditional research sensitivity summaries. Serveable assessments
were not produced because the candidate failed qualification. Review remains
explicitly incomplete for that reason and the previously unavailable original
test ledger. Private evidence is under
`data/processed/okaloosa/modeling/experiment-v3-positive/` and
`data/processed/okaloosa/modeling/review-v3-positive/`.

Verification: 229 Python tests passed in the optional research environment;
the dependency-free environment passed with eleven optional tests skipped.
All 88 JavaScript tests, npm installation, type/syntax checks and the frontend
build passed. Isaac reviews rendered visuals. The local implementation enforces
zero/unknown exclusion at production, artifact loading and proxy validation;
excluded parcels are displayed as unscored with a plain-language explanation.

## Requested policy amendment: ridge becomes advisory

After reviewing the result, the user explicitly requested removal of the ridge
promotion gates. Protocol `mapping-proxy-positive-nested-spatial-v4` records this
post-result decision change. Ridge metrics stay visible as descriptive evidence;
they no longer control qualification. This is **not a preregistered success of
the original policy**. The original v3 model/evaluation remain unchanged.

`qualify-positive` verifies the completed v3 protocol, model/evaluation hashes,
native re-export, folds, predictions and population, then writes a new identity
and decision record without retraining. The six predictors and exact tree
weights are unchanged. Subgroup/full MAE improvement, parcel/equal-block
non-regression, mean-baseline improvements, feature support and portable parity
remain required. All eight remaining checks passed.

| Identity | Value |
| --- | --- |
| Qualified model | `mapped-susceptibility-v4-positive-736f711e2596` |
| Model SHA-256 | `2f1a2bc4884bb563c309ea03eeb565bf692a806e683edc11898c129cbf107183` |
| Evaluation SHA-256 | `1f2eced1ff1e846eccea59f7493468d38a7395e302ca680b138f23b6fddd4c24` |
| Decision protocol SHA-256 | `4fbf294bca942e7c042a6d292600f2ecca9ded54dd9bc8b5b73a08ba7ecff3e5` |

Reproduce this explicit decision revision into a new output directory:

```sh
python3 -m quasar.modeling qualify-positive \
  --experiment data/processed/okaloosa/modeling/experiment-v3-positive \
  --output data/processed/okaloosa/modeling/experiment-v4-positive

python3 -m quasar.modeling assess-replay \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/20261017-reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --inspection data/processed/okaloosa/parcel-inspection/20261018-marseille \
  --weather data/processed/isaias-2026.json \
  --model data/processed/okaloosa/modeling/experiment-v4-positive/model.json \
  --evaluation data/processed/okaloosa/modeling/experiment-v4-positive/evaluation.json \
  --output data/processed/okaloosa/modeling/replay-v4-positive
```

Replay production reuses static model predictions within this one run while
rechecking each window's rainfall, validity, source identity and exclusions.
Each artifact retains the complete county inventory, exact model/evaluation
hashes, reference fraction and conditional scope. Training and scoring exclude
zero overlap; unknown overlap never becomes a low score.

Actual in-memory s390x inference of this qualified identity matched 10,000 local
predictions exactly (12.281 seconds). This proves portable host execution of
these weights, not activation or a deployed app result. Activation remains the
separate runtime-owner step specified in the original plan. Pin the inventory
host and proxy to the exact reviewed v4 model identity and use its prepared
directory; mismatched/absent artifacts must remain unavailable.

## Tools comparison and completed replay handoff

The user also requested an explicit V1/V2 toggle in Tools. **V1** selects the
original archived served model; **V2** selects the qualified revised positive-only
model above. The v4 suffix is an internal experiment/decision identity, not a
third Tools choice. [Version routing](exposure-display.md#tools-v1--v2-model-selection)
uses separate directories and exact identity pins. Explicit V1 selection is
permitted; it is never silently substituted when V2 is absent.

All **25 V2 replay assessments** were generated and verified, including complete
113,818-parcel inventories and R4–R7 aggregation. Each window contains 22,146
scored and 91,672 unscored parcels; exclusions remain unknown in full-inventory
coverage denominators. Existing original V1 assessments for all 25 positions
were retrieved read-only and matched their previously recorded checksums.
The local comparison environment is in ignored `.context/exposure-comparison.env`.

Representative real-data checks exercised both choices at the first, middle
and final replay hours. Parcel **81** had an assessment under both models;
zero-overlap parcel **1** had a V1 assessment and remained explicitly excluded
under V2. All six API-logic checks retained the expected version, model hash,
evaluation/source identity, inventory and H3 summaries. The receipt is
`data/processed/okaloosa/modeling/comparison-verification.json`. These are local
API-logic checks, not a deployed HTTP/app or visual check.

The complete assessment review is in
`data/processed/okaloosa/modeling/review-v4-positive/`: 25/25 windows verified;
its remaining incomplete-evidence blocker is the unavailable original test
ledger. Current qualification is valid under the amended policy; the missing
historical ledger is still disclosed rather than synthesized.

Final verification passed: **233 Python tests** in the research environment;
the dependency-free environment passed with eleven optional checks skipped;
**91 JavaScript tests**, npm installation, type/syntax checks and frontend build.
Committed frontend assets were rebuilt for the Tools selector. Tests cover
version-specific requests/caches, unavailable choices, stale responses after
switching, proxy identity checks, exclusion, unchanged original artifacts and
advisory-only ridge policy. Isaac reviews the rendered layout.
