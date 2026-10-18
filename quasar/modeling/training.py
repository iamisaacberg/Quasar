"""Explicit local experiments. Imports ML dependencies only inside training calls."""
import json
import math
import platform
import statistics
from pathlib import Path

from . import FEATURES, NOTICE, TARGET, digest, utcnow, write_json, read_json
from .dataset import load_dataset, samples
from .portable import export_saved, predict


def metrics(rows, predicted):
    if not rows or len(rows) != len(predicted):
        raise ValueError("Nonempty aligned evaluation rows required")
    errors = [float(p)-float(r["target"]) for r, p in zip(rows, predicted)]
    groups = {}
    for row, err in zip(rows, errors):
        groups.setdefault(row["block"], []).append(err)
    parcel = {"mae": statistics.mean(abs(e) for e in errors),
              "rmse": math.sqrt(statistics.mean(e*e for e in errors))}
    block = {"mae": statistics.mean(statistics.mean(abs(e) for e in g) for g in groups.values()),
             "rmse": math.sqrt(statistics.mean(statistics.mean(e*e for e in g) for g in groups.values()))}
    ranges = {}
    for name, low, high in (("zero", 0, 0), ("partial", 0, 1), ("one", 1, 1)):
        chosen = [e for r, e in zip(rows, errors) if (r["target"] == low if low == high else low < r["target"] < high)]
        ranges[name] = {"count": len(chosen), "mae": statistics.mean(map(abs, chosen)) if chosen else None}
    return {"parcel": parcel, "equal_block": block, "target_ranges": ranges, "count": len(rows)}


def train(directory, output):
    # Load native libraries before threadpoolctl discovers/limits their pools.
    import numpy
    import xgboost
    import sklearn.linear_model
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=3):
        return _train(directory, output)


