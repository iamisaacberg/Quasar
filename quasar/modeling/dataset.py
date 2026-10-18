"""Manifest auditing and spatial preparation. GIS dependencies are offline only."""
import hashlib
import json
import math
import sqlite3
import zlib
from collections import Counter
from contextlib import closing
from pathlib import Path

from ..parcel_context import readonly
from . import COUNTY, FEATURES, NOTICE, TARGET, digest, feature_values, label_value, read_json, utcnow, write_json


def audit(database, inputs, boundary, inspection=None):
    database, inputs, boundary = Path(database), Path(inputs), Path(boundary)
    required = [database, database.with_suffix(database.suffix+".manifest.json"), inputs/"manifest.json",
                inputs/"parcel-inputs.sqlite3", boundary]
    if inspection:
        required.extend([Path(inspection)/"manifest.json", Path(inspection)/"inspection.sqlite3"])
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        return {"status": "missing", "missing": missing, "training_ready": False}
    parent, db_manifest = read_json(inputs/"manifest.json"), read_json(required[1])
    county = read_json(boundary)
    if (parent.get("county_fips") != COUNTY or db_manifest.get("county_fips") != COUNTY
            or db_manifest.get("database_sha256") != digest(database)
            or len(county.get("features", [])) != 1
            or county["features"][0]["properties"].get("GEOID") != COUNTY):
        raise ValueError("County or parcel database checksum mismatch")
    expected = next(a["sha256"] for a in parent["artifacts"] if a["path"] == "parcel-inputs.sqlite3")
    if digest(inputs/"parcel-inputs.sqlite3") != expected:
        raise ValueError("Descriptive input checksum mismatch")
    with closing(readonly(database)) as source, closing(readonly(inputs/"parcel-inputs.sqlite3")) as records:
        meta = {k: json.loads(v) for k, v in source.execute("SELECT key,value FROM metadata")}
        provenance = meta["source_provenance"]
        if (meta.get("county_fips") != COUNTY or meta.get("h3_resolutions") != [4, 5, 6, 7]
                or provenance.get("crs") != "EPSG:4326" or provenance.get("units") != "degrees"
                or provenance["output_sha256"] != parent["sources"]["parcels"]["output_sha256"]
                or provenance["county_boundary"]["sha256"] != digest(boundary)
                or parent["sources"]["boundary_sha256"] != digest(boundary)
                or parent["terrain"].get("units") not in ("m", "meters")
                or parent["terrain"].get("vertical_datum") != "North American Vertical Datum of 1988"
                or parent.get("hydrography", {}).get("units") not in (None, "meters")):
            raise ValueError("Incompatible inventory/boundary/terrain references")
        ids = {r[0] for r in source.execute("SELECT parcel_id FROM parcels")}
        seen, counts = set(), Counter()
        for identifier, county_id, raw in records.execute("SELECT parcel_id,county_fips,inputs_json FROM parcel_inputs"):
            record = json.loads(raw)
            if (identifier in seen or identifier not in ids or county_id != COUNTY
                    or record.get("parcel_id") != identifier or record.get("county_fips") != COUNTY
                    or record.get("risk_score") is not None):
                raise ValueError("Wrong, duplicate or out-of-inventory descriptive input")
            seen.add(identifier)
            features, reasons = feature_values(record)
            counts.update(reasons)
            counts["feature_eligible"] += features is not None
            counts["label_eligible"] += features is not None and label_value(record) is not None
        if ids != seen:
            raise ValueError("Descriptive inventory is incomplete")
    result = {"status": "verified", "training_ready": counts["label_eligible"] > 0,
              "inventory_id": provenance["output_sha256"], "boundary_version": digest(boundary),
              "parcel_count": len(ids), "coverage": dict(counts), "features": FEATURES, "target": TARGET,
              "sources": parent["sources"], "provenance": {k: parent[k] for k in ("terrain", "fema", "hydrography")},
              "checksums": {"database": digest(database), "inputs": expected, "boundary": digest(boundary),
                            "inputs_manifest": digest(inputs/"manifest.json")},
              "units": {"terrain_elevation": "meters NAVD88", "parcel_area": "square meters",
                        "mapped_stream_distance": "meters",
                        "manifest_terrain_units": parent["terrain"]["units"],
                        "transformations": ["log1p(area_m2)", "log1p(distance_m)"]},
              "notice": NOTICE}
    if inspection:
        manifest = read_json(Path(inspection)/"manifest.json")
        if (manifest.get("county_fips") != COUNTY or manifest.get("inventory_id") != result["inventory_id"]
                or manifest.get("boundary_version") != result["boundary_version"]
                or manifest.get("database_sha256") != digest(Path(inspection)/"inspection.sqlite3")
                or manifest.get("cell_index_version") != meta.get("cell_index_sha256")
                or manifest.get("parent_manifest_sha256") != digest(inputs/"manifest.json")):
            raise ValueError("Inspection provenance mismatch")
        result["inspection_sha256"] = manifest["database_sha256"]
    return result


