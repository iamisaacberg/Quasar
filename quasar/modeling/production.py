"""Explicit offline, batched assessment production. No GIS, ML libraries or cloud calls."""
import json
import math
import platform
import resource
import shutil
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..adapters import county_weather
from ..adapters.weathernext import timestamp, iso
from ..parcel_context import readonly
from ..replay import run_rows
from . import FEATURES, NOTICE, POLICY, TARGET, digest, feature_values, label_value, finite, read_json, utcnow, write_json
from .dataset import audit
from .portable import load, predict


def weather_window(data, start, mode, now):
    county_weather.validate(data, now=now)
    clock = timestamp(start)
    if clock.minute or clock.second or clock.microsecond or mode not in ("current", "replay"):
        raise ValueError("Whole-hour six-hour current/replay window required")
    retrieved = timestamp(data["retrieved_at"])
    if retrieved > now:
        raise ValueError("Forecast retrieval time is in the future")
    eligible = [r for r in data["runs"] if timestamp(r["init_time"]) <= clock
                and (not r.get("published_at") or timestamp(r["published_at"]) <= clock)]
    if not eligible:
        raise ValueError("No eligible forecast initialization; no assessment artifact published")
    run = max(eligible, key=lambda r: timestamp(r["init_time"]))
    init = timestamp(run["init_time"])
    expiry = min(init+timedelta(hours=12), retrieved+timedelta(hours=2), clock+timedelta(hours=6))
    stale = clock-init > timedelta(hours=12)
    if mode == "current":
        if data["kind"] != "current_county_forecasts":
            raise ValueError("Current production requires a current county snapshot")
        expiry = min(expiry, timestamp(data["valid_to"]))
        stale = stale or now >= expiry
    rows = run_rows(run, allowed={c["id"] for c in data["native_cells"]})
    result = {}
    for cell in data["native_cells"]:
        selected = [rows.get((cell["id"], iso(clock+timedelta(hours=h)))) for h in range(1, 7)]
        values = [r["rainfall_1h_mm"] for r in selected if r and r["rainfall_1h_mm"] is not None]
        result[cell["id"]] = None if stale or len(values) != 6 else sum(values)
    metadata = {"status": "stale" if stale else "ready", "init_time": run["init_time"],
                "published_at": run.get("published_at"), "retrieved_at": data["retrieved_at"],
                "source_table": data["source_table"], "native_resolution": data["native_resolution"],
                "statistic": data["statistic"], "units": "mm / 6h", "valid_from": iso(clock),
                "valid_to": iso(clock+timedelta(hours=6)), "expires_at": iso(expiry),
                "source_sha256": None, "mode": mode,
                "availability_basis": "publication-constrained" if run.get("published_at") else "initialization-based reconstruction"}
    return result, metadata


def parcel_rainfall(overlaps, rainfall):
    if not isinstance(overlaps, list) or not overlaps:
        return None
    seen, total, weighted = set(), 0., 0.
    for overlap in overlaps:
        identifier, fraction = overlap.get("native_cell_id"), overlap.get("area_fraction")
        if (not isinstance(identifier, str) or identifier in seen or not finite(fraction) or not 0 < fraction <= 1
                or not finite(rainfall.get(identifier)) or rainfall[identifier] < 0):
            return None
        seen.add(identifier)
        total += fraction
        weighted += fraction*rainfall[identifier]
    # Associations are verified by offline inspection preparation; do not renormalize missing coverage.
    return weighted/total if math.isclose(total, 1., abs_tol=1e-6) else None


def assessment(identifier, inputs, overlaps, model, rainfall, *, prediction_cache=None):
    values, missing = feature_values(inputs)
    if model.get("inference_population") == "positive_fema_overlap":
        reference = label_value(inputs)
        if reference is None:
            missing.append("verified_positive_fema_overlap_required")
        elif reference == 0:
            missing.append("excluded_zero_fema_overlap")
    result = {"missing": []}
    if values is not None and not missing:
        key = (model["model_version"], tuple(values))
        if prediction_cache is not None and key in prediction_cache:
            result = prediction_cache[key]
        else:
            result = predict(model, values)
            if prediction_cache is not None:
                prediction_cache[key] = result
    missing += result["missing"]
    rain = parcel_rainfall(overlaps, rainfall)
    if rain is None:
        missing.append("complete_fresh_native_rainfall")
    base = {"parcel_id": identifier, "score": None, "factors": [], "missing": missing}
    if missing:
        return base
    susceptibility = result["susceptibility"]
    stress = rain/(rain+50.)
    score = round(100*susceptibility*stress, 6)
    return {**base, "score": score,
            "factors": [{"name": "susceptibility_rainfall_interaction", "value": score, "contribution": score}],
            "model_details": {"susceptibility": susceptibility, "raw_susceptibility": result["raw_susceptibility"],
                              "fema_mapped_area_fraction": label_value(inputs),
                              "rainfall_6h_mm": rain, "rainfall_stress": stress,
                              "model_instability": result["model_instability"], "baseline": result["baseline"],
                              "attributions": result["attributions"]}}


