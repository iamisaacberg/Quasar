"""Explicit offline preparation. GIS imports stay out of the application runtime."""
import json
import sqlite3
import subprocess
import zlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .parcel_context import digest, readonly


def prepare(database, inputs, boundary, weather, output):
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    from shapely.strtree import STRtree
    from .adapters.county_weather import validate

    database, inputs, boundary, output = map(Path, (database, inputs, boundary, output))
    parent = json.loads((inputs / "manifest.json").read_text())
    input_db = inputs / "parcel-inputs.sqlite3"
    expected = next(a["sha256"] for a in parent["artifacts"] if a["path"] == input_db.name)
    if parent.get("county_fips") != "12091" or digest(input_db) != expected:
        raise ValueError("Completed input artifact checksum/county mismatch")
    db_manifest = json.loads(database.with_suffix(database.suffix + ".manifest.json").read_text())
    if db_manifest.get("county_fips") != "12091" or digest(database) != db_manifest["database_sha256"]:
        raise ValueError("Parcel database checksum/county mismatch")
    county_data = json.loads(boundary.read_text())
    if (len(county_data.get("features", [])) != 1
            or county_data["features"][0]["properties"].get("GEOID") != "12091"):
        raise ValueError("Authoritative Okaloosa boundary required")
    county = shape(county_data["features"][0]["geometry"])
    if not county.is_valid or county.is_empty:
        raise ValueError("Invalid county geometry")
    with closing(readonly(database)) as source, closing(readonly(input_db)) as records:
        meta = {k: json.loads(v) for k, v in source.execute("SELECT key,value FROM metadata")}
        provenance = meta["source_provenance"]
        if (meta.get("county_fips") != "12091" or meta.get("h3_resolutions") != [4, 5, 6, 7]
                or provenance["output_sha256"] != parent["sources"]["parcels"]["output_sha256"]
                or digest(boundary) != provenance["county_boundary"]["sha256"]
                or digest(boundary) != parent["sources"]["boundary_sha256"]):
            raise ValueError("Input artifact, parcel inventory and boundary are incompatible")
        count = source.execute("SELECT count(*) FROM parcels").fetchone()[0]
        if records.execute("SELECT count(*) FROM parcel_inputs").fetchone()[0] != count:
            raise ValueError("Descriptive input inventory is incomplete")
        # Generate H3 geometry with the already pinned JS library, not a new Python GIS dependency.
        cells = list(source.execute("SELECT cell_id,resolution FROM county_cells ORDER BY cell_id"))
        js = "const h3=require('h3-js');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s).map(id=>({id,geometry:{type:'Polygon',coordinates:[h3.cellToBoundary(id,true)]}})))));"
        cell_geometries = json.loads(subprocess.run(["node", "-e", js], input=json.dumps([c[0] for c in cells]),
                                                   text=True, capture_output=True, check=True).stdout)
        native, weather_sources = {}, []
        for filename in weather:
            snapshot = json.loads(Path(filename).read_text())
            validate(snapshot)
            if snapshot["county_geometry"] != county_data["features"][0]["geometry"]:
                raise ValueError("Forecast county geometry differs from the authoritative input")
            weather_sources.append({"sha256": digest(filename), "source_table": snapshot["source_table"],
                                    "retrieved_at": snapshot["retrieved_at"], "license": snapshot["license"],
                                    "native_resolution": snapshot["native_resolution"], "units": snapshot["units"]})
            for cell in snapshot["native_cells"]:
                if cell["id"] in native and native[cell["id"]] != cell:
                    raise ValueError("Conflicting native geometry")
                native[cell["id"]] = cell
        project = Transformer.from_crs("EPSG:4326", "EPSG:26916", always_xy=True)
        native_values = list(native.values())
        native_shapes = [transform(project.transform, shape(c["geometry"])) for c in native_values]
        tree = STRtree(native_shapes)
        for i, geom in enumerate(native_shapes):
            for j in tree.query(geom):
                if int(j) > i and geom.intersection(native_shapes[int(j)]).area > .001:
                    raise ValueError("Native forecast cells overlap in area; parcel rainfall would be ambiguous")

        def overlaps(geometry):
            if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
                return []
            projected = transform(project.transform, geometry)
            result = []
            for index in tree.query(projected):
                area = projected.intersection(native_shapes[int(index)]).area
                if area > 0:
                    cell = native_values[int(index)]
                    result.append({"native_cell_id": cell["id"], "geometry": cell["geometry"],
                                   "area_fraction": min(1, area / projected.area)})
            return sorted(result, key=lambda c: c["native_cell_id"])

        output.mkdir(parents=True, exist_ok=False)
        target = output / "inspection.sqlite3"
        with closing(sqlite3.connect(target)) as destination:
            destination.execute("CREATE TABLE inspection (kind TEXT, identifier TEXT, context_json TEXT NOT NULL, PRIMARY KEY(kind,identifier)) WITHOUT ROWID")
            for parcel_id, feature_z in source.execute("SELECT parcel_id,feature_z FROM parcels ORDER BY parcel_id"):
                row = records.execute("SELECT county_fips,inputs_json FROM parcel_inputs WHERE parcel_id=?", (parcel_id,)).fetchone()
                if row is None or row[0] != "12091":
                    raise ValueError("Missing/wrong-county parcel input")
                inputs_record = json.loads(row[1])
                if (inputs_record.get("parcel_id") != parcel_id or inputs_record.get("county_fips") != "12091"
                        or inputs_record.get("risk_score") is not None):
                    raise ValueError("Invalid descriptive record identity/score")
                geom = shape(json.loads(zlib.decompress(feature_z))["geometry"])
                if geom.is_valid and not county.covers(geom):
                    raise ValueError("Source parcel is outside exact county geometry")
                payload = {"county_fips": "12091", "parcel_id": parcel_id, "risk_score": None,
                           "inputs": inputs_record, "forecast_overlaps": overlaps(geom)}
                destination.execute("INSERT INTO inspection VALUES ('parcel',?,?)", (str(parcel_id), json.dumps(payload, allow_nan=False)))
            # Query the indexed memberships directly. Never sum overlapping child counts.
            source.execute("ATTACH DATABASE ? AS descriptive", (input_db.resolve().as_uri() + "?mode=ro",))
            for (cell, resolution), geometry in zip(cells, cell_geometries):
                total, terrain, fema, partial = source.execute("""
                    SELECT count(DISTINCT cp.parcel_id),
                           count(DISTINCT CASE WHEN json_extract(pi.inputs_json,'$.terrain.status')='complete' THEN cp.parcel_id END),
                           count(DISTINCT CASE WHEN json_extract(pi.inputs_json,'$.fema.status')='complete' THEN cp.parcel_id END),
                           count(DISTINCT CASE WHEN json_extract(pi.inputs_json,'$.fema.status')='partial' THEN cp.parcel_id END)
                    FROM cell_parcels cp LEFT JOIN descriptive.parcel_inputs pi USING(parcel_id) WHERE cp.cell_id=?
                """, (cell,)).fetchone()
                geom = shape(geometry["geometry"])
                payload = {"county_fips": "12091", "cell_id": cell, "resolution": resolution,
                           "risk_score": None, "parcel_count": total, "terrain_complete_count": terrain,
                           "fema_complete_count": fema, "fema_partial_count": partial,
                           "forecast_overlaps": overlaps(geom.intersection(county)),
                           "notice": "Distinct indexed parcels, not homes; memberships can overlap adjacent cells. Coarse memberships follow indexed R7 ancestors. H3 does not sharpen forecasts."}
                destination.execute("INSERT INTO inspection VALUES ('cell',?,?)", (cell, json.dumps(payload, allow_nan=False)))
            destination.commit()
    manifest = {"schema_version": 1, "county_fips": "12091", "inventory_id": provenance["output_sha256"],
                "cell_index_version": meta["cell_index_sha256"], "boundary_version": digest(boundary),
                "prepared_at": datetime.now(timezone.utc).isoformat(), "database_sha256": digest(target),
                "parent_manifest_sha256": digest(inputs / "manifest.json"), "parcel_count": count,
                "provenance": {"terrain": parent["terrain"], "fema": parent["fema"], "hydrography": parent["hydrography"],
                               "sources": parent["sources"], "weather": weather_sources,
                               "analysis_crs": "EPSG:26916", "units": "meters; overlap fractions are dimensionless",
                               "processing": "Verified completed inputs copied unchanged; exact county validation; positive-area native overlaps; distinct indexed parcel counts. No scores."}}
    # Completion marker is last. An interrupted directory cannot be served.
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return manifest
