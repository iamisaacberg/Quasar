# Experimental FEMA mapping proxy

The model estimates the fraction of parcel area mapped as FEMA Special Flood Hazard Area. It was trained against regulatory mapping, not observed floods. Its output and the derived exposure index are neither flood probability nor depth. Follow official NWS/local guidance.

All real-data numbers below come from the committed [first-run report](../modeling-run-v1.md). The original weights, evaluation, residuals and dataset ledger are not present in this checkout, so they were **not independently reverified during this implementation**. `verify-model-evidence` provides a read-only arithmetic/identity check when that bundle is supplied; it does not retrain or select a model.

## Data and method

Model `mapped-susceptibility-v1-7673922e5dca` has SHA-256 `c3896f84e4593bbe20af909aade20edf7d46e43459b79e7aa79d5dc13188457f`. Source inputs are county-validated parcels, reconciled terrain/FEMA/mapped streams and the authoritative Census boundary. Original source dates, terms, datum and preparation lineage must travel with their manifests; the training date is not the source observation date.

The six predictors are terrain minimum, mean, maximum and relief in NAVD88 meters, log parcel area, and log distance to retained mapped streams. IDs, location, H3 and FEMA-derived predictors are excluded. Incomplete terrain and inputs outside development feature ranges produce unknown assessments. Missing coastal/lake/canal coverage and stream connectivity remain limitations.

The recorded inventory has 113,818 parcels, with 112,237 having complete predictors and an eligible FEMA target. Fixed 10 km spatial blocks separate development/validation/test. A 1 km buffer excludes 2,804 development parcels near holdouts; development retains 98,358 parcels, validation 3,165, and test 7,910. There are 1,581 ineligible/unlabeled parcels. Five grouped development folds and validation selection choose configuration; the retained ledger permits one test evaluation. Do not tune against that published test by recreating its dataset.

Five XGBoost members use depth 4, L2 1, 136 trees, eta 0.05, row subsampling 0.8 and seeds 42–46. The recorded environment was Python 3.12.14, XGBoost 3.4.1, NumPy 2.5.4 and scikit-learn 1.9.1. Optional packages stay outside the app runtime.

## Recorded held-out results

Errors below are in mapped-area fraction on the same 7,792 supported test parcels. The 118 unsupported test parcels remain unknown.

| Method | Parcel MAE | Parcel RMSE | Equal-block MAE | Equal-block RMSE |
| --- | ---: | ---: | ---: | ---: |
| Ensemble | 0.039631 | 0.115756 | 0.074609 | 0.144684 |
| Development mean | 0.166738 | 0.233466 | 0.153155 | 0.198298 |
| Standardized ridge | 0.129328 | 0.215976 | 0.182860 | 0.268382 |

Recorded test support is 98.5082%. Recorded native/portable parity used 10,000 distinct development parcels with maximum absolute difference `3.1861144e-7`. Promotion means passing the experimental mapping-proxy gates, not deployment or safety approval. Saved ridge predictions are not available in the existing residual contract; the new evidence command explicitly leaves ridge arithmetic recorded-only.

Subgroup errors materially limit use: test MAE is 0.012002 on 6,567 zero-target parcels, 0.172181 on 1,015 partially mapped parcels, and 0.262964 on 210 fully mapped parcels. The selected candidate's fully mapped validation MAE was **0.779924 on 60 parcels**. Keep this visible in any presentation. This release is restricted to experimental descriptive comparison; it is unsuitable for property safety decisions or automatic prioritization without independent review. A subgroup investigation remains open.

## Rainfall interaction and execution boundary

`index = 100 × susceptibility × rainfall_mm / (rainfall_mm + 50)` combines the mapping proxy with a complete forward-six-hour native forecast. The 50 mm constant is uncalibrated. Tree-path contributions explain the model's arithmetic, not physical causes; ensemble spread is not a confidence interval.

One recorded local assessment covers October 9, 2026, 05:00–11:00 UTC (midnight–06:00 Central): 112,120 scored and 1,698 unknown. Recorded local production plus R4–R7 aggregation took 45.23 seconds and about 393.2 MiB peak RSS on Mac ARM64. These are not LinuxONE timings. The archive is an initialization-based forecast reconstruction, not observations or proof of as-issued availability. Twenty-five-position real-data production, actual `s390x` parity, activation and Isaac's visual acceptance remain open.
