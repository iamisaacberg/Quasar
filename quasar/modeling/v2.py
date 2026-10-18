"""One preregistered, buffered nested spatial experiment on the existing FEMA proxy.

Optional native libraries are imported only by explicit research commands. The
original test partition and its evaluation ledger are never used for selection.
"""
import hashlib
import json
import math
import platform
import statistics
import time
import zlib
from collections import Counter
from contextlib import closing
from pathlib import Path

from . import FEATURES, NOTICE, TARGET, digest, feature_values, label_value, read_json, utcnow, write_json
from .dataset import audit, load_dataset, samples
from .portable import export_saved, predict
from .training import metrics

PROTOCOL_ID = "mapping-proxy-nested-spatial-v2"
PROTOCOL = {
    "id": PROTOCOL_ID, "county_fips": "12091", "target": TARGET,
    "features": FEATURES, "pool": ["development", "validation"],
    "original_test": "excluded; existing ledger preserved",
    "outer_folds": 5, "inner_folds": 3, "block_m": 10000,
    "buffer_m": 1000, "crs": "EPSG:26916", "seeds": [42, 43, 44, 45, 46],
    "depths": [2, 3, 4], "l2": [1, 10], "eta": .05,
    "max_rounds": 400, "early_stopping_rounds": 40, "threads": 3,
    "weights": "min(5, n/(nonempty_groups * group_n)), then normalize to mean 1; fit rows only",
    "candidate_selection": "mean zero/partial/full MAE; then rounds, depth, L2",
    "comparator_selection": "parcel RMSE; then rounds, depth, L2",
    "ablation": "same outer split and candidate inner-selected settings; terrain=0:4, stream=5, combined=all six",
    "gates": {"subgroup_mae_ratio": .9, "full_mae_ratio": .9, "rmse_max_ratio": 1.05,
              "baseline_rmse_ratio": .9, "support_min": .9,
              "parity_rows_min": 10000, "parity_error_max": 1e-6},
    "notice": "Existing research data cross-validation; neither an untouched external test nor flood-outcome skill."
}


def protocol_hash():
    return hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def target_group(target):
    return "zero" if target == 0 else "one" if target == 1 else "partial"


def balanced_weights(rows):
    """Call separately for each fit; neither held-out prevalence nor targets enter."""
    if not rows:
        raise ValueError("Nonempty training rows required")
    counts = Counter(target_group(r["target"]) for r in rows)
    weights = [min(5., len(rows)/(len(counts)*counts[target_group(r["target"])])) for r in rows]
    mean = statistics.mean(weights)
    return [w/mean for w in weights]


def summarize(rows, predicted):
    result = metrics(rows, predicted)
    group_maes = [result["target_ranges"][name]["mae"] for name in ("zero", "partial", "one")]
    result["macro_subgroup_mae"] = statistics.mean(group_maes) if all(v is not None for v in group_maes) else None
    return result


def acceptance(comparisons, parity, coverage):
    """Only the frozen engineering policy can promote a candidate."""
    candidate, old = comparisons["candidate"], comparisons["unweighted"]
    def ratio(a, b, maximum):
        return type(a) in (int, float) and type(b) in (int, float) and math.isfinite(a) and math.isfinite(b) and b > 0 and a <= maximum*b
    gates = {
        "macro_subgroup_improvement": ratio(candidate["macro_subgroup_mae"], old["macro_subgroup_mae"], .9),
        "fully_mapped_improvement": ratio(candidate["target_ranges"]["one"]["mae"], old["target_ranges"]["one"]["mae"], .9),
        "feature_support": type(coverage) in (int, float) and .9 <= coverage <= 1,
        "portable_parity": (parity.get("passed") is True and parity.get("unique_rows", 0) >= 10000
                            and 0 <= parity.get("max_absolute_error", math.inf) <= 1e-6),
    }
    for weighting in ("parcel", "equal_block"):
        gates[weighting+"_non_regression"] = ratio(candidate[weighting]["rmse"], old[weighting]["rmse"], 1.05)
        for baseline in ("constant_mean", "ridge"):
            gates[weighting+"_beats_"+baseline] = ratio(candidate[weighting]["rmse"], comparisons[baseline][weighting]["rmse"], .9)
    return gates


