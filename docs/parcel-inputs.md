# Preparing real parcel inputs locally

`scripts/prepare_parcel_inputs.py` prepares descriptive terrain, FEMA and mapped
river/stream inputs for the acquired Okaloosa parcel inventory. The output is a
separate research artifact. The application continues to show real parcel scores
as unknown; the six fictional sites keep their existing exercise inputs.

## Run

Use a separate Python 3.12 environment:

```sh
uv venv --python 3.12 .context/gis-venv
uv pip install --python .context/gis-venv/bin/python -r requirements-gis.txt
.context/gis-venv/bin/python scripts/prepare_parcel_inputs.py
```

This command has no network/cloud operations. It checks acquired input hashes
and county provenance before processing. Each invocation writes a new directory
under ignored `data/processed/okaloosa/parcel-inputs/`; an explicit `--output`
must also name a new directory. A run is complete only when `manifest.json`
exists. Failed directories can be retained for inspection; they are not complete
artifacts. Source downloads and the existing app parcel database are preserved.

The optional packages are pinned in `requirements-gis.txt`. PyPI had no published
`s390x` wheels for Rasterio 1.4.3, Fiona 1.10.1, Shapely 2.1.2 or PyProj 3.7.2
when checked October 17, 2026. These are local preparation dependencies; they
are not app, notebook or container requirements. Transfer the generated SQLite,
JSON and GeoTIFF artifacts if needed. No IBM host access or transfer occurs here.

## Artifacts

| File | Content |
| --- | --- |
| `elevation-county.tif` | Native-grid USGS elevation, cropped/masked to the authoritative county; no resampling or vertical conversion |
| `fema-zones.geojsonl.gz` | One county-clipped FEMA feature per line, WGS84 geometry, original zone/subtype, IDs, units, vertical datum, source citation and repair flags |
| `parcel-inputs.sqlite3` | One descriptive input record per source parcel, keyed by `parcel_id`; no owner/address data |
| `manifest.json` | Source retrieval dates, licenses, checksums, dates, transformations, software versions, coverage counts and output hashes |

The SQLite `parcel_inputs` table has `parcel_id`, `county_fips`, `inputs_json`.
The `metadata` table contains the preparation manifest under key `manifest`
(output file hashes are in the external manifest to avoid a circular hash).

## Terrain

The acquired tile is NAD83 geographic (`EPSG:4269`), with 1/3 arc-second pixels,
approximately 10 m. Vendor XML identifies elevation meters above NAVD88 and source
dates December 2019–January 2022, with publication July 6, 2026. Publication date
is not the date every elevation was observed. The county crop retains the
source grid and NoData; geographic transformations use PyProj's installed PROJ
operations, with reported accuracy recorded (`-1` means unknown).

Terrain records contain minimum/mean/maximum of valid native pixel centers
inside the parcel, selected/valid pixel counts and valid fraction. Status is
`complete`, `partial`, `missing`, `no_pixel_centers` or `unknown`. Negative real
elevations and zero are valid. Source mask/NoData/nonfinite values are missing.

Small/narrow parcels may contain no pixel centers. An interior representative
point's containing pixel is reported separately; it never fills polygon
statistics. Neither quantity is surveyed building or floor elevation. NoData
must not become zero or low risk. County-wide pixel coverage includes water;
missing-pixel causes are not inferred from the DEM alone.

## FEMA

Area intersections use NAD83 / UTM 16N (`EPSG:26916`) in meters. All positively
overlapping polygons are retained, including X subtypes; touching boundaries
alone do not count as area. Unioned intersection area prevents double counting
overlapping source polygons. A parcel can have several zones; no single
"worst zone" is assigned. Unmapped portions remain unknown.

