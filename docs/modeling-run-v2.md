# Completed v2 exposure-model experiment

Run completed October 18, 2026 UTC (October 17 Central). County FIPS `12091`.
Protocol: `mapping-proxy-nested-spatial-v2`. **Result: research-only; two frozen
engineering gates failed. V2 was not activated.** No thresholds were relaxed and
no second retraining experiment was run after inspecting these results.

## Teammate and judge explanation

The model learns to approximate FEMA mapped-area fractions from terrain, parcel
area and mapped-stream distance. Geographic evaluation shows useful mapping
patterns beyond mean and ridge baselines. Terrain provides most of this evidence;
stream distance alone performed poorly. These are mapping results, not evidence
that the model predicts hurricane flooding. Actual FEMA coverage is already
available for the evaluated parcels, so added decision value beyond that reference
remains unproven.

Balancing the three target groups helped fully mapped parcels but increased
overall error too much. Fully mapped parcels remain the candidate's weakest
aggregate subgroup, with substantial geographic variation. The rainfall layer
still uses an experimental 50 mm constant, without flood calibration. Actual
portable inference ran on LinuxONE; the new candidate was not connected to the
live API or app because it failed qualification. The existing API still returned
the separately identified v1 artifact when checked.

## Artifact inventory and lineage

The private handoff was retrieved read-only from LinuxONE `/srv/quasar/data`.
Nine transferred county/source files passed SHA-256 verification. Raw data,
databases, trained weights, observations, receipts and credentials remain ignored.

| Artifact or claim | Evidence and limitation |
| --- | --- |
| County parcel inventory | Verified prepared database/manifest; 113,818 parcels; authoritative Census county geometry SHA `03d0eb4232382046cf1bc85c77c3fd7b7178bb0ac9af8dafdc8c1de09c3b00f4` |
| Reconciled terrain/FEMA/stream inputs | Verified database/manifest checksums, prepared coverage, units, datum and actual county containment; terrain meters/NAVD88, area m², stream distance meters |
| Inspection artifact and forecast archive | Retrieved and checksummed; inspection provenance identifies the exact archive; native rainfall remains 0.1 degree ensemble mean, mm / 6h |
| Raw upstream GIS sources | Acquisition dates, terms, source identifiers and checksums are recorded in the prepared manifests. The complete original DEM/FEMA raw acquisition set was not recovered/reprocessed here; recorded metadata is not independent verification of those raw bytes |
| Historical local v1 report | Model SHA `c3896f84e4593bbe20af909aade20edf7d46e43459b79e7aa79d5dc13188457f`; dataset SHA `447374887feed64c7d11918aca14fff9715fedaf4eebdda48ed5cde98ba93f87` |
| Served v1 bundle | Staged portable weights/evaluation match model SHA `5fbfe10500f05e1b5fbd16ebc622b52596489aa19aea479ab063cf872d0535a7`, dataset ID `8ab0884720f21ce9fe492b8c1aabe317e28850f82857ab0dff880a3a1c057179`; current source API returned this model hash. Its weights and metrics are kept together |
| Recovered original dataset | Existing deterministic preparation reproduced the historical local dataset **byte for byte**, ID `447374887feed64c7d11918aca14fff9715fedaf4eebdda48ed5cde98ba93f87`. Source checksums, all split assignments and counts also match the staged report. The different staged serialized dataset ID remains distinct |
| Original v1 native weights and test ledger | Not found in the accessible host/workspace handoff. Missing evidence remains a blocker; neither file was fabricated. The portable v1 bundle is archived only as its own comparison record |
| V2 run | Native five-member ensemble, portable weights, protocol, folds/exclusions, out-of-fold predictions, subgroup support, block residuals and evaluation saved together; native re-export matches portable trees |

### V2 identities

| Identity | Value |
| --- | --- |
| Model | `mapped-susceptibility-v2-814b84ddebcb` |
| Model SHA-256 | `38c02a76bd508e98c8e0e58e0985769a2eb8da2da5b738f05a4d9648f4952aa4` |
| Evaluation SHA-256 | `80b1b823169b51ff1d87ea43b3f3d7bbcbcf1f628627c2475a12c429b55b2459` |
| Training dataset ID | `447374887feed64c7d11918aca14fff9715fedaf4eebdda48ed5cde98ba93f87` |
| Frozen protocol SHA-256 | `6f373dd9a4427338cb3a1fd3f3c57b89024fef96c15c935e1034c3b0bd43bbf4` |
| Inventory ID | `0d8bf9c244cbae678108bbc8149d80c60db30f60824e24cd49435f2b93b4fd5a` |