def research_rows(directory):
    database, manifest = load_dataset(directory)
    # SQL filtering is deliberate: original test row JSON/targets are not loaded.
    rows = list(samples(database, "development")) + list(samples(database, "validation"))
    rows.sort(key=lambda r: r["parcel_id"])
    seen = set()
    for r in rows:
        if (type(r.get("parcel_id")) is not int or r["parcel_id"] in seen
                or r.get("split") not in PROTOCOL["pool"]
                or manifest["assignments"].get(r.get("block")) != r["split"]
                or not isinstance(r.get("features"), list) or len(r["features"]) != 6
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in r["features"])
                or any(type(r.get(k)) not in (int, float) or not math.isfinite(r[k]) for k in ("x", "y"))
                or type(r.get("target")) not in (int, float) or not 0 <= r["target"] <= 1):
            raise ValueError("Invalid research pool identity/features/target/split")
        seen.add(r["parcel_id"])
    if len({r["block"] for r in rows}) < 5 or len({target_group(r["target"]) for r in rows}) != 3:
        raise ValueError("Five research blocks and zero/partial/full targets required")
    if manifest.get("spatial_policy") != {"crs": "EPSG:26916", "block_m": 10000, "buffer_m": 1000, "seed": 42}:
        raise ValueError("Unexpected original spatial policy")
    return rows, manifest


def geometries_and_sources(rows, database, inputs, boundary):
    """Validate real polygon containment and each research row against audited inputs."""
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    from ..parcel_context import readonly
    county = shape(read_json(boundary)["features"][0]["geometry"])
    if not county.is_valid or county.is_empty:
        raise ValueError("Invalid authoritative county geometry")
    project = Transformer.from_crs("EPSG:4326", "EPSG:26916", always_xy=True).transform
    wanted = {r["parcel_id"]: r for r in rows}
    geometries = {}
    with closing(readonly(database)) as source, closing(readonly(Path(inputs)/"parcel-inputs.sqlite3")) as descriptions:
        for identifier, compressed in source.execute("SELECT parcel_id,feature_z FROM parcels ORDER BY parcel_id"):
            if identifier not in wanted:
                continue
            geom = shape(json.loads(zlib.decompress(compressed))["geometry"])
            if not geom.is_valid or geom.is_empty or not county.covers(geom):
                raise ValueError("Research parcel outside authoritative county polygon")
            projected = transform(project, geom)
            point = projected.representative_point()
            row = wanted[identifier]
            raw = descriptions.execute("SELECT inputs_json FROM parcel_inputs WHERE parcel_id=?", (identifier,)).fetchone()
            record = json.loads(raw[0]) if raw else {}
            values, missing = feature_values(record)
            if (missing or values != row["features"] or label_value(record) != row["target"]
                    or record.get("parcel_id") != identifier
                    or abs(row["x"]-point.x) > 1e-6 or abs(row["y"]-point.y) > 1e-6
                    or row["block"] != f"{math.floor(point.x/10000)}:{math.floor(point.y/10000)}"):
                raise ValueError("Research row differs from audited source features/label/block")
            geometries[identifier] = projected
    if set(geometries) != set(wanted):
        raise ValueError("Research geometry inventory incomplete")
    return geometries


def buffered_split(rows, fit_indices, held_indices, geometries):
    from shapely.strtree import STRtree
    fit, held = [rows[int(i)] for i in fit_indices], [rows[int(i)] for i in held_indices]
    if {r["block"] for r in fit} & {r["block"] for r in held}:
        raise ValueError("Geographic blocks overlap")
    index = STRtree([geometries[r["parcel_id"]] for r in held])
    excluded, retained = [], []
    for row in fit:
        (excluded if len(index.query(geometries[row["parcel_id"]], predicate="dwithin", distance=1000)) else retained).append(row)
    if len({r["block"] for r in retained}) < 3 or len({r["target"] for r in retained}) < 2:
        raise ValueError("Insufficient training blocks/variation after geographic buffering")
    return retained, held, [r["parcel_id"] for r in excluded]


