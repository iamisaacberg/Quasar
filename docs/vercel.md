# Password-protected Vercel demo

Quasar can be shared through a Vercel preview when campus Wi-Fi blocks direct
connections to a laptop. Vercel runs the Python entry point in `api/index.py`;
the existing Python application logic and synthetic/mixed-data notices remain
in effect. The hosted app never loads `.env` or starts cloud queries.

## Access gate

Set `QUASAR_TEAM_PASSWORD` as a **runtime secret** for each Vercel environment
that will be deployed. Use a unique, randomly generated password of at least
12 characters. Visitors sign in through Quasar’s team access page. A successful sign-in sets a signed, HTTP-only browser session cookie that expires after 12 hours. Do not use a `VITE_` or other frontend environment variable for this
password, and do not put credentials in a URL.

Missing, blank, or invalid passwords block every app route with HTTP 503.
Missing access shows the sign-in page; an incorrect passphrase returns the same page with an error. API and non-page requests without a valid session return HTTP 401. Authentication runs
before serving the page, JavaScript, CSS, configuration, reports, exports and
all other API routes. Unsupported methods are protected too. Query strings and Vercel bypass headers cannot unlock the application gate. Only a signed session cookie issued after the passphrase check is accepted.

All app responses disable caching and indexing. The static output directory may
contain only a harmless placeholder because Vercel rejects empty outputs; the
build fails if any other file appears. An unconditional route sends every URL
to the protected Python entry point **before filesystem lookup**, including the
placeholder URL. Source files, `.env`, raw data and workspace
artifacts are not publicly served even after sign-in. This is shared team
access, not individual accounts or an audited user-management system.

Vercel Authentication is a separate outer gate. If enabled, teammates must also
have Vercel deployment access. Only remove that outer gate for this project
after verifying the application gate on a deployed preview. No paid Vercel
password-protection feature is required for the application gate.

## Build and upload

`vercel.json` overrides the Vite preset. Vite still builds the React shell into
`quasar/static/ui/`, which the Python entry point serves after authentication.
`scripts/prepare_vercel.py` keeps all app content out of static output. Keep the
unconditional `routes` rule ahead of any filesystem handling; replacing it with
a rewrite that runs after filesystem lookup would weaken that guarantee.

`.vercelignore` allows only the app/build inputs and these optional normalized
snapshots from `data/processed/`:

- `weathernext.json`
- `evacuation-network.json`
- `isaias-advisories.json`
- `isaias-2026.json`

Raw downloads, property datasets, local `.env` files, credentials, `.context`,
notebooks and dependencies installed on the laptop are excluded. Snapshots are
included only when present in the deployment source. Git deployments do not
include ignored local snapshots. Missing rainfall or routing inputs retain
their unknown/unavailable states. Included WeatherNext snapshots retain their
original timestamps and become stale; deployment does not refresh them.

Configure `MAPBOX_PUBLIC_TOKEN` with only a `pk.` token and, optionally,
`MAPBOX_STYLE`. The application's token variable is `MAPBOX_PUBLIC_TOKEN`, not
`MAPBOX_API_TOKEN`. Check its URL restrictions for the deployed origin. No Google
credentials or Shadcnblocks registry key are required on the hosted app.

## Verify and share

Before deploying, run the project checks and review `vercel deploy --dry --json`
to ensure the upload excludes secrets and raw files. Deploy a preview from the
current feature branch; do not push to `main` or promote a production deployment
without task authorization.

On the actual deployed URL, check the page, static assets, direct function paths,
API routes, report downloads and HEAD/POST requests. Requests without credentials
or with a wrong password must be blocked. Authenticated app/API requests should
work, and authenticated requests for `.env`, source files or raw data must still
be rejected. Verify that an authenticated response is not cached for a later
unauthenticated visitor.

Share the URL and password separately with teammates. To revoke access, change
`QUASAR_TEAM_PASSWORD` and redeploy. Existing immutable deployments retain their
original environment: remove or protect older deployments separately when
revoking their credentials. The browser session expires after 12 hours. Changing
`QUASAR_TEAM_PASSWORD` invalidates existing sessions.
