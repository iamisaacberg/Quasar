"""Read explicit parcel assessments and aggregate complete county inventories.

This module does not invent a parcel scoring model. The configured assessment
artifact is separate from geometry-only risk fields. Run serving/aggregation on
LinuxONE; hosted instances proxy that service instead of recomputing its results.
"""
import json
import math
import os
import platform
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener

from .config import COUNTY_FIPS
from .parcels import SourceUnavailable, _NoRedirect

SCALE = json.loads((Path(__file__).parent / "static/exposure-scale.json").read_text())
MAX_BYTES = 128 * 1024 * 1024


def valid_score(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100


def percentile90(scores):
    """Linear interpolation at (n-1)*0.9; unknowns are excluded, never zeroed."""
    values = sorted(scores)
    if not values:
        return None
    position = (len(values) - 1) * .9
    lower = math.floor(position)
    return round(values[lower] + (values[math.ceil(position)] - values[lower]) * (position - lower), 6)


def summarize(scores):
    known = [value for value in scores if value is not None]
    total, scored = len(scores), len(known)
    return {"parcel_count": total, "scored_count": scored, "unknown_count": total - scored,
            "coverage": scored / total if total else 0,
            "incomplete": total == 0 or scored < total,
            "elevated_count": sum(value >= 65 for value in known),
            "p90_score": percentile90(known)}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Exposure timestamp must include a timezone")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Exposure timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def validate_assessment(record):
    """Enforce the same factor contract for local and proxied assessments."""
    if not isinstance(record, dict):
        raise ValueError("Invalid exposure assessment")
    score = record.get("score")
    missing, factors = record.get("missing", []), record.get("factors", [])
    if (not isinstance(missing, list) or not all(isinstance(x, str) for x in missing)
            or not isinstance(factors, list)):
        raise ValueError("Invalid exposure explanation")
    for factor in factors:
        if (not isinstance(factor, dict) or not isinstance(factor.get("name"), str)
                or not isinstance(factor.get("value"), (str, int, float, type(None)))
                or isinstance(factor.get("value"), bool)
                or (isinstance(factor.get("value"), float) and not math.isfinite(factor["value"]))
                or not valid_score(factor.get("contribution"))):
            raise ValueError("Invalid exposure factor")
    if score is not None and (not valid_score(score) or missing or not factors
            or not math.isclose(sum(f["contribution"] for f in factors), score, abs_tol=.11)):
        raise ValueError("Exposure score requires complete, matching factor contributions")
    result = {"parcel_id": record.get("parcel_id"), "score": score, "factors": factors, "missing": missing}
    if "model_details" in record:
        from .modeling.contracts import details
        result["model_details"] = details(record["model_details"], score)
    return result


def model_context(data):
    """Whitelist optional modeling context, preserving legacy schema-1 artifacts."""
    if "model_metadata" not in data and "forecast_provenance" not in data:
        return {}
    from .modeling.contracts import metadata, forecast
    return {"model_metadata": metadata(data.get("model_metadata")),
            "forecast_provenance": forecast(data.get("forecast_provenance"))}


@lru_cache(maxsize=2)
def _artifact(path, size, modified):
    if size > MAX_BYTES:
        raise ValueError("Exposure artifact exceeds its size limit")
    data = json.loads(Path(path).read_bytes())
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("county_fips") != COUNTY_FIPS
            or not all(isinstance(data.get(key), str) and data[key] for key in
                       ("run_id", "method_version", "inventory_id"))
            or not isinstance(data.get("windows"), list)):
        raise ValueError("Invalid exposure artifact identity")
    windows = {}
    context = model_context(data)
    for window in data["windows"]:
        start, end = timestamp(window["valid_from"]), timestamp(window["valid_to"])
        timestamp(window["computed_at"])
        if end - start != timedelta(hours=6) or (start, end) in windows:
            raise ValueError("Duplicate or invalid six-hour exposure window")
        records = {}
        if context and (timestamp(context["forecast_provenance"]["valid_from"]) != start
                        or timestamp(context["forecast_provenance"]["valid_to"]) != end):
            raise ValueError("Model forecast provenance/window mismatch")
        if not isinstance(window.get("parcels"), list):
            raise ValueError("Exposure parcels must be a list")
        for record in window["parcels"]:
            parcel_id, score = record.get("parcel_id"), record.get("score")
            if type(parcel_id) is not int or parcel_id < 0 or parcel_id in records:
                raise ValueError("Duplicate or invalid exposure parcel ID")
            records[parcel_id] = validate_assessment(record)
            if context and score is not None and ("model_details" not in records[parcel_id]
                    or context["forecast_provenance"]["status"] != "ready"):
                raise ValueError("Model scores require diagnostics and ready source data")
        windows[start, end] = {**window, "records": records}
    return {**data, "windows": windows}