def supported(fit, held):
    ranges = [[min(r["features"][i] for r in fit), max(r["features"][i] for r in fit)] for i in range(6)]
    return [r for r in held if all(lo <= v <= hi for v, (lo, hi) in zip(r["features"], ranges))]


def _matrix(rows, features, balanced=False):
    import numpy as np
    import xgboost as xgb
    return xgb.DMatrix(np.asarray([[r["features"][i] for i in features] for r in rows], dtype=np.float32),
                       label=[r["target"] for r in rows], feature_names=[FEATURES[i] for i in features],
                       weight=balanced_weights(rows) if balanced else None)


def _macro_metric(predicted, data, rows):
    # Preserve exact reference groups: float32 DMatrix labels can round a
    # nearly-full partial parcel to 1, changing its subgroup during stopping.
    score = summarize(rows,
                      [max(0., min(1., float(p))) for p in predicted])["macro_subgroup_mae"]
    if score is None:
        raise ValueError("Inner evaluation lacks zero/partial/full support")
    return "macro_subgroup_mae", score


def _select(rows, geometries, balanced):
    import xgboost as xgb
    from sklearn.model_selection import GroupKFold
    folds = []
    for a, b in GroupKFold(3).split(rows, groups=[r["block"] for r in rows]):
        fit, held, excluded = buffered_split(rows, a, b, geometries)
        eligible = supported(fit, held)
        if not eligible:
            raise ValueError("No supported inner evaluation parcels")
        folds.append((fit, eligible, {"fit": [r["parcel_id"] for r in fit],
                      "held": [r["parcel_id"] for r in held], "buffer_excluded": excluded,
                      "supported": [r["parcel_id"] for r in eligible]}))
    candidates = []
    for depth in PROTOCOL["depths"]:
        for l2 in PROTOCOL["l2"]:
            params = {"objective": "reg:squarederror", "eval_metric": "rmse", "max_depth": depth,
                      "lambda": l2, "eta": .05, "seed": 42, "nthread": 3,
                      "tree_method": "hist", "subsample": .8}
            scores, rounds = [], []
            for fit, held, _ in folds:
                check = _matrix(held, range(6))
                model = xgb.train(params, _matrix(fit, range(6), balanced), num_boost_round=400,
                                  evals=[(check, "inner")], early_stopping_rounds=40, verbose_eval=False,
                                  custom_metric=(lambda values, matrix: _macro_metric(values, matrix, held)) if balanced else None)
                rounds.append(model.best_iteration+1)
                values = [max(0., min(1., float(p))) for p in model.predict(check, iteration_range=(0, rounds[-1]))]
                result = summarize(held, values)
                scores.append(result["macro_subgroup_mae"] if balanced else result["parcel"]["rmse"])
            if any(s is None for s in scores):
                raise ValueError("Insufficient subgroup support for selection")
            candidates.append({"params": params, "rounds": max(1, round(statistics.median(rounds))),
                               "inner_score": statistics.mean(scores), "inner_fold_scores": scores})
    selected = min(candidates, key=lambda c: (c["inner_score"], c["rounds"], c["params"]["max_depth"], c["params"]["lambda"]))
    return selected, {"selected": selected, "candidates": candidates, "folds": [f[2] for f in folds]}


def _ensemble(fit, held, selected, balanced, features=range(6)):
    import numpy as np
    import xgboost as xgb
    train_matrix, check = _matrix(fit, features, balanced), _matrix(held, features)
    members = [xgb.train({**selected["params"], "seed": seed}, train_matrix, num_boost_round=selected["rounds"])
               for seed in PROTOCOL["seeds"]]
    values = np.mean([np.clip(m.predict(check), 0, 1) for m in members], axis=0).tolist()
    return members, values


