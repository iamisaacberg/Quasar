"""Offline, optional GIS research: terrain summaries and source polygon joins.

This module is never imported by the application. It requires requirements-gis.txt
in a separate local environment. Outputs are descriptive inputs, never scores.
"""

import gzip
import hashlib
import json
import math
import shutil
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

COUNTY = "12091"
METRIC_CRS = "EPSG:26916"  # NAD83 / UTM zone 16N, meters.
NOTICE = ("Research inputs only. No flood score, depth, probability or safety claim. "
          "Current reference geometry is not verified as-issued storm data. "
          "FEMA later-revision completeness and hydrologic connectivity are unknown.")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _polygonal(geometry):
    from shapely.geometry import MultiPolygon
    if geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    parts = []
    for item in getattr(geometry, "geoms", ()):
        selected = _polygonal(item)
        if selected.geom_type == "Polygon" and not selected.is_empty:
            parts.append(selected)
        elif selected.geom_type == "MultiPolygon":
            parts.extend(selected.geoms)
    return MultiPolygon(parts)


def _known_number(value):
    # FEMA's -9999/-8888 values are sentinels, never valid zero elevations.
    if value is None or value in (-9999, -8888):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _fema_attributes(properties):
    fields = ("DFIRM_ID", "VERSION_ID", "FLD_AR_ID", "STUDY_TYP", "FLD_ZONE",
              "ZONE_SUBTY", "SFHA_TF", "V_DATUM", "LEN_UNIT", "SOURCE_CIT")
    result = {key: properties.get(key) for key in fields}
    for key in ("STATIC_BFE", "DEPTH"):
        result[key] = _known_number(properties.get(key))
    factor = {"Feet": 0.3048, "Meters": 1.0}.get(properties.get("LEN_UNIT"))
    result["static_bfe_m"] = (result["STATIC_BFE"] * factor
                               if factor is not None and result["STATIC_BFE"] is not None else None)
    result["depth_m"] = (result["DEPTH"] * factor
                          if factor is not None and result["DEPTH"] is not None else None)
    return result


def normalize_fema(archive, county, output):
    import fiona
    from pyproj import Transformer
    from shapely import make_valid, prepare
    from shapely.geometry import shape, mapping
    from shapely.ops import transform
    from shapely.strtree import STRtree

    url = f"zip://{Path(archive).resolve()}!S_FLD_HAZ_AR.shp"
    records, geoms, counts = [], [], Counter()
    with fiona.open(url) as source:
        source_crs = source.crs.to_string()
        project = Transformer.from_crs(source.crs, METRIC_CRS, always_xy=True)
        geographic = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True)
        for feature in source:
            counts["source_features"] += 1
            props = dict(feature["properties"])
            if props.get("DFIRM_ID") != "12091C":
                raise ValueError("FEMA feature belongs to a different county")
            geom = shape(feature["geometry"])
            repaired = not geom.is_valid
            if repaired:
                counts["repaired_features"] += 1
                geom = _polygonal(make_valid(geom))
            geom = _polygonal(transform(project.transform, geom).intersection(county))
            if geom.is_empty:
                counts["excluded_empty_or_outside"] += 1
                continue
            if not geom.is_valid:
                raise ValueError("FEMA normalization produced invalid geometry")
            attrs = _fema_attributes(props)
            attrs["geometry_repaired"] = repaired
            records.append(attrs)
            prepare(geom)
            geoms.append(geom)
        operation = {"description": project.description, "accuracy_m": project.accuracy}
    with gzip.open(output, "wt", encoding="utf-8") as target:
        # GeoJSONL keeps this streamable; each feature carries its source ID.
        for props, geom in zip(records, geoms):
            target.write(json.dumps({"type": "Feature", "id": props["FLD_AR_ID"],
                                     "properties": props,
                                     "geometry": mapping(transform(geographic.transform, geom))},
                                    separators=(",", ":"), allow_nan=False) + "\n")
    with fiona.open(f"zip://{Path(archive).resolve()}!S_FIRM_PAN.shp") as panels:
        dates = sorted({f["properties"]["EFF_DATE"] for f in panels if f["properties"]["EFF_DATE"]})
    with zipfile.ZipFile(archive) as source:
        metadata_names = [n for n in source.namelist() if n.lower().endswith("_metadata.xml")]
        publications = sorted({el.text for name in metadata_names
                               for el in ET.fromstring(source.read(name)).iter("pubdate") if el.text})
    counts["retained_features"] = len(records)
    return STRtree(geoms), geoms, records, {
        **dict(counts), "source_crs": source_crs, "analysis_crs": METRIC_CRS,
        "output_crs": "EPSG:4326", "coordinate_operation": operation,
        "panel_effective_dates": dates, "package_publication_dates": publications,
        "later_revision_completeness": "unknown; no LOMR reconciliation performed",
        "processing": "Make invalid source polygons valid with recorded flags; retain polygonal parts; transform, intersect exact county, preserve source zone/subtype and datum. Convert only known length units; preserve sentinel values as null.",
    }


