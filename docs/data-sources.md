# Okaloosa source catalog

All county inputs target **FIPS 12091**. Downloads are ignored under `data/raw/`; derived artifacts and manifests are under `data/processed/`. Reacquisition does not establish a validated flood model, current official alerts or historic flood outcomes.

| Input | Authoritative source | Acquisition and preparation |
| --- | --- | --- |
| County geometry | [Census TIGERweb](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1) | `scripts/acquire_local_data.py`, exact GEOID 12091; WGS84 geometry used for full containment checks. |
| Parcels | [Okaloosa GIS parcels, layer 0](https://okgis.myokaloosa.com/arcgis/rest/services/Land-Ownership/Parcels/MapServer/0) | `scripts/acquire_county_parcels.py`, OBJECTID and geometry only. October 17: 114,009 source features, 113,818 fully county-contained, 191 excluded. No owner/contact fields or flood scores. |
| FEMA | [NFHL county package](https://msc.fema.gov/portal/downloadProduct?productID=NFHL_12091C) | Downloaded `NFHL_12091C`; offline preparation clips 2,854 polygons and preserves effective dates, CRS, units and datum. Live attribute audit found two conflicting open-water SFHA flags, affecting zero retained parcels; geometry/LOMA reconciliation remains open. Regulatory mapping, not an event forecast. |
| Elevation | [USGS 3DEP catalog](https://tnmaccess.nationalmap.gov/api/v1/products) | Acquired 1/3 arc-second tile `n31w087` and vendor XML; original GeoTIFF about 314 MB. County crop retains NAD83 native grid, meters/NAVD88 and NoData. 112,280 complete parcel polygon summaries; 1,523 parcels have no native pixel centers and retain separate point samples; 15 invalid parcel geometries remain unknown. |
| Gauges | [USGS monitoring locations](https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items) | 72 stream station points pass FIPS and county polygon checks; one rejected. Station metadata is not stage observations or a gauge-to-parcel linkage. |
| Roads | [County centerlines, layer 120](https://okgis.myokaloosa.com/arcgis/rest/services/Infrastructure/Transportation/MapServer/120) | `scripts/acquire_supporting_data.py`: minimal identifiers/names and WGS84 geometry. 22,389 of 22,540 segments fully county-contained. Exercise topology, speeds, connectors and destinations remain simulated. |
| Hydrography | [County rivers/streams/water layers](https://okgis.myokaloosa.com/arcgis/rest/services/Natural-Features/LandCover_Planimetrics/MapServer) | Supporting importer retains 16 river and 3,456 stream features. Water-bodies service reports zero records; lakes service currently fails and is marked unavailable. Missing coverage never becomes zero distance or low risk. |
| Current/historical rainfall | [WeatherNext BigQuery](https://developers.google.com/weathernext/guides/bigquery) | Explicit county native-cell importer; dry-run and cumulative budget checks before execution. See [integration budget](integrations.md). Old Miami-Dade point rainfall is not Okaloosa rainfall. |
| Storm context | [NHC Isaias 2026 archive](https://www.nhc.noaa.gov/archive/2026/ISAIAS.shtml) | `scripts/prepare_isaias.py --only advisories`: 14 original public advisories, original issue times and hashes. These storm-level documents can be reused after identity checks. They do not establish local observed flooding. |
| Official local guidance | [NWS Mobile/Pensacola](https://www.weather.gov/mob/) and [Okaloosa emergency management](https://myokaloosa.com/emergency-management) | Point-alert adapter uses the relocated exercise sites. Dashboard remains explicitly not connected until alert ingestion/freshness/coverage are implemented. |

County GIS output is transformed from EPSG:2238 (US survey feet) to EPSG:4326 via the source service. Retain the [Property Appraiser disclaimer](https://www.okaloosapa.com/gis-mapping/): reference data, no accuracy warranty, not a survey/legal document. Miami-Dade license claims do not transfer to Okaloosa.

## Commands

```sh
python3 scripts/acquire_local_data.py
python3 scripts/acquire_county_parcels.py
python3 scripts/acquire_supporting_data.py
python3 scripts/prepare_isaias.py
node scripts/index_parcels_by_h3.mjs data/raw/okaloosa_parcels_wgs84.geojsonl.gz data/raw/census_okaloosa_county.geojson data/processed/okaloosa/linuxone
```

Build SQLite with `scripts/build_linuxone_parcel_db.py` and explicit `--parcels`, `--source-manifest`, `--cell-map`, `--cells`, and `--output` paths in the Okaloosa directory. Its manifest records counts/checksums. Real parcels always retain null scores. Keep raw files, normalized snapshots, import reports and checksums together when transferring a bundle; ignored files do not follow a Git push or Vercel deployment.

## Offline parcel input joins

Use [local parcel input preparation](parcel-inputs.md) for native DEM coverage checks, county-masked elevation, FEMA polygon overlaps and descriptive distances to retained mapped rivers/streams. Research artifacts remain separate from app scoring. Source masks, unmapped areas, later FEMA revision uncertainty and incomplete hydrography stay explicit.
