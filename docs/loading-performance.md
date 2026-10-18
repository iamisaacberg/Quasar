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
Vercel continues proxying to the authenticated host. Installing artifacts,
changing configuration or restarting that host requires separate authorization.

## Browser and HTTP behavior

- Session request caching deduplicates reads, expires after 15 seconds or earlier
  source expiry, and does not cache errors. Abandoning one view does not cancel
  another view's shared request. Explicit source rechecks invalidate cached reads.
- Exposure results are separate from the displayed hour. Frame storage is bounded
  to 20 MiB, retains parcel assessments for three hours, and retains at most 10 MiB
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

Compare cold/warm entry, a dense R7 cell, returning to that cell, 25-hour replay,
and Map → Data → Reports → Map under identical conditions. Targets: 30% faster
first useful data, cached state changes within 150 ms, prepared warm exposure
p95 below 250 ms, no geometry replacement solely for hour changes, and no Quasar
preparation/storage task above 100 ms. Synthetic processor timings and bundle
sizes do not establish those browser/network targets. Real-artifact timings and
Isaac's visual review remain separate evidence.