These identities link this report to its evaluation and weights. Metrics from the
historical local v1 report are not substituted for those of the served v1 bundle.

## One controlled experiment

The research pool was the original development (98,358) and validation (3,165)
partitions: **101,523 parcels in 23 original 10 km geographic blocks**. All 7,910
original test rows were excluded by SQL before their targets/JSON were loaded.
The original preparation's 2,804 buffer exclusions and 1,581 unlabeled rows were
also excluded. A separate exclusive v2 experiment ledger reserves this run;
the unavailable original test ledger is not claimed to have been preserved.

Five outer geographic folds evaluated each comparator on common supported held-out
parcels. Three inner folds selected parameters/rounds. Every split removed fit
parcels within 1 km of held-out parcel polygons. Candidate weights used fit rows
only, capped before mean-one normalization. Mean, standardized ridge and
unweighted XGBoost were refit in each outer fold. Terrain/stream ablations shared
the candidate's inner-selected settings and support, without separate tuning.
The combined model also contains parcel area, so this is not a clean causal
estimate of stream distance's incremental contribution.

Execution took 881.58 seconds in the pinned local optional research environment.
This is cross-validation on existing research data, **not an untouched external
test**. All errors below are FEMA area fractions, not flood probabilities.
Parentheses give the minimum–maximum across the five geographic folds; these are
descriptive variation, not confidence intervals. Aggregates pool held-out rows
(or weight blocks equally), and need not equal an unweighted mean of fold scores.

| Method | Parcel MAE (fold range) | Parcel RMSE (fold range) | Equal-block RMSE (fold range) | Mean subgroup MAE (fold range) |
| --- | ---: | ---: | ---: | ---: |
| Balanced candidate | .1022 (.0395–.1494) | .1976 (.1005–.2588) | .1731 (.1184–.2180) | .1969 (.1531–.3248) |
| Unweighted XGBoost | .0778 (.0251–.1157) | .1809 (.0778–.2407) | .1711 (.1104–.2187) | .2176 (.1890–.3276) |
| Development mean, refit per fold | .2072 (.1706–.2490) | .3053 (.1894–.3880) | .2331 (.2077–.3880) | .4800 (.4213–.5139) |
| Standardized ridge | .1770 (.0437–.2577) | .2757 (.1225–.3441) | .2146 (.1983–.3441) | .4236 (.3820–.4610) |
| Terrain alone | .1197 (.0538–.1751) | .2230 (.1402–.2802) | .1898 (.0993–.2802) | .2007 (.1212–.2876) |
| Stream distance alone | .3712 (.3474–.3962) | .4054 (.3717–.4208) | .3849 (.3421–.4208) | .4765 (.4195–.4998) |

### Subgroups and coverage

| Method | Zero MAE (fold range) | Partial MAE (fold range) | Fully mapped MAE (fold range) |
| --- | ---: | ---: | ---: |
| Balanced candidate | .0641 (.0321–.0918) | .2436 (.1553–.3221) | .2830 (.2042–.5605) |
| Unweighted XGBoost | .0258 (.0144–.0517) | .2586 (.1812–.3025) | .3683 (.3057–.6286) |
| Mean | .1270 (.0955–.1612) | .4231 (.2638–.5418) | .8900 (.8388–.9045) |
| Ridge | .1089 (.0275–.1538) | .3435 (.2518–.4260) | .8183 (.7548–.8668) |
| Terrain alone | .0857 (.0457–.1334) | .2491 (.1785–.2837) | .2674 (.1309–.5096) |
| Stream distance alone | .3537 (.3081–.4007) | .3678 (.2774–.4463) | .7079 (.5804–.7451) |

| Target group | Research pool | Supported out-of-fold | Unknown |
| --- | ---: | ---: | ---: |
| Zero | 80,897 | 80,453 | 444 |
| Partial | 16,268 | 16,135 | 133 |
| Fully mapped | 4,358 | 4,351 | 7 |

Evaluation support was **99.425%**, with fold support 98.688%–99.989%.
Unknown rows were retained as abstentions, not scored as zero. Fold 3 had the
largest candidate fully mapped MAE (.5605), despite the pooled .2830 result.
Private `folds.json`, `out-of-fold.json`, `block-residuals.json` and
`spatial-residuals.svg` retain exact assignments, exclusions and geographic errors.

### Frozen gate decision

