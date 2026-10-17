# Mapbox, WeatherNext 3 and H3 setup

## Verified project connection

On October 17, 2026, the signed-in Google Cloud console showed the existing WeatherNext 3 linked dataset and its two tables:

- Project: `quasar-ibm-z-datathon`.
- Precipitation table: `quasar-ibm-z-datathon.weathernext_3.weathernext_3_0_0_0p1deg`.
- Linked dataset location: `US`.
- Console account: the owner's existing Google account.
- BigQuery currently shows sandbox mode. No billing upgrade was performed.

The owner authorized Cloud Shell, and the existing importer completed a live BigQuery import. The snapshot is configured in the ignored local `.env`, and the existing Quasar run on port `55000` was restarted with the owner's approval. `/api/weather/status` reported `ready`; `/api/properties?scenario=weathernext` returned all six fictional sites with six hourly forecast inputs each. The missing-terrain site remained unscored.

Observed snapshot (October 17, 2026):

- Initialization: `2026-10-17T10:00:00Z`.
- Forecast window: `2026-10-17T18:00:00Z` through `2026-10-18T00:00:00Z` (2–8 p.m. Miami time).
- Imported: `2026-10-17T18:38:40.193291Z`; 36 hourly rows.
- Local file: `data/processed/weathernext.json`; provenance and source terms: `data/raw/weathernext/source_metadata.json`.
- Dry-run estimate / actual bytes processed: `17,738,611,200`. This single import used an explicit `20,000,000,000` byte cap; the importer's default remains `1,000,000,000`.
- Job: `quasar-ibm-z-datathon:US.bqjob_r1be97a868200b640_000001a14b28a2b4_1`. The job report is saved in `data/processed/weathernext-import-report.json`.

This is a manually imported snapshot. Under the current two-hour import-age rule, it becomes stale at `2026-10-17T20:38:40.193291Z` (3:38 p.m. Central); refresh explicitly before then for continued current-data use. Dashboard requests do not refresh BigQuery.

Configure the Mapbox token locally. For future imports, authenticate the approved Google account using Google Cloud CLI or the authorized Cloud Shell session. Do not paste private keys or OAuth/refresh tokens into chat, `.env`, Git or browser configuration. Permission to read the linked dataset and run queries in the billing project must already be available to that account.

## Mapbox

Create `.env` from `.env.example` if it does not exist and set:

```dotenv
MAPBOX_PUBLIC_TOKEN=pk.your_public_browser_token
MAPBOX_STYLE=mapbox://styles/mapbox/dark-v11
QUASAR_WEATHERNEXT_FILE=
```

Restart `python3 -m quasar`. The `/api/config` response deliberately contains the public `pk.` token so Mapbox can use it in the browser. Secret `sk.` tokens are refused. Configure the token's allowed URLs for the actual local/demo origin and use only the browser scopes needed by your style. `.env` is ignored and excluded from the container image. The Mapbox client makes no Google Cloud calls.

## WeatherNext 3 BigQuery