def produce(database, inputs, boundary, inspection, model_path, evaluation_path, weather_path,
            start, mode, output, *, now=None, prediction_cache=None):
    began = time.perf_counter()
    now = now or datetime.now(timezone.utc)
    output = Path(output)
    if output.exists():
        raise ValueError("Use a new assessment path; activate it explicitly after review")
    # 50 GB host disk is a capacity, not permission to fill it. Reserve >=1 GiB free.
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(parent).free < 1024**3:
        raise ValueError("At least 1 GiB free disk required")
    audited = audit(database, inputs, boundary, inspection)
    model, evaluation = load(model_path), read_json(evaluation_path)
    if (audited["status"] != "verified" or not model["promoted"] or evaluation.get("promoted") is not True
            or evaluation.get("model_sha256") != digest(model_path)
            or evaluation.get("dataset_manifest", {}).get("dataset_id") != model["training_dataset_id"]
            or model["inventory_id"] != audited["inventory_id"] or model["boundary_version"] != audited["boundary_version"]):
        raise ValueError("Only promoted, evaluated, inventory-matched models can produce assessments")
    lineage = {}
    if model.get("evaluation_protocol") or model["model_version"].startswith("mapped-susceptibility-v2-"):
        from .v2 import verify_evaluation
        verify_evaluation(model, evaluation)
        if evaluation["dataset_manifest"].get("checksums") != audited["checksums"]:
            raise ValueError("V2 assessment inputs differ from the evaluated source snapshot")
        candidate = evaluation["comparisons"]["candidate"]
        lineage = {"training_dataset_id": model["training_dataset_id"],
                   **({"inference_population": model["inference_population"]} if "inference_population" in model else {}),
                   "evaluation_sha256": digest(evaluation_path), "evaluation_protocol": evaluation["evaluation_protocol"],
                   "evaluation_summary": {"macro_subgroup_mae": candidate["macro_subgroup_mae"],
                                          "fully_mapped_mae": candidate["target_ranges"]["one"]["mae"],
                                          "parcel_rmse": candidate["parcel"]["rmse"],
                                          "equal_block_rmse": candidate["equal_block"]["rmse"], "coverage": evaluation["coverage"]}}
    weather = read_json(weather_path)
    # Prepared overlaps must be from this exact verified snapshot, not merely share cell IDs.
    inspection_manifest = read_json(Path(inspection)/"manifest.json")
    if digest(weather_path) not in {r["sha256"] for r in inspection_manifest["provenance"]["weather"]}:
        raise ValueError("Forecast snapshot not verified by inspection preparation")
    if weather["county_geometry"] != read_json(boundary)["features"][0]["geometry"]:
        raise ValueError("Forecast boundary does not match parcel preparation")
    rainfall, source = weather_window(weather, start, mode, now)
    source["source_sha256"] = digest(weather_path)
    counts = Counter()
    run_id = "exposure-"+now.strftime("%Y%m%dT%H%M%S%f")
    # Stream JSON into a private partial file. Never hold the county assessment inventory in memory.
    import os
    import tempfile
    fd, temporary = tempfile.mkstemp(dir=parent, suffix=".partial")
    try:
        with os.fdopen(fd, "w") as stream, closing(readonly(Path(inspection)/"inspection.sqlite3")) as db:
            header = {"schema_version": 1, "county_fips": "12091", "run_id": run_id,
                      "method_version": POLICY+":"+model["model_version"], "inventory_id": audited["inventory_id"],
                      "model_metadata": {"schema_version": 1, "model_version": model["model_version"], "target": TARGET,
                                         "policy": POLICY, "promoted": True, "model_sha256": digest(model_path),
                                         "notice": NOTICE, **lineage}, "forecast_provenance": source}
            stream.write(json.dumps(header, allow_nan=False)[:-1]+',"windows":[{')
            window = {"valid_from": iso(timestamp(start)), "valid_to": iso(timestamp(start)+timedelta(hours=6)),
                      "computed_at": now.isoformat()}
            stream.write(json.dumps(window, allow_nan=False)[1:-1]+',"parcels":[')
            first = True
            cursor = db.execute("SELECT identifier,context_json FROM inspection WHERE kind='parcel' ORDER BY identifier")
            while batch := cursor.fetchmany(256):
                for identifier, raw in batch:
                    context = json.loads(raw)
                    if (context.get("county_fips") != "12091" or context.get("parcel_id") != int(identifier)):
                        raise ValueError("Invalid inspection record identity")
                    record = assessment(int(identifier), context["inputs"], context["forecast_overlaps"], model, rainfall,
                                        prediction_cache=prediction_cache)
                    counts["total"] += 1
                    counts["scored" if record["score"] is not None else "unknown"] += 1
                    counts.update(record["missing"])
                    stream.write(("" if first else ",")+json.dumps(record, allow_nan=False, separators=(",", ":")))
                    first = False
            stream.write("]}]}")
            stream.flush()
            os.fsync(stream.fileno())
        if counts["total"] != audited["parcel_count"] or Path(temporary).stat().st_size > 128*1024*1024:
            raise ValueError("Incomplete or oversized assessment artifact")
        # Same-directory hard link publishes a complete file atomically without
        # clobbering a destination created by another producer during this run.
        os.link(temporary, output)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if platform.system() == "Darwin" else peak*1024
    benchmark = {"architecture": platform.machine(), "system": platform.system(),
                 "python": platform.python_version(), "logical_cpus": os.cpu_count(),
                 "elapsed_seconds": time.perf_counter()-began, "peak_rss_bytes": peak_bytes,
                 "artifact_bytes": output.stat().st_size, "disk_free_bytes": shutil.disk_usage(parent).free,
                 "host_budget": {"vcpus": 3, "ram_bytes": 8*1024**3, "disk_bytes": 50*1024**3},
                 "targets_met": time.perf_counter()-began < 300 and peak_bytes < 2*1024**3,
                 "target_host_evidence": platform.machine() == "s390x", "counts": dict(counts),
                 "artifact_sha256": digest(output), "notice": "Local runs are not LinuxONE benchmark evidence."}
    write_json(output.with_suffix(output.suffix+".benchmark.json"), benchmark)
    return benchmark


