"""Read-only, dependency-free inspection of verified descriptive parcel inputs."""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from .parcels import SourceUnavailable


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def readonly(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.execute("PRAGMA query_only=ON")
    return connection


def inventory_metadata():
    database = os.environ.get("QUASAR_PARCEL_DATABASE")
    if not database:
        raise SourceUnavailable("Indexed parcel inventory is not configured.")
    try:
        with closing(readonly(database)) as connection:
            meta = {k: json.loads(v) for k, v in connection.execute("SELECT key,value FROM metadata")}
        if meta["county_fips"] != "12091" or meta["h3_resolutions"] != [4, 5, 6, 7]:
            raise ValueError("Wrong county/index")
        source = meta["source_provenance"]
        if (not all(isinstance(value, str) and value for value in (
                source["output_sha256"], source["county_boundary"]["sha256"], meta["cell_index_sha256"],
                source["source_url"], source["retrieved_at"]))):
            raise ValueError("Missing provenance")
        return meta
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        raise SourceUnavailable("Indexed parcel provenance is unavailable or incompatible.") from exc


@lru_cache(maxsize=4)
def _verified(directory, manifest_stat, database_stat):
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text())
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("county_fips") != "12091"
            or not all(isinstance(manifest.get(key), str) and manifest[key] for key in (
                "inventory_id", "boundary_version", "cell_index_version", "prepared_at", "database_sha256"))
            or not isinstance(manifest.get("provenance"), dict)
            or manifest.get("database_sha256") != digest(root / "inspection.sqlite3")):
        raise ValueError("Inspection artifact checksum/county mismatch")
    return manifest


def artifact():
    directory = os.environ.get("QUASAR_PARCEL_CONTEXT_DIRECTORY", "")
    if not directory:
        raise SourceUnavailable("Prepared parcel inputs are not configured; inputs remain unknown.")
    try:
        root = Path(directory).resolve()
        def stamp(path):
            stat = path.stat()
            return (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        manifest = _verified(str(root), stamp(root / "manifest.json"), stamp(root / "inspection.sqlite3"))
        meta = inventory_metadata()
        source = meta["source_provenance"]
        if (manifest["inventory_id"] != source["output_sha256"]
                or manifest["boundary_version"] != source["county_boundary"]["sha256"]
                or manifest["cell_index_version"] != meta["cell_index_sha256"]):
            raise ValueError("Inspection artifact and parcel inventory differ")
        return root / "inspection.sqlite3", manifest
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        raise SourceUnavailable("Prepared parcel inputs failed provenance/checksum validation; inputs remain unknown.") from exc


def inspection(kind, identifier, inventory_id=None):
    if kind == "parcel":
        if not re.fullmatch(r"[0-9]{1,16}", str(identifier)):
            raise ValueError("Invalid parcel ID")
        identifier = str(int(identifier))
    elif kind == "cell":
        if not re.fullmatch(r"8[4-7][0-9a-f]{13}", str(identifier)):
            raise ValueError("An H3 cell at resolution 4 through 7 is required")
    else:
        raise ValueError("Unknown inspection type")
    path, manifest = artifact()
    if inventory_id is not None and inventory_id != manifest["inventory_id"]:
        raise SourceUnavailable("Parcel inventory changed; refresh this cell.")
    try:
        with closing(readonly(path)) as connection:
            row = connection.execute("SELECT context_json FROM inspection WHERE kind=? AND identifier=?",
                                     (kind, identifier)).fetchone()
        if row is None:
            raise ValueError("Identifier is outside the prepared county inventory")
        context = json.loads(row[0])
        if (not isinstance(context, dict) or context.get("county_fips") != "12091" or context.get("risk_score") is not None
                or (context.get("parcel_id") if kind == "parcel" else context.get("cell_id"))
                != (int(identifier) if kind == "parcel" else identifier)):
            raise SourceUnavailable("Invalid prepared context; inputs remain unknown.")
        return {**context, "status": "ready", "risk_score": None, "risk_band": "unknown",
                "inventory_id": manifest["inventory_id"], "artifact_version": manifest["database_sha256"],
                "prepared_at": manifest["prepared_at"], "provenance": manifest["provenance"]}
    except (sqlite3.Error, OSError, json.JSONDecodeError) as exc:
        raise SourceUnavailable("Prepared parcel inputs could not be read; inputs remain unknown.") from exc
