# Isaias 2026 replay and evacuation exercise

> Current application behavior is defined by [data-contract.md](data-contract.md).
> Synthetic scoring, fictional sites, what-if controls and simulated routing
> described below are retained offline research context; their application
> endpoints are retired. The app uses native county forecasts and prepared
> parcel inputs, with transparent unknown interiors and no synthetic fallback.


Open **Map overview**, then choose **Isaias simulation** in the map toolbar
(or use the legacy `/#isaias-replay` link). Playback, site inspection, trends and
routing share the map side panel; **Exit Isaias simulation** returns to the
previous data source. The replay spans
October 9 04:00 UTC through October 10 04:00 UTC (October 9 in Central time), displayed in Central time. The
hourly score always describes the **following six forecast hours**. It uses the
existing illustrative scoring function, not a trained or validated flood model.

## Local data preparation

From the repository root, fetch public NHC advisory context and a curated road
network. This command uses public HTTP sources; it never queries BigQuery:

```sh
python3 scripts/prepare_isaias.py
```

`--only advisories` and `--only roads` prepare each source separately. Raw
responses stay under ignored `data/raw/isaias/`; normalized files stay under
ignored `data/processed/`. Current source road geometry is not historical proof.
The road graph uses a subset of Okaloosa's street-centerline service, checked
against the Census county polygon. All full line segments, including simulated
access connectors, must stay inside that polygon. Source identifiers, checksums,
CRS, units, retrieval times, terms and processing notes accompany the outputs.
These local sources are not included in Git: teammates must prepare their own.

Historical WeatherNext rainfall requires an authenticated `bq` CLI on the local
computer or in Cloud Shell. Start with the capped **dry run**:

```sh
python3 -m quasar.adapters.historical \
  --project quasar-ibm-z-datathon \
  --table quasar-ibm-z-datathon.weathernext_3.weathernext_3_0_0_0p1deg \
  --location US
```

Review the dry-run estimate, then repeat with `--execute` to import. The default
`--maximum-bytes-billed` is 1,000,000,000; requests exceeding it fail. SQL can be
inspected offline using `--print-query`. The importer selects six-hourly
initializations from October 9 00:00 UTC through October 10 00:00 UTC and each
run's first 18 hourly precipitation intervals. Only the six fictional site
coordinates are queried. Native-cell geometry and ensemble-mean hourly rainfall
are retained, with source meters multiplied by 1000 once.

If running in Cloud Shell, copy the credential-free importer files there, execute
the same commands, and download only `data/processed/isaias-2026.json` back into
that path in this workspace. No cloud credentials belong in the app or snapshot.
The October 17 current-forecast snapshot is a separate file and is not altered.

Optional environment paths:

```dotenv
QUASAR_REPLAY_FILE=data/processed/isaias-2026.json
QUASAR_ROUTES_FILE=data/processed/evacuation-network.json
```

App requests read local files; they never launch imports. Snapshot and graph file
changes are picked up without a restart. Newly added Python routes/modules require
restarting an existing older process through the user's usual run controls.

## Reading the reconstruction

At each replay hour, choose the latest initialization no newer than that hour,
and no more than 12 hours old at replay time. If `published_at` is supplied, it
must also be no later than the selected hour. Otherwise the UI explicitly says
**initialization-based archive reconstruction**: this is not proof of the exact
forecast available to a resident at that time. Actual retrieval timestamps stay
visible in feature/timeline API metadata; today's clock never makes a deliberate
historical archive stale. Current WeatherNext freshness rules are unchanged.

Six contiguous, non-null forecast hours are required. Missing hours remain
unknown, and duplicates invalidate a run rather than trigger fallback. The
+5/+10 mm/hour presets add synthetic rainfall only to complete windows. All
terrain, FEMA, waterway and gauge factors remain fictional. The missing-terrain
site stays unscored. Chart gaps and unavailable hourly changes preserve nulls.

NHC advisory context uses original issue timestamps and only shows advisories
issued by the selected replay hour. The NHC office location does not determine storm impact; advisory context alone does not establish local observed inundation. No archived official local warning feed
or observed-outcome validation has been added.

## Routing and presenter walkthrough

Routing is enabled in **What-if exercise** mode. Archive mode keeps historical
road and destination availability unknown. The three destinations are fictional
exercise points, not an assertion that shelters are open.

Routing excludes closed/unknown segments and unavailable destinations, then
minimizes modeled travel time, distance and stable IDs. Speeds are an assumed
30 km/h throughout, with two-way exercise traversal. Site access connectors are
synthetic and drawn dashed. Road geometry is real source data; directionality,
turn restrictions, traffic and flood passability are not validated navigation.
Conditions apply at departure time and are not predicted throughout the journey.
Site scores and H3 summaries never determine road passability.

1. Select a site; scrub or play the hourly timeline. Playback advances at most
   one hour per second while requests complete, and stops at the final hour.
2. Enter What-if exercise and select a rainfall preset. Without historical
   rainfall, the score stays unknown while the routing exercise remains usable.
3. Inspect the chosen route and its unrestricted comparison. The default
   sequence closes a segment at hour 6, removes the original destination at
   hour 12, and closes all segments at hour 18.
4. Use segment state overrides and destination checkboxes to change the exercise.
   Overrides persist across hours until reset (maximum 100 road overrides).
5. Reset to hour zero, archived rainfall, archive mode, and no overrides.

Network-unavailable, historical-conditions-unavailable and no-route are separate
states. No route is drawn through a closed or unknown segment. These estimates
supplement official NWS/local guidance; they are not evacuation orders or safety
assurances. No notifications are sent.

## Verification

```sh
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
npm test
npm run build
```

Tests use clearly synthetic hourly and road fixtures. They exercise nulls,
duplicates, historical initialization/publication selection, county holes and
concavities, routing restrictions/ties, API validation, playback/reset and late
responses. They are not historical model validation. Isaac reviews visuals.

## Okaloosa transition

Replay covers October 9 in America/Chicago: 2026-10-09T05:00:00Z through 2026-10-10T05:00:00Z, inclusive. Forecast validity extends six hours past the final endpoint. Use the county importer in [integrations.md](integrations.md); original Miami-Dade point archives are incompatible. Reacquire roads with `scripts/acquire_supporting_data.py` before preparing the exercise graph. NHC advisory issue timestamps and public source URLs remain unchanged.
