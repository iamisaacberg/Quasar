"""Explicit offline preparation and read-only indexed exposure serving.

No import, training, inference or cloud query runs on a serving request.
"""
import argparse
import hashlib
import json
import os
import platform
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .config import COUNTY_FIPS


def encoded(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def connect(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def prepare(inventory, artifacts, output):
    """Validate every source, compare stored results, then atomically publish."""
    from .exposure import _artifact, _aggregate, timestamp
    inventory, output = Path(inventory), Path(output)
    sources = sorted(Path(artifacts).glob("*.json")) if Path(artifacts).is_dir() else [Path(artifacts)]
    if not sources:
        raise ValueError("No assessment artifacts found")
    if output.resolve() == inventory.resolve() or any(output.resolve() == p.resolve() for p in sources):
        raise ValueError("Output must not replace a source")
    inventory_stat = inventory.stat()
    source_stats = {path: (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ino) for path in sources}
    with closing(connect(inventory)) as source:
        metadata = {k: json.loads(v) for k, v in source.execute("SELECT key,value FROM metadata")}
    if metadata.get("county_fips") != COUNTY_FIPS or not metadata.get("source_provenance", {}).get("county_boundary"):
        raise ValueError("A county-validated Okaloosa inventory is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
    os.close(fd)
    windows = 0
    try:
        with closing(sqlite3.connect(temporary)) as destination:
            destination.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE summaries(start TEXT,end TEXT,resolution INTEGER,payload TEXT NOT NULL,
                    PRIMARY KEY(start,end,resolution));
                CREATE TABLE assessments(start TEXT,end TEXT,parcel_id INTEGER,payload TEXT NOT NULL,
                    PRIMARY KEY(start,end,parcel_id));
            """)
            receipts = []
            for path in sources:
                stat = path.stat()
                data = _artifact(str(path), stat.st_size, stat.st_mtime_ns)
                receipts.append({"source_identifier": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                for (start, end), window in data["windows"].items():
                    # UTC canonical keys accept equivalent timezone spellings.
                    keys = (start.isoformat(), end.isoformat())
                    if timestamp(window["computed_at"]) > datetime.now(timezone.utc):
                        raise ValueError("Assessment computation time is in the future")
                    for resolution in range(4, 8):
                        result = _aggregate(str(inventory), inventory_stat.st_size, inventory_stat.st_mtime_ns,
                                            str(path), stat.st_size, stat.st_mtime_ns, start, end, resolution)
                        destination.execute("INSERT INTO summaries VALUES(?,?,?,?)", (*keys, resolution, encoded(result)))
                        stored = json.loads(destination.execute("SELECT payload FROM summaries WHERE start=? AND end=? AND resolution=?",
                                                                (*keys, resolution)).fetchone()[0])
                        if stored != result:
                            raise ValueError("Prepared summary parity failed")
                    destination.executemany("INSERT INTO assessments VALUES(?,?,?,?)", (
                        (*keys, identifier, encoded(record)) for identifier, record in window["records"].items()))
                    for identifier, payload in destination.execute("SELECT parcel_id,payload FROM assessments WHERE start=? AND end=?", keys):
                        if json.loads(payload) != window["records"][identifier]:
                            raise ValueError("Prepared assessment parity failed")
                    windows += 1
                # Do not retain county-sized records for previous hours.
                _artifact.cache_clear()
            if not windows:
                raise ValueError("No assessment windows found")
            final_stat = inventory.stat()
            if (final_stat.st_size, final_stat.st_mtime_ns, final_stat.st_ino) != (inventory_stat.st_size, inventory_stat.st_mtime_ns, inventory_stat.st_ino):
                raise ValueError("Inventory changed during preparation")
            if any((path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ino) != source_stats[path] for path in sources):
                raise ValueError("Assessment sources changed during preparation")
            destination.executemany("INSERT INTO metadata VALUES(?,?)", [
                ("schema_version", "1"), ("complete", "true"), ("county_fips", encoded(COUNTY_FIPS)),
                ("source_provenance", encoded(metadata["source_provenance"])),
                ("sources", encoded(receipts)), ("windows", str(windows)),
                ("prepared_at", encoded(datetime.now(timezone.utc).isoformat())),
                ("processing", encoded("Validated schema-1 assessments; exact parcel_p90_linear R4-R7 summaries; indexed unchanged records"))])
            destination.commit()
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Prepared database integrity check failed")
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"windows": windows, "output": str(output)}


@lru_cache(maxsize=4)
def _verified(path, signature, inventory, inventory_signature):
    with closing(connect(path)) as connection, closing(connect(inventory)) as source:
        metadata = {k: json.loads(v) for k, v in connection.execute("SELECT key,value FROM metadata")}
        current = {k: json.loads(v) for k, v in source.execute("SELECT key,value FROM metadata")}
        if (metadata.get("schema_version") != 1 or metadata.get("complete") is not True
                or metadata.get("county_fips") != COUNTY_FIPS or current.get("county_fips") != COUNTY_FIPS
                or not current.get("source_provenance", {}).get("county_boundary")
                or metadata.get("source_provenance") != current.get("source_provenance")
                or connection.execute("PRAGMA quick_check").fetchone()[0] != "ok"):
            raise ValueError("Prepared exposure database does not match the county inventory")
        return metadata


def read(path, inventory, start, end, resolution, ids):
    def signature(file):
        stat = Path(file).stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    _verified(path, signature(path), inventory, signature(inventory))
    keys = (start.isoformat(), end.isoformat())
    with closing(connect(path)) as connection:
        row = connection.execute("SELECT payload FROM summaries WHERE start=? AND end=? AND resolution=?",
                                 (*keys, resolution)).fetchone()
        if row is None:
            return None, {}
        result = json.loads(row[0])
        result["aggregation_architecture"] = platform.machine()
        records = {}
        if ids:
            placeholders = ",".join("?" for _ in ids)
            records = {identifier: json.loads(payload) for identifier, payload in connection.execute(
                f"SELECT parcel_id,payload FROM assessments WHERE start=? AND end=? AND parcel_id IN ({placeholders})", (*keys, *ids))}
    return result, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--assessments", type=Path, required=True, help="One schema-1 JSON file or a directory of hourly files")
    parser.add_argument("--output", type=Path, default=Path("data/processed/exposure-serving.sqlite3"))
    args = parser.parse_args()
    try:
        print(encoded(prepare(args.inventory, args.assessments, args.output)))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, f"Exposure preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
