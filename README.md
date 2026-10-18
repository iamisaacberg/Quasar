# Quasar

Okaloosa County flood risk intelligence starter for the IBM Z Datathon.

Quasar follows the team's Flood Emergency Alert System proposal, narrowed to **Okaloosa County, Florida (FIPS `12091`)**. It gives the team a working path from a property-like record to an explainable score, a map, and a simulated notification.

## Documentation

Start with the [documentation index](docs/README.md) for the full reading guide, existing contracts, and setup references.

- [App premise and product boundaries](docs/app-premise.md): the problem, intended audiences, current workflows, and limits of the demonstration.
- [Data guide](docs/data-guide.md): fictional and imported inputs, provenance, geographic scales, freshness, missing data, and BI interpretation.
- [Local parcel input preparation](docs/parcel-inputs.md): separate research environment, terrain coverage and unscored FEMA/waterway joins.
- [Mechanisms](docs/mechanisms.md): scoring formulas, architecture, forecast imports, replay, routing, frontend behavior, API, and configuration.
- [Improvement roadmap](docs/improvement-roadmap.md): concrete implementation gaps, data milestones, model evaluation, usability, scale, and completion evidence.

## Run locally

Install Python 3.11 or later. From this repository's root:

```sh
python3 -m quasar
```

Open <http://127.0.0.1:8000>. The Python backend has no third-party runtime dependencies. Add your Mapbox public token to enable the map. The site list, H3 indexing, score details and synthetic notification previews work without map credentials. Mapbox's SDK and basemap require internet access. The server is a local demo server, not a production hosting stack.

### Share with teammates over Wi-Fi

From a terminal, run:

```sh
npm run dev:wifi
# Or, without Node.js:
sh scripts/run-wifi.sh
```

Enter and confirm a shared password of at least 12 characters (use a unique,
hard-to-guess passphrase). The launcher detects your Mac's Wi-Fi address and
prints an **https://** team URL. Teammates on the same Wi-Fi open that URL and
enter the shared passphrase on the Quasar team access page. The passphrase
protects the page, static assets, health endpoint and API. A successful
sign-in opens a short-lived browser session.

The launcher creates a temporary HTTPS certificate and prints its SHA-256
fingerprint. Browsers show a certificate warning: teammates should compare the
certificate's SHA-256 fingerprint with yours before accepting it. The certificate
and key are removed on normal shutdown; restarting creates a new certificate.
The password is never printed or written by the launcher. For a noninteractive
run, optionally set `QUASAR_WIFI_PASSWORD` in your ignored `.env` instead of
entering it each time. Never put it in a command argument or share your `.env`.

Keep your laptop awake and the terminal running; **Ctrl-C** stops sharing.
Allow incoming connections for Python if macOS prompts. Guest/campus Wi-Fi may
block device-to-device connections even when everyone uses the same network.
The launcher requires OpenSSL and binds only to the selected Wi-Fi address;
it does not open a public tunnel or configure your router. To select an address
or a different port explicitly:

```sh
npm run dev:wifi -- --host 192.168.1.42 --port 8001
```

If your Mapbox public token is restricted to localhost, allow this HTTPS demo
origin in its URL restrictions so teammates can load the map. This shared
password gate is for temporary team demos; anyone with the password can access
the app while it is running.

### Share a hosted preview

For networks that block device-to-device Wi-Fi traffic, use the
[password-protected Vercel setup](docs/vercel.md). Every page, asset and API
route requires the shared team password. The hosted app refuses access if
`QUASAR_TEAM_PASSWORD` is missing or invalid.

### Local configuration

```sh
cp .env.example .env  # only if you do not already have .env
```

Edit `.env` and set `MAPBOX_PUBLIC_TOKEN=pk.your_public_token`. The app reads `.env` at startup; restart after editing. Existing environment variables take precedence. Use a public browser token with the appropriate Mapbox URL restrictions for your local/demo origin. Secret `sk.` tokens are rejected. `.env` is ignored by Git. An optional `MAPBOX_STYLE` accepts a `mapbox://styles/...` URL.

The app now targets Okaloosa County (12091), uses Central time, and supports countywide native WeatherNext rainfall cells. Old Miami-Dade snapshots are incompatible. Boundary, parcels, FEMA, elevation, monitoring stations and roads are reacquired separately; real parcel scores stay unknown. WeatherNext imports are explicit and capped; see [integration setup and monthly budget](docs/integrations.md).

```sh
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
npm test
```

## Data workspace

The **Data** sidebar view uses imported county-native WeatherNext cells and the verified parcel inventory, separately from the fictional-site reports. Its summary, charts, searchable cell table and CSV preserve six-hour rainfall, missing/stale states and source provenance. Select a retained forecast window to inspect it. Parcel counts come from the indexed inventory manifest; older hosts or live GIS browsing without a verified total show unknown. Real parcels remain unscored. No configured county snapshot means an unavailable state, with no synthetic fallback. Rechecking reads configured local/bridge sources and does not start a cloud import.