def _experiment(rows, geometries):
    import numpy as np
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    methods = ("candidate", "unweighted", "constant_mean", "ridge", "terrain_only", "stream_only")
    predictions = {name: [] for name in methods}
    scored, folds, records = [], [], []
    for number, (a, b) in enumerate(GroupKFold(5).split(rows, groups=[r["block"] for r in rows])):
        fit, held, excluded = buffered_split(rows, a, b, geometries)
        eligible = supported(fit, held)
        if not eligible:
            raise ValueError("No supported outer evaluation parcels")
        candidate, candidate_selection = _select(fit, geometries, True)
        unweighted, old_selection = _select(fit, geometries, False)
        values = {}
        for name, selection, balance, features in (
            ("candidate", candidate, True, range(6)), ("unweighted", unweighted, False, range(6)),
            ("terrain_only", candidate, True, range(4)), ("stream_only", candidate, True, [5])):
            _, values[name] = _ensemble(fit, eligible, selection, balance, features)
        values["constant_mean"] = [statistics.mean(r["target"] for r in fit)]*len(eligible)
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(
            np.asarray([r["features"] for r in fit], dtype=np.float32), [r["target"] for r in fit])
        values["ridge"] = np.clip(ridge.predict(np.asarray([r["features"] for r in eligible], dtype=np.float32)), 0, 1).tolist()
        fold_metrics = {name: summarize(eligible, values[name]) for name in methods}
        folds.append({"fold": number, "fit": [r["parcel_id"] for r in fit],
                      "held": [r["parcel_id"] for r in held], "buffer_excluded": excluded,
                      "supported": [r["parcel_id"] for r in eligible], "support": len(eligible)/len(held),
                      "metrics": fold_metrics, "candidate_selection": candidate_selection,
                      "unweighted_selection": old_selection})
        positions = {r["parcel_id"]: i for i, r in enumerate(eligible)}
        for row in held:
            position = positions.get(row["parcel_id"])
            records.append({k: row[k] for k in ("parcel_id", "block", "target", "x", "y")} |
                           {"fold": number, "missing": [] if position is not None else ["outside_fold_training_ranges"],
                            "predictions": {name: values[name][position] if position is not None else None for name in methods}})
        scored.extend(eligible)
        for name in methods:
            predictions[name].extend(values[name])
    return {name: summarize(scored, values) for name, values in predictions.items()}, folds, records, len(scored)/len(rows)