def _train(directory, output):
    import numpy as np
    import sklearn
    import xgboost as xgb
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    database, manifest = load_dataset(directory)
    if (Path(directory)/"test-evaluation.json").exists():
        raise FileExistsError("This dataset's untouched test is already reserved/evaluated")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    development, validation = list(samples(database, "development")), list(samples(database, "validation"))
    if len({r["block"] for r in development}) < 5 or not validation:
        raise ValueError("Five development blocks and a nonempty validation set required")
    if len({r["target"] for r in development}) < 2:
        raise ValueError("Training target has no variation")
    X = np.asarray([r["features"] for r in development], dtype=np.float32)
    y = np.asarray([r["target"] for r in development])
    VX = np.asarray([r["features"] for r in validation], dtype=np.float32)
    vy = np.asarray([r["target"] for r in validation])
    groups = [r["block"] for r in development]
    dtrain = xgb.DMatrix(X, label=y, feature_names=FEATURES)
    dval = xgb.DMatrix(VX, label=vy, feature_names=FEATURES)
    candidates = []
    for depth in (2, 3, 4):
        for regularization in (1, 10):
            params = {"objective": "reg:squarederror", "eval_metric": "rmse", "max_depth": depth,
                      "lambda": regularization, "eta": .05, "seed": 42, "nthread": 3,
                      "tree_method": "hist", "subsample": .8}
            rounds, folds = [], []
            for a, b in GroupKFold(5).split(X, y, groups):
                fit = xgb.DMatrix(X[a], label=y[a], feature_names=FEATURES)
                check = xgb.DMatrix(X[b], label=y[b], feature_names=FEATURES)
                model = xgb.train(params, fit, num_boost_round=400, evals=[(check, "fold")],
                                  early_stopping_rounds=40, verbose_eval=False)
                rounds.append(model.best_iteration+1)
                folds.append(float(model.best_score))
            count = max(1, round(statistics.median(rounds)))
            model = xgb.train(params, dtrain, num_boost_round=count)
            validation_score = metrics(validation, np.clip(model.predict(dval), 0, 1))
            candidates.append({"params": params, "rounds": count, "fold_rmse": folds,
                               "validation": validation_score})
    selected = min(candidates, key=lambda c: (c["validation"]["parcel"]["rmse"], c["rounds"], c["params"]["max_depth"], c["params"]["lambda"]))
    members, saved = [], []
    for i in range(5):
        model = xgb.train({**selected["params"], "seed": 42+i}, dtrain, num_boost_round=selected["rounds"])
        path = root/f"member-{i}.json"
        model.save_model(path)
        saved.append(read_json(path))
        members.append(model)
    ranges = [[min(r["features"][i] for r in development), max(r["features"][i] for r in development)] for i in range(len(FEATURES))]
    metadata = {"model_version": "mapped-susceptibility-v1-"+digest(root/"member-0.json")[:12],
                "training_dataset_id": manifest["dataset_id"], "inventory_id": manifest["inventory_id"],
                "boundary_version": manifest["boundary_version"], "feature_ranges": ranges, "promoted": False}
    portable = export_saved(saved, metadata)
    parity_rows = development[:10000]
    native = np.mean([np.clip(m.predict(xgb.DMatrix(np.asarray([r["features"] for r in parity_rows], dtype=np.float32),
                                                     feature_names=FEATURES)), 0, 1) for m in members], axis=0)
    errors = [abs(predict(portable, r["features"])["susceptibility"]-float(p)) for r, p in zip(parity_rows, native)]
    parity = {"unique_rows": len(parity_rows), "max_absolute_error": max(errors), "tolerance": 1e-6,
              "passed": max(errors) <= 1e-6 and len(parity_rows) >= 10000}
    # Fail closed on numerical disagreement even on a deliberately small research dataset.
    if max(errors) > 1e-6:
        raise ValueError("Portable/native inference disagrees")
    test = list(samples(database, "test"))
    supported = [r for r in test if not predict(portable, r["features"])["missing"]]
    if not supported:
        raise ValueError("No supported held-out test parcels")
    ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(X, y)
    tx = np.asarray([r["features"] for r in supported], dtype=np.float32)
    predictions = [predict(portable, r["features"])["susceptibility"] for r in supported]
    baselines = {"constant_mean": [float(np.mean(y))]*len(supported), "ridge": np.clip(ridge.predict(tx), 0, 1).tolist()}
    # Exclusive dataset-level reservation prevents retraining against the same test labels.
    ledger = Path(directory)/"test-evaluation.json"
    with ledger.open("x") as reservation:
        json.dump({"status": "reserved", "experiment": str(root.resolve()), "created_at": utcnow()}, reservation)
    evaluation = {"model": metrics(supported, predictions),
                  **{name: metrics(supported, values) for name, values in baselines.items()},
                  "test_total": len(test), "scored_count": len(supported), "unknown_count": len(test)-len(supported),
                  "coverage": len(supported)/len(test)}
    improvement = all(evaluation["model"][weight]["rmse"] <= .9*evaluation[baseline][weight]["rmse"]
                      and evaluation[baseline][weight]["rmse"] > 0
                      for weight in ("parcel", "equal_block") for baseline in baselines)
    portable["promoted"] = improvement and parity["passed"] and evaluation["coverage"] >= .9
    write_json(root/"model.json", portable)
    report = {"schema_version": 1, "created_at": utcnow(), "target": TARGET, "notice": NOTICE,
              "dataset_manifest": manifest, "candidates": candidates, "selected": selected,
              "test": evaluation, "parity": parity, "promoted": portable["promoted"],
              "promotion_policy": "10% RMSE reduction over both baselines under both weights; >=90% test support; >=10000 parity rows",
              "versions": {"python": platform.python_version(), "xgboost": xgb.__version__,
                           "numpy": np.__version__, "sklearn": sklearn.__version__},
              "native_models": [{"path": f"member-{i}.json", "sha256": digest(root/f"member-{i}.json")} for i in range(5)],
              "model_sha256": digest(root/"model.json")}
    write_json(root/"evaluation.json", report)
    write_json(ledger, {"status": "evaluated", "experiment": str(root.resolve()), "report_sha256": digest(root/"evaluation.json")})
    residuals = [{"parcel_id": r["parcel_id"], "x": r["x"], "y": r["y"], "block": r["block"],
                  "target": r["target"], "prediction": p, "residual": p-r["target"]} for r, p in zip(supported, predictions)]
    supported_ids = {r["parcel_id"] for r in supported}
    write_json(root/"spatial-residuals.json", {"crs": "EPSG:26916", "units": "meters", "rows": residuals,
                                               "unknown_parcel_ids": [r["parcel_id"] for r in test if r["parcel_id"] not in supported_ids]})
    xs, ys = [r["x"] for r in residuals], [r["y"] for r in residuals]
    min_x, min_y = min(xs), min(ys)
    width, height = max(xs)-min_x or 1, max(ys)-min_y or 1
    circles = []
    for row in residuals:
        x, y = 40+700*(row["x"]-min_x)/width, 540-460*(row["y"]-min_y)/height
        color = "#dc2626" if row["residual"] > 0 else "#2563eb"
        circles.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2" fill="{color}" fill-opacity="0.5"/>')
    (root/"spatial-residuals.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">'
        '<rect width="800" height="600" fill="white"/><text x="30" y="25">Held-out FEMA mapping proxy residuals</text>'
        '<text x="30" y="48">Red: overestimate; blue: underestimate. EPSG:26916; unknowns omitted.</text>'
        + ''.join(circles) + '<text x="30" y="580">Spatial positions; not a flood observation or inundation map.</text></svg>')
    (root/"MODEL_CARD.md").write_text(
        "# Learned mapped susceptibility\n\n"+NOTICE+"\n\nTarget: "+TARGET+
        "\n\nDevelopment-only preprocessing, geographically grouped tuning, and one untouched test evaluation. "
        "The rainfall interaction is an uncalibrated visualization rule; ensemble spread is not a confidence interval. "
        "See evaluation.json for exclusions, source dates/terms, parameters, coverage, baselines and gate results. "
        "Current FEMA reference layers do not establish historical as-issued knowledge. "
        "Hydrography omits some lakes, canals and coastal waters. No gauge or floor-height model.\n\n"
        f"Promoted: {portable['promoted']}. Portable model SHA256: {report['model_sha256']}.\n")
    return report


def export(experiment, output):
    """Re-export only checksum-matched saved members and verify exact experiment parity."""
    root = Path(experiment)
    report = read_json(root/"evaluation.json")
    existing = read_json(root/"model.json")
    if digest(root/"model.json") != report["model_sha256"]:
        raise ValueError("Experiment model checksum mismatch")
    saved = []
    for entry in report["native_models"]:
        path = root/entry["path"]
        if path.parent.resolve() != root.resolve() or digest(path) != entry["sha256"]:
            raise ValueError("Native model checksum/path mismatch")
        saved.append(read_json(path))
    model = export_saved(saved, {k: v for k, v in existing.items() if k != "members"})
    if model != existing:
        raise ValueError("Re-export differs from evaluated model")
    write_json(output, model)
    return {"model_sha256": digest(output), "promoted": model["promoted"]}