## Map workspace UI

The exposure map uses a fixed green/yellow/orange/red gradient, gray hatching for
unknown or incomplete inputs, and numeric inspection. Optional explicit parcel
assessments and server-side P90 cell summaries follow the
[exposure display contract](docs/exposure-display.md). A matching assessment
artifact is required; real parcel indices otherwise remain unknown. Green does
not establish safety.

The Map overview fills the space beside the stock Application Shell 2 navigation
sidebar. A floating county address/place search sits at the top, a tools dock at
bottom-left, shared forecast/archive playback at bottom-center, and the active
legend at bottom-right. Tools contains source, display, H3 and inspection controls.
The Mapbox Light style is the default; `MAPBOX_STYLE` can override it.

Search uses temporary Mapbox geocodes and filters result coordinates against the
authoritative Okaloosa polygon, including holes and islands. Selecting a location
moves the map and adds a temporary marker; it does not assign a parcel or score.
Search requires a public token and available county boundary. The site inspector
remains available without a working map. Details float over the map; on mobile
they open as a modal bottom sheet. Isaac reviews the rendered layout.

Imported forecast playback reads retained hourly rows through
`/api/weather/timeline`; it never launches an import. Each frame shows the
following six-hour rainfall total, advancing one hour at a time. An 18-hour
county run supports 13 positions; older six-hour-only files provide one frame.
The same play control drives the October 9 archive when that source is selected.
Static synthetic windows have no playback. Freshness uses real time; scrubbing
cannot revive expired inputs. Missing values stay unavailable. Initialization,
import time, native resolution, units and interpretation are in the expandable
legend information. Simulated routing remains exclusive to the archive/what-if
workflow.

When an imported WeatherNext snapshot is selectable, the map opens with that
source and **Rainfall · mm / 6h**. Native forecast polygons show county rainfall when a county snapshot is imported; blue points and numeric labels show rainfall at the six fictional sites. The summary shows the
validity window, initialization/import times, native resolution, available-site
count and unavailable values. Stale or incomplete rainfall remains unavailable;
valid zero rainfall stays zero even when missing terrain prevents a site score.
Site scores remain fictional; native rainfall cells are not flood depth. **Relative
exposure** switches to experimental parcel indices and server-side P90 H3 summaries
when matching assessments are configured; otherwise those indices stay unknown.
A neutral county H3 grid stays available for parcel browsing in rainfall mode. Legends and demo labels remain visible.

**Inspect sites** opens the site selector and factor explanation, including when
Mapbox is unavailable. The **Isaias simulation** button opens archive/what-if
controls, playback, selected-site trend and simulated routing in the same map's
floating details panel. Exit returns to the preceding data source. The old `/#isaias-replay`
link still opens the simulation within Map overview. The other navigation links
retain sites, source status, reports and the guide.

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

- Six **fictional** Okaloosa exercise sites, including one with missing terrain data.
- Three deterministic exercise windows with changing synthetic rainfall and gauge conditions.
- A Mapbox GL JS map, prioritized site list, factor contributions, and explicit unknown scores.
- Countywide H3 browsing at resolutions 4–7, adapting to zoom like TrialSmiles. Every cell click opens a summary with an explicit zoom action; resolution-7 cells progressively load matching county GIS polygons and keep them in a bounded browser cache across visits. A parcel opens its own details panel with a back-to-cell action. Parcel scores remain unknown; configured verified inputs appear as descriptive context. Hexagons intersect the authoritative Census boundary and can extend past it; they are not county boundaries, flood extents or sharper weather predictions.
- A WeatherNext 3 BigQuery importer for the native 0.1-degree ensemble-mean hourly precipitation product, with six-hour aggregation, provenance, missing-data and staleness checks.
- Opt-in SMS/email **previews** for elevated scores. Nothing is sent or stored, and no contact details are collected.
- A JSON/GeoJSON API and a separately callable NWS point-alert client.
- Automated tests, GitHub Actions, and a portable container starter.

