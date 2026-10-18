# Architecture and implementation status

> Current application behavior is defined by [data-contract.md](data-contract.md).
> Synthetic scoring, fictional sites, what-if controls and simulated routing
> described below are retained offline research context; their application
> endpoints are retired. The app uses native county forecasts and prepared
> parcel inputs, with transparent unknown interiors and no synthetic fallback.


```text
Synthetic JSON adapters
    -> Okaloosa scope checks
    -> property/weather feature contract
    -> illustrative score + factor contributions + unknown state
    -> GeoJSON API
    -> Mapbox / H3 occupied-site summaries / list / simulated notification preview

Locally authenticated BigQuery CLI (explicit, dry-run by default)
    -> WeatherNext 3 native-cell point join, one run and six hourly steps
    -> validated local JSON snapshot
    -> freshness + completeness checks
    -> real rainfall + fictional property/gauge inputs (MIXED DEMO)

Optional NWS point client -> timestamped official feed response (CLI only)

Planned: county GIS / FEMA / USGS / historical archive
    -> spatial joins + provenance + freshness -> validated model + replay
```

One Python process serves the API and static frontend. The React/Tailwind application shell in `frontend/` wraps the existing map/data controller; Vite compiles it into committed `quasar/static/ui/` assets. The Python runtime serves only explicit asset routes, and its container needs no Node.js runtime. The Shadcnblocks key is used only by development tooling, never by the API or browser. A separate SQLite store holds minimal county parcel geometry and H3 memberships. There is no scoring database, worker, scheduler or external message delivery. This keeps the starter easy to run on each teammate's computer and on IBM Z. A later public service needs an application hosting stack, individual authentication, persistence, rate limits and operational monitoring.

The optional `quasar.wifi` launcher binds to the laptop's Wi-Fi IPv4 address and
requires HTTPS plus a shared passphrase entered on the Quasar team access page. A signed, HTTP-only session cookie protects static files and API endpoints together. Credentials are compared through constant-time
digest comparison and never enter frontend configuration. A temporary local TLS
certificate is generated with OpenSSL and its fingerprint is printed for manual
verification. The private key is removed on normal exit. This is temporary team access,
not individual accounts or a public hosting service. The normal localhost command
does not enable this gate; use `npm run dev:wifi` when sharing with teammates.

The default API mode uses synthetic fixtures. A separate WeatherNext scenario uses imported rainfall with fictional property/gauge inputs and is explicitly labeled `mixed_forecast_demo`. No dashboard request queries Google Cloud. Notification previews are limited to fully synthetic scenarios. The NWS adapter is intentionally separate: live alerts must not appear to validate a synthetic property score. Call it explicitly to inspect official alerts for one fixture coordinate:

```sh
python3 -m quasar.adapters.nws --property-id demo-001 --user-agent 'Quasar-datathon/0.1 (YOUR_CONTACT)'
```

Replace `YOUR_CONTACT` with a team-approved identifying contact. The client queries the official NWS active-alert endpoint by point, preserves the raw GeoJSON and retrieval time, uses a timeout, and propagates failures. Its response is not countywide coverage. Before UI integration, add expiration/freshness validation, caching, retry/backoff and comprehensive zone/polygon coverage tests. Do not infer "no flood hazard" from an empty response.

## Scoring baseline

| Input | Weight | Illustrative exposure normalization |
| --- | --- | --- |
| Six-hour rainfall (mm) | 35% | rainfall / 120 |
| Terrain elevation (m) | 20% | (10 - elevation) / 10 |
| FEMA zone | 20% | V/VE: 1; A/AE/AH/AO: 0.8; X: 0.2 |
| Distance to waterway (m) | 10% | 1 - distance / 1000 |
| Gauge margin below flood stage (m) | 15% | (1 - margin) / 1.5 |

Clamp each normalized feature to 0-1, multiply by its weight and 100, and sum. Contributions are reported in score points. Bands are `lower_relative` below 35, `moderate` from 35 to below 65, and `elevated` at 65 or above. Any missing factor or unrecognized FEMA zone yields `unknown`, with a null score. A complete synthetic input reports `data_status: synthetic`; missing inputs report `incomplete`.

