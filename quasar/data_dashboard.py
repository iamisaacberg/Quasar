"""Real native forecast values for the Data tab; no fixture sites or scoring."""
from datetime import datetime, timedelta, timezone

from .adapters import county_weather
from .adapters.weathernext import iso, summarize, timestamp
from .bridge import BridgeUnavailable, read_snapshot
from .config import COUNTY_FIPS, TIMEZONE


def weather_data(*, now=None):
    now = now or datetime.now(timezone.utc)
    base = {"county_fips": COUNTY_FIPS, "timezone": TIMEZONE, "units": "mm / 6h",
            "generated_at": iso(now), "frames": [], "default_index": 0}
    try:
        data = read_snapshot("weathernext")
        if data is None:
            return {**base, "status": "not_configured", "message": "No imported county forecast is configured."}
        if data.get("schema_version") != 3:
            return {**base, "status": "unavailable", "message": "A county native-cell snapshot is required. The six-site demo import is not used here."}
        county_weather.validate(data, now=now)
        if data["kind"] != "current_county_forecasts":
            raise ValueError("Expected a current county forecast")
        ids = {cell["id"] for cell in data["native_cells"]}
        original = summarize(county_weather.current_snapshot(data), allowed=ids, now=now)
        start = timestamp(data["init_time"])
        rows = data["runs"][0]["rows"]
        last = max(timestamp(row["forecast_time"]) for row in rows) - timedelta(hours=6)
        frames = []
        clock = start
        while clock <= last:
            window = {**data, "valid_from": iso(clock), "valid_to": iso(clock + timedelta(hours=6))}
            summary = summarize(county_weather.current_snapshot(window), allowed=ids, now=now)
            records = []
            for identifier in sorted(ids):
                record = summary["records"][identifier]
                stale = original["status"] == "stale"
                records.append({"native_cell_id": identifier,
                                "status": "stale" if stale else record["status"],
                                "rainfall_6h_mm": None if stale else record["rainfall_6h_mm"],
                                "available_hours": record["available_hours"]})
            frames.append({"at": iso(clock), "valid_to": window["valid_to"], "rows": records})
            clock += timedelta(hours=1)
        if not frames:
            raise ValueError("No six-hour forecast windows")
        metadata = {key: data[key] for key in ("init_time", "retrieved_at", "source_table", "native_resolution", "statistic")}
        return {**base, **metadata, "status": original["status"], "frames": frames,
                "default_index": next((i for i, frame in enumerate(frames) if frame["at"] == data["valid_from"]), 0),
                "expires_at": min(data["valid_to"], iso(start + timedelta(hours=12)),
                                  iso(timestamp(data["retrieved_at"]) + timedelta(hours=2))),
                "message": "Imported native cells intersecting Okaloosa County; cells may extend beyond the boundary. Forecast rainfall is not observed rain or parcel flood risk."}
    except BridgeUnavailable:
        return {**base, "status": "unavailable", "message": "The forecast source is unavailable. No import was started."}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {**base, "status": "invalid", "message": "The county forecast is invalid or unreadable. No substitute values are shown."}
