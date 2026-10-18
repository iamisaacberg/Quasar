# Public Vercel datathon app

Quasar's hosted app is public. No team passphrase or browser session is required.
`QUASAR_TEAM_PASSWORD` is unused and can be removed from Vercel settings. Existing
immutable deployments keep their older code until a new deployment replaces the
alias. Vercel deployment protection is a separate project setting; the shared
public alias must also be accessible without Vercel authentication.

## Runtime and source boundaries

`api/index.py` serves the existing application route and asset allowlist. Every
URL is routed through Python before filesystem lookup. `.env`, server source,
workspace attachments, private keys, raw files and SQLite databases remain
unavailable through HTTP. `scripts/prepare_vercel.py` rejects unexpected static
output. Public access does not make source credentials public.

Configure only a `pk.` token in `MAPBOX_PUBLIC_TOKEN`, plus optional
`MAPBOX_STYLE`. LinuxONE snapshot reads use server-only `QUASAR_DATA_BRIDGE_URL`
and `QUASAR_DATA_BRIDGE_TOKEN`. Parcel reads use `QUASAR_LINUXONE_API_URL` and
`QUASAR_LINUXONE_API_TOKEN`. Never prefix these credentials with `VITE_`.

The default application is the Isaias archive. Map, Data and Reports preserve
native-cell rainfall, date/units metadata and the shared selected hour. Unknown
inputs remain unknown. No request starts a cloud query or imports new forecasts.

## Build and verification

Run the project checks and `npm run build`; runtime frontend assets are committed
under `quasar/static/ui`. Review the deployment file inventory before uploading.
`.vercelignore` excludes `.env`, `.context`, raw downloads and property datasets.
It allows named normalized snapshots only; Git deployments do not include ignored
snapshots on a developer's laptop. Prefer the configured snapshot bridge.

Deploy the reviewed feature branch to Preview only after authorization. Do not
push `main` or promote production. Verify anonymous GET and HEAD requests for the
page/assets and APIs, selected-hour downloads, and rejection of private paths.
Verify real source readiness separately from deployment readiness. Isaac reviews
the rendered map and print layout.

## LinuxONE activation

The current Quasar service and proxy must serve authenticated `/api/parcels`,
`/api/parcels/manifest`, `/api/parcels/*/context`, `/api/cells/*/summary` and
`/api/exposure`, plus allowlisted snapshot endpoints. An older snapshot-only
bridge does not implement the inspection API. See [data-bridge.md](data-bridge.md)
and [real-data-rollout.md](real-data-rollout.md).

Use the Okaloosa database and matching prepared inspection artifact. No parcel
score is produced merely by configuring these files. Matching exposure results
are optional and remain unknown when unavailable.

`npm run dev:wifi` is a separate optional laptop-sharing utility with its own
local passphrase. It does not control hosted access.
