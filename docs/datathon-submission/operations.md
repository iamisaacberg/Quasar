# Reproduction and runtime handoff

These are operator commands and a reviewable optional catalog candidate. [Verified execution](verified-run.md) records the authorized 91-file transfer, fresh LinuxONE run/parity and bounded API checks already completed. The existing directory-based service remains active and unchanged. Host-specific access details and credentials are not in this package. Do not search another workspace or change the shared host to obtain them. Administration/submission tasks are excluded by Isaac.

## Transfer, audit and model evidence

The required release and its relative paths are listed in [audit D1](../DATATHON-DEV-HANDOFF.md#d1--recover-and-verify-the-existing-artifacts-p0-incoming-developer--isaacmodel-owner). Preserve the bundle and producer receipts unchanged. A transfer manifest is private JSON with `schema_version: 1`, `county_fips: "12091"`, and `files`, each having `path`, `role`, `required` (boolean), and producer-supplied `sha256`. Paths are relative to the supplied root. The [active release hashes](verified-run.md) differ from the historical local report; preserve them separately. Model/assessment hashes are file hashes; the inventory identifier is not automatically the parcel SQLite hash. Missing required files and any mismatched supplied file fail the transfer check. Do not manufacture expected hashes by hashing the candidate you are supposed to verify.

```sh
python3 -m quasar.modeling verify-bundle \
  --manifest .context/datathon-evidence/transfer-manifest.json \
  --root data \
  --output .context/datathon-evidence/transfer-verification.json

python3 -m quasar.modeling audit \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/20261017-reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --inspection data/processed/okaloosa/parcel-inspection/20261018-marseille

python3 -m quasar.modeling verify-model-evidence \
  --experiment data/processed/okaloosa/modeling/original-training/experiment-v1 \
  --dataset data/processed/okaloosa/modeling/original-training/dataset-v1 \
  --output .context/datathon-evidence/model-verification.json
```

The original experiment/dataset commands above remain conditional examples: the runtime transfer did not contain original native members, residuals or the test ledger. Do not retrain/recreate the dataset to fill that gap. Transfer integrity is not authoritative polygon-containment proof. Retain preparation containment records; use the optional GIS environment for actual containment checks when needed. Model evidence verification reconciles the dataset/model/native members/evaluation/test-ledger, recomputes portable predictions and model/development-mean metrics from full saved test residuals, and checks every supported/unknown ID. Ridge results stay recorded-only because ridge predictions were not saved. It neither trains nor resets a ledger.

## Target-host inference and parity

On the authorized target host, inventory revision, `uname -m`, Python, existing configuration and free resources before staging a new release. Reuse the current county runtime. Do not install native training libraries or replace it with the retired standalone bridge. Execute [audit D2's assessment and benchmark commands](../DATATHON-DEV-HANDOFF.md#d2--execute-trained-inference-on-linuxone-p0-incoming-developer--ibm-integrator). They use new output paths and the exact 05:00–11:00 UTC demo window. Substitute the current active model/evaluation paths listed above for historical D2 path examples; retain the distinct release identities.

Capture complete redacted logs, actual architecture, revision, identities, run ID, scored/unknown counts, production and R4–R7 aggregation timing, peak RSS and free disk. Internal targets remain under 300 seconds and 2 GiB peak RSS, with at least 1 GiB free disk. These are project targets, not official limits. Do not compare assessment bytes across hosts as a parity test: time/run metadata changes.

After copying the candidate result through the approved channel:

```sh
python3 -m quasar.modeling compare-assessments \
  --reference data/processed/okaloosa/modeling/maputo-local/exposure.json \
  --candidate data/processed/okaloosa/modeling/maputo-linuxone/maputo-inference.json \
  --output .context/datathon-evidence/parity-linuxone.json
```

Every parcel ID, known/unknown status, reason, method and forecast identity must agree. Fixed absolute tolerances are `1e-6` for model details and `1e-5` for rounded index/factors; relative tolerance is zero. The tool compares every parcel and caps only printed mismatches at 100. Computation time/run ID may differ. A `matched` parity report alone does not establish which host ran the candidate.

## Optional all-hour release

This reads the same saved archive/timeline and calls the existing producer one window at a time. The dry run writes no outputs and starts no query or server:

```sh
python3 -m quasar.modeling assess-replay \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/20261017-reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --inspection data/processed/okaloosa/parcel-inspection/20261018-marseille \
  --model data/processed/okaloosa/modeling/edmonton-20261018/model.json \
  --evaluation data/processed/okaloosa/modeling/edmonton-20261018/evaluation.json \
  --weather data/processed/isaias-2026.json \
  --output data/processed/okaloosa/modeling/replay-release-v2
```

Review the 25 positions, including the final forward window ending October 10 at 11:00 UTC, input identities and disk estimate. Repeat with `--execute` to produce a **new** release directory. No existing directory is overwritten. A worst-case 128 MiB per eligible window plus 1 GiB reserve is required before production. A source gap is recorded explicitly; a production/identity error aborts publication rather than becoming a pretend source gap. Partial parcel coverage remains unknown where the producer cannot score.

Each produced window has its own provenance, production/aggregation benchmark and checksum. `coverage.json` includes all requested windows, counts, gaps and timings. `catalog.json` is published atomically as the final completion marker only after all referenced windows pass validation. A failed release stays unactivated and has no catalog marker. No previous release is modified. Do not report real all-hour coverage or host memory acceptance until this command runs against the actual reviewed county bundle on the intended host.

## Activation candidate and rollback

Candidate behavior: preserve the existing read-only parcel database, inspection paths, forecast files, HTTPS proxy and tokens. On the inventory host, choose either the reviewed single-window `QUASAR_EXPOSURE_FILE`, or:

```dotenv
QUASAR_EXPOSURE_CATALOG=/srv/quasar/data/processed/okaloosa/modeling/replay-release-v2/catalog.json
QUASAR_EXPOSURE_ARTIFACT_ROOT=/srv/quasar/data/processed/okaloosa/modeling/replay-release-v2
```

These are proposed absolute target paths, not verified existing files. Catalog configuration wins over file/directory configuration. Without a catalog, legacy FILE and DIRECTORY remain mutually exclusive; existing directory activation continues unchanged. Missing catalog windows and invalid files cannot fall back to the old single file. Vercel continues using its existing server-only `QUASAR_LINUXONE_API_URL` and token. No new browser setting is needed.

Before any activation, the runtime owner must record the current immutable code/artifact pointers and private configuration backup. Stage reviewed code/data in a new release, verify hashes and exact input identities, then present the concrete configuration/restart steps for authorization under `AGENTS.md`. Keep old service/environment/Caddy settings and artifacts. No infrastructure change or restart has been made here.

Verify source authentication rejection and authenticated supported/unsupported windows; compare the same model/run/inventory/window through source and Vercel API, then have Isaac check exposure mode. Source rainfall colors alone are not model proof. For rollback, restore the previous catalog/file environment and previous code pointer with authorized restart steps, then repeat supported/unsupported/auth checks. Atomic file replacement alone does not prove operational rollback.

Measure a declared small source/API request sample before load testing. Record cold/warm summaries and 1/100-parcel lookups, bytes, errors and source identities. Check actual 12-second exposure proxy timeout and 2 MB body cap. Keep concurrency/load tests pending an agreed host cap and stop rule. Do not claim p95 from a tiny sample, general high availability or hardware acceleration.

## Optional current official alerts

The importer is independent of model scoring and defaults to no network activity unless invoked explicitly:

```sh
python3 -m quasar.adapters.county_alerts \
  --user-agent 'Quasar/0.1 (TEAM_APPROVED_IDENTIFYING_CONTACT)' \
  --output data/raw/nws/okaloosa-current.json
```

Set `QUASAR_NWS_ALERTS_FILE` to that saved snapshot only after reviewing it. `GET /api/official-alerts?source=current` reads it; the default/archive query stays disconnected. The importer follows at most eight same-host, same-county pages, ten-second per-request timeout, 2 MB/page and 8 MB total. One invocation makes no retries; rerun explicitly after investigating an error. Source URLs/headers/contact are not serialized in failure text. A snapshot expires after 120 seconds. Partial imports, source errors, invalid messages and expired snapshots do not become an empty success. No periodic job was configured.

The [NWS county-query guide](https://www.weather.gov/media/documentation/docs/NWS_Geolocation.pdf) supports county UGC `FLC091` returning county and intersecting zone products. Polygon absence is allowed for zone messages. Updates/cancellations, duplicate IDs, future issue/onset and expiry are handled separately. An empty fresh complete query means no matching messages returned for that query/time; it is not evidence of safety. A live canonical county fetch is recorded in [verified execution](verified-run.md). The current-alert UI/refresh remains unactivated, and its separate human acceptance remains open.
