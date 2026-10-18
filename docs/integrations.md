# Mapbox, WeatherNext 3 and H3

Quasar targets **Okaloosa County, FIPS 12091**, in `America/Chicago` time. WeatherNext access is through the existing linked table `quasar-ibm-z-datathon.weathernext_3.weathernext_3_0_0_0p1deg`, location `US`. Access entitlement does not imply a configured or fresh app snapshot.

## WeatherNext budget

The October 17 live job-history audit found 401,510,332,800 bytes processed and 401,511,284,736 bytes billed before the county transition. This includes the original Miami-Dade point imports and a small metadata scan. These numbers are a checkpoint, not the current balance after future queries.

Google Sandbox provides 1 TiB (1,099,511,627,776 bytes) of query processing per month. Quasar uses a stricter **1,000,000,000,000-byte** planning ceiling. Query cost follows scanned columns/partitions, not downloaded file size. A small output or fewer parcels does not guarantee a smaller scan. [Google Sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox).

Before each execution, list all project jobs for the current month, retrieve full query statistics, include completed scans and reserve capacity for running jobs. Dry-run the exact SQL and parameters, record its estimate, then pass a hard `--maximum-bytes-billed` cap. Do not run concurrent importers or silently repeat a failed/truncated download with another source query. Retrieve completed job results again instead.

## County import

`python3 -m quasar.adapters.county_weather` imports native forecast cells intersecting the authoritative county polygon. It queries cells once, then associates fictional sites locally. It does not query once per parcel or H3 cell.

```sh
python3 -m quasar.adapters.county_weather \
  --project quasar-ibm-z-datathon \
  --table quasar-ibm-z-datathon.weathernext_3.weathernext_3_0_0_0p1deg \
  --location US --historical
```

Default is a dry run with a 1 GB per-query cap. `--print-query` prints SQL without cloud access. For current forecasts replace `--historical` with an available `--init-time` and `--window-start`, both whole-hour UTC timestamps. Execution requires `--execute` and a reviewed `--maximum-bytes-billed`. The importer audits all current-month project job metadata, reserves running-job caps and performs a fresh dry run before execution. It rejects an unknown/truncated job inventory or a total above the planning ceiling. Optional `--verified-month-bytes` can raise this reservation; it cannot lower the audited usage. No dashboard request queries BigQuery.

County snapshots use schema 3, native cell geometries and hourly rows grouped by initialization. The site pipeline also accepts the older six-site schemas 1/2 for Okaloosa; Miami-Dade snapshots are rejected by county identity. Historical replay is October 9 midnight through October 10 midnight Central time (`05:00Z` through `05:00Z`, 25 hourly endpoints). Each endpoint needs its next six hourly accumulations. Four initializations (October 9 00/06/12/18 UTC) suffice: the 18 UTC run covers the final 05 UTC replay clock plus its next six hours, within the existing 12-hour replay age policy. Omitting the following midnight run avoids another initialization-date partition; this is a selected-run reconstruction, not a claim that later forecasts did not exist.

Preserve native 0.1-degree cells, initialization, validity, import time, units and source table. Sum six contiguous hourly ensemble means after multiplying meters by 1000 once. Missing/null hours remain unknown; duplicates are invalid. Current forecasts become stale after 2 hours since retrieval, 12 hours since initialization, or window expiry. Historical freshness uses the replay clock. Publication timing remains unverified. Forecasts are not observations or flood outcomes.

Set `QUASAR_WEATHERNEXT_FILE=data/processed/weathernext.json` after importing, and use the Isaias archive path in `.env.example`. Runtime reads may instead use the existing authenticated [LinuxONE bridge](data-bridge.md). Imported files remain ignored; retain their manifests and backups outside Git.

## Mapbox and H3

Use only a public `pk.` Mapbox token in `MAPBOX_PUBLIC_TOKEN`; secret `sk.` tokens are rejected. `MAPBOX_STYLE` defaults to `mapbox://styles/mapbox/light-v11`; set another Mapbox style URL to override it. Google credentials and bridge tokens stay server-side. H3 R4–R7 supports county browsing, with parcel drill-down at R7. Displayed H3 cells are clipped to the county boundary and summarize the maximum overlapping native forecast, with incomplete or unavailable coverage transparent. H3 does not increase forecast resolution; API payloads and exports retain WeatherNext's native geometry. Real parcel scores remain unknown.

[WeatherNext schema and query guidance](https://developers.google.com/weathernext/guides/bigquery).


## Verified Okaloosa import, October 17

Live imports completed for 45 native county-intersecting cells: four historical runs / 3,240 hourly rows, plus one current run / 810 hourly rows. The historical day remains October 9 in Central time. Current initialization is October 17 14:00 UTC; source publication timing is unverified. Snapshot freshness is evaluated at runtime.

Reviewed upper-bound estimates were 271,373,414,400 bytes for the four-run archive and 185,791,449,600 for current weather. Hard caps were 280 GB and 190 GB. Actual billed bytes were 65,011,712 and 12,582,912 respectively. A separate latest-initialization metadata query used about 778 MB. The final all-project monthly audit reported **402,366,922,752 billed bytes**: 597,633,077,248 below the conservative 1,000 GB ceiling, or 697,144,705,024 below Google's 1 TiB allowance. These are dated checkpoints, not permission for automatic refreshes.

Jobs: `quasar_okaloosa_historical_20261017_213504` and `quasar_okaloosa_current_20261017_213504`. Raw hourly rows, execution metadata, dry runs and the monthly audit are retained with the ignored weather download. Dry-run upper bounds are deliberately used for execution gating even when spatial pruning makes actual scans much smaller.