| Gate | Measured result | Decision |
| --- | --- | --- |
| ≥10% lower mean subgroup MAE | 9.52% improvement | **Fail** |
| ≥10% lower fully mapped MAE | 23.18% improvement | Pass |
| ≤5% worse parcel RMSE | 9.22% worse | **Fail** |
| ≤5% worse equal-block RMSE | 1.21% worse | Pass |
| ≥10% lower mean and ridge RMSE under both weightings | All four comparisons passed | Pass |
| ≥90% evaluation support | 99.425% | Pass |
| Native/portable error ≤1e-6 on ≥10,000 distinct parcels | 10,000; maximum 2.176e-7 | Pass |

The gates are engineering selection rules, not flood-accuracy standards. The
failed candidate is ineligible for assessment publication. An actual
`assess-model-replay` invocation returned exit 2, “Unknown or unqualified v2 evaluation
protocol,” before creating a replay directory. Twenty-five research sensitivity
summaries were produced; **zero serveable v2 assessments were published**.

## What rainfall changes

All 25 existing archive positions were analyzed using final fitted predictions
on the non-test research pool. These are descriptive method comparisons on the
fit pool, not additional held-out performance estimates. The 50 mm rule stays
unchanged. A 2026-10-10 00:00–06:00 UTC example illustrates sensitivity:

| Constant | Mean score | Maximum | Lower (<35) | Moderate (35–<65) | Elevated (65–<85) | Highest (≥85) | Top-decile overlap with 50 mm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 25 mm | 9.809 | 69.874 | 89,392 | 12,106 | 25 | 0 | 99.38% |
| 50 mm | 7.019 | 53.698 | 93,926 | 7,597 | 0 | 0 | 100% |
| 100 mm | 4.478 | 36.703 | 101,518 | 5 | 0 | 0 | 99.13% |

Rankings change less than band occupancy. Tie-aware rank correlations with the
50 mm scores were .999920 and .999928 for 25/100 mm. At 50 mm, using actual FEMA
coverage directly instead gave mean score 5.341, maximum 54.679 and 8,885 moderate
parcels. Model/direct-FEMA rank correlation was .664630, with 87.24% top-decile
overlap. Actual FEMA fractions and out-of-fold estimates are retained alongside
each other in the private prediction file. FEMA is the available reference here,
not a rival predictive model or observed-flood truth.

Constructed formula checks preserve zero rainfall → zero score and the cap
`100 × estimated mapped fraction`: a .2 fraction can never exceed 20, even at
extreme rainfall. This can suppress local pluvial-flood signals outside mapped
areas. No change in the constant fixes omitted surge, drainage, upstream flow
or floor elevation. Sensitivity alone cannot choose a calibrated replacement.

## Observations actually obtained

Discovery stayed within a two-hour public-source time box. User authorization
also covered historical Okaloosa storms. Raw bytes and retrieval receipts are in
`data/raw/model-observations/`; the reviewed normalized bundle is
`data/processed/okaloosa/model-observations-reviewed/`. No new WeatherNext query
was made. Each mapped point was checked against the authoritative county polygon;
a county tag or bounding box was insufficient.

| Source | Obtained | Meaning and limitations |
| --- | --- | --- |
| USGS instantaneous measurements, selected replay | 968 measurements: stage/discharge at four county stations, October 9 05:00–October 10 11:00 UTC | Provisional qualifiers retained. Stage is feet above each gauge's local datum, not parcel NAVD88 or flood depth |
| USGS measurements, Sally 2020 | 6,884 measurements across ten series at five stations | Historical station evidence only; no newly acquired matching historical forecasts |
| CEW/DTS/VPS METAR via Iowa State IEM | 265 one-hour precipitation reports, including 14 traces | Inches; original overlapping routine/SPECI periods retained without summing them. Trace is distinct from measured zero; invalid/missing values remain unknown |
| NWS MOB local storm reports via IEM | One selected-replay flash-flood report at October 10 00:41 UTC | Public report near Fort Walton Beach; coarse location, no verified parcel association |
| NOAA Storm Events bulk 2018–2025 | 18 county/point-validated flash-flood records across 11 episodes | Event narratives, times/time zones and source retained. One county-tagged point outside the actual county polygon was excluded |
| USGS Flood Event Viewer/STN high-water marks | No eligible Okaloosa marks obtained from the inspected Michael 2018/Sally 2020 endpoints | Michael returned 522 Florida marks outside Okaloosa; Sally returned none. This bounded search does not establish countywide absence of high-water evidence |

