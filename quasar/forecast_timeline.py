"""Map playback from retained forecast rows. Reads one snapshot; never imports."""
from datetime import datetime, timedelta, timezone

from .adapters import county_weather as county
from .adapters.weathernext import iso, timestamp, summarize
from .bridge import BridgeUnavailable, read_snapshot
from .config import COUNTY_FIPS
from .pipeline import weather_collection


def timeline(*, now=None):
    now = now or datetime.now(timezone.utc)
    base = {"county_fips": COUNTY_FIPS, "frames": [], "default_index": 0,
            "units": "mm / 6h", "timezone": "America/Chicago"}
    try:
        data = read_snapshot("weathernext")
        if data is None:
            return {**base, "status": "not_configured", "message": "Import a forecast snapshot to enable playback."}
        if data.get("schema_version") != 3:
            # Older imports retain a single six-hour window, not a multi-hour run.
            forecast = summarize(data, now=now)
            return {**base, "status": forecast["status"],
                    "frames": [{"at": data["valid_from"], "collection": weather_collection(forecast)}]}
        county.validate(data, now=now)
        if data["kind"] != "current_county_forecasts":
            raise ValueError("Current forecast required")
        ids = {c["id"] for c in data["native_cells"]}
        original = summarize(county.current_snapshot(data), allowed=ids, now=now)
        # Global freshness is tied to the imported snapshot, never the slider clock.
        stale = original["status"] == "stale"
        rows = data["runs"][0]["rows"]
        if not rows:
            raise ValueError("No retained hourly rows")
        start = timestamp(data["init_time"])
        last = max(timestamp(r["forecast_time"]) for r in rows) - timedelta(hours=6)
        frames = []
        clock = start
        while clock <= last:
            window = {**data, "valid_from": iso(clock), "valid_to": iso(clock + timedelta(hours=6))}
            cells = county.collection(window, now=now)
            forecast = summarize(county.for_sites(window, now=now), now=now)
            forecast["coverage"] = "County native forecast cells; site scores still use fictional inputs"
            if stale:
                forecast["status"] = "stale"
                for record in forecast["records"].values():
                    record.update(status="stale", rainfall_6h_mm=None)
                for feature in cells["features"]:
                    feature["properties"].update(status="stale", rainfall_6h_mm=None)
            forecast["county_cells"] = cells
            frames.append({"at": iso(clock), "collection": weather_collection(forecast)})
            clock += timedelta(hours=1)
        if not frames:
            raise ValueError("Fewer than six retained forecast hours")
        default = next((i for i, f in enumerate(frames) if f["at"] == data["valid_from"]), 0)
        metadata = {k: data[k] for k in ("init_time", "retrieved_at", "source_table", "native_resolution", "statistic")}
        return {**base, **metadata, "status": original["status"], "frames": frames, "default_index": default,
                "expires_at": min(iso(timestamp(data["retrieved_at"]) + timedelta(hours=2)),
                                  iso(start + timedelta(hours=12)), data["valid_to"]),
                "notice": "Imported forecast rainfall with fictional site inputs; real parcel scores remain unknown."}
    except BridgeUnavailable:
        return {**base, "status": "unavailable", "message": "Forecast bridge unavailable. No new import was started."}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {**base, "status": "invalid", "message": "Forecast snapshot invalid or unavailable. No new import was started."}
