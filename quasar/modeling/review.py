"""Offline artifact lineage and exposure-method evidence; never downloads or serves data."""
import math
import sqlite3
import statistics
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import TARGET, digest, finite, label_value, read_json, utcnow, write_json
from .dataset import audit, load_dataset
from .portable import export_saved, load


def distribution(values):
    known = [x for x in values if x is not None]
    if any(not finite(x) or not 0 <= x <= 100 for x in known):
        raise ValueError("Exposure values must be finite indices")
    from ..exposure import percentile90
    counts = Counter("lower" if x < 35 else "moderate" if x < 65 else "elevated" if x < 85 else "highest" for x in known)
    return {"count": len(known), "unknown": len(values)-len(known), "mean": statistics.mean(known) if known else None,
            "min": min(known) if known else None, "max": max(known) if known else None,
            "p90": percentile90(known), "bands": {k: counts[k] for k in ("lower", "moderate", "elevated", "highest")}}


def _ranks(values):
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    ranks, at = [0.]*len(values), 0
    while at < len(ordered):
        end = at+1
        while end < len(ordered) and values[ordered[end]] == values[ordered[at]]:
            end += 1
        for i in ordered[at:end]:
            ranks[i] = (at+end-1)/2
        at = end
    return ranks


def ranking(first, second, ids):
    """Average-rank correlation; deterministic top-decile ties are disclosed."""
    if len(first) != len(second) or len(first) != len(ids) or len(set(ids)) != len(ids):
        raise ValueError("Aligned, unique parcel comparisons required")
    if not first:
        return {"count": 0, "spearman": None, "top_decile_overlap": None}
    if any(not finite(x) for x in first+second):
        raise ValueError("Finite ranking values required")
    a, b = _ranks(first), _ranks(second)
    center = (len(a)-1)/2
    denominator = math.sqrt(sum((x-center)**2 for x in a)*sum((x-center)**2 for x in b))
    count = max(1, math.ceil(.1*len(ids)))
    def top(values):
        order = sorted(range(len(ids)), key=lambda i: (-values[i], ids[i]))
        cutoff = values[order[count-1]]
        return {ids[i] for i in order[:count]}, sum(x == cutoff for x in values)
    one, ties_one = top(first)
    two, ties_two = top(second)
    return {"count": len(ids), "spearman": sum((x-center)*(y-center) for x, y in zip(a, b))/denominator if denominator else None,
            "top_decile_size": count, "top_decile_overlap": len(one & two)/count,
            "first_cutoff_ties": ties_one, "second_cutoff_ties": ties_two,
            "tie_policy": "parcel ID ascending; tied/all-zero rankings do not demonstrate useful prioritization"}


def sensitivity(records, references):
    """Known assessments only; missing FEMA labels are not reference zeroes."""
    rows = []
    for record in records:
        if record.get("score") is None:
            continue
        model = record.get("model_details")
        if model is None:
            continue
        rows.append((record["parcel_id"], model["susceptibility"], model["rainfall_6h_mm"]))
    ids = [r[0] for r in rows]
    results, reference_results = {}, {}
    for constant in (25, 50, 100):
        scores = [100*s*rain/(rain+constant) for _, s, rain in rows]
        base = [100*s*rain/(rain+50) for _, s, rain in rows]
        paired = [(identifier, score, 100*references[identifier]*rain/(rain+constant))
                  for (identifier, _, rain), score in zip(rows, scores) if identifier in references]
        results[str(constant)] = {"distribution": distribution(scores), "versus_50mm": ranking(scores, base, ids)}
        reference_results[str(constant)] = {
            "paired_count": len(paired), "reference_missing": len(rows)-len(paired),
            "model_distribution": distribution([p[1] for p in paired]),
            "direct_fema_distribution": distribution([p[2] for p in paired]),
            "comparison": ranking([p[1] for p in paired], [p[2] for p in paired], [p[0] for p in paired])}
    return {"notice": "Method/sensitivity comparisons, not observed flood validation. The 50 mm serving rule is unchanged.",
            "scored": len(rows), "unknown_or_without_diagnostics": len(records)-len(rows),
            "constants_mm": results, "direct_fema_reference": reference_results,
            "analytical_checks": {"notice": "Constructed formula checks, not observed rainfall or real flood outcomes.",
                "zero_rain_score": 0, "score_cap": "100 * learned mapped fraction",
                "example_fraction": .2, "example_cap": 20,
                "example_1000000mm_score": 100*.2*1000000/(1000000+50),
                "omitted_mechanisms": ["storm surge", "drainage capacity", "floor height", "observed water levels"]}}


