# Loading performance

The app retains Okaloosa-only scope, exact county geometry and unknown/stale
semantics. No serving request imports data, trains a model or starts a cloud query.

## Prepare exposure serving data

Run explicitly in an environment that already has the validated inventory and
assessment files. This command changes no service configuration:

```sh
python3 -m quasar.exposure_store \
  --inventory data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --assessments data/processed/okaloosa/modeling/replay \
  --output data/processed/okaloosa/exposure-serving.sqlite3
```

For the actual directory release, pass `--manifest` pointing to the existing
verified producer `replay-manifest.json`. Only its listed assessment files are
read; benchmark JSON sidecars are excluded. Original producer checksums,
complete parcel coverage and consistent model/forecast-source identities are
required. `--dry-run` checks selected paths and the disk budget without writing.
Preparation reserves three times the source bytes plus 1 GiB free and retains
one decoded window at a time. Publication remains atomic.

The assessment input can also be a single schema-1 file. Preparation validates
all windows, retains original records and provenance, computes R4–R7 summaries
using the existing P90 implementation, verifies stored parity and SQLite
integrity, and atomically replaces the output only on success. Input changes or
duplicate windows reject preparation; a previous output is preserved.

On the inventory host, `QUASAR_EXPOSURE_DATABASE` selects this read-only serving
database alongside `QUASAR_PARCEL_DATABASE`. Existing API shapes, authentication,
100-ID limits, freshness and exact-window checks remain in force. A configured
invalid database returns unavailable/invalid results; it never falls back to an
older file. Without this setting, the existing file/directory path remains valid.
A catalog and prepared database cannot be configured together; this prevents
bypassing the catalog identity checks. Vercel continues proxying to the authenticated host. Installing artifacts,
changing configuration or restarting that host requires separate authorization.

`python3 -m quasar --warm-serving` is opt-in for the inventory host. Before
opening a listener it verifies the inventory/optional inspection artifact,
prepares the archive, requires matching exposure windows at every R4–R7
resolution for all 25 hours, and warms the default exposure window and archive
compression. Missing/invalid inputs fail startup. Clear FILE, DIRECTORY,
CATALOG and ARTIFACT_ROOT when selecting the database. See the reviewed
[performance drop-in](../ops/linuxone/quasar-performance.conf.example).

## Browser and HTTP behavior

- Session request caching deduplicates reads, expires after 15 seconds or earlier
  source expiry, and does not cache errors. Abandoning one view does not cancel
  another view's shared request. Explicit source rechecks invalidate cached reads.
  Exposure requests bypass this TTL and use the exposure frame cache.
- Exposure results are separate from the displayed hour. Frame storage is bounded
  to 20 MiB, retains parcel assessments for the three most recently saved frames, and retains at most 10 MiB
  of active parcel assessments. Unknown values remain transparent when evicted.
  Up to three parcel-assessment batches run concurrently. Selected/visible parcels
  lead the queue; playback waits for summaries and the selected parcel while other
  parcels hydrate in the background. Next-hour prefetch stops on pause/hidden views.
- A bundled worker prepares exact clipped H3 geometry and native overlaps. A
  worker failure leaves unavailable coverage, not replacement geometry. Mapbox
  feature state updates colors without replacing unchanged geometry sources.
- IndexedDB schema 3 stores separate geometry pages and small progress records
  atomically. Access-time changes update metadata only. Old cache schemas are
  discarded; seven-day retention, 100 MiB LRU and memory fallback remain.
- Data/Reports are loaded on first visit and remain mounted. Hashed UI and worker
  assets are served only from the build allowlist and have immutable caching.
  HTML/data remain no-store; gzip is negotiated for large text/JSON responses.
- Snapshot data, canonical bytes and content identity are reused by full local
  file version (device/inode/size/mtime/ctime). Unchanged archive timelines stay
  prepared; each call still checks the source and current-data expiry. Remote
  snapshots retain the 15-second source TTL and failures never serve old reads.
