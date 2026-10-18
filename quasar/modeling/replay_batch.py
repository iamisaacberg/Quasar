"""Explicit offline replay production; dry run by default, no cloud or service calls."""
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import digest, read_json, write_json
from .production import weather_window, produce, benchmark
from .. import exposure, exposure_catalog, forecast_timeline
from ..adapters.weathernext import timestamp


def assess_replay(database, inputs, boundary, inspection, model, evaluation, weather, output,
                  *, execute=False, now=None):
    now = now or datetime.now(timezone.utc)
    snapshot = read_json(weather)
    timeline = forecast_timeline.timeline(source="archive", now=now, reader=lambda _: snapshot)
    if timeline["status"] not in ("ready", "incomplete") or len(timeline["frames"]) != 25:
        raise ValueError("A valid saved 25-position county archive is required")
    output = Path(output)
    if output.exists():
        raise ValueError("Use a new immutable replay release directory")
    windows = []
    for frame in timeline["frames"]:
        if frame["collection"]["forecast"]["init_time"] is None:
            selected = frame["collection"]["scenario"]
            windows.append({"valid_from": selected["valid_from"], "valid_to": selected["valid_to"],
                            "mode": "replay", "status": "source_gap",
                            "reason": "no_eligible_forecast_initialization", "ready_native_cells": 0,
                            "native_cell_count": len(snapshot["native_cells"])})
            continue
        rainfall, source = weather_window(snapshot, frame["at"], "replay", now)
        ready = sum(value is not None for value in rainfall.values())
        windows.append({"valid_from": source["valid_from"], "valid_to": source["valid_to"],
                        "mode": "replay", "status": "eligible" if ready else "source_gap",
                        "reason": None if ready else "stale_or_incomplete_native_rainfall",
                        "ready_native_cells": ready, "native_cell_count": len(rainfall)})
    parent = output.parent
    while not parent.exists():
        parent = parent.parent
    required = sum(w["status"] == "eligible" for w in windows)*exposure.MAX_BYTES + 1024**3
    report = {"status": "planned", "county_fips": "12091", "windows": windows,
              "weather_sha256": digest(weather), "model_sha256": digest(model),
              "disk_free_bytes": shutil.disk_usage(parent).free, "reserved_bytes": required,
              "notice": "Offline production only. No activation, LinuxONE run or observed-flood validation is implied."}
    if not execute:
        return report
    if report["disk_free_bytes"] < required:
        raise ValueError("Insufficient disk for bounded per-window artifacts plus 1 GiB reserve")
    output.mkdir(parents=True)
    catalog = {"schema_version": 1, "county_fips": "12091", "inventory_id": None,
               "model_sha256": report["model_sha256"], "entries": []}
    try:
        for index, window in enumerate(windows):
            if window["status"] == "source_gap":
                continue
            candidate = output / f"window-{index:02d}.json"
            production = produce(database, inputs, boundary, inspection, model, evaluation, weather,
                                 window["valid_from"], "replay", candidate, now=now)
            # Validate and measure the serving path one window at a time. No
            # decoded parcel map is retained by cached resolution summaries.
            measured = benchmark(database, candidate, output / f"window-{index:02d}.timing.json")
            stat = candidate.stat()
            artifact = exposure._artifact(str(candidate), stat.st_size, stat.st_mtime_ns, exposure_catalog.version(candidate))
            inventory = artifact["inventory_id"]
            if catalog["inventory_id"] not in (None, inventory):
                raise ValueError("Replay inventory changed during production")
            catalog["inventory_id"] = inventory
            entry = {k: window[k] for k in ("mode", "valid_from", "valid_to")}
            entry.update(path=candidate.name, sha256=digest(candidate), forecast_sha256=report["weather_sha256"])
            exposure_catalog.verify(catalog, entry, artifact,
                                    timestamp(window["valid_from"]), timestamp(window["valid_to"]))
            window.update(status="produced", counts=production["counts"],
                          benchmark=measured, artifact_sha256=entry["sha256"])
            catalog["entries"].append(entry)
            del artifact
            exposure._artifact.cache_clear()
            write_json(output / "coverage.json", report)
        if not catalog["entries"]:
            report["status"] = "source_gap"
        else:
            # Validate the entire bounded catalog before publishing its completion marker.
            staging = output / "catalog.candidate.json"
            write_json(staging, catalog)
            exposure_catalog.load(staging)
            staging.unlink()
            report["status"] = "produced" if len(catalog["entries"]) == 25 else "partial"
        write_json(output / "coverage.json", report)
        if catalog["entries"]:
            write_json(output / "catalog.json", catalog)
    except Exception:
        report["status"] = "failed"
        write_json(output / "coverage.json", report)
        raise
    return report