def _unavailable(status, message):
    return {"status": status, "message": message, "county_fips": COUNTY_FIPS,
            "cells": {}, "parcels": {}, "scale_version": SCALE["version"]}


@lru_cache(maxsize=8)
def _aggregate(database, db_size, db_modified, artifact_path, size, modified, start, end, resolution):
    data = _artifact(artifact_path, size, modified)
    window = data["windows"].get((start, end))
    if window is None:
        return None
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        metadata = {k: json.loads(v) for k, v in connection.execute("SELECT key,value FROM metadata")}
        if (metadata.get("county_fips") != COUNTY_FIPS
                or metadata.get("source_provenance", {}).get("output_sha256") != data["inventory_id"]
                or not metadata.get("source_provenance", {}).get("county_boundary")):
            raise ValueError("Exposure inventory does not match county-validated parcel geometry")
        inventory = {row[0] for row in connection.execute("SELECT parcel_id FROM parcels")}
        if not window["records"].keys() <= inventory:
            raise ValueError("Exposure contains parcels absent from the validated inventory")
        groups = {}
        for cell_id, parcel_id in connection.execute(
                "SELECT cp.cell_id,cp.parcel_id FROM cell_parcels cp "
                "JOIN county_cells c USING(cell_id) WHERE c.resolution=?", (resolution,)):
            groups.setdefault(cell_id, []).append(window["records"].get(parcel_id, {}).get("score"))
    return {"status": "ready", "county_fips": COUNTY_FIPS, "run_id": data["run_id"],
            **model_context(data),
            "method_version": data["method_version"], "inventory_id": data["inventory_id"],
            "valid_from": window["valid_from"], "valid_to": window["valid_to"],
            "computed_at": window["computed_at"], "scale_version": SCALE["version"],
            "aggregation": "parcel_p90_linear", "resolution": resolution,
            "aggregation_architecture": platform.machine(),
            "cells": {cell: summarize(scores) for cell, scores in groups.items()},
            "records": window["records"]}


def exposure(query):
    """Bounded summaries or up to 100 parcel assessments for one exact window."""
    mode = query.get("mode", "current")
    if mode not in ("current", "replay"):
        raise ValueError("Exposure mode must be current or replay")
    try:
        start, end = timestamp(query["from"]), timestamp(query["to"])
        resolution = int(query.get("resolution", "7"))
        ids = [int(value) for value in query.get("parcel_ids", "").split(",") if value]
        if (end - start != timedelta(hours=6) or resolution not in (4, 5, 6, 7)
                or len(ids) > 100 or len(ids) != len(set(ids)) or any(x < 0 for x in ids)):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError("Use a six-hour exposure window, R4–R7 and at most 100 parcel IDs") from None
    if os.environ.get("QUASAR_LINUXONE_API_URL"):
        return _remote(query)
    path, database = os.environ.get("QUASAR_EXPOSURE_FILE"), os.environ.get("QUASAR_PARCEL_DATABASE")
    if not path or not database:
        return _unavailable("not_configured", "Parcel exposure results are not configured; scores remain unknown.")
    try:
        file_stat, db_stat = Path(path).stat(), Path(database).stat()
        result = _aggregate(database, db_stat.st_size, db_stat.st_mtime_ns, path, file_stat.st_size,
                            file_stat.st_mtime_ns, start, end, resolution)
        if result is None:
            return _unavailable("unavailable", "No parcel exposure results match this forecast window.")
        now = datetime.now(timezone.utc)
        computed = timestamp(result["computed_at"])
        if computed > now:
            return _unavailable("invalid", "Exposure computation time is in the future.")
        if mode == "current" and (end <= now or now - computed > timedelta(hours=2)):
            return _unavailable("stale", "Parcel exposure results are stale; scores remain unknown.")
        if mode == "current" and result.get("forecast_provenance") and (
                result["forecast_provenance"]["mode"] != "current"
                or timestamp(result["forecast_provenance"]["expires_at"]) <= now):
            return _unavailable("stale", "Model forecast source expired; scores remain unknown.")
        if query.get("run_id") not in (None, result["run_id"]):
            return _unavailable("changed", "Exposure run changed; refresh this selection.")
        return {**{k: v for k, v in result.items() if k != "records"},
                "cells": {} if ids else result["cells"],
                "parcels": {str(i): result["records"].get(i, {"parcel_id": i, "score": None,
                            "factors": [], "missing": ["assessment_unavailable"]}) for i in ids}}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error):
        return _unavailable("invalid", "Parcel exposure artifact is unavailable or invalid; scores remain unknown.")


