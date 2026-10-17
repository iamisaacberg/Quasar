# Quasar

Miami-Dade County flood risk intelligence starter for the IBM Z Datathon.

Quasar follows the team's Flood Emergency Alert System proposal, narrowed to **Miami-Dade County, Florida (FIPS `12086`)**. It gives the team a working path from a property-like record to an explainable score, a map, and a simulated notification.

## Run locally

Install Python 3.11 or later. From this repository's root:

```sh
python3 -m quasar
```

Open <http://127.0.0.1:8000>. The Python backend has no third-party runtime dependencies. Add your Mapbox public token to enable the map. The site list, H3 indexing, score details and synthetic notification previews work without map credentials. Mapbox's SDK and basemap require internet access. The server is a local demo server, not a production hosting stack.

```sh
cp .env.example .env  # only if you do not already have .env
```

Edit `.env` and set `MAPBOX_PUBLIC_TOKEN=pk.your_public_token`. The app reads `.env` at startup; restart after editing. Existing environment variables take precedence. Use a public browser token with the appropriate Mapbox URL restrictions for your local/demo origin. Secret `sk.` tokens are rejected. `.env` is ignored by Git. An optional `MAPBOX_STYLE` accepts a `mapbox://styles/...` URL.

WeatherNext 3 BigQuery access is confirmed by the project owner. The importer and app integration are implemented; the team's actual project, linked table, account and data have not yet been connected or verified. Follow [integration setup](docs/integrations.md).

```sh
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
npm test
```

## Map workspace UI

The map lives inside **Shadcnblocks Application Shell 2**, with an inset sidebar,
icon collapse on desktop, and drawer navigation on mobile. Navigation links lead
to the map, exercise sites, forecast/source status, and the exercise guide.
Mapbox resizes when the sidebar width changes. Site inspection, H3 visibility,
unknown data states, mixed forecast labels, and simulated notification previews
use the existing controller and API.

React/Tailwind source lives in `frontend/`. Vite builds the shell into
`quasar/static/ui/`; those generated assets are committed so `python3 -m quasar`
and the Python-only container do not require Node.js at runtime. After UI changes:

```sh
npm ci --ignore-scripts
npm run check
npm test
npm run build
```

Commit updated shell assets with their source. CI rebuilds and checks for stale
assets. Restart an already running Python server after this upgrade to load the
new static asset routes, then refresh the page.

`components.json` configures the authenticated `@shadcnblocks` registry. To add
blocks, set `SHADCNBLOCKS_API_KEY` in the ignored `.env` and use the shadcn CLI:

```sh
npx shadcn@latest add @shadcnblocks/application-shell2
```

The registry key is development-only and never enters the frontend bundle or
`/api/config`. The original block's example account, branding, and placeholder
navigation have been replaced with Quasar's exercise workspace. The Python
runtime, scoring, and cloud-query behavior remain unchanged.

## What works today

- Six **fictional** Miami-Dade exercise sites, including one with missing terrain data.
- Three deterministic exercise windows with changing synthetic rainfall and gauge conditions.
- A Mapbox GL JS map, prioritized site list, factor contributions, and explicit unknown scores.
- H3 resolution-7 hotspot summaries of occupied exercise sites, with counts, unknown counts and maximum relative score. Hexagons are not flood extents or sharper weather predictions.
- A WeatherNext 3 BigQuery importer for the native 0.1-degree ensemble-mean hourly precipitation product, with six-hour aggregation, provenance, missing-data and staleness checks.
- Opt-in SMS/email **previews** for elevated scores. Nothing is sent or stored, and no contact details are collected.
- A JSON/GeoJSON API and a separately callable NWS point-alert client.
- Automated tests, GitHub Actions, and a portable container starter.

