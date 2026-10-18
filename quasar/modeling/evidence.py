"""Offline transfer and cross-host parity checks; never manufactures host evidence."""
import math
from pathlib import Path

from . import digest, read_json
from .. import exposure
from ..exposure_catalog import artifact_path, sha256, version


def verify_bundle(manifest, root):
    data = read_json(manifest, 1024*1024)
    if (data.get("schema_version") != 1 or data.get("county_fips") != "12091"
            or not isinstance(data.get("files"), list) or not 1 <= len(data["files"]) <= 256):
        raise ValueError("A bounded Okaloosa transfer manifest is required")
    results, seen = [], set()
    for item in data["files"]:
        if (not isinstance(item, dict) or not isinstance(item.get("role"), str)
                or not isinstance(item.get("path"), str) or item["path"] in seen
                or type(item.get("required")) is not bool or not sha256(item.get("sha256"))):
            raise ValueError("Unique files with producer-supplied SHA-256 and required flags are required")
        seen.add(item["path"])
        try:
            path = artifact_path(root, item["path"])
        except FileNotFoundError:
            results.append({"path": item["path"], "role": item["role"], "required": item["required"], "status": "missing"})
            continue
        actual = digest(path)
        results.append({"path": item["path"], "role": item["role"], "required": item["required"],
                        "bytes": path.stat().st_size, "sha256": actual,
                        "status": "matched" if actual == item["sha256"] else "mismatch"})
    passed = all(r["status"] == "matched" or (not r["required"] and r["status"] == "missing") for r in results)
    return {"status": "matched" if passed else "incomplete", "county_fips": "12091",
            "manifest_sha256": digest(manifest), "files": results,
            "notice": "File transfer integrity only. Run modeling audit separately for semantic lineage and authoritative county containment."}


def compare_assessments(reference, candidate):
    """Compare every parcel, preserving method/source identity and fixed tolerances."""
    def load(path):
        stat = Path(path).stat()
        return exposure._artifact(str(Path(path).resolve()), stat.st_size, stat.st_mtime_ns, version(path))

    left, right = load(reference), load(candidate)
    mismatches = []
    mismatch_count = 0

    def mismatch(location):
        nonlocal mismatch_count
        mismatch_count += 1
        if len(mismatches) < 100:
            mismatches.append(location)

    for key in ("county_fips", "inventory_id", "method_version", "model_metadata", "forecast_provenance"):
        if left.get(key) != right.get(key):
            mismatch(key)
    if left["windows"].keys() != right["windows"].keys():
        mismatch("windows")
    compared = 0

    def equal(a, b, tolerance):
        return (type(a) in (int, float) and type(b) in (int, float)
                and math.isclose(a, b, abs_tol=tolerance, rel_tol=0))

    for key in left["windows"].keys() & right["windows"].keys():
        a, b = left["windows"][key]["records"], right["windows"][key]["records"]
        if a.keys() != b.keys():
            mismatch(f"{key[0].isoformat()}:parcel_ids")
        for identifier in a.keys() & b.keys():
            compared += 1
            x, y = a[identifier], b[identifier]
            location = f"{key[0].isoformat()}:{identifier}"
            if x["missing"] != y["missing"] or (x["score"] is None) != (y["score"] is None):
                mismatch(location+":known_or_missing")
                continue
            if x["score"] is not None and not equal(x["score"], y["score"], 1e-5):
                mismatch(location+":score")
            if len(x["factors"]) != len(y["factors"]):
                mismatch(location+":factors")
            else:
                for f, g in zip(x["factors"], y["factors"]):
                    values_match = f.get("value") == g.get("value") or equal(f.get("value"), g.get("value"), 1e-5)
                    if f["name"] != g["name"] or not values_match or not equal(f["contribution"], g["contribution"], 1e-5):
                        mismatch(location+":factor")
            dx, dy = x.get("model_details", {}), y.get("model_details", {})
            if dx.keys() != dy.keys():
                mismatch(location+":model_details")
            for field in dx.keys() & dy.keys():
                if field == "attributions":
                    if dx[field].keys() != dy[field].keys() or any(
                            not equal(value, dy[field].get(feature), 1e-6) for feature, value in dx[field].items()):
                        mismatch(location+":attributions")
                elif not equal(dx[field], dy[field], 1e-6):
                    mismatch(location+":"+field)
    if not compared:
        mismatch("no_parcels_compared")
    return {"status": "matched" if mismatch_count == 0 else "mismatch", "compared_parcels": compared,
            "mismatch_count": mismatch_count, "first_mismatches": mismatches,
            "reference_sha256": digest(reference), "candidate_sha256": digest(candidate),
            "tolerances": {"score_and_factors": 1e-5, "model_details": 1e-6},
            "notice": "Numerical parity only. Computation time/run ID may differ; actual host execution needs its own captured evidence."}


