"""Conditional observed-outcome experiment. Unreported parcels are never negatives."""
import json
import math
import statistics
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..adapters.weathernext import timestamp
from ..parcel_context import readonly
from ..replay import run_rows
from . import COUNTY, FEATURES, NOTICE, digest, finite, read_json, utcnow, write_json
from .dataset import load_dataset, samples
from .production import weather_window, parcel_rainfall

OUTCOME_FEATURES = FEATURES + ["forecast_rainfall_6h_mm", "forecast_rainfall_3h_mm", "forecast_peak_hourly_mm"]


def prepare_outcomes(dataset, observations, inspection, weather_files):
    database, manifest = load_dataset(dataset)
    labels = read_json(observations)
    im = read_json(Path(inspection)/"manifest.json")
    if (labels.get("schema_version") != 1 or labels.get("county_fips") != COUNTY
            or labels.get("inventory_id") != manifest["inventory_id"]
            or labels.get("boundary_version") != manifest["boundary_version"]
            or im.get("inventory_id") != manifest["inventory_id"] or im.get("boundary_version") != manifest["boundary_version"]
            or im.get("database_sha256") != digest(Path(inspection)/"inspection.sqlite3")):
        raise ValueError("Observed outcome/inspection inventory mismatch")
    inventory = {r["parcel_id"]: r for r in samples(database)}
    snapshots = {digest(p): read_json(p) for p in weather_files}
    allowed = {r["sha256"] for r in im["provenance"]["weather"]}
    if not snapshots.keys() <= allowed:
        raise ValueError("Forecasts not verified by inspection preparation")
    if not isinstance(labels.get("records"), list):
        raise ValueError("Observed records required")
    counts, rows, seen, windows = Counter(), [], set(), {}
    with closing(readonly(Path(inspection)/"inspection.sqlite3")) as contexts:
        for record in labels["records"]:
            parcel, episode, at = record.get("parcel_id"), record.get("episode_id"), record.get("at")
            if type(parcel) is not int or parcel not in inventory or not isinstance(episode, str) or not episode:
                raise ValueError("Invalid observed parcel/episode")
            clock = timestamp(at)
            record_identity = (parcel, episode, clock)
            if record_identity in seen:
                raise ValueError("Duplicate parcel/episode/decision-time label")
            seen.add(record_identity)
            if record.get("label") is None:
                counts["unlabeled"] += 1
                continue
            if type(record["label"]) is not int or record["label"] not in (0, 1):
                raise ValueError("Labels must be verified 0/1 or null")
            if (record.get("association_verified") is not True or record.get("observed_coverage") is not True
                    or record.get("mechanism") != "rainfall_driven"
                    or not finite(record.get("spatial_uncertainty_m")) or record["spatial_uncertainty_m"] < 0
                    or not all(isinstance(record.get(k), str) and record[k] for k in
                               ("source_id", "source_url", "source_retrieved_at", "labeling_policy", "coverage_evidence"))):
                counts["unverified_or_unsupported"] += 1
                continue
            observed_from, observed_to = timestamp(record["observation_from"]), timestamp(record["observation_to"])
            timestamp(record["source_retrieved_at"])
            if not clock <= observed_from <= observed_to <= clock+timedelta(hours=6):
                raise ValueError("Observed labels must belong to the next six-hour window")
            if record["label"] == 0 and (observed_from != clock or observed_to != clock+timedelta(hours=6)):
                counts["negative_window_not_fully_observed"] += 1
                continue
            reference = record.get("reference_mode")
            if reference == "as_issued":
                if timestamp(record["reference_available_at"]) > clock:
                    raise ValueError("Future reference information leaks into outcome predictors")
            elif reference != "current_reference_retrospective":
                raise ValueError("Declare historical reference availability or retrospective limitations")
            source_hash = record.get("forecast_sha256")
            if source_hash not in snapshots:
                raise ValueError("Label references an unavailable forecast snapshot")
            window_identity = (source_hash, at)
            if window_identity not in windows:
                rainfall, forecast = weather_window(snapshots[source_hash], at, "replay", datetime.now(timezone.utc))
                run = next(r for r in snapshots[source_hash]["runs"] if r["init_time"] == forecast["init_time"])
                native_ids = {c["id"] for c in snapshots[source_hash]["native_cells"]}
                hourly = run_rows(run, allowed=native_ids)
                windows[window_identity] = rainfall, forecast, hourly, native_ids
            rainfall, forecast, hourly, native_ids = windows[window_identity]
            raw = contexts.execute("SELECT context_json FROM inspection WHERE kind='parcel' AND identifier=?", (str(parcel),)).fetchone()
            context = json.loads(raw[0]) if raw else {}
            rain = parcel_rainfall(context.get("forecast_overlaps"), rainfall)
            hourly_values = [parcel_rainfall(context.get("forecast_overlaps"), {
                native: hourly.get((native, (clock+timedelta(hours=h)).isoformat().replace("+00:00", "Z")), {}).get("rainfall_1h_mm")
                for native in native_ids}) for h in range(1, 7)]
            base = inventory[parcel]
            if base["features"] is None or rain is None or any(v is None for v in hourly_values):
                counts["missing_predictors"] += 1
                continue
            rows.append({"parcel_id": parcel, "episode": episode, "at": at, "block": base["block"],
                         "target": record["label"], "features": base["features"]+[rain, sum(hourly_values[:3]), max(hourly_values)], "reference_mode": reference,
                         "source_id": record["source_id"], "forecast": forecast})
    episodes = sorted({r["episode"] for r in rows}, key=lambda e: min(timestamp(r["at"]) for r in rows if r["episode"] == e))
    test = set(episodes[-3:])
    valid_count = max(1, math.ceil((len(episodes)-3)*.2))
    validation = set(episodes[-3-valid_count:-3])
    for row in rows:
        row["split"] = "test" if row["episode"] in test else "validation" if row["episode"] in validation else "development"
    support = Counter(r["target"] for r in rows)
    reasons = []
    if len(episodes) < 10:
        reasons.append("ten_independent_episodes_required")
    if support[1] < 200 or support[0] < 200:
        reasons.append("200_verified_positive_and_negative_examples_required")
    if len(test) != 3 or any({r["target"] for r in rows if r["episode"] == e} != {0, 1} for e in test):
        reasons.append("three_heldout_episodes_with_both_classes_required")
    if any({r["target"] for r in rows if r["split"] == s} != {0, 1} for s in ("development", "validation")):
        reasons.append("development_and_validation_require_both_classes")
    return rows, {"status": "ready" if not reasons else "insufficient_evidence", "reasons": reasons,
                  "episode_count": len(episodes), "positive_count": support[1], "negative_count": support[0],
                  "test_episodes": sorted(test), "validation_episodes": sorted(validation), "exclusions": dict(counts),
                  "dataset_id": manifest["dataset_id"], "observations_sha256": digest(observations),
                  "inspection_sha256": im["database_sha256"], "forecast_sha256": sorted(snapshots),
                  "features": OUTCOME_FEATURES, "notice": "Experiment gates are not statistical sufficiency or model validation."}