**This is a baseplate, not a validated flood model.** It has no live parcels, building footprints, FEMA joins, elevation raster processing, trained AI, historical storm replay, real subscriptions, or real delivery. WeatherNext rainfall can be imported for the six fictional site coordinates; when selected, the UI says **MIXED DEMO** because terrain, FEMA and gauge inputs remain invented. Forecasts never validate those property inputs. The dashboard's official-alert panel deliberately says the feed is not connected.

## Demo walkthrough

1. Start at Exercise hour 0 and inspect a site.
2. Switch to hours 6 and 12. The synthetic weather factors change the scores.
3. Inspect the missing-terrain site: it remains unknown rather than receiving a low score.
4. At hour 12, inspect an elevated site, select the simulation opt-in checkbox, and preview an email. The API reports `sent_count: 0`.
5. Explain that the next milestone replaces fixture inputs with timestamped source data and validates the model against a documented Miami-Dade storm.

The exercise dates are a fixed fictional clock, not today's weather or an actual hurricane. All site labels, FEMA zones, elevations, and other attributes are invented.

After importing a valid WeatherNext snapshot and setting `QUASAR_WEATHERNEXT_FILE` in `.env`, restart and choose **WeatherNext 3 + fictional site inputs** in the time-window selector. The UI shows initialization/import timestamps and forecast status. Stale or incomplete rainfall yields unknown scores; it never silently falls back to synthetic rain in that mode. Notification previews remain limited to the synthetic exercise scenarios.

## Reports & exports

Open **Reports & exports** in the sidebar for a scenario overview, a comparison
of the three exercise windows, or an explanation of one fictional site. Charts
have matching data tables. **Print / Save as PDF** prints the selected report with
its labels, dates, source notes and limitations; it links to the interactive map.
Reports work without a Mapbox token. Isaac reviews visual and print layout.

Download CSV for Power BI/Tableau, GeoJSON for spatial analysis, or the **BI bundle**
for all data plus factor rows, metadata and import instructions. Start both
teammates with `/api/exports?scenario=compare&format=zip`: six fictional sites across
three windows produce 18 rows. Power BI can explore changes and completeness;
Tableau can explore spatial patterns and unknowns. Relate factor rows by both
site and scenario; preserve blank scores as unknown, never zero. Download again
to refresh all files together. No export starts a cloud query or sends messages.

