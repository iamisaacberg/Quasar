# Isaias datathon replay

Quasar opens on the **October 9, 2026 Isaias forecast archive for Okaloosa
County, FIPS 12091**. This is an initialization-based forecast reconstruction,
not observed rainfall, proof of local flooding, or a trained flood model.

## Presenter flow

1. Open Map overview. The archive loads independently of the map token and
   county-boundary service. The map colors H3 cells clipped to the authoritative
   county boundary. WeatherNext native polygons remain the underlying source;
   their rectangular outlines are not drawn. The H3 display requires the county boundary.
2. Use Play, the hourly slider, previous/next, or a chart bar. The 25 positions
   run from October 9 midnight through October 10 midnight in America/Chicago
   (`2026-10-09T05:00:00Z` through `2026-10-10T05:00:00Z`). Each position shows
   the **following six forecast hours**.
3. The chart shows the maximum among available native-cell totals at each hour.
   It is not a county mean, cumulative storm total or rainfall observation.
   Hatched bars indicate partial coverage or unavailable rainfall; valid zero
   remains zero. H3 colors use a fixed millimeter scale across all hours, showing
   the maximum among the native forecasts overlapping each hex. Any missing,
   stale or incomplete overlapping forecast, or incomplete spatial coverage,
   leaves the hex transparent. This is a display summary, not higher-resolution weather.
4. Select a county H3 cell to see the range and provenance of its overlapping
   native forecasts immediately, independently of prepared parcel inputs. Zoom in
   and select a parcel. Prepared terrain, FEMA,
   mapped-waterway context and exact native forecast overlaps require the
   matching inspection artifact. Geometry alone never produces a risk score.
5. Open Data or Reports & exports. They retain the selected archive hour. CSV,
   GeoJSON and ZIP preserve source initialization, import time, validity and
   units. Report printing is available through the browser.

Playback reuses one loaded snapshot; it does not download/recompute every frame.
Recheck source explicitly reloads the archive. A failed reload clears rainfall
and playback and shows the source failure. Recheck source also retries the
selected parcel/cell reference inputs. Failed reference requests have their own
retry control; a cache inventory change triggers a context retry after parcel
loading. No current-forecast selector is shown.

## Required runtime sources

The public Vercel app needs a public `MAPBOX_PUBLIC_TOKEN` and either an explicit
`QUASAR_REPLAY_FILE` pointing to a schema-3 county archive or the authenticated
snapshot bridge. The local default in `.env.example` is
`data/processed/isaias-2026.json`; copy/configure it explicitly. Git does not
transfer ignored data.

LinuxONE must run the current Quasar county APIs, with `QUASAR_PARCEL_DATABASE`
and `QUASAR_PARCEL_CONTEXT_DIRECTORY` pointing to compatible Okaloosa artifacts.
Both the service and reverse proxy must expose the authenticated inspection
routes listed in [data-bridge.md](data-bridge.md). The older standalone
Miami-Dade `bridge_service.py` does not support these APIs.

The app is public without a team password. Source credentials remain server-side.
See [Vercel setup](vercel.md) and [runtime activation](real-data-rollout.md).

## Data boundaries

Six contiguous, non-null hourly inputs are required per cell/window. Duplicate,
negative or malformed hourly records invalidate the archive. Unknown values are
never replaced by zero. Today's date does not expire a deliberate archive;
eligible initializations must instead be no more than 12 hours old at replay
time, and documented publication times must not be in the future at that time.
Unknown publication timing remains labeled as initialization-based reconstruction.

Current-import APIs remain available by explicit source selection for integration
compatibility, with their original expiry rules; the application focuses on Isaias.
No runtime request performs a BigQuery query. No new acquisition is necessary for
an already prepared archive. County import commands remain explicit, capped and
dry-run by default; see [integrations.md](integrations.md).

Fictional sites, what-if rainfall, simulated routes and notification previews are
retired from the application. No assessment producer or validated flood model is
introduced here. An absent matching assessment stays unscored. Follow official
NWS and local emergency guidance for real decisions.
