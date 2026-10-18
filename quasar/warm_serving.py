"""Explicit LinuxONE startup checks, completed before opening a listener."""
import os
from datetime import timedelta
from contextlib import closing

from .exposure import exposure, timestamp
from .exposure_store import connect
from .forecast_timeline import timeline
from .bridge import read_snapshot
from .server import compressed_body
from .parcel_context import inventory_metadata, artifact
from .parcels import SourceUnavailable


def warm_serving():
    if os.environ.get("QUASAR_LINUXONE_API_URL") or os.environ.get("QUASAR_DATA_BRIDGE_URL"):
        raise ValueError("Warm serving requires local source inputs, not a proxy")
    database = os.environ.get("QUASAR_EXPOSURE_DATABASE")
    if not database or not os.environ.get("QUASAR_PARCEL_DATABASE"):
        raise ValueError("Warm serving requires exposure and parcel databases")
    if any(os.environ.get(key) for key in ("QUASAR_EXPOSURE_FILE", "QUASAR_EXPOSURE_DIRECTORY", "QUASAR_EXPOSURE_CATALOG")):
        raise ValueError("Clear conflicting exposure selectors before warm serving")
    if len(os.environ.get("QUASAR_PARCEL_API_TOKEN", "")) < 32:
        raise ValueError("Warm serving requires source API authentication")
    try:
        inventory_metadata()
        if os.environ.get("QUASAR_PARCEL_CONTEXT_DIRECTORY"):
            artifact()
    except SourceUnavailable as exc:
        raise ValueError("County inventory or inspection startup validation failed") from exc
    archive = timeline(source="archive")
    if archive.get("status") != "ready" or len(archive.get("frames", [])) != 25:
        raise ValueError("Warm serving requires a complete 25-hour county archive")
    starts = [timestamp(frame["at"]) for frame in archive["frames"]]
    with closing(connect(database)) as connection:
        actual = {(timestamp(start), timestamp(end), resolution) for start, end, resolution in connection.execute(
            "SELECT start,end,resolution FROM summaries")}
    expected = {(start, start + timedelta(hours=6), resolution) for start in starts for resolution in range(4, 8)}
    if actual != expected:
        raise ValueError("Prepared exposure windows do not exactly match the county archive")
    default = archive["frames"][archive["default_index"]]["at"]
    for resolution in range(4, 8):
        result = exposure({"from": default, "to": (timestamp(default) + timedelta(hours=6)).isoformat(),
                           "mode": "replay", "resolution": str(resolution)})
        if result.get("status") != "ready":
            raise ValueError("Prepared exposure startup validation failed")
    snapshot = read_snapshot("isaias-2026")
    compressed_body(snapshot.encoded)
    return {"status": "ready", "county_fips": "12091", "windows": 25}