- All authenticated LinuxONE proxy clients negotiate gzip. Wire and decoded
  bytes both retain the existing endpoint limits; corrupt, truncated, trailing
  or oversized compressed responses fail unavailable. Compression caching is
  bounded to four bodies up to 30 MB each. No public API fields change.

## Measurements and acceptance

Run the offline synthetic benchmark without starting the app:

```sh
python3 scripts/benchmark_loading.py
node scripts/benchmark_loading.cjs
```

Browser diagnostics are available in `window.QuasarPerformance.snapshot()`:
request/cache timing, decoded response bytes, worker preparation, parcel storage
and geometry-source updates. Samples are session-only and bounded to 500.
HTTP `Server-Timing` reports processing time separately from network delay.
Fixed-name source, preparation, query, encoding, compression and upstream
durations appear where applicable, without paths, credentials or identifiers.

## Actual host/API benchmark

`scripts/benchmark_linuxone.py` defaults to zero network activity. Supply an
ignored workload JSON with `starts` (25 ISO starts), `parcel_ids` (100 distinct
IDs), `cell` (densest R7), its exact H3 `ring`, first/middle/final page `offsets`,
`inventory_id`, and optional recorded `identities`. Derive these from the
reviewed county inventory and producer receipt; do not fabricate county data.
The workload contains private operational details and stays in `.context/`.

```sh
# Set QUASAR_BENCH_ORIGIN and QUASAR_BENCH_TOKEN privately in the process env.
# Public mode needs no source token. A source archive read additionally uses
# the existing QUASAR_DATA_BRIDGE_TOKEN; never put credentials in CLI arguments.
python3 scripts/benchmark_linuxone.py --workload .context/workload.json \
  --label loopback --output .context/baseline-loopback.json
python3 scripts/benchmark_linuxone.py --execute --workload .context/workload.json \
  --label loopback --pid SERVING_PID --output .context/candidate-loopback.json \
  --baseline .context/baseline-loopback.json
```

Use labels `loopback`, `source`, and `public` for the three routes. Reports
record the vantage architecture, supplied artifact/code identities, bytes,
latencies, body hashes and fixed-name timings, not URLs, headers or bodies.
Run `--smoke` first: it emits no p95 because the samples are intentionally
small. A full run collects 100 warm samples for each exposure class, exercises
all hours/resolutions for three cycles, returns to the first hour, tests dense
cell pages/context, archive/timeline and a three-request burst. First observed
request time is explicitly not a cold-process measurement. Record startup
duration separately from the candidate launch log.

Run on LinuxONE with `--pid` to monitor the serving process. The monitor samples
CPU/RSS and available memory twice a second, stops on less than 1 GiB available
or over 90% host CPU for 30 seconds, and stops requests after an unexpected
HTTP/data error or timeout. The run has a 15-minute budget. Remote measurements
without a Linux PID do not establish host resource acceptance. Reports compare
median changes and payload sets; an incomplete/stopped run is never acceptance.
Keep preparation and serving measurements sequential. Do not drop the OS cache
or restart the active service merely to obtain cold measurements.

Promotion targets: warm loopback exposure p95 ≤250 ms, public exposure median
across the same complete mix of warm reads and replay switches at least 50%
below a matched baseline, other measured endpoint medians no more
than 10% worse, serving peak RSS below 1 GiB without replay-cycle growth, and
identical supported/unknown/failure results. Stage on a separate loopback port,
preserve the old release/environment, and obtain explicit activation approval.
The RSS check allows 8 MiB of allocator/page variation between the first and
third cycle; all measured values remain in the report. Missing resource
measurements, missing baselines or mismatched sample counts cannot pass promotion.

Compare cold/warm entry, a dense R7 cell, returning to that cell, 25-hour replay,
and Map → Data → Reports → Map under identical conditions. Targets: 30% faster
first useful data, cached state changes within 150 ms, prepared warm exposure
p95 below 250 ms, no geometry replacement solely for hour changes, and no Quasar
preparation/storage task above 100 ms. Synthetic processor timings and bundle
sizes do not establish those browser/network targets. Real-artifact timings and
Isaac's visual review remain separate evidence.