**This is a baseplate, not a validated flood model.** Offline [parcel input preparation](docs/parcel-inputs.md) produces descriptive terrain summaries and FEMA/mapped-waterway joins in separate research artifacts. An optional verified inspection artifact connects those descriptive inputs to parcel details and cell summaries; they do not enter app scoring. See [parcel inspection setup](docs/parcel-inputs.md#application-inspection-artifact). Building footprints, trained AI, a fully sourced historical replay, real subscriptions and real delivery remain unavailable. Real parcel geometry is loaded on selection from Okaloosa GIS, with full county containment checks; exercise scores never apply to those parcels. WeatherNext rainfall can be imported once for county native cells and associated locally with the six fictional sites; when selected, the UI says **MIXED DEMO** because terrain, FEMA and gauge inputs remain invented. Forecasts never validate those property inputs. The dashboard's official-alert panel deliberately says the feed is not connected.

## Isaias 2026 replay

The map toolbar’s **Isaias simulation** action connects hourly forecast reconstruction, a selected-site trend, and a simulated resident evacuation route. Archive and what-if modes stay separate; missing historical rainfall stays unknown. Public NHC context and a county-contained real-road exercise network can be prepared locally with `python3 scripts/prepare_isaias.py`. Historical WeatherNext rainfall requires a separate explicit, capped import; the current October 17 snapshot is not reused. See [replay setup and walkthrough](docs/isaias-demo.md).

## Demo walkthrough

1. Start at Exercise hour 0 and inspect a site.
2. Switch to hours 6 and 12. The synthetic weather factors change the scores.
3. Inspect the missing-terrain site: it remains unknown rather than receiving a low score.
4. At hour 12, inspect an elevated site, select the simulation opt-in checkbox, and preview an email. The API reports `sent_count: 0`.
5. Explain that the next milestone replaces fixture inputs with timestamped source data and validates the model against a documented Okaloosa storm.

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
| GET | `/api/county` | Authoritative Census Okaloosa boundary and provenance; unavailable sources return 502 |
| GET | `/api/parcels?ring=...&offset=0` | County-validated parcel polygons intersecting an R7 ring; automatically paginated by the map |
| GET | `/api/parcels/manifest` | Lightweight geometry/source version for persistent browser caching |
| GET | `/api/parcels/{id}/context` | Verified descriptive parcel inputs and native forecast overlaps; no score |
| GET | `/api/cells/{h3}/summary` | Distinct indexed parcel counts, input coverage and native overlaps at R4–R7 |
| GET | `/api/exposure?from=...&to=...&mode=current&resolution=7` | Optional matching parcel assessments and complete-inventory P90 summaries; [contract](docs/exposure-display.md) |
| GET | `/api/weather/status` | Explicit not-configured, ready, incomplete, stale or invalid snapshot status |
| GET | `/api/data/weather` | Native-cell forecast windows for the Data tab, without fictional sites or scores |
| GET | `/api/reports?scenario=compare` | Shared analysis for reports; single windows also supported |
| GET | `/api/exports?scenario=compare&format=zip` | CSV, GeoJSON or BI bundle download |
| GET | `/api/timeline?site=demo-001` | Isaias hourly forward-six-hour scores and source status |
| GET/POST | `/api/routes` | Isaias exercise routing, explicit availability, and simulated overrides |
| GET | `/api/replay/context` | Locally acquired NHC advisory context |
| GET | `/api/official-alerts` | Explicit `not_connected` status |
| POST | `/api/notifications/preview` | Simulation only; no delivery |

Example preview body:

```json
{"property_ids":["demo-001"],"scenario":"peak","channel":"sms","opt_in":true}
```

Other county FIPS values are rejected. `scenario` accepts `baseline`, `heavy-rain`, `peak`, or `weathernext` when a valid snapshot is configured; `isaias-2026` adds optional `at`, `preset`, and `mode` parameters. Unknown sites and scenarios return errors. No cloud query is triggered by loading the dashboard.

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

Develop locally first and run an early compatibility check on IBM Z. The backend uses only Python's standard library, avoiding compiled GIS/ML packages at this stage. This local transition does not establish the current IBM server state; verify a transferred bundle independently.

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

1. Use the locally acquired authoritative county polygon to validate and clip residential parcels/building footprints. Review source terms and keep owner/address fields out of the modeling dataset.
2. Normalize the locally acquired FEMA NFHL and USGS 3DEP inputs with CRS, vertical datum, missing-data flags, source timestamps, and county clipping. Evaluate coastal/tidal and canal conditions specific to Okaloosa.
3. Select hydrologically relevant USGS stations and acquire observations; ingest NWS official alerts. Implement caching, staleness, expired-alert handling and outage states before wiring a live feed into the UI.
4. Refresh WeatherNext snapshots explicitly with a dry run and byte cap. Use native county cells, then associate assets locally without per-parcel cloud queries.
5. Select and document a historical storm that affected Okaloosa, acquire archived inputs and observed outcomes, and implement reproducible replay. Split training/evaluation by event/time to avoid leakage.
6. Compare the transparent baseline with a trained model, document validation and uncertainty, then demonstrate the pipeline on IBM Z.
7. Add persistent consent, unsubscribe, deduplication and delivery infrastructure only if real notifications are in scope. The datathon proposal calls for simulated delivery.

See [architecture](docs/architecture.md), [data contract](docs/data-contract.md), and [source catalog](docs/data-sources.md).