def write_experiment_summary(root, report, oof):
    """Small committed-source report generator; private parcel rows stay ignored."""
    root = Path(root)
    lines = ["# FEMA mapping-proxy experiment", "", report["notice"], "",
             f"Status: **{report['status']}**. Model SHA-256: `{report['model_sha256']}`.",
             f"Dataset: `{report['dataset_manifest']['dataset_id']}`. Protocol: `{report['evaluation_protocol']}`.",
             "", "Original test excluded. Scores measure mapped-area fraction, not event probability or flood depth.",
             "", "| Method | MAE | RMSE | Equal-block RMSE | Macro subgroup MAE | Fully mapped MAE |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    def number(value):
        return f"{value:.6f}" if value is not None else "Unavailable"
    for method, result in report["comparisons"].items():
        lines.append(f"| {method} | {number(result['parcel']['mae'])} | {number(result['parcel']['rmse'])} | "
                     f"{number(result['equal_block']['rmse'])} | {number(result['macro_subgroup_mae'])} | {number(result['target_ranges']['one']['mae'])} |")
    if report.get("inference_population") == "positive_fema_overlap":
        lines += ["", f"Positive-overlap population only: {report['research_pool_count']} included; "
                  f"{report['excluded_zero_count']} original research zero-overlap parcels excluded. "
                  "Macro MAE averages partial/full only. No countywide or flood-outcome skill is established."]
    from .v2 import target_group
    support = {}
    lines += ["", "## Target-group support", "", "| Group | Held | Supported | Unknown |", "| --- | ---: | ---: | ---: |"]
    for group in ("zero", "partial", "one"):
        selected = [r for r in oof if target_group(r["target"]) == group]
        count = sum(r["predictions"]["candidate"] is not None for r in selected)
        support[group] = {"total": len(selected), "supported": count, "unknown": len(selected)-count}
        lines.append(f"| {group} | {len(selected)} | {count} | {len(selected)-count} |")
    write_json(root/"support.json", support)
    lines += ["", "## Frozen gates", ""]+[f"- {name}: {'passed' if passed else 'failed'}" for name, passed in report["gates"].items()]
    lines += ["", "## Geographic fold variation", "", "| Fold | Supported / held | MAE | RMSE | Macro subgroup MAE | Fully mapped MAE |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for fold in read_json(root/"folds.json"):
        result = fold["metrics"]["candidate"]
        lines.append(f"| {fold['fold']} | {len(fold['supported'])}/{len(fold['held'])} | {number(result['parcel']['mae'])} | "
                     f"{number(result['parcel']['rmse'])} | {number(result['macro_subgroup_mae'])} | {number(result['target_ranges']['one']['mae'])} |")
    lines += ["", "## Interpretation", "",
              "The learned model estimates mapping from independent terrain/area/stream inputs. Actual FEMA coverage remains the reference where available. "
              "Better mapping reconstruction does not establish added flood-prediction value over using that reference directly.", "",
              "Terrain-only uses four elevation summaries; stream-only uses distance. Combined also includes parcel area. "
              "Ablations share the candidate's inner-selected settings and outer support; they are not separately optimized.", "",
              "See folds.json for geographic variation and subgroup support; out-of-fold.json for reference-versus-predicted fractions. "
              "Ensemble spread is not a confidence interval. The 50 mm rainfall constant remains uncalibrated."]
    (root/"MODEL_CARD.md").write_text("\n".join(lines)+"\n")
    known = [r for r in oof if r["predictions"]["candidate"] is not None]
    blocks = {}
    for row in known:
        blocks.setdefault(row["block"], []).append(row["predictions"]["candidate"]-row["target"])
    write_json(root/"block-residuals.json", {"units": "FEMA mapped-area fraction", "notice": "Not flood outcomes.",
        "blocks": {b: {"count": len(errors), "mean_residual": statistics.mean(errors),
                       "mae": statistics.mean(abs(e) for e in errors), "rmse": math.sqrt(statistics.mean(e*e for e in errors))}
                   for b, errors in blocks.items()}})
    if known:
        xs, ys = [r["x"] for r in known], [r["y"] for r in known]
        low_x, low_y, width, height = min(xs), min(ys), max(xs)-min(xs) or 1, max(ys)-min(ys) or 1
        circles = []
        for r in known:
            color = "#dc2626" if r["predictions"]["candidate"] > r["target"] else "#2563eb"
            circles.append(f'<circle cx="{40+700*(r["x"]-low_x)/width:.2f}" cy="{540-460*(r["y"]-low_y)/height:.2f}" r="2" fill="{color}" fill-opacity="0.4"/>')
        (root/"spatial-residuals.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">'
            '<rect width="800" height="600" fill="white"/><text x="25" y="25">Out-of-fold FEMA mapping residuals; not flood observations</text>'
            + ''.join(circles)+'<text x="25" y="580">EPSG:26916; red overestimate, blue underestimate; unknowns omitted</text></svg>')


def research_exposure(model, inspection, weather_path, references):
    """Research-only summaries for the pool, including rejected candidates.

    No assessment-schema artifacts are published. Static predictions are computed
    once; original test parcels are skipped before decoding their input records.
    """
    import json
    from ..parcel_context import readonly
    from . import feature_values
    from .portable import predict
    from .production import weather_window, parcel_rainfall
    weather = read_json(weather_path)
    weather_hash = digest(weather_path)
    static = []
    with closing(readonly(Path(inspection)/"inspection.sqlite3")) as db:
        for identifier, raw in db.execute("SELECT identifier,context_json FROM inspection WHERE kind='parcel' ORDER BY identifier"):
            identifier = int(identifier)
            if identifier not in references:
                continue
            context = json.loads(raw)
            if context.get("county_fips") != "12091" or context.get("parcel_id") != identifier:
                raise ValueError("Research inspection identity mismatch")
            values, missing = feature_values(context["inputs"])
            predicted = predict(model, values) if not missing else {"missing": missing}
            static.append((identifier, predicted.get("susceptibility") if not predicted["missing"] else None, context["forecast_overlaps"]))
    if {r[0] for r in static} != set(references):
        raise ValueError("Research inspection pool incomplete")
    windows = []
    start = datetime(2026, 10, 9, 5, tzinfo=timezone.utc)
    for hour in range(25):
        clock = start+timedelta(hours=hour)
        rainfall, source = weather_window(weather, clock.isoformat(), "replay", datetime.now(timezone.utc))
        source["source_sha256"] = weather_hash
        records = []
        for identifier, susceptibility, overlaps in static:
            rain = parcel_rainfall(overlaps, rainfall)
            if susceptibility is None or rain is None:
                records.append({"parcel_id": identifier, "score": None})
            else:
                records.append({"parcel_id": identifier, "score": 100*susceptibility*rain/(rain+50),
                                "model_details": {"susceptibility": susceptibility, "rainfall_6h_mm": rain}})
        windows.append({"at": clock.isoformat(), "forecast": source, "sensitivity": sensitivity(records, references)})
    return {"scope": "Research pool only; original test excluded. Summary comparisons, not serveable assessments or flood validation.",
            "candidate_promoted": model["promoted"], "windows": windows}


def review(output, *, dataset=None, experiment=None, database=None, inputs=None, boundary=None,
           inspection=None, weather=None, assessments=None, research_sensitivity=False):
    """Inventory even a missing bundle. A report never asserts current host status."""
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    supplied = {"dataset": dataset, "experiment": experiment, "database": database, "inputs": inputs,
                "boundary": boundary, "inspection": inspection, "weather": weather, "assessments": assessments}
    items, blockers = {}, []
    for name, path in supplied.items():
        exists = path is not None and Path(path).exists()
        items[name] = {"path": str(path) if path is not None else None, "status": "present" if exists else "missing"}
        if not exists:
            blockers.append(name+" missing")
    report = {"schema_version": 1, "created_at": utcnow(), "county_fips": "12091", "target": TARGET,
              "inventory": items, "blockers": blockers, "host_status": "not checked; local artifact verification only",
              "historical_records": {"local_report": {"model_sha256": "c3896f84e4593bbe20af909aade20edf7d46e43459b79e7aa79d5dc13188457f",
                                                        "dataset_id": "447374887feed64c7d11918aca14fff9715fedaf4eebdda48ed5cde98ba93f87"},
                  "activation_record": {"model_sha256": "5fbfe10500f05e1b5fbd16ebc622b52596489aa19aea479ab063cf872d0535a7",
                                        "dataset_id": "8ab0884720f21ce9fe492b8c1aabe317e28850f82857ab0dff880a3a1c057179"},
                  "notice": "Recorded documents only; matching artifacts must establish lineage. No metrics transferred between identities."}}
    def verify(name, action):
        try:
            result = action()
            report[name] = result
            return result
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
            report[name] = {"status": "invalid", "message": str(exc)}
            blockers.append(name+": "+str(exc))
            return None
    audited = None
    if all(items[n]["status"] == "present" for n in ("database", "inputs", "boundary", "inspection")):
        audited = verify("source_audit", lambda: audit(database, inputs, boundary, inspection))
        if audited and audited["status"] != "verified":
            blockers.append("source audit not verified")
    manifest = None
    if items["dataset"]["status"] == "present":
        loaded = verify("dataset_identity", lambda: {"status": "verified", "manifest": load_dataset(dataset)[1],
            "test_ledger_sha256": digest(Path(dataset)/"test-evaluation.json") if (Path(dataset)/"test-evaluation.json").exists() else None})
        manifest = loaded.get("manifest") if loaded else None
        if loaded and loaded["test_ledger_sha256"] is None:
            blockers.append("original test ledger unavailable; not synthesized or reused")
        if manifest and audited and audited.get("status") == "verified" and any(manifest.get(k) != audited[k] for k in ("inventory_id", "boundary_version", "checksums")):
            blockers.append("dataset/source identity mismatch")
    model = evaluation = None
    if items["experiment"]["status"] == "present":
        def bundle():
            nonlocal model, evaluation
            model = load(Path(experiment)/"model.json")
            evaluation = read_json(Path(experiment)/"evaluation.json")
            if (evaluation["model_sha256"] != digest(Path(experiment)/"model.json")
                    or evaluation["dataset_manifest"]["dataset_id"] != model["training_dataset_id"]
                    or evaluation.get("promoted") is not model["promoted"]):
                raise ValueError("Model/evaluation identity or promotion mismatch")
            if manifest and model["training_dataset_id"] != manifest["dataset_id"]:
                raise ValueError("Bundle uses a different dataset; do not substitute its metrics")
            if audited and audited.get("status") == "verified" and any(model[k] != audited[k] for k in ("inventory_id", "boundary_version")):
                raise ValueError("Model/source identity mismatch")
            if audited and audited.get("status") == "verified" and evaluation["dataset_manifest"].get("checksums") != audited["checksums"]:
                raise ValueError("Evaluation/source snapshot mismatch")
            saved = []
            missing_native = []
            for entry in evaluation["native_models"]:
                path = Path(experiment)/entry["path"]
                if not path.exists():
                    missing_native.append(entry["path"])
                    continue
                if path.resolve().parent != Path(experiment).resolve() or digest(path) != entry["sha256"]:
                    raise ValueError("Native model path/checksum mismatch")
                saved.append(read_json(path))
            if missing_native:
                blockers.append("native model files missing: "+", ".join(missing_native))
            elif export_saved(saved, {k: v for k, v in model.items() if k != "members"}) != model:
                raise ValueError("Native re-export differs from portable weights")
            if model.get("evaluation_protocol"):
                from .v2 import POSITIVE_PROTOCOL, protocol_for, protocol_hash, verify_evaluation
                protocol = protocol_for(model["evaluation_protocol"])
                if (evaluation.get("evaluation_protocol") != protocol["id"]
                        or evaluation.get("protocol_sha256") != protocol_hash(protocol)
                        or read_json(Path(experiment)/"protocol.json") != protocol):
                    raise ValueError("V2 frozen protocol identity mismatch")
                if protocol.get("inference_population") == "positive_fema_overlap":
                    if digest(Path(experiment)/"population.json") != evaluation["population_sha256"]:
                        raise ValueError("Positive-only population checksum mismatch")
                    population = read_json(Path(experiment)/"population.json")
                    from .v2 import research_rows
                    if dataset:
                        original = research_rows(dataset)[0]
                        if (population["parent_dataset_id"] != manifest["dataset_id"]
                                or population["included_ids"] != [r["parcel_id"] for r in original if r["target"] > 0]
                                or population["excluded_zero_ids"] != [r["parcel_id"] for r in original if r["target"] == 0]
                                or len(population["excluded_zero_ids"]) != evaluation["excluded_zero_count"]):
                            raise ValueError("Positive-only research population mismatch")
                if model["promoted"]:
                    verify_evaluation(model, evaluation)
                for name, key in (("folds.json", "folds_sha256"), ("out-of-fold.json", "out_of_fold_sha256")):
                    if digest(Path(experiment)/name) != evaluation[key]:
                        raise ValueError("V2 saved evidence checksum mismatch")
            return {"status": "verified", "model_version": model["model_version"], "model_sha256": evaluation["model_sha256"],
                    "training_dataset_id": model["training_dataset_id"], "evaluation_sha256": digest(Path(experiment)/"evaluation.json"),
                    **({"inference_population": model["inference_population"]} if "inference_population" in model else {}),
                    "promoted": model["promoted"], "evaluation_protocol": evaluation.get("evaluation_protocol", "v1 recorded test")}
        if verify("model_lineage", bundle) is None:
            model = evaluation = None
        elif not model["promoted"]:
            blockers.append("candidate research-only; not eligible for serving")
    references = {}
    if audited and audited.get("status") == "verified":
        import json
        from ..parcel_context import readonly
        pool_ids = None
        if manifest:
            from .v2 import research_rows
            pool_ids = {r["parcel_id"] for r in research_rows(dataset, positive_only=bool(model and model.get("inference_population") == "positive_fema_overlap"))[0]}
        with closing(readonly(Path(inputs)/"parcel-inputs.sqlite3")) as db:
            for identifier, raw in db.execute("SELECT parcel_id,inputs_json FROM parcel_inputs"):
                if pool_ids is not None and identifier not in pool_ids:
                    continue
                value = label_value(json.loads(raw))
                if value is not None:
                    references[identifier] = value
    if items["weather"]["status"] == "present":
        def verify_weather():
            from ..adapters.county_weather import validate
            data = read_json(weather)
            validate(data)
            source_hash = digest(weather)
            if items["inspection"]["status"] == "present" and source_hash not in {r["sha256"] for r in read_json(Path(inspection)/"manifest.json")["provenance"]["weather"]}:
                raise ValueError("Forecast not verified by inspection preparation")
            if boundary and data["county_geometry"] != read_json(boundary)["features"][0]["geometry"]:
                raise ValueError("Forecast boundary mismatch")
            return {"status": "verified", "sha256": source_hash, "kind": data["kind"],
                    "retrieved_at": data["retrieved_at"], "native_resolution": data["native_resolution"]}
        verify("forecast", verify_weather)
    if research_sensitivity:
        if (model is not None and manifest is not None and audited and audited.get("status") == "verified"
                and report.get("forecast", {}).get("status") == "verified"):
            verify("research_sensitivity", lambda: research_exposure(model, inspection, weather, references))
        else:
            blockers.append("research sensitivity requires a verified model/source/pool/forecast bundle")
    windows = []
    if items["assessments"]["status"] == "present" and model is not None and items["database"]["status"] == "present":
        from .. import exposure
        from .contracts import metadata
        from .production import benchmark
        first = datetime(2026, 10, 9, 5, tzinfo=timezone.utc)
        for hour in range(25):
            start = first+timedelta(hours=hour)
            path = Path(assessments)/(start.strftime("%Y%m%dT%H%M%SZ")+".json")
            def window_check():
                data = read_json(path)
                context = metadata(data["model_metadata"])
                if context["model_sha256"] != evaluation["model_sha256"] or data["inventory_id"] != model["inventory_id"]:
                    raise ValueError("Assessment comes from different model/inventory")
                if model.get("evaluation_protocol") and (context.get("evaluation_sha256") != digest(Path(experiment)/"evaluation.json")
                        or context.get("training_dataset_id") != model["training_dataset_id"]):
                    raise ValueError("Assessment v2 lineage mismatch")
                if report.get("forecast", {}).get("sha256") != data["forecast_provenance"]["source_sha256"]:
                    raise ValueError("Assessment forecast mismatch/unverified source")
                window = data["windows"][0]
                records = window["parcels"]
                stat, db_stat = path.stat(), Path(database).stat()
                summary = exposure._aggregate(str(database), db_stat.st_size, db_stat.st_mtime_ns,
                    str(path), stat.st_size, stat.st_mtime_ns, start, start+timedelta(hours=6), 7)
                if summary is None:
                    raise ValueError("Assessment has no exact requested replay window")
                if audited and len(records) != audited["parcel_count"]:
                    raise ValueError("Assessment lacks complete inventory")
                evidence = {"status": "verified", "at": start.isoformat(), "sha256": digest(path),
                            "run_id": summary["run_id"], "sensitivity": sensitivity(records, references),
                            "scored": sum(r["score"] is not None for r in records),
                            "unknown": sum(r["score"] is None for r in records)}
                # The aggregation benchmark validates all four resolutions without a service.
                benchmark(database, path, root/(path.stem+".benchmark.json"))
                exposure._artifact.cache_clear()
                exposure._aggregate.cache_clear()
                return evidence
            result = verify("window_"+str(hour), window_check)
            if result:
                windows.append(result)
    report["verified_window_count"] = len(windows)
    if items["assessments"]["status"] == "present" and len(windows) != 25:
        blockers.append("25 exact replay windows not verified")
    report["status"] = "verified" if not blockers else "incomplete"
    write_json(root/"review.json", report)
    lines = ["# Exposure artifact review", "", f"Status: **{report['status']}**. County: 12091.",
             "", "This is a local artifact review, not a live host check or flood-outcome validation.",
             "", "## Blockers", ""]+(["- "+b for b in blockers] or ["- None in the supplied local bundle."])
    lines += ["", "## Lineage", "", "See review.json for verified identities and the two distinct historical records. "
              "Metrics belong only to their matching weights and dataset. V1 is an archived comparator, not an automatic serving fallback.",
              "", f"Exact replay windows verified: {len(windows)}/25."]
    (root/"REVIEW.md").write_text("\n".join(lines)+"\n")
    return report