def verify_model_evidence(experiment, dataset):
    """Recompute saved test metrics without training or selecting another model."""
    import statistics
    from .dataset import load_dataset, samples
    from .portable import load, predict, export_saved
    from .training import metrics

    root = Path(experiment)
    database, manifest = load_dataset(dataset)
    report = read_json(root/"evaluation.json")
    ledger = read_json(Path(dataset)/"test-evaluation.json")
    model = load(root/"model.json")
    if (ledger.get("status") != "evaluated" or ledger.get("report_sha256") != digest(root/"evaluation.json")
            or report.get("dataset_manifest") != manifest or report.get("model_sha256") != digest(root/"model.json")
            or model["training_dataset_id"] != manifest["dataset_id"]
            or model["inventory_id"] != manifest["inventory_id"]
            or model["boundary_version"] != manifest["boundary_version"]
            or report.get("promoted") != model["promoted"]):
        raise ValueError("Model, dataset, evaluation and retained test ledger must agree")
    native = []
    for entry in report["native_models"]:
        path = artifact_path(root, entry["path"])
        if digest(path) != entry["sha256"]:
            raise ValueError("Saved native model checksum mismatch")
        native.append(read_json(path))
    if export_saved(native, {k: v for k, v in model.items() if k != "members"}) != model:
        raise ValueError("Portable model differs from evaluated saved members")
    test = list(samples(database, "test"))
    expected = {r["parcel_id"]: (r, predict(model, r["features"])) for r in test}
    supported = {i: v for i, v in expected.items() if not v[1]["missing"]}
    residuals = read_json(root/"spatial-residuals.json")
    rows = residuals["rows"]
    if (residuals.get("crs") != "EPSG:26916" or residuals.get("units") != "meters"
            or len(rows) != len(supported) or len({r["parcel_id"] for r in rows}) != len(rows)
            or {r["parcel_id"] for r in rows} != supported.keys()
            or set(residuals["unknown_parcel_ids"]) != expected.keys()-supported.keys()
            or len(residuals["unknown_parcel_ids"]) != len(expected)-len(supported)):
        raise ValueError("Residual support and unknown IDs must match the full test partition")
    for row in rows:
        source, prediction = supported[row["parcel_id"]]
        if (row["block"] != source["block"] or row["x"] != source["x"] or row["y"] != source["y"]
                or row["target"] != source["target"]
                or not math.isclose(row["prediction"], prediction["susceptibility"], rel_tol=0, abs_tol=1e-6)
                or not math.isclose(row["residual"], row["prediction"]-row["target"], rel_tol=0, abs_tol=1e-10)):
            raise ValueError("Saved residual differs from its dataset or portable inference")
    recomputed = metrics(rows, [r["prediction"] for r in rows])
    development = list(samples(database, "development"))
    mean = statistics.mean(r["target"] for r in development)
    mean_metrics = metrics(rows, [mean]*len(rows))

    def agrees(left, right):
        if isinstance(left, dict):
            return isinstance(right, dict) and left.keys() == right.keys() and all(agrees(v, right[k]) for k, v in left.items())
        if left is None:
            return right is None
        return type(right) in (int, float) and math.isclose(left, right, rel_tol=0, abs_tol=1e-8)

    if (not agrees(recomputed, report["test"]["model"]) or not agrees(mean_metrics, report["test"]["constant_mean"])
            or report["test"]["test_total"] != len(test) or report["test"]["scored_count"] != len(rows)
            or report["test"]["unknown_count"] != len(test)-len(rows)
            or not math.isclose(report["test"]["coverage"], len(rows)/len(test), rel_tol=0, abs_tol=1e-10)):
        raise ValueError("Recomputed metrics/counts differ from the saved evaluation")
    return {"status": "verified_model_metrics", "model_sha256": digest(root/"model.json"),
            "evaluation_sha256": digest(root/"evaluation.json"), "residuals_sha256": digest(root/"spatial-residuals.json"),
            "dataset_id": manifest["dataset_id"], "model": recomputed, "constant_mean": mean_metrics,
            "ridge": {"status": "recorded_only", "metrics": report["test"]["ridge"]},
            "test_total": len(test), "supported": len(rows), "unknown": len(test)-len(rows),
            "notice": "Saved mapping-proxy arithmetic and portable predictions verified. Ridge predictions were not saved; their metrics remain recorded only. No retraining, new model selection or observed-flood evaluation."}
