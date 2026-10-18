# Quasar

Okaloosa County flood risk intelligence starter for the IBM Z Datathon.

Quasar follows the team's Flood Emergency Alert System proposal, narrowed to **Okaloosa County, Florida (FIPS `12091`)**. The application displays sourced county parcels, prepared reference inputs and imported native forecast rainfall.

## Documentation

Start with the [documentation index](docs/README.md) for the full reading guide, existing contracts, and setup references.

- [App premise and product boundaries](docs/app-premise.md): the problem, intended audiences, current workflows, and limits of the demonstration.
- [Data guide](docs/data-guide.md): fictional and imported inputs, provenance, geographic scales, freshness, missing data, and BI interpretation.
- [Local parcel input preparation](docs/parcel-inputs.md): separate research environment, terrain coverage and unscored FEMA/waterway joins.
- [Mechanisms](docs/mechanisms.md): scoring formulas, architecture, forecast imports, replay, routing, frontend behavior, API, and configuration.
- [Improvement roadmap](docs/improvement-roadmap.md): concrete implementation gaps, data milestones, model evaluation, usability, scale, and completion evidence.

## Run locally

```sh
python3 -m quasar
```

Set a public `MAPBOX_PUBLIC_TOKEN=pk...` in ignored `.env`. Configure
`QUASAR_WEATHERNEXT_FILE` and `QUASAR_REPLAY_FILE` for existing schema-3 county
snapshots, or use the authenticated LinuxONE snapshot bridge. Set
`QUASAR_PARCEL_DATABASE` and `QUASAR_PARCEL_CONTEXT_DIRECTORY` on the inventory
host for prepared parcel inputs. Missing settings never load synthetic data.

The Python runtime is dependency-free. Optional GIS preparation stays separate.
The hosted app is public without a sign-in screen. `npm run dev:wifi` remains
a separate optional password-protected laptop-sharing utility; see
[hosted access](docs/vercel.md) and [real-data activation](docs/real-data-rollout.md).
Do not start a deployment or restart shared services without authorization.

## County sources

The map, Data tab and Reports use imported native county forecast cells only.
The map opens directly on the Isaias October 9 archive, with 25 hourly
positions, county-clipped H3 rainfall and compact rewind, play/pause and forward
controls. Tools → Archive details contains the interactive maximum-native-cell
rainfall trend, hour scrubber and source recheck.
Each hex uses the maximum of its overlapping native forecasts; this does not
increase forecast resolution. Missing overlaps leave the hex transparent.
Map, Data and Reports share the selected hour. The current forecast is absent
from the application controls. Archive rainfall is a forecast reconstruction, not an observation.
Source initialization, retrieval, validity, resolution and mm / 6h remain visible.
Missing, stale or invalid imports remain unavailable. No serving request starts
cloud queries. Old site-only imports are rejected by these views.

County parcels retain exact boundary validation, progressive loading and the
persistent browser cache. Prepared terrain, FEMA and mapped-waterway context
appears in parcel details and indexed cell summaries when its verified artifact
is configured. Unknown interiors are transparent with thin outlines; selected
parcels have a distinct outline. H3 does not sharpen native rainfall forecasts.

Real parcel scores remain unknown unless separately produced matching exposure
assessments exist. Optional offline modeling implements an experimental FEMA
mapping proxy and rainfall interaction. The original v1 experiment passed its
mapping-proxy promotion gates; see the [v1 report](docs/modeling-run-v1.md).
LinuxONE serves a separately identified, matching v1 bundle for all 25 archive
positions; see [activation](docs/real-data-rollout.md#exposure-activation).
The [v2 experiment](docs/modeling-run-v2.md) failed qualification and remains
research-only; its weights have not replaced that running bundle.
No observed-flood validation is established.
Exposure colors are not flood probability or depth, and green does not establish safety.

Fictional sites, synthetic scenarios, what-if additions, notification previews and
simulated routes are absent from the application. Their old HTTP endpoints return
410. Offline research modules and clearly labeled test fixtures remain in source.
The official NWS feed remains explicitly disconnected; this is not an all-clear.

## Development and checks

React/Tailwind source is in `frontend/`; committed runtime assets are in
`quasar/static/ui/`. Isaac reviews rendered visuals.

```sh
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
npm test
npm run build
```

Commit rebuilt assets with their source. Do not commit `.env`, credentials,
keys, raw property data or prepared databases. Existing notebooks and importers
remain optional, explicit research tools; see the documentation index.

## Offline parcel modeling

The current [revised experiment](docs/modeling-positive.md) follows the request
to exclude zero FEMA-overlap parcels. It fits/evaluates only verified positive
overlap, and leaves excluded or unknown-overlap properties unscored. This is a
conditional mapping model; it does not identify flooding outside FEMA's map.
**Tools → Exposure model** selects V1 (original) or V2 (the revised model).
Ridge comparisons are advisory under the user's revised policy. Both versions
have separately identified 25-hour local replay bundles; runtime configuration
and activation remain separate from this local implementation.

The [v2 datathon experiment](docs/modeling-v2.md) strengthens this same FEMA
mapping-proxy task with buffered nested spatial evaluation, target-group-balanced
training, explicit lineage review and rainfall sensitivity comparisons. V2 must
pass its frozen engineering gates before assessment production. V1 remains a
historical comparator; source changes do not activate a new hosted model.
The [completed v2 experiment](docs/modeling-run-v2.md) failed two frozen gates;
its candidate remains research-only. The report also inventories acquired storm
observations and records actual LinuxONE inference separately from activation.

The optional [modeling pipeline](docs/modeling.md) prepares spatially split datasets,
evaluates a FEMA mapping proxy, exports portable trees and produces experimental
rainfall/exposure assessments, with a separate gated observed-outcome experiment.
The [first real-data run](docs/modeling-run-v1.md) produced a trained portable
model and a local archived-rainfall assessment. Training artifacts stay under
ignored `data/processed/`; cloning this repo does not include them. The
[LinuxONE activation](docs/real-data-rollout.md#exposure-activation) records the
separately verified serving artifact and host benchmarks.
