# App premise and product boundaries

Quasar explores how a county analyst can inspect a dated rainfall forecast alongside local parcel context, experimental model output and missing evidence. Scope is Okaloosa County, Florida, FIPS `12091`. It supplements official NWS/local information; it does not issue evacuation orders or determine property safety.

## The analyst task

Choose a source/hour, inspect rainfall and prepared parcel terrain/FEMA/stream inputs, explain an experimental score or unknown state, and inspect H3 coverage. Map, Data and Reports share the rainfall frame. Reports/export describe source rainfall, not a separate model-result report. The [problem and comparison brief](datathon-submission/problem-and-comparison.md) states the benefit hypothesis and how it could be tested without inventing adoption or emergency outcomes.

## What the application currently does

The app opens the October 9 forecast reconstruction with 25 hourly starts, from midnight October 9 through midnight October 10 Central. Each start looks forward six hours; the last requires source hours beyond midnight. The map retains native source timing, retrieval, resolution and units. H3 rainfall is a maximum of overlaps, not finer weather data.

County-validated parcels load progressively with persistent geometry caching. Optional matching prepared inputs explain terrain, FEMA mapping and retained-stream context. Optional matching exposure artifacts supply an experimental index and factors. Missing configuration/data, mismatched identities, stale current sources and unsupported windows remain unknown. An exact-window catalog can select different single-window artifacts without reusing prior scores.

The trained model predicts FEMA mapped fraction, not observed flooding. A deterministic uncalibrated formula combines that output with rainfall. The [model summary](datathon-submission/model-summary.md) states the recorded metrics and weak subgroups. The current checkout has no real model/data artifacts, and no model activation on LinuxONE was verified here.

Official alerts remain disconnected for the archive. An optional explicit current NWS importer/API exists separately; a source error or empty query cannot establish safety. Current-forecast controls are absent pending a complete fresh data path. Fictional exercise sites, what-if controls, simulated routes and notification previews are retired from the app; old HTTP endpoints return 410.

## What evidence exists

Source and fixture tests support software contracts, including unknown preservation and window/race handling. The committed [training report](modeling-run-v1.md) records one local real-data run. The [activation record](real-data-rollout.md) records earlier LinuxONE county-context serving. Neither proves this checkout has artifacts, current freshness, target-host model inference, rendered acceptance or a complete end-to-end demonstration.

Isaac reviews visuals. User studies, independent flood-outcome validation, agency adoption, measured community benefit and reliable operational warning lead time remain unestablished. A low score is not safe; a blank score is unknown. H3 is a display/aggregation unit, not an inundation model. Routing, contacts and message delivery remain outside the authorized application scope.

Start with the [current architecture](architecture.md), [data guide](data-guide.md), [runtime contract](data-contract.md), [evidence package](datathon-submission/README.md) and [workboard](DATATHON-WORKBOARD.md). The [research protocols](datathon-submission/research-protocols.md) define the independent evidence needed before expanding interpretation.