The selected report describes significant flash flooding near Fort Walton Beach
at coarse coordinates [-86.6, 30.4]. This falls within the 00:00–06:00 UTC research
window above, whose 50 mm candidate scores contained **no elevated parcels**.
This case illustrates why band occupancy cannot be presented as flood-detection
evidence. It does not establish a parcel-level missed prediction or miss rate:
the report is not associated with a specific evaluated parcel, its location is
coarse, and precipitation/surge mechanisms were not independently resolved.
The archive's “Isaias” project name is not verification of a storm identity.

There are **zero verified parcel labels and zero covered parcel negatives**.
No report does not establish no flooding. These observations were kept out of
mapping-model training; they are evidence for review, not manufactured outcome
labels. Original retrieval dates/checksums, processing, units, geometry and
unavailable evidence are in the manifest. Redistribution terms still require
review. Bulk NOAA 2026 coverage inspected during discovery did not yet include
the selected October event; absence there is not a negative observation.

Source entry points: [NOAA Storm Events](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/),
[USGS instantaneous measurements](https://waterservices.usgs.gov/nwis/iv/),
[USGS Flood Event Viewer](https://apps.usgs.gov/fev/data-download-portal),
[IEM METAR archive](https://mesonet.agron.iastate.edu/request/download.phtml),
[IEM local storm reports](https://mesonet.agron.iastate.edu/request/gis/lsrs.phtml).
Exact query URLs and returned hashes are in the private retrieval manifest.

## LinuxONE, API and app evidence

An authorized read-only in-memory check used the actual existing portable
inference module on architecture **s390x**, Python 3.12.3. It evaluated 10,000
distinct eligible research parcels with the exact v2 model/evaluation hashes
above. Maximum platform difference from local portable predictions was **0.0**;
the prediction loop took 11.245 seconds, peak process RSS 34,590,720 bytes.
Inference source SHA was
`ffff7ea772b137736f75e8bfd0a2b377bf908ee77779fb2ca5589c4cb91571be`.
This is current host inference evidence; it is not a full-county production or
H3 benchmark for v2.

The running source API separately returned ready v1 assessments, model SHA
`5fbfe10500f05e1b5fbd16ebc622b52596489aa19aea479ab063cf872d0535a7`, and
s390x aggregation metadata for parcel 19144 in the first replay window. The 25
running artifact headers also identified that same v1 bundle. No service paths,
files, credentials or infrastructure were changed. No deployed v2 API result,
app rendering or visual acceptance is claimed.

Local producer/API/proxy tests cover additive dataset/evaluation/protocol lineage,
actual versus estimated FEMA coverage, source/model mismatch rejection, unknown
terrain/features, incomplete/zero rainfall and stale sources. Exact v2 model
pinning returns unavailable for a mismatched archived model. The failed candidate
cannot silently produce a replacement or select v1 as its fallback. The running
older release remains unchanged until a separately authorized runtime decision.

## Reproduce and review

See [the frozen protocol and commands](modeling-v2.md). Do not repeat training on
this reserved dataset after seeing the result. Review and cached observation
normalization can be rerun into new output directories without fitting again.
Local private artifact paths:

- `data/raw/linuxone-handoff/`: transfer receipt, dataset recovery, running artifact/API receipts.
- `data/processed/okaloosa/modeling/v1-archive/`: served v1 weights and their evaluation.
- `data/processed/okaloosa/modeling/dataset-recovered/`: reconstructed original database, split manifest and exclusive v2 ledger.
- `data/processed/okaloosa/modeling/experiment-v2/`: exact native/portable weights, evaluation, folds, predictions, residuals and LinuxONE inference receipt.
- `data/processed/okaloosa/modeling/review-v2-final/`: verified source/model identities and all 25 research sensitivity summaries; status incomplete for failed qualification and unavailable original ledger/assessments.
- `data/processed/okaloosa/model-observations-reviewed/`: observations and acquisition/processing manifest.

Final checks passed: required dependency-free Python suite (221 tests, ten
optional checks skipped), optional ML/GIS suite (221 tests, no skips),
`npm ci --ignore-scripts`, `npm run check`, JavaScript suite (86 tests),
`npm run build`, and whitespace checks. Rebuilt frontend assets had no diff;
the build retained its existing large-chunk advisory. Isaac reviews visuals.

The review handoff is a reproducible **failed-gate experiment**, honest mapping
comparisons and obtained case evidence. A qualifying served v2, independently
validated storm prediction, verified warning lead time and added decision value
over direct FEMA coverage remain unestablished. A future change needs a separately
reviewed protocol and appropriate independent evidence; this result does not
justify loosening the current gates.
