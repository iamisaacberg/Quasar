# Real-data runtime activation

## October 18 activation

The Marseille activation replaced the older standalone Miami-Dade bridge with
this repository's authenticated Okaloosa API runtime on LinuxONE (`s390x`).
The active inspection artifact is
`data/processed/okaloosa/parcel-inspection/20261018-marseille/` (113,818 parcels).
It was built from the existing reconciled inputs, exact county boundary and
45-cell Isaias archive, with no new cloud queries.

Authenticated public HTTPS checks confirmed the manifest, parcel 24759 and R7
cell 8744e5a59ffffff. The parcel has complete FEMA coverage, a 9.424685 m mean
terrain elevation and one native forecast overlap. The cell has 3,072 distinct
indexed parcels. No exposure artifact exists; the API returns `not_configured`
without a fabricated score. Unauthenticated source endpoints still reject reads.

Service/proxy configuration backups are on the host under
`/etc/quasar/backups/marseille-20261018`. The previous standalone bridge remains
under `/opt/quasar/bridge`. Host-specific activation files and verification
receipts are ignored under `.context/rollout/` and `.context/checks/`.

Activation requires explicit approval for the LinuxONE service/proxy restart,
Vercel Preview environment changes and a Preview deployment. Preparing artifacts
and passing tests do not activate the hosted application.

## Prepared and verified

The reconciled Okaloosa inventory has 113,818 parcel records. The earlier prepared inspection
artifact was `data/processed/okaloosa/parcel-inspection/20261018-real-data/`, with
113,818 parcel contexts and 833 indexed H3 contexts across resolutions 4–7.
Preparation validates the source database, reconciled inputs, exact county
boundary, inventory identity and checksums. All scores remain unknown.
The manifest is the completion marker; transfer both files unchanged.

The imported October 9 archive has 45 native cells and 25 hourly positions.
The existing current snapshot has expired under the unchanged freshness policy.
This change runs no cloud query and does not manufacture fresh timestamps.

## Activation sequence after approval

1. Back up the active Caddyfile, service unit and private environment file.
   Keep the currently running bridge code for rollback.
2. Transfer the reviewed Python package into a new immutable directory under
   `/opt/quasar/releases/` and the inspection directory under
   `/srv/quasar/data/processed/okaloosa/parcel-inspection/`. Verify the transferred
   hashes against their local manifests before switching `/opt/quasar/current`.
3. Add the two path settings in `ops/linuxone/bridge.env.additions.example` to
   the existing private `/etc/quasar/bridge.env`. Preserve existing credentials
   and forecast paths. Install `ops/linuxone/quasar-bridge.service` and the
   prepared Caddy route change, retaining the existing host/TLS configuration.
   Run Caddy config validation and systemd unit validation before reloading.
4. Restart Quasar and reload Caddy. Verify authenticated public snapshot,
   manifest, parcel context and cell summary requests; confirm matching FIPS,
   inventory/checksum IDs and actual `s390x` host. Missing exposure results must
   stay explicitly unavailable. Unauthorized requests must fail, and the proxy
   must continue blocking all other application paths.
5. Run `scripts/configure_vercel_bridge.py` with the existing SSH identity,
   target, HTTPS origin, Vercel scope and project. Its default verifies the source
   and lists four pending Preview settings; `--apply` writes those settings.
   It reads credentials through SSH into memory and passes values to Vercel on
   stdin. It never writes credentials into the repository or deploys.
6. Deploy the reviewed feature branch to Vercel Preview. Verify the real-data
   APIs through the team access gate, expiry behavior, archive and parcel input
   reads. Isaac reviews the map. Do not promote production or push main.

`.context/rollout/` holds the exact host-specific config changes and real-artifact
verification receipt for this workspace. These files are intentionally ignored.

For rollback, restore the previous service/Caddy/environment files and previous
package pointer, validate configurations, then restart/reload. Restore previous
Vercel Preview settings and retain the previous immutable deployment. Rollback
must not replace real-data failures with synthetic values.
