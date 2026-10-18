"""Offline research and portable inference. No optional dependencies at import time."""
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

COUNTY = "12091"
FEATURES = ["terrain_min_m", "terrain_mean_m", "terrain_max_m", "terrain_relief_m",
            "log_area_m2", "log_mapped_stream_distance_m"]
TARGET = "FEMA SFHA fraction of parcel area (mapping proxy, not observed flooding)"
POLICY = "susceptibility-rainfall-stress-v1"
NOTICE = ("Experimental relative exposure. Trained against FEMA mapping, not flood outcomes. "
          "Not flood depth, probability, or safety guidance. Mapped streams have incomplete coverage.")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path, limit=128 * 1024 * 1024):
    if Path(path).stat().st_size > limit:
        raise ValueError("Artifact exceeds size limit")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def write_json(path, value):
    """Atomic replacement, including on failed serialization; never publish partial data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as out:
            name = out.name
            json.dump(value, out, allow_nan=False, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def feature_values(record):
    """Never include FEMA, identity, location, coverage flags or invented gauge inputs."""
    missing = []
    terrain = record.get("terrain", {})
    values = [terrain.get(key) for key in ("min_m", "mean_m", "max_m")]
    if (record.get("geometry_status") != "valid" or record.get("county_fips") != COUNTY):
        missing.append("invalid_county_geometry")
    if (terrain.get("status") != "complete" or terrain.get("units") != "m"
            or terrain.get("vertical_datum") != "NAVD88" or not all(finite(v) for v in values)
            or (all(finite(v) for v in values) and not values[0] <= values[1] <= values[2])):
        missing.append("complete_terrain_required")
    area = record.get("area_m2")
    if not finite(area) or area <= 0:
        missing.append("parcel_area")
    hydro = record.get("hydrography", {})
    distance = hydro.get("nearest_retained_river_stream_distance_m")
    if (hydro.get("status") not in ("complete", "partial_reference_coverage")
            or not finite(distance) or distance < 0):
        missing.append("mapped_stream_distance")
    if missing:
        return None, missing
    low, mean, high = values
    return [low, mean, high, high-low, math.log1p(area), math.log1p(distance)], []


def label_value(record):
    fema = record.get("fema", {})
    value = fema.get("sfha_mapped_area_fraction")
    mapped = fema.get("mapped_area_fraction")
    if (fema.get("status") != "complete" or not finite(mapped) or not .999999 <= mapped <= 1
            or fema.get("sfha_reference_status") == "conflicting_source_flags"
            or not finite(value) or not 0 <= value <= 1):
        return None
    return value
