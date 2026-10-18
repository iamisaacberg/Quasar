"""Explicit offline preparation and read-only indexed exposure serving.

No import, training, inference or cloud query runs on a serving request.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import tempfile
from threading import RLock
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .config import COUNTY_FIPS
from .bridge import file_version
from .timing import phase

_verification_lock = RLock()


def encoded(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def connect(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def preparation_sources(artifacts, manifest=None):
    root = Path(artifacts).resolve()
    if manifest:
        receipt = json.loads(Path(manifest).read_text())
        if receipt.get("status") != "verified" or not isinstance(receipt.get("windows"), list):
            raise ValueError("A verified producer replay manifest is required")
        sources = {}
        for entry in receipt["windows"]:
            path = Path(entry["artifact"])
            path = (root / path).resolve() if not path.is_absolute() else path.resolve()
            if (not path.is_relative_to(root) or path in sources
                    or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", ""))):
                raise ValueError("Invalid producer manifest path, checksum or duplicate")
            sources[path] = entry
        return sources
    # Replay directories also contain producer *.benchmark.json sidecars.
    paths = sorted(root.glob("[0-9]??????????????Z.json")) if root.is_dir() else [root]
    if root.is_dir() and not paths:
        paths = [p for p in sorted(root.glob("*.json")) if not p.name.endswith(".benchmark.json")]
    return {path: None for path in paths}


def preflight(inventory, artifacts, output, manifest=None):
    sources = preparation_sources(artifacts, manifest)
    if not sources:
        raise ValueError("No assessment artifacts found")
    parent = Path(output).resolve().parent
    while not parent.exists():
        parent = parent.parent
    # SQLite rows/indexes and temporary journal overhead, plus a 1 GiB reserve.
    estimate = sum(path.stat().st_size for path in sources) * 3
    if shutil.disk_usage(parent).free < estimate + 1024 ** 3:
        raise ValueError("Insufficient disk for preparation plus 1 GiB reserve")
    return {"source_files": len(sources), "estimated_bytes": estimate, "reserve_bytes": 1024 ** 3}


def prepare(inventory, artifacts, output, manifest=None, progress=None):
    """Validate every source, compare stored results, then atomically publish."""
    from .exposure import _artifact, _aggregate, timestamp, model_context
    from .exposure_catalog import version
    inventory, output = Path(inventory), Path(output)
    sources = preparation_sources(artifacts, manifest)
    preflight(inventory, artifacts, output, manifest)
    if output.resolve() == inventory.resolve() or any(output.resolve() == p.resolve() for p in sources):
        raise ValueError("Output must not replace a source")
    if manifest and output.resolve() == Path(manifest).resolve():
        raise ValueError("Output must not replace the producer manifest")
    manifest_version = file_version(manifest) if manifest else None
    manifest_digest = digest(manifest) if manifest else None
    inventory_stat = inventory.stat()
    inventory_version = file_version(inventory)
    source_stats = {path: file_version(path) for path in sources}
    with closing(connect(inventory)) as source:
        metadata = {k: json.loads(v) for k, v in source.execute("SELECT key,value FROM metadata")}
        inventory_count = source.execute("SELECT count(*) FROM parcels").fetchone()[0]
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
            identity = None
            for path, receipt in sources.items():
                stat = path.stat()
                revision = version(path)
                sha256 = digest(path)
                if receipt and sha256 != receipt["sha256"]:
                    raise ValueError("Assessment producer checksum mismatch")
                _artifact.cache_clear()
                data = _artifact(str(path), stat.st_size, stat.st_mtime_ns, revision, sha256)
                if not data["windows"] or (receipt and len(data["windows"]) != 1):
                    raise ValueError("Each producer artifact must contain its declared window")
                context = model_context(data)
                current_identity = (data["inventory_id"], data["method_version"], context.get("model_metadata"),
                                    context.get("forecast_provenance", {}).get("source_sha256"))
                if identity is not None and current_identity != identity:
                    raise ValueError("Assessment model/inventory identities differ across windows")
                identity = current_identity
                receipts.append({"source_identifier": path.name, "sha256": sha256})
                for (start, end), window in data["windows"].items():
                    if receipt and (timestamp(receipt["from"]) != start or len(window["records"]) != inventory_count):
                        raise ValueError("Producer window or complete parcel coverage mismatch")
                    # UTC canonical keys accept equivalent timezone spellings.
                    keys = (start.isoformat(), end.isoformat())
                    if timestamp(window["computed_at"]) > datetime.now(timezone.utc):
                        raise ValueError("Assessment computation time is in the future")
                    for resolution in range(4, 8):
                        result = _aggregate(str(inventory), inventory_stat.st_size, inventory_stat.st_mtime_ns,
                                            str(path), stat.st_size, stat.st_mtime_ns, start, end, resolution, revision, sha256)
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
                    if progress is not None:
                        progress(windows)
                # Do not retain county-sized records for previous hours.
                _artifact.cache_clear()
                del data, window
            if not windows:
                raise ValueError("No assessment windows found")
            if file_version(inventory) != inventory_version:
                raise ValueError("Inventory changed during preparation")
            if any(file_version(path) != source_stats[path] for path in sources):
                raise ValueError("Assessment sources changed during preparation")
            if manifest and file_version(manifest) != manifest_version:
                raise ValueError("Producer manifest changed during preparation")
            destination.executemany("INSERT INTO metadata VALUES(?,?)", [
                ("schema_version", "1"), ("complete", "true"), ("county_fips", encoded(COUNTY_FIPS)),
                ("source_provenance", encoded(metadata["source_provenance"])),
                ("sources", encoded(receipts)), ("windows", str(windows)),
                ("producer_manifest_sha256", encoded(manifest_digest)),
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
    # lru_cache alone does not coalesce concurrent cache misses.
    with phase("source"), _verification_lock:
        before, inventory_before = file_version(path), file_version(inventory)
        _verified(path, before, inventory, inventory_before)
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
    if file_version(path) != before or file_version(inventory) != inventory_before:
        raise ValueError("Serving inputs changed during reading")
    return result, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--assessments", type=Path, required=True, help="One schema-1 JSON file or a directory of hourly files")
    parser.add_argument("--output", type=Path, default=Path("data/processed/exposure-serving.sqlite3"))
    parser.add_argument("--manifest", type=Path, help="Verified producer replay manifest with original checksums")
    parser.add_argument("--dry-run", action="store_true", help="Check source paths/disk budget without writing")
    args = parser.parse_args()
    try:
        result = (preflight(args.inventory, args.assessments, args.output, args.manifest) if args.dry_run else
                  prepare(args.inventory, args.assessments, args.output, args.manifest))
        print(encoded(result))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, f"Exposure preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