These weights, limits and bands are arbitrary demonstration parameters. FEMA X variants are simplified and need proper subtype handling. Low absolute elevation alone is not a flood model. Gauge-to-property linkage, terrain connectivity, drainage/canals, coastal tides, surge, soils and antecedent conditions are not modeled. All fixture gauges and attributes are invented. A gauge flood-stage margin is meaningful only with a defensible gauge linkage and compatible vertical datum. Do not use this score for operational decisions.

For real data, maintain observed time, forecast issue/valid times, data age and source references at feature level. The WeatherNext integration enforces initialization age <=12 hours, import age <=2 hours, and a window that has not ended. These are conservative starter policies, not a meteorologically validated operational policy. Incomplete six-hour windows and stale imports produce null rainfall and unknown scores. The fixed synthetic exercise clock has no live-weather meaning.

## Mapbox and H3

Mapbox GL JS 3.33.0 renders the site GeoJSON as a circle layer and H3 cells as fill/outline layers. A runtime configuration endpoint returns only the public Mapbox token and style. The table remains usable when credentials, WebGL, SDK resources or map tiles are unavailable.

H3 4.3.0 is bundled as browser JavaScript with its Apache license/notice. `spatial.js` retains resolution-7 fictional-site indexing and summaries. The county exposure layer instead colors cells using server-side P90 summaries from complete indexed parcel memberships, with explicit coverage and unknown counts. Optional assessments must match the displayed parcel inventory and forecast window; absent assessments stay gray/hatched. See the [exposure display contract](exposure-display.md); no parcel scoring method is implemented here.

Hexagon boundaries are not clipped to the county and may cross its border; the browsing grid covers county-intersecting cells. Hexagons are not inundation areas or proof of complete assessment coverage. Their sizes do not increase WeatherNext's original 0.1-degree resolution. Forecast values are associated using the source polygon directly, before any H3 display aggregation. Real property terrain, footprints and waterway relations must retain their own geometry.

See [integration setup](integrations.md) for authentication, query semantics, required project details and remaining live checks.

## Hosted team preview

The optional Vercel adapter in `api/index.py` routes every page, static asset and
API call through a shared-password gate. A missing or invalid
`QUASAR_TEAM_PASSWORD` blocks all app requests. An unconditional route runs before
filesystem lookup; static output contains only a harmless placeholder. Only named normalized demo
snapshots may be uploaded; missing/stale states remain explicit. See the
[Vercel setup](vercel.md) for environment configuration, verification and access
revocation. The Python application and local IBM Z workflow remain reusable.

## IBM Z plan

Research can use `notebooks/01_shared_code_starter.ipynb`, while regular Python/editor users can run `python -m quasar.analysis --compare`. Both call `quasar.analysis`, which delegates scoring to the existing application pipeline. Notebook-specific dependencies live in the optional `.[notebooks]` extra and are not installed by the application or container. CI executes clean notebook sources in fresh kernels; no running notebook is needed by the service. See [notebook workflow](../notebooks/README.md).

The Python core has no third-party runtime packages and the container has no processor-specific build instructions. This is a portability design choice, not certification. Run the tests and container on the actual Linux `s390x` host before claiming IBM Z compatibility. Add ML/GIS packages only after checking native wheels or a reproducible build on the team's target host.

An optional authenticated [LinuxONE snapshot bridge](data-bridge.md) lets the
Vercel Python function fetch the allow-listed normalized inputs from the IBM
host. The browser still calls the Vercel API; no IBM token reaches frontend code.
The bridge is disabled by default and requires operator-provided HTTPS ingress.

## Isaias replay and exercise routing

The additive `isaias-2026` scenario reads a separate historical archive; `quasar.replay` selects runs against a shared replay clock and calls the existing score function. Historical and current-forecast freshness policies are separate. A forward-six-hour score is recomputed hourly; missing values remain null. The timeline and routes include the same timestamp/mode/preset. The frontend commits their responses together and ignores late requests.

`quasar.routing` uses standard-library Dijkstra over a locally prepared, county-contained road graph. Road geometry is from county centerlines; two-way traversal, constant speed, destinations, connectors and closure phases are explicitly simulated. Complete line validation in `quasar.geometry` checks polygon holes and concavities. No property score or H3 bin is treated as evidence of passability. Runtime graph reads are cached by file modification time and size. No replay or route API performs a cloud query.