def classification_metrics(rows, scores):
    from sklearn.metrics import average_precision_score, precision_score, recall_score, confusion_matrix
    y = [r["target"] for r in rows]
    predicted = [int(s >= .5) for s in scores]
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {"count": len(rows), "average_precision": float(average_precision_score(y, scores)),
            "precision_at_0_5": float(precision_score(y, predicted, zero_division=0)),
            "recall_at_0_5": float(recall_score(y, predicted, zero_division=0)),
            "false_alarms": int(fp), "missed_impacts": int(fn), "true_positive": int(tp), "true_negative": int(tn)}


def train_outcomes(dataset, observations, inspection, weather_files, output):
    import numpy
    import xgboost
    import sklearn.linear_model
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=3):
        return _train_outcomes(dataset, observations, inspection, weather_files, output)


def _train_outcomes(dataset, observations, inspection, weather_files, output):
    if (Path(dataset)/"outcome-test-evaluation.json").exists():
        raise FileExistsError("This dataset's outcome test is already reserved/evaluated")
    rows, readiness = prepare_outcomes(dataset, observations, inspection, weather_files)
    if readiness["status"] != "ready":
        raise ValueError("Outcome training disabled: "+json.dumps(readiness))
    import numpy as np
    import xgboost as xgb
    import sklearn
    import platform
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    # A separate geographic holdout is never used for tuning, regardless of episode.
    blocks = sorted({r["block"] for r in rows})
    if len(blocks) < 5:
        raise ValueError("At least five spatial blocks needed for the separate spatial holdout")
    spatial = set(blocks[::5])
    development = [r for r in rows if r["split"] == "development" and r["block"] not in spatial]
    validation = [r for r in rows if r["split"] == "validation" and r["block"] not in spatial]
    test = [r for r in rows if r["split"] == "test" and r["block"] not in spatial]
    spatial_rows = [r for r in rows if r["block"] in spatial]
    if any({r["target"] for r in group} != {0, 1} for group in (development, validation, test, spatial_rows)):
        raise ValueError("Each event/spatial partition must retain both classes")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    def X(group): return np.asarray([r["features"] for r in group], dtype=np.float32)
    def Y(group): return np.asarray([r["target"] for r in group])
    logistic = make_pipeline(StandardScaler(), LogisticRegression(C=1., max_iter=1000, random_state=42)).fit(X(development), Y(development))
    candidates = []
    for depth in (2, 3, 4):
        for regularization in (1, 10):
            classifier = xgb.XGBClassifier(max_depth=depth, reg_lambda=regularization, n_estimators=200,
                                          learning_rate=.05, subsample=.8, n_jobs=3, random_state=42)
            classifier.fit(X(development), Y(development))
            score = classification_metrics(validation, classifier.predict_proba(X(validation))[:, 1])
            candidates.append((score["average_precision"], -depth, -regularization, classifier))
    selected = max(candidates, key=lambda c: c[:3])[-1]
    ledger = Path(dataset)/"outcome-test-evaluation.json"
    with ledger.open("x") as reservation:
        json.dump({"status": "reserved", "created_at": utcnow(), "observations_sha256": readiness["observations_sha256"]}, reservation)
    report = {"readiness": readiness, "created_at": utcnow(), "promoted": False,
              "versions": {"python": platform.python_version(), "xgboost": xgb.__version__, "sklearn": sklearn.__version__, "numpy": np.__version__},
              "selected_parameters": {k: selected.get_params()[k] for k in
                                      ("max_depth", "reg_lambda", "n_estimators", "learning_rate", "subsample", "n_jobs", "random_state")},
              "decision_threshold": .5,
              "notice": "Research comparison only; no automatic activation or probability/depth claim.",
              "validation_candidates": [{"average_precision": c[0], "max_depth": -c[1], "reg_lambda": -c[2]} for c in candidates],
              "coverage": {"labeled_scored": len(rows), "excluded": readiness["exclusions"]}, "evaluations": {}}
    for name, group in (("event_holdout", test), ("spatial_holdout", spatial_rows)):
        report["evaluations"][name] = {}
        for label, model in (("logistic", logistic), ("boosted_trees", selected)):
            scores = model.predict_proba(X(group))[:, 1]
            report["evaluations"][name][label] = {"overall": classification_metrics(group, scores), "per_storm": {
                episode: classification_metrics([r for r in group if r["episode"] == episode],
                                                [s for r, s in zip(group, scores) if r["episode"] == episode])
                for episode in sorted({r["episode"] for r in group})}}
    selected.save_model(root/"outcome-classifier.json")
    # Portable logistic coefficients for reproducibility, not application activation.
    scaler, reg = logistic.steps[0][1], logistic.steps[1][1]
    write_json(root/"logistic.json", {"features": OUTCOME_FEATURES, "mean": scaler.mean_.tolist(),
                                      "scale": scaler.scale_.tolist(), "coefficients": reg.coef_[0].tolist(),
                                      "intercept": float(reg.intercept_[0])})
    write_json(root/"evaluation.json", report)
    (root/"MODEL_CARD.md").write_text("# Observed-outcome research experiment\n\n"
        "Synthetic or independently reviewed observed labels must be distinguished by the operator. "
        "No automatic promotion. Scores are not displayed as flood probabilities or depths. "
        "See evaluation.json for source hashes, retrospective reference limitations, class counts, "
        "event/spatial holdouts, parameters, versions, false alarms and missed impacts. "
        "The evidence-count gates do not establish statistical sufficiency.\n")
    write_json(root/"splits.json", [{k: r[k] for k in ("parcel_id", "episode", "at", "block", "split", "reference_mode")} for r in rows])
    write_json(ledger, {"status": "evaluated", "report_sha256": digest(root/"evaluation.json")})
    return report
