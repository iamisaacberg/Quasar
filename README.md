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
positions, native rainfall polygons and an interactive maximum-cell rainfall trend.
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
mapping proxy and rainfall interaction; no validated flood model is established.
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

The optional [modeling pipeline](docs/modeling.md) prepares spatially split datasets,
evaluates a FEMA mapping proxy, exports portable trees and produces experimental
rainfall/exposure assessments, with a separate gated observed-outcome experiment.
No real trained model or LinuxONE benchmark is established by adding this code;
absent datasets and failed promotion gates remain explicit.