def clip_terrain(dem, metadata_xml, county_wgs, output):
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask, geometry_window
    from shapely.geometry import box, mapping
    from shapely.ops import transform

    xml = ET.parse(metadata_xml).getroot()
    vertical = xml.findtext(".//altdatum")
    units = xml.findtext(".//altunits")
    if vertical != "North American Vertical Datum of 1988" or units != "meters":
        raise ValueError("Expected explicit NAVD88 / meters in vendor metadata")
    with rasterio.open(dem) as source:
        if source.count != 1 or source.crs.to_epsg() != 4269 or source.nodata is None:
            raise ValueError("Expected single-band NAD83 DEM with explicit NoData")
        project = Transformer.from_crs("EPSG:4326", source.crs, always_xy=True)
        county = transform(project.transform, county_wgs)
        extent_covers = box(*source.bounds).covers(county)
        if not extent_covers:
            raise ValueError("DEM extent does not cover the entire county; acquire missing tiles")
        window = geometry_window(source, [mapping(county)])
        affine = source.window_transform(window)
        values = source.read(1, window=window)
        source_valid = source.read_masks(1, window=window) > 0
        inside = geometry_mask([mapping(county)], values.shape, affine, invert=True, all_touched=False)
        valid = source_valid & np.isfinite(values) & (values != source.nodata)
        profile = source.profile.copy()
        profile.update(width=values.shape[1], height=values.shape[0], transform=affine,
                       compress="deflate", tiled=True, blockxsize=256, blockysize=256)
        with rasterio.open(output, "w", **profile) as target:
            target.write(np.where(inside & valid, values, source.nodata), 1)
            target.set_band_unit(1, "m")
            target.update_tags(vertical_datum="NAVD88", county_fips=COUNTY,
                               processing="Native grid; pixel centers inside Census county; no resampling",
                               source_sha256=digest(dem))
        selected = values[inside & valid]
        summary = {
            "source_crs": source.crs.to_string(), "vertical_datum": vertical, "units": units,
            "native_pixel_degrees": list(source.res), "source_nodata": source.nodata,
            "extent_covers_entire_county": extent_covers,
            "county_pixel_centers": int(inside.sum()),
            "valid_county_pixel_centers": int((inside & valid).sum()),
            "missing_county_pixel_centers": int((inside & ~valid).sum()),
            "valid_fraction": float((inside & valid).sum() / inside.sum()),
            "min_m": float(selected.min()) if selected.size else None,
            "max_m": float(selected.max()) if selected.size else None,
            "vendor_publication_date": xml.findtext(".//citeinfo/pubdate"),
            "source_date_range": [xml.findtext(".//begdate"), xml.findtext(".//enddate")],
            "coordinate_operation_accuracy_m": project.accuracy,
            "processing": "Native-resolution crop and county pixel-center mask, no vertical conversion or interpolation. Invalid/NoData remains missing. Pixels are not building elevations or water levels.",
        }
    # Keep source pixels within the crop, including edge centers outside county,
    # for boundary parcel windows; each parcel is separately county-contained.
    return values, valid, affine, county, summary