def produce_replay(database, inputs, boundary, inspection, model_path, evaluation_path, weather_path, output):
    """Prepare all 25 v2 windows locally; no activation, query, or v1 fallback."""
    from .v2 import verify_evaluation
    model, evaluation = load(model_path), read_json(evaluation_path)
    verify_evaluation(model, evaluation)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    start = datetime(2026, 10, 9, 5, tzinfo=timezone.utc)
    receipts = []
    prediction_cache = {}
    for hour in range(25):
        clock = start+timedelta(hours=hour)
        path = root/(clock.strftime("%Y%m%dT%H%M%SZ")+".json")
        produce(database, inputs, boundary, inspection, model_path, evaluation_path, weather_path,
                iso(clock), "replay", path, prediction_cache=prediction_cache)
        measured = benchmark(database, path, root/(path.stem+".aggregation.json"))
        receipts.append({"at": iso(clock), "file": path.name, "sha256": digest(path),
                         "targets_met": measured["targets_met"], "architecture": measured["architecture"]})
    manifest = {"status": "prepared", "county_fips": "12091", "model_version": model["model_version"],
                "model_sha256": digest(model_path), "evaluation_sha256": digest(evaluation_path),
                "forecast_sha256": digest(weather_path), "windows": receipts,
                "notice": "Prepared local artifacts only. Runtime activation and actual LinuxONE evidence are separate."}
    write_json(root/"manifest.json", manifest)
    return manifest


def benchmark(database, artifact, output):
    """Measure R4–R7 aggregation after production, without starting a service."""
    from .. import exposure
    began = time.perf_counter()
    data = read_json(artifact)
    if len(data["windows"]) != 1:
        raise ValueError("Benchmark one complete county window at a time")
    window = {k: data["windows"][0][k] for k in ("valid_from", "valid_to")}
    # Drop the large decoded JSON before measuring the actual aggregator's memory footprint.
    del data
    db_stat, stat = Path(database).stat(), Path(artifact).stat()
    summaries = {}
    for resolution in (4, 5, 6, 7):
        result = exposure._aggregate(str(database), db_stat.st_size, db_stat.st_mtime_ns,
            str(artifact), stat.st_size, stat.st_mtime_ns, timestamp(window["valid_from"]),
            timestamp(window["valid_to"]), resolution)
        summaries[str(resolution)] = {"cell_count": len(result["cells"]), "run_id": result["run_id"]}
    elapsed = time.perf_counter()-began
    production_report = read_json(Path(artifact).with_suffix(Path(artifact).suffix+".benchmark.json"))
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if platform.system() == "Darwin" else peak*1024
    total = elapsed+production_report["elapsed_seconds"]
    report = {"production": production_report, "aggregation_seconds": elapsed,
              "elapsed_seconds": total, "peak_rss_bytes": max(peak_bytes, production_report["peak_rss_bytes"]),
              "architecture": platform.machine(), "python": platform.python_version(), "summaries": summaries,
              "artifact_sha256": digest(artifact), "targets_met": total < 300 and max(peak_bytes, production_report["peak_rss_bytes"]) < 2*1024**3,
              "target_host_evidence": platform.machine() == "s390x",
              "notice": "Measured production plus R4–R7 aggregation. Target-host evidence requires s390x and a complete real inventory."}
    if report["artifact_sha256"] != production_report["artifact_sha256"]:
        raise ValueError("Benchmark artifact differs from the produced artifact")
    write_json(output, report)
    return report
