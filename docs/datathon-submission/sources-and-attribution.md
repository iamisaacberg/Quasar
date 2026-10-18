# Sources and attribution

Reviewed October 17–18, 2026 UTC/Central against repository source, lockfiles, vendor notices and the primary pages linked below. This is a resource inventory. License ownership, permissions for this team's account, source redistribution and judge access remain separate review items. Do not describe licensed UI components as original work or the entire repository as cleared for public redistribution.

## Data and services

| Resource / identifier | Primary reference and terms | Quasar use / notice |
| --- | --- | --- |
| WeatherNext 3, 0.1-degree ensemble mean | [Official model/data terms](https://developers.google.com/weathernext/guides/models), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), [BigQuery access](https://developers.google.com/weathernext/guides/bigquery) | Google DeepMind forecast source; retain attribution, native resolution, initialization, validity, import time and processing. Official docs distinguish historical CC BY data from experimental real-time terms. The exact source table/retrieval is in each saved snapshot. No new query was run here. |
| Okaloosa GIS / Property Appraiser parcels | [County parcel service](https://okgis.myokaloosa.com/arcgis/rest/services/Land-Ownership/Parcels/MapServer/0), [Property Appraiser GIS terms](https://www.okaloosapa.com/gis-mapping/) | Retain Okaloosa County GIS/Property Appraiser attribution and as-is reference-data, no-survey/no-legal-document disclaimer from producer manifests. Terms page returned 403 during this check; current redistribution permission remains unresolved. |
| Census county boundary, GEOID 12091 | [TIGERweb source service](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1), [TIGER/Line documentation](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | Authoritative containment boundary; preserve exact geometry hash, retrieval, geographic CRS and source attribution. A county tag or bounding box is not containment evidence. |
| FEMA NFHL, product NFHL_12091C | [FEMA map service center](https://msc.fema.gov/portal/home), [NFHL service](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer) | Regulatory mapped-zone context and training target; preserve effective dates, coverage/conflicts and FEMA attribution. Not event observations or model validation. Review original product metadata before redistributing data. |
| USGS 3DEP terrain | [3DEP](https://www.usgs.gov/3d-elevation-program), [USGS credits/terms](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits) | Prepared polygon elevation statistics, NAVD88 meters; original tile IDs, dates, horizontal/vertical datum, units and processing travel in the manifest. Credits page fetch timed out here; retain supplied notices and resolve current terms before redistribution. |
| Mapped streams / county reference hydrography | [County source service root](https://okgis.myokaloosa.com/arcgis/rest/services/), [USGS NHD description](https://www.usgs.gov/national-hydrography/national-hydrography-dataset) | Exact retained layers/source versions come from the prepared-input manifests, not an assumed NHD release. Limited mapped-stream distance is not full lake/canal/coastal coverage or hydraulic connectivity. |
| USGS monitoring-location research | [Water data API](https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items) | Discovery/retained research only; station locations do not establish a stage series, compatible datum or parcel linkage. Not a serving model predictor. |
| NOAA Storm Events research | [Official database](https://www.ncei.noaa.gov/access/storm-events-database/) | Potential incident discovery; no retained incident count, parcel labels or negatives were verified here. Do not quote the older count without its source files. |
| NWS official alerts | [NWS API documentation](https://www.weather.gov/documentation/services-web-api), [county-query geolocation guide](https://www.weather.gov/media/documentation/docs/NWS_Geolocation.pdf) | Separate optional county UGC `FLC091` importer. Retain original text, IDs, issue/expiry and retrieval. NWS documents open data and identifying User-Agent use. Archive has no current alerts. One bounded live county import is recorded in [verified execution](verified-run.md); no current UI/refresh was activated. |
| Mapbox GL JS 3.33.0 / Mapbox tiles | [GL JS documentation](https://docs.mapbox.com/mapbox-gl-js/), [service terms](https://www.mapbox.com/legal/tos), [required attribution](https://docs.mapbox.com/help/getting-started/attribution/) | Browser SDK loaded from Mapbox; preserve required Mapbox/data-provider attribution. Only public `pk.` token in browser. Account/service rights are not inferred from npm licenses. |

Raw sources and models stay ignored. Reproduction uses code plus permitted acquisition and privately supplied manifests; this package does not include a public county-data ZIP. Source terms/entitlements do not establish a live configured connection.

## Software and UI

The [machine-readable inventory](dependency-inventory.json) records every npm lockfile entry, including optional platform binaries and development packages. Regenerate with `python3 scripts/record_dependency_inventory.py`. Versions below are locked versions, not the ranges in `package.json`. Preserve actual upstream LICENSE/NOTICE files when distributing software.

| Direct resource | Locked version | Declared license / primary project |
| --- | --- | --- |
| React / React DOM | 19.3.1 / 19.3.1 | MIT; [React](https://github.com/facebook/react) |
| Radix UI | 1.8.1 | MIT; [Radix](https://github.com/radix-ui/primitives) |
| Recharts | 3.8.0 | MIT; [Recharts](https://github.com/recharts/recharts) |
| Lucide React icons | 0.468.0 | ISC; [Lucide](https://github.com/lucide-icons/lucide) |
| Polygon clipping | 0.15.7 | MIT; [polygon-clipping](https://github.com/mfogel/polygon-clipping) |
| Class variance authority | 0.7.1 | Apache-2.0; [CVA](https://github.com/joe-bell/cva) |
| clsx | 2.1.1 | MIT; [clsx](https://github.com/lukeed/clsx) |
| tailwind-merge | 3.7.0 | MIT; [tailwind-merge](https://github.com/dcastil/tailwind-merge) |
| Tailwind CSS / Vite plugin | 4.3.3 / 4.3.3 | MIT; [Tailwind](https://github.com/tailwindlabs/tailwindcss) |
| tw-animate-css | 1.4.0 | MIT; [tw-animate-css](https://github.com/Wombosvideo/tw-animate-css) |
| TypeScript | 5.9.3 | Apache-2.0; [TypeScript](https://github.com/microsoft/TypeScript) |
| Vite / React Vite plugin | 7.3.7 / 5.2.0 | MIT; [Vite](https://github.com/vitejs/vite), [React plugin](https://github.com/vitejs/vite-plugin-react) |
| H3 JS | 4.3.0 | Apache-2.0; [H3 JS](https://github.com/uber/h3-js); existing [license](../../quasar/static/vendor/h3-LICENSE) and [notice](../../quasar/static/vendor/h3-NOTICE) stay vendored |
| fake-indexeddb | 6.2.6 | Apache-2.0; [fake-indexeddb](https://github.com/dumbmatter/fakeIndexedDB); tests only |
| Node/React/React DOM types | 22.20.5 / 19.3.0 / 19.3.0 | MIT; [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped); development only |
| Python runtime | Baseline 3.14.7; research 3.12.14 | [PSF license](https://docs.python.org/3/license.html); server imports standard library only |
| Optional XGBoost | 3.4.1 | Apache-2.0; [XGBoost](https://github.com/dmlc/xgboost); local training only |
| Optional scikit-learn / NumPy | 1.9.1 / 2.5.4 | BSD-3-Clause; [scikit-learn](https://github.com/scikit-learn/scikit-learn), [NumPy](https://github.com/numpy/numpy); local research only |
| Optional Shapely / pyproj | 2.1.2 / 3.7.2 | BSD-3-Clause / MIT; [Shapely](https://github.com/shapely/shapely), [pyproj](https://github.com/pyproj4/pyproj); inspect bundled native-library notices separately |
| Optional Jupyter stack | Pins in [pyproject.toml](../../pyproject.toml) | [Jupyter](https://jupyter.org/about); research only, not installed for this implementation |
| Shadcnblocks application-shell/dashboard/chart components | Source references in `frontend/components/` | [License](https://www.shadcnblocks.com/license), [terms](https://www.shadcnblocks.com/terms). Commercial template provenance; not claimed as self-authored. License/account scope and source-sharing permission need Isaac's review. No permission was inferred from registry access. |

Use upstream tags/license files and the applicable account terms for any final redistribution decision. The lockfile inventory records declarations rather than granting rights. No repository-wide license was added over third-party components. Attribution and event originality questions remain open until their actual permission/contribution evidence exists; administrative event questions were excluded from this implementation.