def terrain_for_polygon(geometry, values, valid, affine):
    import numpy as np
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, transform as window_transform
    from shapely.geometry import mapping

    left, bottom, right, top = geometry.bounds
    c0, r0 = ~affine * (left, top)
    c1, r1 = ~affine * (right, bottom)
    x0, y0 = max(0, math.floor(c0)), max(0, math.floor(r0))
    x1, y1 = min(values.shape[1], math.ceil(c1)), min(values.shape[0], math.ceil(r1))
    count = available = 0
    sampled = np.array([], dtype=float)
    if x1 > x0 and y1 > y0:
        local = values[y0:y1, x0:x1]
        # Explicit center rule avoids attributing neighboring pixels to narrow parcels.
        inside = geometry_mask([mapping(geometry)], local.shape,
                               window_transform(Window(x0, y0, x1-x0, y1-y0), affine),
                               all_touched=False, invert=True)
        count = int(inside.sum())
        sampled = local[inside & valid[y0:y1, x0:x1]]
        available = int(sampled.size)
    point = geometry.representative_point()
    col, row = ~affine * (point.x, point.y)
    col, row = math.floor(col), math.floor(row)
    point_value = (float(values[row, col]) if 0 <= row < values.shape[0] and 0 <= col < values.shape[1]
                   and valid[row, col] else None)
    return {
        "status": ("no_pixel_centers" if not count else "missing" if not available
                   else "complete" if count == available else "partial"),
        "pixel_centers": count, "valid_pixel_centers": available,
        "valid_fraction": available / count if count else None,
        "min_m": float(sampled.min()) if available else None,
        "mean_m": float(sampled.mean(dtype=np.float64)) if available else None,
        "max_m": float(sampled.max()) if available else None,
        "representative_point_m": point_value,
        "representative_point_method": "single native pixel containing an interior representative point; separate from polygon statistics",
        "vertical_datum": "NAVD88", "units": "m", "building_elevation": None,
    }


def fema_for_polygon(parcel, tree, geometries, records):
    from shapely.ops import unary_union
    pieces, sfha, hits = [], [], []
    for index in tree.query(parcel):
        zone = geometries[index]
        if zone.covers(parcel):
            overlap = parcel
        elif zone.intersects(parcel):
            overlap = parcel.intersection(zone)
        else:
            continue
        if overlap.area <= 0:
            continue  # Touching a boundary is not area coverage.
        pieces.append(overlap)
        attrs = records[index]
        if attrs["SFHA_TF"] == "T":
            sfha.append(overlap)
        hits.append({**attrs, "intersection_area_m2": overlap.area,
                     "parcel_area_fraction": min(1.0, overlap.area / parcel.area)})
    mapped = unary_union(pieces).area if pieces else 0.0
    special = unary_union(sfha).area if sfha else 0.0
    fraction = min(1.0, mapped / parcel.area)
    return {
        "status": "unmapped" if not pieces else "complete" if fraction >= 0.999999 else "partial",
        "mapped_area_fraction": fraction,
        "sfha_mapped_area_fraction": min(1.0, special / parcel.area) if pieces else None,
        "unmapped_area_fraction": max(0.0, 1.0 - fraction),
        "zones": sorted({hit["FLD_ZONE"] for hit in hits if hit["FLD_ZONE"]}),
        "overlaps": sorted(hits, key=lambda hit: hit["FLD_AR_ID"]),
        "notice": "Mapped regulatory area overlap only. Unmapped area is unknown; X or no SFHA overlap does not establish safety. BFE minus DEM is not calculated.",
    }


