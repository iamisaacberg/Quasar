"""Native county forecast playback. Never loads fixture sites or computes scores."""
from datetime import datetime, timedelta, timezone
from collections import OrderedDict
import hashlib
import json
from threading import Lock
from time import monotonic

from .adapters import county_weather as county
from .adapters.weathernext import iso, timestamp, summarize
from .bridge import BridgeUnavailable, read_snapshot
from .config import COUNTY_FIPS, TIMEZONE


_prepared = OrderedDict()
_prepare_lock = Lock()


def timeline(*, source="archive", now=None, reader=None):
    # Always consult the source first: an expired bridge cache or failed read
    # must never be masked by a derived forecast cache. Explicit research clocks
    # and injected readers stay uncached, making mutations/freshness testable.
    if (reader is not None and reader is not read_snapshot) or now is not None or source not in ("archive", "current"):
        return _timeline(source=source, now=now, reader=reader)
    try:
        data = (reader or read_snapshot)("isaias-2026" if source == "archive" else "weathernext")
    except (BridgeUnavailable, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        def failed_read(_):
            raise exc
        return _timeline(source=source, reader=failed_read)
    if data is None:
        return _timeline(source=source, reader=lambda _: None)
    try:
        key = (source, hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).digest())
    except (TypeError, ValueError):
        return _timeline(source=source, reader=lambda _: data)
    with _prepare_lock:
        cached = _prepared.get(key)
        clock = datetime.now(timezone.utc)
        if cached and monotonic() < cached[1]:
            expiry = cached[2].get("expires_at")
            if not expiry or timestamp(expiry) > clock:
                _prepared.move_to_end(key)
                return cached[2]
        result = _timeline(source=source, now=clock, reader=lambda _: data)
        if result["frames"]:
            _prepared[key] = (data, monotonic() + 15, result)
            while len(_prepared) > 2:
                _prepared.popitem(last=False)
        return result


def _timeline(*, source="archive", now=None, reader=None):
    if source not in ("current", "archive"):
        raise ValueError("Source must be current or archive")
    now = now or datetime.now(timezone.utc)
    base = {"county_fips": COUNTY_FIPS, "frames": [], "default_index": 0,
            "units": "mm / 6h", "timezone": TIMEZONE, "source": source}
    try:
        data = (reader or read_snapshot)("weathernext" if source == "current" else "isaias-2026")
        if data is None:
            return {**base, "status": "not_configured", "message": "The Isaias county archive is not configured or its file is missing. No rainfall values are available." if source == "archive" else "No imported county forecast is configured."}
        if data.get("schema_version") != 3:
            return {**base, "status": "unavailable", "message": "A county native-cell snapshot is required. Site-only imports are not used."}
        prepared = county.PreparedForecast(data, now=now)
        expected = "current_county_forecasts" if source == "current" else "historical_county_forecasts"
        if data["kind"] != expected:
            raise ValueError("Wrong forecast kind")
        ids = {cell["id"] for cell in data["native_cells"]}
        stale = False
        if source == "current":
            original = summarize(county.current_snapshot(data), allowed=ids, now=now)
            stale = original["status"] == "stale"
            start = timestamp(data["init_time"])
            last = max(timestamp(row["forecast_time"]) for row in data["runs"][0]["rows"]) - timedelta(hours=6)
        else:
            from .replay import START, END
            start, last = START, END
        frames = []
        clock = start
        while clock <= last:
            window = {**data, "valid_from": iso(clock), "valid_to": iso(clock + timedelta(hours=6))}
            cells = prepared.collection(window=window, at=iso(clock) if source == "archive" else None)
            for feature in cells["features"]:
                # The archive adapter also supports research what-if experiments. This
                # public path fixes archived rainfall and exposes no synthetic additions.
                feature["properties"].pop("synthetic_increment_mm_per_hour", None)
                if stale:
                    feature["properties"].update(status="stale", rainfall_6h_mm=None)
            metadata = {key: data[key] for key in ("source_table", "retrieved_at", "native_resolution", "statistic")}
            if source == "archive":
                metadata["reconstruction"] = next(iter(cells["features"]))["properties"]["reconstruction"]
            metadata["init_time"] = data.get("init_time") if source == "current" else next(
                (f["properties"].get("init_time") for f in cells["features"] if f["properties"].get("init_time")), None)
            status = "stale" if stale else "ready" if all(f["properties"]["status"] == "ready" for f in cells["features"]) else "incomplete"
            notice = "Imported native forecast rainfall; not observed rain, parcel flood risk, depth or probability. Follow official NWS/local guidance."
            collection = {"type": "FeatureCollection", "county_fips": COUNTY_FIPS, "features": [],
                          "mode": "county_forecast" if source == "current" else "county_archive",
                          "scenario": {"id": "weathernext" if source == "current" else "isaias-2026",
                                       "valid_from": cells["valid_from"], "valid_to": cells["valid_to"]},
                          "forecast": {**metadata, "status": status}, "weather_cells": cells, "notice": notice}
            frames.append({"at": iso(clock), "collection": collection})
            clock += timedelta(hours=1)
        if not frames:
            raise ValueError("No six-hour forecast windows")
        metadata = {key: data[key] for key in ("retrieved_at", "source_table", "native_resolution", "statistic")}
        metadata.update({key: data[key] for key in ("license", "publication_timing", "archive_policy", "processing") if key in data})
        default_at = iso(start + timedelta(hours=10)) if source == "archive" else data.get("valid_from")
        result = {**base, **metadata, "status": "stale" if stale else "ready" if all(
            f["collection"]["forecast"]["status"] == "ready" for f in frames) else "incomplete",
                  "frames": frames, "default_index": next((i for i, f in enumerate(frames) if f["at"] == default_at), 0),
                  "notice": notice}
        if source == "current":
            result.update(init_time=data["init_time"], expires_at=min(
                iso(timestamp(data["retrieved_at"]) + timedelta(hours=2)),
                iso(start + timedelta(hours=12)), data["valid_to"]))
        return result
    except BridgeUnavailable:
        return {**base, "status": "unavailable", "message": "Forecast bridge unavailable. No substitute data or new import was used."}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {**base, "status": "invalid", "message": "Forecast snapshot invalid or unavailable. No substitute data or new import was used."}
