"""Build a low-memory SQLite parcel/cell store for IBM Z LinuxONE.

The database stores each minimal parcel geometry once and a compact index from
every intersecting county H3 resolution-7 cell to its parcels. Runtime queries
need only Python's standard-library sqlite3 and zlib modules.
"""

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARCELS = ROOT / "data/raw/okaloosa_parcels_wgs84.geojsonl.gz"
DEFAULT_SOURCE_MANIFEST = ROOT / "data/raw/okaloosa_parcels_wgs84.manifest.json"
DEFAULT_MAP = ROOT / "data/processed/okaloosa/linuxone/parcel-cell-index.tsv.gz"
DEFAULT_CELLS = ROOT / "data/processed/okaloosa/linuxone/county-cells.json"
DEFAULT_OUTPUT = ROOT / "data/processed/okaloosa/linuxone/quasar-parcels.sqlite3"


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parcels", type=Path, default=DEFAULT_PARCELS)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--cell-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--cells", type=Path, default=DEFAULT_CELLS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    for path in (args.parcels, args.source_manifest, args.cell_map, args.cells):
        if not path.exists():
            raise SystemExit(f"Required input is missing: {path}")

    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    if (source_manifest.get("county_fips") != "12091"
            or source_manifest.get("county_validated_count") != source_manifest.get("source_count") - source_manifest.get("excluded_count")
            or source_manifest.get("output_sha256") != digest_file(args.parcels)):
        raise SystemExit("Source provenance does not match the county parcel snapshot")

    cells_metadata = json.loads(args.cells.read_text(encoding="utf-8"))
    if cells_metadata.get("county_fips") != "12091" or cells_metadata.get("h3_resolutions") != [4, 5, 6, 7]:
        raise SystemExit("Expected the Okaloosa H3 resolution 4-7 cell index")
    cells_by_resolution = cells_metadata.get("cells_by_resolution")
    expected_count = cells_metadata.get("source_count")
    if (not isinstance(cells_by_resolution, dict) or any(
            not isinstance(cells_by_resolution.get(str(resolution)), list) or not cells_by_resolution[str(resolution)]
            for resolution in (4, 5, 6, 7)) or type(expected_count) is not int):
        raise SystemExit("Cell index metadata is incomplete")
    cells = [(cell, resolution) for resolution in (4, 5, 6, 7)
             for cell in cells_by_resolution[str(resolution)]]

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    parcel_count = membership_count = 0
    try:
        connection.execute("PRAGMA page_size=4096")
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA cache_size=-65536")
        connection.executescript("""
            CREATE TABLE parcels (
                parcel_id INTEGER PRIMARY KEY,
                feature_z BLOB NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE county_cells (
                cell_id TEXT PRIMARY KEY,
                resolution INTEGER NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE cell_parcels (
                cell_id TEXT NOT NULL,
                parcel_id INTEGER NOT NULL,
                PRIMARY KEY (cell_id, parcel_id),
                FOREIGN KEY (cell_id) REFERENCES county_cells(cell_id),
                FOREIGN KEY (parcel_id) REFERENCES parcels(parcel_id)
            ) WITHOUT ROWID;
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
        """)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executemany("INSERT INTO county_cells(cell_id,resolution) VALUES (?,?)", cells)
        connection.commit()

        with gzip.open(args.parcels, "rt", encoding="utf-8") as source:
            batch = []
            for line in source:
                if not line.strip():
                    continue
                feature = json.loads(line)
                parcel_id = feature.get("properties", {}).get("parcel_id", feature.get("id"))
                if (type(parcel_id) is not int or feature.get("properties", {}).get("county_fips") != "12091"
                        or feature.get("properties", {}).get("risk_score") is not None
                        or feature.get("properties", {}).get("risk_band") != "unknown"):
                    raise SystemExit("Parcel snapshot has invalid identity or non-unknown risk fields")
                batch.append((parcel_id, zlib.compress(json.dumps(feature, separators=(",", ":"), allow_nan=False).encode(), 6)))
                if len(batch) >= 5000:
                    connection.executemany("INSERT INTO parcels(parcel_id,feature_z) VALUES (?,?)", batch)
                    parcel_count += len(batch)
                    batch.clear()
                    connection.commit()
                    if parcel_count % 50000 == 0:
                        print(f"Loaded {parcel_count:,}/{expected_count:,} parcel geometries", flush=True)
            if batch:
                connection.executemany("INSERT INTO parcels(parcel_id,feature_z) VALUES (?,?)", batch)
                parcel_count += len(batch)
                connection.commit()
        if parcel_count != expected_count:
            raise SystemExit(f"Expected {expected_count:,} parcels, imported {parcel_count:,}")

        with gzip.open(args.cell_map, "rt", encoding="ascii") as source:
            batch = []
            for line in source:
                cell, parcel_text = line.rstrip("\n").split("\t")
                batch.append((cell, int(parcel_text)))
                if len(batch) >= 20000:
                    connection.executemany("INSERT INTO cell_parcels(cell_id,parcel_id) VALUES (?,?)", batch)
                    membership_count += len(batch)
                    batch.clear()
                    connection.commit()
                    if membership_count % 200000 == 0:
                        print(f"Loaded {membership_count:,} cell memberships", flush=True)
            if batch:
                connection.executemany("INSERT INTO cell_parcels(cell_id,parcel_id) VALUES (?,?)", batch)
                membership_count += len(batch)
                connection.commit()

        connection.execute("ANALYZE")
        meta = {
            "schema_version": 1,
            "county_fips": "12091",
            "parcel_count": parcel_count,
            "h3_resolutions": [4, 5, 6, 7],
            "county_cell_counts": {str(resolution): len(cells_by_resolution[str(resolution)]) for resolution in (4, 5, 6, 7)},
            "county_cell_count": len(cells),
            "cell_parcel_membership_count": membership_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cell_index_sha256": digest_file(args.cell_map),
            "county_cells_sha256": digest_file(args.cells),
            "storage": "SQLite WITHOUT ROWID tables; parcel GeoJSON stored once as zlib-compressed bytes; indexed by intersecting H3 cells at resolutions 4 through 7.",
            "notice": "Parcel geometries only; no parcel flood score is available; unknown must stay unknown.",
            "source_terms": source_manifest["license"],
            "source_provenance": source_manifest,
        }
        connection.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", ((key, json.dumps(value)) for key, value in meta.items()))
        connection.commit()
        connection.close()
        os.replace(temporary, output)
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise

    manifest = {
        "schema_version": 1,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "county_fips": "12091",
        "h3_resolutions": [4, 5, 6, 7],
        "county_cell_counts": {str(resolution): len(cells_by_resolution[str(resolution)]) for resolution in (4, 5, 6, 7)},
        "parcel_count": parcel_count,
        "county_cell_count": len(cells),
        "cell_parcel_membership_count": membership_count,
        "database": output.name,
        "database_bytes": output.stat().st_size,
        "database_sha256": digest_file(output),
        "parcel_snapshot_sha256": digest_file(args.parcels),
        "source_url": source_manifest["source_url"],
        "source_retrieved_at": source_manifest["retrieved_at"],
        "source_license": source_manifest["license"],
        "crs": source_manifest["crs"],
        "units": source_manifest["units"],
        "processing": source_manifest["processing"],
        "county_boundary": source_manifest["county_boundary"],
        "cell_index_sha256": digest_file(args.cell_map),
        "county_cells_sha256": digest_file(args.cells),
        "runtime_requirements": "Python standard library only: sqlite3 and zlib; open database read-only and page queries by cell_id.",
        "limitations": ["Parcel geometries are county-boundary validated and mapped to overlapping H3 cells at resolutions 4 through 7.",
                        "No flood score is available; parcel scores remain unknown.",
                        "Retain Okaloosa County GIS/Property Appraiser attribution and its no-warranty reference-data disclaimer."],
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