def normalize_hydro(paths, county, boundary_sha):
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    from shapely.strtree import STRtree
    geoms, ids, provenance = [], [], []
    from shapely import prepare
    containment = county.buffer(0.001)
    prepare(containment)
    project = Transformer.from_crs("EPSG:4326", METRIC_CRS, always_xy=True)
    for path in paths:
        data = json.loads(Path(path).read_text())
        if (data.get("county_fips") != COUNTY or data.get("crs") != "EPSG:4326"
                or data.get("county_boundary_sha256") != boundary_sha):
            raise ValueError("Hydrography county/CRS/boundary provenance mismatch")
        for feature in data["features"]:
            geom = transform(project.transform, shape(feature["geometry"]))
            if not geom.is_valid or geom.is_empty or geom.geom_type not in ("LineString", "MultiLineString", "Polygon", "MultiPolygon"):
                raise ValueError("Invalid hydrography geometry")
            # Projection discretization can introduce sub-mm county edge differences.
            # Full containment was already validated on the geographic source geometry.
            if not containment.covers(geom):
                raise ValueError("Hydrography geometry outside county")
            geoms.append(geom)
            ids.append({"layer": Path(path).stem, "source_id": feature["id"]})
        provenance.append({k: data.get(k) for k in (
            "source_url", "retrieved_at", "license", "crs", "source_count", "excluded_count")})
    if not geoms:
        raise ValueError("No hydrography geometries; distance is unavailable")
    return STRtree(geoms), geoms, ids, provenance


