# LinuxONE to Vercel data bridge

Quasar can read selected normalized snapshots from an IBM LinuxONE Quasar
instance at request time. The browser continues to call the Vercel-hosted Quasar
API. Only the Vercel Python function makes the outbound request to LinuxONE, and
the bridge token stays in server-side environment variables.

```text
Importer -> normalized snapshot on LinuxONE
Browser -> Vercel Quasar API -> HTTPS bridge on LinuxONE
                         -> existing Quasar validation and API response
```

## Allowed snapshots

Snapshot routes serve only these named files; request paths cannot select
arbitrary files. Raw downloads and credentials are not exposed. County parcels
have a separate authenticated, cell-scoped API described below.

| Name | Default path | Maximum size |
| --- | --- | ---: |
| `weathernext` | `data/processed/weathernext.json` | 5 MB |
| `isaias-2026` | `data/processed/isaias-2026.json` | 30 MB |
| `isaias-advisories` | `data/processed/isaias-advisories.json` | 2 MB |
| `evacuation-network` | `data/processed/evacuation-network.json` | 8 MB |

WeatherNext, replay, and routing snapshots use their existing `QUASAR_*_FILE`
paths where configured. The importer must finish and validate a snapshot before
the app uses it. The Vercel app applies its existing schema, county,
freshness, and completeness checks. A missing or stale snapshot stays missing or
stale; bridge errors do not fall back to synthetic rainfall.

## Configure LinuxONE

Run Quasar with `QUASAR_DATA_BRIDGE_SERVE=1` and a random token of at least 32
characters in `QUASAR_DATA_BRIDGE_TOKEN`. Configure the existing snapshot file
paths for imported data as needed. Keep the Python app bound to localhost and
put a TLS reverse proxy in front of it. Forward `/bridge/v1/snapshots/*` to the
Quasar process without logging the Authorization header. Do not expose the
plain HTTP app port to the public internet.

The protected read endpoint is:

```text
GET /bridge/v1/snapshots/weathernext
Authorization: Bearer <shared random token>
```

The same route accepts only the other names in the allowlist above. It sends
`Cache-Control: no-store`, validates the JSON object and size, and rejects
unauthorized requests. It is disabled unless `QUASAR_DATA_BRIDGE_SERVE=1`.

## Configure Vercel

Set these as server-side runtime environment variables for each Vercel
environment that should read LinuxONE data:

```text
QUASAR_DATA_BRIDGE_URL=https://your-public-host.example/bridge/v1
QUASAR_DATA_BRIDGE_TOKEN=<the same random token>
```

Do not prefix either variable with `VITE_`. Deploy the code and variables to a
Preview deployment first. The Vercel team password remains a separate browser
access gate; it is not the bridge credential. The bridge uses HTTPS certificate
verification, refuses redirects, times out after eight seconds, enforces each
snapshot size limit, and caches successful reads in the Vercel process for at
most 15 seconds. Vercel deployments without the bridge URL continue to use local
snapshots as before.

WeatherNext appears through the existing `/api/weather/status`, `/api/scenarios`
and `/api/properties?scenario=weathernext` routes. Historical rainfall uses the
existing replay API; route inputs use the existing route API. No new browser
route exposes raw snapshots.

## Operational limits

LinuxONE must be running and reachable from Vercel over public HTTPS. This bridge
is intended for the small normalized exercise snapshots above. Large property
inventories or frequent bulk refreshes should go to managed object storage or a
database with narrow query endpoints; do not add them to this file allowlist.
The snapshot bridge does not refresh imports. Those remain explicit operator
commands.

## County parcel lookup

The county parcel inventory is an indexed SQLite file at
`/srv/quasar/data/processed/okaloosa/linuxone/quasar-parcels.sqlite3`. The LinuxONE
bridge reads it in read-only mode. `/api/parcels` requires
`QUASAR_PARCEL_API_TOKEN` in the `X-Quasar-Parcel-Token` header and accepts only indexed
Okaloosa resolution-7 cell IDs. It returns 100 polygon rows per page; the
browser never connects directly to LinuxONE.

On Vercel Preview, set server-side `QUASAR_LINUXONE_API_URL` to the LinuxONE
HTTPS origin and `QUASAR_LINUXONE_API_TOKEN` to the same token. The authenticated
Vercel API proxies each page. The reverse proxy forwards `/api/parcels` without
logging the token header; the Python service stays on localhost.

Retain the Okaloosa County GIS/Property Appraiser reference-data disclaimer and attribution. [Source terms](https://www.okaloosapa.com/gis-mapping/). Old Miami-Dade snapshots and databases fail the Okaloosa county checks. Stage a new county bundle, verify checksums and disk capacity, then switch the database and snapshot paths together. Keep the previous bundle for rollback. A Git push does not transfer ignored data.