def train_v2(dataset, database, inputs, boundary, inspection, output):
    """New experiment ledger; never overwrites the original dataset/test ledger."""
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    write_json(root/"protocol.json", PROTOCOL)
    began = time.perf_counter()
    ledger = None
    try:
        import numpy
        import sklearn
        import xgboost
        from threadpoolctl import threadpool_limits
        audited = audit(database, inputs, boundary, inspection)
        if audited["status"] != "verified":
            raise ValueError("Missing source bundle: "+json.dumps(audited))
        rows, manifest = research_rows(dataset)
        if any(manifest.get(k) != audited[k] for k in ("inventory_id", "boundary_version", "checksums")):
            raise ValueError("Dataset source identity/checksums differ from audited inputs")
        geometry = geometries_and_sources(rows, database, inputs, boundary)
        old_ledger = Path(dataset)/"test-evaluation.json"
        old_hash = digest(old_ledger) if old_ledger.exists() else None
        ledger = Path(dataset)/"v2-experiment.json"
        # One controlled experiment per original dataset, even after a failure.
        with ledger.open("x") as stream:
            json.dump({"status": "reserved", "output": str(root.resolve()),
                       "protocol_sha256": protocol_hash(), "created_at": utcnow()}, stream)
        with threadpool_limits(limits=3):
            comparisons, folds, oof, coverage = _experiment(rows, geometry)
            write_json(root/"folds.json", folds)
            write_json(root/"out-of-fold.json", {"notice": PROTOCOL["notice"], "records": oof})
            selection, final_tuning = _select(rows, geometry, True)
            parity_rows = rows[:10000]
            members, native = _ensemble(rows, parity_rows, selection, True)
        saved = []
        for number, member in enumerate(members):
            member.save_model(root/f"member-{number}.json")
            saved.append(read_json(root/f"member-{number}.json"))
        member_hashes = [digest(root/f"member-{i}.json") for i in range(5)]
        identity = hashlib.sha256((manifest["dataset_id"]+protocol_hash()+"".join(member_hashes)).encode()).hexdigest()[:12]
        model = export_saved(saved, {"model_version": "mapped-susceptibility-v2-"+identity,
            "training_dataset_id": manifest["dataset_id"], "inventory_id": manifest["inventory_id"],
            "boundary_version": manifest["boundary_version"], "evaluation_protocol": PROTOCOL_ID,
            "feature_ranges": [[min(r["features"][i] for r in rows), max(r["features"][i] for r in rows)] for i in range(6)],
            "promoted": False})
        errors = [abs(predict(model, r["features"])["susceptibility"]-p) for r, p in zip(parity_rows, native)]
        parity = {"unique_rows": len(parity_rows), "max_absolute_error": max(errors), "tolerance": 1e-6,
                  "passed": len(parity_rows) >= 10000 and max(errors) <= 1e-6}
        gates = acceptance(comparisons, parity, coverage)
        model["promoted"] = all(gates.values())
        # Refuse publication if the immutable original evidence changed mid-run.
        if (old_hash != (digest(old_ledger) if old_ledger.exists() else None)
                or digest(Path(dataset)/"dataset.sqlite3") != manifest["dataset_id"]):
            raise ValueError("Original dataset/test ledger changed during v2 research")
        write_json(root/"model.json", model)
        report = {"schema_version": 1, "created_at": utcnow(), "status": "qualified" if model["promoted"] else "research_only",
                  "evaluation_protocol": PROTOCOL_ID, "protocol_sha256": protocol_hash(), "target": TARGET,
                  "notice": NOTICE+" "+PROTOCOL["notice"], "dataset_manifest": manifest,
                  "research_pool_count": len(rows), "original_test_ledger_sha256": old_hash,
                  "comparisons": comparisons, "coverage": coverage, "parity": parity, "gates": gates,
                  "promoted": model["promoted"], "model_sha256": digest(root/"model.json"),
                  "folds_sha256": digest(root/"folds.json"), "out_of_fold_sha256": digest(root/"out-of-fold.json"),
                  "final_selection": final_tuning,
                  "native_models": [{"path": f"member-{i}.json", "sha256": h} for i, h in enumerate(member_hashes)],
                  "versions": {"python": platform.python_version(), "numpy": numpy.__version__,
                               "sklearn": sklearn.__version__, "xgboost": xgboost.__version__},
                  "elapsed_seconds": time.perf_counter()-began}
        write_json(root/"evaluation.json", report)
        write_json(ledger, {"status": "evaluated", "output": str(root.resolve()),
                           "protocol_sha256": protocol_hash(), "evaluation_sha256": digest(root/"evaluation.json")})
        from .review import write_experiment_summary
        write_experiment_summary(root, report, oof)
        return report
    except Exception as exc:
        write_json(root/"failure.json", {"status": "unavailable", "message": str(exc),
                                        "protocol_sha256": protocol_hash(), "created_at": utcnow()})
        raise


def verify_evaluation(model, evaluation):
    """Recompute v2 gates instead of trusting a claimed promotion boolean."""
    if (model.get("evaluation_protocol") != PROTOCOL_ID or evaluation.get("evaluation_protocol") != PROTOCOL_ID
            or evaluation.get("protocol_sha256") != protocol_hash()
            or evaluation.get("status") != "qualified"):
        raise ValueError("Unknown or unqualified v2 evaluation protocol")
    gates = acceptance(evaluation["comparisons"], evaluation["parity"], evaluation["coverage"])
    if not all(gates.values()) or evaluation.get("gates") != gates or evaluation.get("promoted") is not True:
        raise ValueError("V2 engineering acceptance gates not satisfied")
    return gates