def block_splits(blocks):
    ordered = sorted(set(blocks), key=lambda b: hashlib.sha256(("42:"+b).encode()).hexdigest())
    if len(ordered) < 10:
        raise ValueError("At least ten occupied 10 km blocks required for spatial evaluation")
    n = len(ordered)
    a, b = math.floor(.7*n), math.floor(.85*n)
    return {block: "development" if i < a else "validation" if i < b else "test"
            for i, block in enumerate(ordered)}


def prepare(database, inputs, boundary, output):
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    from shapely.strtree import STRtree

    report = audit(database, inputs, boundary)
    if report["status"] != "verified" or not report["training_ready"]:
        raise ValueError("Input audit failed: " + json.dumps(report))
    county = shape(read_json(boundary)["features"][0]["geometry"])
    if not county.is_valid or county.is_empty:
        raise ValueError("Invalid authoritative county polygon")
    project = Transformer.from_crs("EPSG:4326", "EPSG:26916", always_xy=True)
    rows, geometries = [], []
    with closing(readonly(database)) as source, closing(readonly(Path(inputs)/"parcel-inputs.sqlite3")) as descriptions:
        for identifier, compressed in source.execute("SELECT parcel_id,feature_z FROM parcels ORDER BY parcel_id"):
            geom = shape(json.loads(zlib.decompress(compressed))["geometry"])
            raw = descriptions.execute("SELECT inputs_json FROM parcel_inputs WHERE parcel_id=?", (identifier,)).fetchone()
            record = json.loads(raw[0])
            values, reasons = feature_values(record)
            projected, point = None, None
            if not geom.is_valid or geom.is_empty:
                reasons.append("invalid_source_geometry")
            elif not county.covers(geom):
                # A correct supplied FIPS/hash does not replace actual polygon containment.
                raise ValueError("Parcel outside authoritative county polygon")
            else:
                projected = transform(project.transform, geom)
                point = projected.representative_point()
            block = f"{math.floor(point.x/10000)}:{math.floor(point.y/10000)}" if point else None
            rows.append({"parcel_id": identifier, "features": values if not reasons else None,
                         "target": label_value(record) if not reasons else None, "block": block,
                         "x": point.x if point else None, "y": point.y if point else None,
                         "missing": reasons})
            geometries.append(projected)
    assignments = block_splits(r["block"] for r in rows if r["target"] is not None)
    holdout = [g for r, g in zip(rows, geometries) if g is not None
               and assignments.get(r["block"]) in ("validation", "test")]
    index = STRtree(holdout)
    exclusions = Counter()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with closing(sqlite3.connect(output/"dataset.sqlite3")) as db:
        db.execute("CREATE TABLE samples(parcel_id INTEGER PRIMARY KEY, block TEXT, split TEXT, target REAL, row_json TEXT)")
        for row, geom in zip(rows, geometries):
            split = assignments.get(row["block"], "unlabeled") if row["target"] is not None else "unlabeled"
            if split == "development" and len(index.query(geom, predicate="dwithin", distance=1000)):
                split = "buffer_excluded"
            row["split"] = split
            exclusions.update(row["missing"])
            if row["target"] is None:
                exclusions["label_unavailable"] += 1
            db.execute("INSERT INTO samples VALUES (?,?,?,?,?)",
                       (row["parcel_id"], row["block"], split, row["target"], json.dumps(row, allow_nan=False)))
        db.commit()
    manifest = {**report, "schema_version": 1, "county_fips": COUNTY, "prepared_at": utcnow(),
                "dataset_id": digest(output/"dataset.sqlite3"), "assignments": assignments,
                "splits": dict(Counter(r["split"] for r in rows)), "exclusions": dict(exclusions),
                "spatial_policy": {"crs": "EPSG:26916", "block_m": 10000, "buffer_m": 1000, "seed": 42}}
    write_json(output/"manifest.json", manifest)
    return manifest


def load_dataset(directory):
    root = Path(directory)
    manifest = read_json(root/"manifest.json")
    if (manifest.get("schema_version") != 1 or manifest.get("county_fips") != COUNTY
            or manifest.get("features") != FEATURES or manifest.get("target") != TARGET
            or manifest.get("dataset_id") != digest(root/"dataset.sqlite3")):
        raise ValueError("Training dataset checksum/schema mismatch")
    return root/"dataset.sqlite3", manifest


def samples(database, split=None):
    with closing(readonly(database)) as db:
        query = "SELECT row_json FROM samples" + (" WHERE split=?" if split else "") + " ORDER BY parcel_id"
        for (raw,) in db.execute(query, (split,) if split else ()):
            yield json.loads(raw)