The source package publication is March 8, 2021; panel effective dates are
recorded separately, including older panels. [Okaloosa's published guidance](https://www.myokaloosa.com/index.php/crs-flood-facts-elevation-certificates)
lists March 9, 2021 as the effective flood map date. **Completeness against later
Letters of Map Revision is unverified.** These reference joins cannot establish
the precise regulatory map as of October 9, 2026.

### Live reference audit

The optional explicit command below compares minimal attributes with FEMA's
[public NFHL REST service](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer),
and checks its LOMR layer against the exact county polygon:

```sh
.context/gis-venv/bin/python scripts/audit_fema_reference.py
```

It preserves raw responses and request/retrieval receipts under
`data/raw/okaloosa/fema-live-audit/`; the comparison is
`data/processed/okaloosa/fema-reference-audit.json`. It does not query BigQuery,
replace the local map or change a parcel score. Attribute comparison treats
blank strings and null as equivalent, preserving both raw representations.

The October 17 audit returned the same 2,855 source IDs and zone labels as the
downloaded package. Two `OPEN WATER` features (`12091C_1580`, `12091C_2511`)
had conflicting `SFHA_TF` flags: `T` in the package and `F` in the live service.
There were also 4,385 blank/null field representation differences. No returned LOMR candidate
intersected the authoritative Okaloosa polygon; the one envelope candidate
belonged to neighboring Walton County. **Zone geometry was not compared,
LOMA point amendments were not reconciled, and a current service read cannot
prove the exact information available at the historical replay time.** This
narrows the revision uncertainty without claiming a legal map determination.

Attach the audit to a **new** research artifact after preparation:

```sh
.context/gis-venv/bin/python scripts/prepare_parcel_inputs.py \
  --reconcile-from data/processed/okaloosa/parcel-inputs/PREPARED_RUN \
  --output data/processed/okaloosa/parcel-inputs/RECONCILED_RUN
```

This step verifies parent artifact/source hashes and audit receipts. It preserves
the parent, original package attributes and package SFHA area fraction. For
parcels overlapping either conflicting feature, `sfha_mapped_area_fraction`
becomes null and `sfha_reference_status` is `conflicting_source_flags`; both
source values are retained. The mapped-area coverage status is separate from
this attribute uncertainty. A changed zone inventory or other substantive
attribute changes require explicit source review before reconciliation.

To replay the attribute comparison from its original, checksum-verified raw
responses without another network read:

```sh
.context/gis-venv/bin/python scripts/audit_fema_reference.py \
  --reuse data/processed/okaloosa/fema-reference-audit.json
```

Invalid FEMA geometry is repaired explicitly and flagged. Invalid parcel
geometry is kept as an unknown record, without silently repairing a real
property boundary. FEMA sentinel elevations/depths become null. Known source
feet convert to meters at 0.3048; unknown units stay unknown. Source vertical
datum and values remain available. DEM is never subtracted from BFE to claim
event flood depth.

## Hydrography

`nearest_retained_river_stream_distance_m` is the planar distance from the
parcel edge to the nearest retained county river/stream geometry. Source layer
and feature ID are retained. It is a descriptive measurement over an incomplete
reference network: the county lakes source is unavailable, boundary-crossing
features were excluded during acquisition, and coastal/canal coverage is not
complete. Zero means geometric intersection with a retained mapped feature.

Hydrologic connectivity, the scoring field `waterway_distance_m`, and gauge
margin remain unknown. Geometric proximity does not establish a connected
flow path, drainage direction or flood susceptibility.

## Remaining work

Reconcile later FEMA map changes, investigate terrain gaps affecting assets,
complete hydrography and establish hydrologic relevance. Historical observed
rainfall/stage, verified flooding/closures, building footprints and floor heights
are still separate acquisition/modeling tasks. Feature preparation does not
validate the heuristic or produce safe navigation/evacuation guidance.

## October 17, 2026 preparation checkpoint

Completed artifact:
`data/processed/okaloosa/parcel-inputs/20261017-reconciled/`.
Its parent `20261017-prepared/` preserves the package-only preparation; the
interrupted `20261017-initial/` has no completion manifest and is excluded from
the transfer bundle. The app's parcel database and fixtures were not replaced.

| Result | Count |
| --- | ---: |
| Parcel records, all with unknown scores | 113,818 |
| Valid source parcel geometry | 113,803 |
| Complete terrain polygon summaries | 112,280 |
| No native terrain pixel centers; separate interior point sample available | 1,523 |
| Invalid source geometry; inputs remain unknown | 15 |
| Complete FEMA mapped-area coverage | 113,760 |
| Partial FEMA mapped-area coverage | 43 |
| Parcels overlapping the two conflicting open-water SFHA flags | 0 |

Every valid parcel has an available interior point sample, and every parcel with
selected native pixel centers has complete valid terrain pixels. The county
mask has 35,429,903 pixel centers, of which 4,667,598 (13.17%) are NoData. The
county-wide missing pixels do not establish missing terrain at every asset;
parcel results above report actual intersections. NoData causes are unclassified.

The 15 invalid source polygons have explicit geometry failure reasons. The 43
partial FEMA coverages range from 19.81% to 99.9949% mapped area; their unmapped
portions remain unknown. Descriptive distances were prepared for 113,803 valid
parcels, retaining the incomplete-network and unknown-connectivity labels.

Data read-back checks confirmed 113,818 unique SQLite records, database
integrity `ok`, matching artifact SHA-256 hashes, all scores null/unknown, and
no reversed minimum/mean/maximum or invalid pixel counts. These are preparation
and consistency checks, not flood-model evaluation or app/deployment acceptance.