def _remote(query):
    base = os.environ.get("QUASAR_LINUXONE_API_URL", "").rstrip("/")
    parsed = urlsplit(base)
    token = os.environ.get("QUASAR_LINUXONE_API_TOKEN", "")
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path or len(token) < 32):
        raise SourceUnavailable("LinuxONE exposure service is not configured correctly.")
    allowed = {key: query[key] for key in ("from", "to", "mode", "resolution", "parcel_ids", "run_id") if key in query}
    request = Request(base + "/api/exposure?" + urlencode(allowed),
                      headers={"X-Quasar-Parcel-Token": token, "Accept": "application/json"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=12) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError()
        data = json.loads(body)
        if (data.get("county_fips") != COUNTY_FIPS or data.get("scale_version") != SCALE["version"]
                or not isinstance(data.get("cells"), dict) or not isinstance(data.get("parcels"), dict)):
            raise ValueError()
        if data.get("status") == "ready":
            context = model_context(data)
            if context:
                source = context["forecast_provenance"]
                if (timestamp(source["valid_from"]) != timestamp(query["from"])
                        or timestamp(source["valid_to"]) != timestamp(query["to"])
                        or (query.get("mode", "current") == "current" and
                            (source["mode"] != "current" or timestamp(source["expires_at"]) <= datetime.now(timezone.utc)))):
                    raise ValueError("Expired or mismatched model forecast source")
            if (timestamp(data["valid_from"]) != timestamp(query["from"])
                    or timestamp(data["valid_to"]) != timestamp(query["to"])
                    or query.get("run_id", data["run_id"]) != data["run_id"]):
                raise ValueError()
            computed, now = timestamp(data["computed_at"]), datetime.now(timezone.utc)
            if (not all(isinstance(data.get(key), str) and data[key] for key in
                        ("run_id", "method_version", "inventory_id"))
                    or data.get("resolution") != int(query.get("resolution", "7"))
                    or data.get("aggregation") != "parcel_p90_linear"
                    or computed > now
                    or (query.get("mode", "current") == "current" and
                        (timestamp(data["valid_to"]) <= now or now-computed > timedelta(hours=2)))):
                raise ValueError()
            requested = {str(int(value)) for value in query.get("parcel_ids", "").split(",") if value}
            if not data["parcels"].keys() <= requested:
                raise ValueError()
            for key, record in data["parcels"].items():
                if type(record.get("parcel_id")) is not int or str(record["parcel_id"]) != key:
                    raise ValueError()
            for cell in data["cells"].values():
                total, scored = cell.get("parcel_count"), cell.get("scored_count")
                if (type(total) is not int or type(scored) is not int or not 0 <= scored <= total
                        or cell.get("unknown_count") != total-scored
                        or not math.isclose(cell.get("coverage", -1), scored/total if total else 0)
                        or cell.get("incomplete") != (total == 0 or scored < total)
                        or type(cell.get("elevated_count")) is not int or not 0 <= cell["elevated_count"] <= scored
                        or (scored == 0 and cell.get("p90_score") is not None)
                        or (scored > 0 and not valid_score(cell.get("p90_score")))):
                    raise ValueError()
                if context and context["forecast_provenance"]["status"] != "ready" and scored:
                    raise ValueError("Unavailable model source cannot supply known summaries")
            data["parcels"] = {key: validate_assessment(record) for key, record in data["parcels"].items()}
            if context and any(r["score"] is not None and ("model_details" not in r
                    or context["forecast_provenance"]["status"] != "ready") for r in data["parcels"].values()):
                raise ValueError("Missing model diagnostics or unavailable source")
        return data
    except Exception as exc:
        raise SourceUnavailable("LinuxONE exposure service unavailable; scores remain unknown.") from exc