def prepare(root, output):
    import fiona
    import numpy
    import pyproj
    import rasterio
    import shapely
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    root, output = Path(root).resolve(), Path(output).resolve()
    implementation = [{"path": str(path.relative_to(root)), "sha256": digest(path)} for path in (
        root / "quasar/parcel_inputs.py", root / "scripts/prepare_parcel_inputs.py", root / "requirements-gis.txt")]
    # Each run gets a new directory. A failed run cannot overwrite the last artifact.
    output.mkdir(parents=True, exist_ok=False)
    raw = root / "data/raw"
    source_manifest_path = root / "data/processed/source_manifest.json"
    manifest = json.loads(source_manifest_path.read_text())
    parcel_manifest = json.loads((raw / "okaloosa_parcels_wgs84.manifest.json").read_text())
    if manifest.get("county_fips") != COUNTY or parcel_manifest.get("county_fips") != COUNTY:
        raise ValueError("Expected Okaloosa source manifests")
    sources = {}
    for entry in manifest["sources"]:
        if digest(root / entry["path"]) != entry["sha256"]:
            raise ValueError(f"Source checksum mismatch: {entry['path']}")
        sources[entry["path"]] = entry
    parcels = raw / "okaloosa_parcels_wgs84.geojsonl.gz"
    if digest(parcels) != parcel_manifest["output_sha256"]:
        raise ValueError("Parcel checksum mismatch")
    boundary_path = raw / "census_okaloosa_county.geojson"
    boundary_sha = digest(boundary_path)
    if boundary_sha != parcel_manifest["county_boundary"]["sha256"]:
        raise ValueError("Parcel and county boundary provenance mismatch")
    boundary = json.loads(boundary_path.read_text())
    if len(boundary["features"]) != 1 or boundary["features"][0]["properties"]["GEOID"] != COUNTY:
        raise ValueError("County boundary identity mismatch")
    county_wgs = shape(boundary["features"][0]["geometry"])
    if not county_wgs.is_valid:
        raise ValueError("Invalid county boundary")
    shapely.prepare(county_wgs)
    metric = Transformer.from_crs("EPSG:4326", METRIC_CRS, always_xy=True)
    county_metric = transform(metric.transform, county_wgs)
    dem_entries = [entry for entry in manifest["sources"] if entry["path"].endswith(".tif")]
    if len(dem_entries) != 1:
        raise ValueError("This preparer expects one verified county-covering DEM tile")
    dem_entry = dem_entries[0]
    metadata_path = root / dem_entry["metadata"]["path"]
    if digest(metadata_path) != dem_entry["metadata"]["sha256"]:
        raise ValueError("DEM metadata checksum mismatch")
    values, valid, affine, _, elevation_summary = clip_terrain(
        root / dem_entry["path"], metadata_path, county_wgs, output / "elevation-county.tif")
    print("County elevation coverage:", json.dumps(elevation_summary), flush=True)
    fema_tree, fema_geoms, fema_records, fema_summary = normalize_fema(
        raw / "fema_nfhl_okaloosa_12091c.zip", county_metric, output / "fema-zones.geojsonl.gz")
    print("FEMA normalized:", json.dumps(fema_summary), flush=True)
    hydro_paths = [root / f"data/processed/okaloosa/{name}.geojson" for name in ("rivers", "streams")]
    hydro_tree, hydro_geoms, hydro_ids, hydro_provenance = normalize_hydro(hydro_paths, county_metric, boundary_sha)
    to_dem = Transformer.from_crs("EPSG:4326", "EPSG:4269", always_xy=True)
    counts = Counter()
    connection = sqlite3.connect(output / "parcel-inputs.sqlite3")
    try:
        connection.execute("CREATE TABLE parcel_inputs (parcel_id INTEGER PRIMARY KEY, county_fips TEXT NOT NULL CHECK(county_fips='12091'), inputs_json TEXT NOT NULL) WITHOUT ROWID")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID")
        batch = []
        with gzip.open(parcels, "rt", encoding="utf-8") as source:
            for line in source:
                feature = json.loads(line)
                props = feature["properties"]
                parcel_id = props["parcel_id"]
                if type(parcel_id) is not int or props.get("county_fips") != COUNTY:
                    raise ValueError("Invalid parcel identity")
                geom = shape(feature["geometry"])
                record = {"parcel_id": parcel_id, "county_fips": COUNTY,
                          "geometry_status": "valid", "area_m2": None,
                          "terrain": {"status": "unknown"}, "fema": {"status": "unknown"},
                          "hydrography": {"status": "unknown"},
                          "risk_score": None, "risk_band": "unknown",
                          "waterway_distance_m": None, "gauge_margin_m": None}
                if not geom.is_valid or geom.is_empty or geom.area <= 0:
                    record["geometry_status"] = "invalid_source_geometry"
                    record["geometry_reason"] = shapely.is_valid_reason(geom)
                elif not county_wgs.covers(geom):
                    record["geometry_status"] = "outside_exact_county"
                else:
                    projected = transform(metric.transform, geom)
                    record["area_m2"] = projected.area
                    record["terrain"] = terrain_for_polygon(transform(to_dem.transform, geom), values, valid, affine)
                    record["fema"] = fema_for_polygon(projected, fema_tree, fema_geoms, fema_records)
                    nearest = int(hydro_tree.nearest(projected))
                    record["hydrography"] = {
                        "status": "partial_reference_coverage",
                        "nearest_retained_river_stream_distance_m": projected.distance(hydro_geoms[nearest]),
                        "nearest_feature": hydro_ids[nearest],
                        "hydrologic_connectivity": "unknown", "lakes_coverage": "unavailable",
                        "notice": "Planar parcel-edge distance to the retained mapped rivers/streams; boundary-crossing source features were excluded. Lakes, canals and coastal water are not complete. This is not the scoring waterway-distance input.",
                    }
                counts["parcels"] += 1
                for key, value in (("geometry", record["geometry_status"]),
                                   ("terrain", record["terrain"]["status"]), ("fema", record["fema"]["status"])):
                    counts[f"{key}_{value}"] += 1
                counts["terrain_point_available"] += record["terrain"].get("representative_point_m") is not None
                batch.append((parcel_id, COUNTY, json.dumps(record, separators=(",", ":"), allow_nan=False)))
                if len(batch) >= 2000:
                    connection.executemany("INSERT INTO parcel_inputs VALUES (?,?,?)", batch)
                    connection.commit()
                    batch.clear()
                    print(f"Prepared {counts['parcels']:,} parcels", flush=True)
        if batch:
            connection.executemany("INSERT INTO parcel_inputs VALUES (?,?,?)", batch)
        if counts["parcels"] != parcel_manifest["county_validated_count"]:
            raise ValueError("Parcel count differs from source manifest")
        summary = {
            "schema_version": 1, "county_fips": COUNTY,
            "prepared_at": datetime.now(timezone.utc).isoformat(), "notice": NOTICE,
            "counts": dict(counts), "terrain": elevation_summary, "fema": fema_summary,
            "hydrography": {"status": "partial_reference_coverage", "sources": hydro_provenance,
                            "feature_count": len(hydro_geoms), "lakes_status": json.loads((root / "data/processed/okaloosa/lakes-status.json").read_text()),
                            "units": "meters", "analysis_crs": METRIC_CRS},
            "sources": {"acquisition_manifest": manifest, "parcels": parcel_manifest,
                        "boundary_sha256": boundary_sha,
                        "supporting_files": [{"path": str(p.relative_to(root)), "sha256": digest(p)} for p in hydro_paths]},
            "software": {"rasterio": rasterio.__version__, "fiona": fiona.__version__,
                         "numpy": numpy.__version__, "shapely": shapely.__version__, "pyproj": pyproj.__version__},
            "implementation": implementation,
            "metric_coordinate_operation": {"description": metric.description, "accuracy_m": metric.accuracy},
            "limitations": [
                "No real parcel scores or app runtime changes. No building footprints or floor heights.",
                "Terrain summaries count native pixel centers. Small parcels may contain none; point samples are reported separately and never substituted for polygon statistics.",
                "Partial/NoData coverage is retained. Terrain is bare-earth reference elevation, not event flood depth.",
                "FEMA zones are a dated regulatory reference; later LOMR completeness is unverified. Overlaps may coexist; area is unioned to avoid double counting. No single worst-zone assignment.",
                "Mapped hydrography distance is descriptive and incomplete; connectivity and scoring waterway_distance_m remain unknown.",
                "Historical observed rainfall, stream levels, closures and flood outcomes are not included.",
            ],
        }
        connection.execute("INSERT INTO metadata VALUES (?,?)", ("manifest", json.dumps(summary, allow_nan=False)))
        connection.commit()
    finally:
        connection.close()
    summary["artifacts"] = [{"path": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
                            for path in sorted(output.iterdir()) if path.is_file()]
    write_json(output / "manifest.json", summary)
    # Success marker is published last; consumers must require this manifest.
    print(json.dumps({"output": str(output), "counts": dict(counts)}, indent=2), flush=True)
    return summary


def reconcile_fema_reference(root, prepared, audit_path, output):
    """Attach a live attribute audit to a new artifact, preserving the parent.

    Conflicting SFHA flags invalidate that derived fraction for affected parcels.
    The package's original attributes and fraction remain available separately.
    """
    root, prepared, output = Path(root).resolve(), Path(prepared).resolve(), Path(output).resolve()
    audit_path = Path(audit_path).resolve()
    parent_path = prepared / "manifest.json"
    summary = json.loads(parent_path.read_text())
    audit = json.loads(audit_path.read_text())
    if summary.get("county_fips") != COUNTY or audit.get("county_fips") != COUNTY:
        raise ValueError("Expected Okaloosa preparation and audit")
    if (audit.get("source_url") != "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
            or audit.get("boundary_sha256") != summary["sources"]["boundary_sha256"]):
        raise ValueError("FEMA audit source/boundary mismatch")
    package = next(s for s in summary["sources"]["acquisition_manifest"]["sources"]
                   if s["path"].endswith("fema_nfhl_okaloosa_12091c.zip"))
    if audit.get("local_package_sha256") != package["sha256"]:
        raise ValueError("Audit describes a different source package")
    if audit.get("local_only_ids") or audit.get("live_only_ids"):
        raise ValueError("FEMA zone inventory changed; reacquire geometry before reconciliation")
    changes = {entry["source_id"]: entry for entry in audit["attribute_differences"]}
    if any(entry["fields"] != ["SFHA_TF"] or "values" not in entry for entry in changes.values()):
        raise ValueError("Unsupported attribute changes require explicit source review")
    for receipt in audit["receipts"]:
        if digest(root / receipt["path"]) != receipt["sha256"]:
            raise ValueError("Audit receipt checksum mismatch")
    for artifact in summary["artifacts"]:
        if digest(prepared / artifact["path"]) != artifact["sha256"]:
            raise ValueError("Parent preparation artifact checksum mismatch")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(prepared / "elevation-county.tif", output / "elevation-county.tif")
    with gzip.open(prepared / "fema-zones.geojsonl.gz", "rt") as source, gzip.open(output / "fema-zones.geojsonl.gz", "wt") as target:
        for line in source:
            feature = json.loads(line)
            if feature["id"] in changes:
                feature["properties"]["live_reference_comparison"] = changes[feature["id"]]
            target.write(json.dumps(feature, separators=(",", ":"), allow_nan=False) + "\n")
    shutil.copyfile(prepared / "parcel-inputs.sqlite3", output / "parcel-inputs.sqlite3")
    affected = 0
    connection = sqlite3.connect(output / "parcel-inputs.sqlite3")
    try:
        if changes:
            placeholders = ",".join("?" for _ in changes)
            rows = connection.execute(
                "SELECT DISTINCT p.parcel_id,p.inputs_json FROM parcel_inputs p, "
                "json_each(p.inputs_json,'$.fema.overlaps') zone "
                f"WHERE json_extract(zone.value,'$.FLD_AR_ID') IN ({placeholders})", tuple(changes)).fetchall()
            for parcel_id, payload in rows:
                record = json.loads(payload)
                fema = record["fema"]
                for hit in fema["overlaps"]:
                    if hit["FLD_AR_ID"] in changes:
                        hit["live_reference_comparison"] = changes[hit["FLD_AR_ID"]]
                fema["sfha_reference_status"] = "conflicting_source_flags"
                fema["package_sfha_mapped_area_fraction"] = fema["sfha_mapped_area_fraction"]
                fema["sfha_mapped_area_fraction"] = None
                connection.execute("UPDATE parcel_inputs SET inputs_json=? WHERE parcel_id=?",
                                   (json.dumps(record, separators=(",", ":"), allow_nan=False), parcel_id))
                affected += 1
        summary.pop("artifacts")
        summary["fema"]["live_attribute_audit"] = audit
        summary["fema"]["later_revision_completeness"] = "IDs/attributes compared; geometry and LOMA amendments unverified"
        summary["counts"]["fema_conflicting_sfha_parcels"] = affected
        summary["reference_reconciled_at"] = datetime.now(timezone.utc).isoformat()
        summary["parent_preparation"] = {"path": str(parent_path.relative_to(root)), "sha256": digest(parent_path)}
        summary["reference_audit"] = {"path": str(audit_path.relative_to(root)), "sha256": digest(audit_path)}
        summary["reconciliation_implementation_sha256"] = digest(root / "quasar/parcel_inputs.py")
        summary["limitations"].append("Live/package SFHA conflicts retain both values; affected SFHA fractions become null. A current audit is not as-issued historical proof.")
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", ("manifest", json.dumps(summary, allow_nan=False)))
        connection.commit()
    finally:
        connection.close()
    summary["artifacts"] = [{"path": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
                            for path in sorted(output.iterdir()) if path.is_file()]
    write_json(output / "manifest.json", summary)
    print(json.dumps({"output": str(output), "counts": summary["counts"]}, indent=2))
    return summary