The owner has chosen BigQuery. The implementation follows [Google's current schema](https://developers.google.com/weathernext/guides/bigquery): the **0.1-degree** table provides hourly precipitation mean in `forecast.total_precipitation_1hr_mean` in meters. The 0.05-degree station table is for temperature/dew point and is not a higher-resolution rainfall substitute.

Use the locally authenticated `bq` CLI from Google Cloud CLI, or run the import in Google Cloud Shell. The Python app itself needs no Google SDK or credentials. If using Cloud Shell, run from a clone of this branch and transfer only the resulting JSON snapshot to the local/IBM Z app.

The importer reads only the six curated demo coordinates. It queries an exact initialization partition, uses source-cell `ST_COVERS` point matching, and selects the six hourly steps ending one through six hours after the chosen start. It converts meters to mm and saves hourly rows plus source grid geometry and run metadata. A point lying on two source-cell boundaries can yield duplicates; the importer rejects that ambiguity instead of adding both cells' rain.

From the repository root, substitute your actual identifiers and timestamps:

```sh
python3 -m quasar.adapters.weathernext \
  --project YOUR_BILLING_PROJECT \
  --table YOUR_PROJECT.YOUR_LINKED_DATASET.weathernext_3_0_0_0p1deg \
  --location YOUR_DATASET_LOCATION \
  --init-time 2026-10-17T12:00:00Z \
  --window-start 2026-10-17T12:00:00Z
```

Those dates illustrate the format; select an initialization that exists and a useful current forecast window. The command defaults to a **dry run** and a 1,000,000,000-byte billing cap; it does not save a forecast. Add `--print-query` to inspect the generated SQL without any authentication or cloud request. Verify the exact linked schema and dry-run estimate before selecting an execution budget. A query exceeding `--maximum-bytes-billed` fails rather than exceeding that cap; this byte cap is not a dollar budget.

When ready, repeat the command with `--execute` to run the query and write `data/processed/weathernext.json`. This is an explicit cloud operation, never triggered by a page refresh. An import failure preserves the previous snapshot. The verified import above used the already linked dataset through the owner's authorized Cloud Shell session. No IAM roles or billing configuration were changed.

Set this in `.env` and restart:

```dotenv
QUASAR_WEATHERNEXT_FILE=data/processed/weathernext.json
```

Choose **WeatherNext 3 + fictional site inputs** in the dashboard. Both the API and UI label the result **MIXED DEMO**: actual forecast rainfall, invented property/FEMA/elevation/gauge attributes and an unvalidated scoring baseline. Synthetic scenarios remain separately selectable. Real forecast mode has no notification-preview control.

## Data quality and freshness

- Exactly six contiguous hourly inputs from one run are required for each point. Missing/null rainfall is unknown, not zero.
- Duplicate or out-of-window hours, negative/non-finite values, incorrect units/table resolution, unexpected point IDs, malformed timestamps or future initialization/retrieval times invalidate the import.
- An initialization older than 12 hours, snapshot import older than 2 hours, or forecast window that has ended is stale. These are explicit starter thresholds and should be revisited with the team.
- Stale/incomplete per-site rainfall is not passed as a numeric value into scoring. There is no silent fallback to synthetic rain in WeatherNext mode.
- Six-hour ensemble means are computed by summing hourly means. Hourly p90 values must not be summed and called a six-hour p90; ensemble trajectories are needed for that calculation.
- Forecast values retain the native 0.1-degree source grid. Assigning them to a point or H3 cell does not create address-level weather accuracy.

## H3 choice

H3 is useful for consistent site indexing and hotspot summaries. The initial implementation uses **resolution 7** in the browser through pinned `h3-js` 4.3.0. `npm ci --ignore-scripts` installs developer tooling; `npm run vendor` regenerates the committed browser bundle and license/notice from that version. Run `npm test` to verify indexing, aggregation, GeoJSON ring order, and that the vendored file matches the pinned artifact.

H3 is not used to infer terrain or join forecasts by a hexagon center. Forecast association uses each site's coordinate against the original WeatherNext polygon; H3 aggregates those results afterward. Cells show counts, unknown counts, maximum and mean relative scores for the sample sites only. The map colors by maximum. Unknown-only cells stay gray. No grid cells are invented for unsampled areas. Hexagons may cross the county boundary; the map is not showing complete county coverage or inundation extent.

Mapbox and H3 run in the browser, keeping the IBM Z Python backend free of new compiled dependencies. Later server-side H3 work needs an explicit `s390x` dependency/build check. The BigQuery table schema and first real forecast import were verified as recorded above. The actual IBM Z host and its runtime still require live verification; successful local API responses do not prove IBM Z readiness.

References: [Mapbox GL JS](https://docs.mapbox.com/mapbox-gl-js/), [WeatherNext 3 BigQuery](https://developers.google.com/weathernext/guides/bigquery), [BigQuery dry runs](https://docs.cloud.google.com/bigquery/docs/running-queries), [H3 API](https://h3geo.org/docs/api/indexing/).