These are synthetic or mixed demonstrations of an unvalidated heuristic, not a
trained flood model or countywide coverage. WeatherNext reports keep the imported
forecast's freshness and native resolution visible alongside fictional site inputs.
See [the export contract](docs/data-contract.md#reports-and-bi-exports-additive-contract).

## API

| Method | Path | Result |
| --- | --- | --- |
| GET | `/health` | Server status, county, demo mode |
| GET | `/api/config` | Fixed pilot scope and notices |
| GET | `/api/scenarios` | Three synthetic windows |
| GET | `/api/properties?scenario=peak` | Scored GeoJSON points |
| GET | `/api/properties?scenario=weathernext` | Imported forecast + fictional property inputs, when a valid snapshot is configured |
| GET | `/api/weather/status` | Explicit not-configured, ready, incomplete, stale or invalid snapshot status |
| GET | `/api/reports?scenario=compare` | Shared analysis for reports; single windows also supported |
| GET | `/api/exports?scenario=compare&format=zip` | CSV, GeoJSON or BI bundle download |
| GET | `/api/official-alerts` | Explicit `not_connected` status |
| POST | `/api/notifications/preview` | Simulation only; no delivery |

Example preview body:

```json
{"property_ids":["demo-001"],"scenario":"peak","channel":"sms","opt_in":true}
```

Other county FIPS values are rejected. `scenario` accepts `baseline`, `heavy-rain`, `peak`, or `weathernext` when a valid snapshot is configured. Unknown sites and scenarios return errors. No cloud query is triggered by loading the dashboard.

## Team work areas

The repository supports both regular Python development and optional Jupyter Notebook research. The teammate using notebooks can start with [the shared-code starter](notebooks/01_shared_code_starter.ipynb) and [notebook setup](notebooks/README.md). Everyone else can run the app and the same analysis without installing Jupyter:

```sh
python3 -m quasar.analysis --scenario peak
python3 -m quasar.analysis --compare
```

Reusable analysis lives in `quasar/analysis.py`; it calls the existing application pipeline rather than duplicating scoring. The optional `.[notebooks]` dependency extra stays out of the application runtime/container. GitHub checks that source notebooks have clean outputs and execute from a fresh kernel.

| Area | Start here | First useful contribution |
| --- | --- | --- |
| Data / GIS | `quasar/pipeline.py`, `docs/data-contract.md` | County boundary, parcels and building joins; provenance |
| Modeling / AI | `quasar/scoring.py` | Validated features, baseline evaluation, then trained model |
| Notebook research | `notebooks/01_shared_code_starter.ipynb`, `quasar/analysis.py` | Explore and document; promote reusable work into shared Python functions |
| Frontend | `quasar/static/` | Mapbox layers, H3 summaries, real parcel polygons |
| Integration / IBM Z | `quasar/server.py`, `Dockerfile` | Server smoke test, environment setup, reproducible replay |

Agree on ownership before editing shared contracts. Use feature branches and small pull requests into `preview`; see [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) for shared AI coding instructions.

## IBM Z / LinuxONE

Develop locally first and run an early compatibility check on IBM Z. The backend uses only Python's standard library, avoiding compiled GIS/ML packages at this stage. No IBM server has been accessed or tested yet.

On your IBM Z Linux host with Python 3.11+:

```sh
python3 -m unittest discover -s tests -v
python3 -m quasar --host 127.0.0.1 --port 8000
```

Use an SSH tunnel to view that localhost service from your laptop. Substitute your actual host and user; do not commit credentials:

```sh
ssh -L 8000:127.0.0.1:8000 USER@IBM_Z_HOST
```

Container option (Docker or equivalent Podman commands):

```sh
docker build -t quasar:demo .
docker run --rm --env-file .env -p 127.0.0.1:8000:8000 quasar:demo
```

Build natively on IBM Z, or use a configured cross-builder:

```sh
docker buildx build --platform linux/s390x -t quasar:demo --load .
```

The container runs as a non-root user. The base image tag, container runtime, outbound network access and `s390x` build must be verified on the provided server; CI's container build alone checks x86 Linux. Browser map and H3 rendering stay on the laptop; no compiled H3 Python package is needed on IBM Z. For WeatherNext in a container, mount the normalized snapshot read-only at the configured container path and ensure UID 10001 can read it; do not bake Google credentials into the image. The import can run on a laptop or Cloud Shell, then transfer only its snapshot to IBM Z. There is no cloud deployment in this starter.

## Next milestones

1. Acquire an authoritative Miami-Dade county polygon and clip residential parcels/building footprints. Enforce real geometry membership before accepting external data.
2. Add FEMA NFHL and USGS 3DEP features with CRS, vertical datum, missing-data flags, and source timestamps. Evaluate coastal/tidal and canal conditions specific to Miami-Dade.
3. Ingest NWS official alerts and USGS observations. Implement caching, staleness, expired-alert handling and outage states before wiring a live feed into the UI.
4. Configure the owner's existing WeatherNext BigQuery access, dry-run the generated query against the actual linked schema, and import a current forecast window. Extend coverage to real county-filtered assets after the GIS work.
5. Select and document a historical storm that affected Miami-Dade, acquire archived inputs and observed outcomes, and implement reproducible replay. Split training/evaluation by event/time to avoid leakage.
6. Compare the transparent baseline with a trained model, document validation and uncertainty, then demonstrate the pipeline on IBM Z.
7. Add persistent consent, unsubscribe, deduplication and delivery infrastructure only if real notifications are in scope. The datathon proposal calls for simulated delivery.

See [architecture](docs/architecture.md), [data contract](docs/data-contract.md), and [source catalog](docs/data-sources.md).
