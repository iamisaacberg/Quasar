# Shared instructions for AI coding assistants

## Scope

- This repository is Quasar, a Okaloosa County flood intelligence datathon project. Only county FIPS `12091` is in scope.
- Read `README.md` and relevant `docs/` before changing interfaces. The supplied proposal is context; direct user instructions control scope.
- Keep synthetic data visibly labeled. Never invent source access, official alerts, historic observations, real parcels, or model validation.
- Project estimates supplement official NWS/local guidance. Do not express a score as flood depth, flood probability, an evacuation order, or a guarantee of safety.
- The existing score is an illustrative heuristic, not trained AI. Model work must document training data, evaluation and limitations.

## Development

- Work on a feature branch; open a pull request targeting `preview`. Do not push to `main` or deploy without explicit user authorization.
- Prefer small changes within your assigned area. Coordinate changes to `docs/data-contract.md`, the API, or shared fixtures.
- Run `python3 -m unittest discover -s tests -v`, `npm ci --ignore-scripts`, `npm run check` and `npm test` before proposing a merge. Add tests for changed scoring, data validation and API behavior.
- Keep the Python starter dependency-free unless a new dependency materially helps. Check `s390x` availability before adding compiled GIS/ML packages.
- Store external downloads under ignored `data/raw/` and derived artifacts under ignored `data/processed/`. Record retrieval time, license, CRS, units, source identifier and processing steps.
- External property data requires authoritative county-boundary validation; trusting a supplied FIPS tag or a bounding box is insufficient.
- Preserve unknown and stale data states. Missing inputs never mean low risk. Upstream errors never mean no active alerts.
- Notification code is simulation only. Do not collect real contact data, send messages, or add delivery credentials without explicit task authorization.
- Do not commit secrets, `.env`, real opt-ins, raw property datasets, or server credentials.
- Do not start deployments, change shared infrastructure, or access the team's IBM Z host unless asked.
- Mapbox receives only a public `pk.` token. Never expose Google OAuth tokens, service-account keys or Mapbox secret tokens through an API or browser bundle.
- WeatherNext BigQuery access is confirmed. Keep actual connection status separate from that entitlement; do not claim a live test without one. Cloud queries are explicit importer commands, dry-run by default, with a byte cap.
- H3 resolution-7 cells summarize occupied sites. They do not replace county geometry, native WeatherNext cells or property-level terrain; never claim H3 increases forecast resolution.
- Preserve source initialization, validity, import time, native resolution and rainfall units. Missing, duplicate, null or stale hourly inputs must not become zero rainfall.
- Support both notebook research and regular app/editor development. Jupyter is optional via `.[notebooks]`; do not add it to the app runtime or container.
- Keep reusable analysis, transformations, adapters and model logic in `quasar/` with tests. Notebooks import those functions; they may contain presentation and experiment-specific orchestration, but no second scoring implementation.
- Assign a notebook owner per experiment. Commit clean `.ipynb` source without cell outputs or execution counts. Use `python scripts/check_notebooks.py --clear` and, in the optional environment, `python scripts/check_notebooks.py --execute` before proposing notebook changes. Never turn on automatic cloud queries in the starter.
