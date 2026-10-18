"""Synthetic protocol/lineage checks. No county artifacts, cloud or host access."""
import copy
import importlib.util
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

from quasar import exposure
from quasar.modeling import FEATURES, NOTICE, POLICY, TARGET, digest, read_json, write_json
from quasar.modeling import contracts, production, review, v2
from quasar.modeling.portable import load
import test_modeling as fixtures
import test_county_weather as weather_fixture

OPTIONAL = all(importlib.util.find_spec(n) for n in ("shapely", "pyproj", "numpy", "sklearn", "xgboost"))


def comparison(mae=.1, rmse=.1):
    return {"macro_subgroup_mae": mae, "target_ranges": {"one": {"count": 10, "mae": mae}},
            "parcel": {"rmse": rmse}, "equal_block": {"rmse": rmse}}


def evaluation():
    comparisons = {"candidate": comparison(), "unweighted": comparison(.2, .12),
                   "constant_mean": comparison(.3, .3), "ridge": comparison(.3, .3)}
    parity = {"passed": True, "unique_rows": 10000, "max_absolute_error": 1e-8}
    return {"evaluation_protocol": v2.PROTOCOL_ID, "protocol_sha256": v2.protocol_hash(),
            "status": "qualified", "comparisons": comparisons, "parity": parity, "coverage": .95,
            "gates": v2.acceptance(comparisons, parity, .95), "promoted": True}


def pool(root):
    """Every spatial block contains all target groups and identical feature support."""
    directory = root/"dataset";directory.mkdir()
    rows, assignments = [], {}
    for block in range(20):
        name = f"{block}:0"
        split = "development" if block < 16 else "validation"
        assignments[name] = split
        for j in range(12):
            target = (j % 3)/2
            rows.append({"parcel_id": block*12+j+1, "split": split, "block": name, "target": target,
                         "features": [target, target+1, target+2, 2., math.log1p(100), math.log1p(1+target)],
                         "x": block*20000.+j*10, "y": 0.})
    database = directory/"dataset.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE samples(parcel_id INTEGER PRIMARY KEY, block TEXT, split TEXT, target REAL, row_json TEXT)")
        db.executemany("INSERT INTO samples VALUES (?,?,?,?,?)", [(r["parcel_id"], r["block"], r["split"], r["target"], json.dumps(r)) for r in rows])
        # Invalid JSON is a sentinel: loading original test rows would fail.
        db.execute("INSERT INTO samples VALUES (9999,'test','test',1,'DO NOT READ ORIGINAL TEST')")
        db.commit()
    write_json(directory/"manifest.json", {"schema_version": 1, "county_fips": "12091", "features": FEATURES,
        "target": TARGET, "dataset_id": digest(database), "inventory_id": "synthetic-inventory",
        "boundary_version": "synthetic-boundary", "checksums": {}, "assignments": assignments,
        "spatial_policy": {"crs": "EPSG:26916", "block_m": 10000, "buffer_m": 1000, "seed": 42}})
    (directory/"test-evaluation.json").write_text('synthetic frozen original ledger')
    return directory, rows


class ProtocolTests(unittest.TestCase):
    def test_fit_only_weights_cap_and_normalize(self):
        rows = [{"target": 0}]*98+[{"target": .5}, {"target": 1}]
        weights = v2.balanced_weights(rows)
        self.assertAlmostEqual(sum(weights)/100, 1)
        self.assertGreater(weights[-1], weights[0])
        self.assertAlmostEqual(weights[-1]/weights[0], 5/(100/(3*98)))
        self.assertEqual(v2.balanced_weights([{"target": 0}]*4), [1.]*4)
        self.assertEqual(v2.balanced_weights(rows), v2.balanced_weights(rows))

    def test_original_test_json_is_never_loaded_and_ledger_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, expected = pool(Path(temp))
            before = digest(directory/"test-evaluation.json")
            rows, _ = v2.research_rows(directory)
            self.assertEqual(rows, expected)
            self.assertNotIn(9999, {r["parcel_id"] for r in rows})
            self.assertEqual(before, digest(directory/"test-evaluation.json"))

    def test_frozen_gates_reject_missing_subgroups_and_small_or_bad_parity(self):
        report = evaluation()
        self.assertTrue(all(report["gates"].values()))
        for mutation in (
            lambda r: r["comparisons"]["candidate"].update(macro_subgroup_mae=None),
            lambda r: r["comparisons"]["candidate"]["target_ranges"]["one"].update(mae=.3),
            lambda r: r["comparisons"]["candidate"]["parcel"].update(rmse=.4),
            lambda r: r["parity"].update(unique_rows=9999),
            lambda r: r["parity"].update(max_absolute_error=.01),
            lambda r: r.update(coverage=.89),
        ):
            bad = copy.deepcopy(report);mutation(bad)
            self.assertFalse(all(v2.acceptance(bad["comparisons"], bad["parity"], bad["coverage"]).values()))
            with self.assertRaises(ValueError):v2.verify_evaluation({"evaluation_protocol": v2.PROTOCOL_ID}, bad)
        bad = copy.deepcopy(report);bad["protocol_sha256"] = "changed"
        with self.assertRaises(ValueError):v2.verify_evaluation({"evaluation_protocol": v2.PROTOCOL_ID}, bad)

    def test_missing_subgroup_macro_is_unknown(self):
        result = v2.summarize([{"target": 0, "block": "a"}], [.2])
        self.assertIsNone(result["macro_subgroup_mae"])

    def test_reference_unknown_is_not_zero_and_tied_ranks_disclosed(self):
        records = []
        for identifier, susceptibility, rain in ((1, .2, 0), (2, .8, 100), (3, .4, 50)):
            r = production.assessment(identifier, fixtures.inputs_record(identifier),
                [{"native_cell_id": "synthetic", "area_fraction": 1}], fixtures.model_fixture(), {"synthetic": rain})
            r["model_details"]["susceptibility"] = susceptibility
            records.append(r)
        records.append({"parcel_id": 4, "score": None})
        report = review.sensitivity(records, {1: 0, 2: 1})
        self.assertEqual(report["unknown_or_without_diagnostics"], 1)
        self.assertEqual(report["direct_fema_reference"]["50"]["reference_missing"], 1)
        self.assertEqual(set(report["constants_mm"]), {"25", "50", "100"})
        tied = review.ranking([0, 0, 0], [0, 0, 0], [1, 2, 3])
        self.assertIsNone(tied["spearman"])
        self.assertEqual(tied["first_cutoff_ties"], 3)
        with self.assertRaises(ValueError):review.ranking([1], [2], [1, 2])

    def test_missing_bundle_review_writes_actionable_report(self):
        with tempfile.TemporaryDirectory() as temp:
            result = review.review(Path(temp)/"review")
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(len(result["blockers"]), 8)
            self.assertEqual(result["verified_window_count"], 0)
            self.assertIn("not a live host check", (Path(temp)/"review"/"REVIEW.md").read_text())

    def test_review_cli_failure_is_structured_and_does_not_load_native_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/"review"
            command = "from quasar.modeling.__main__ import main; import sys; status=main(); assert not any(n in sys.modules for n in ('xgboost','numpy','shapely','pyproj')); sys.exit(status)"
            result = subprocess.run([sys.executable, "-c", command, "review", "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "incomplete")


class LineageAndServingTests(unittest.TestCase):
    setUp = fixtures.AuditAndProducerTests.setUp
    def prepare_v2(self):
        model = fixtures.model_fixture()
        model.update(model_version="mapped-susceptibility-v2-synthetic", boundary_version=digest(self.boundary),
                     promoted=True, evaluation_protocol=v2.PROTOCOL_ID, training_dataset_id="a"*64)
        model_path, eval_path = self.root/"v2-model.json", self.root/"v2-evaluation.json"
        write_json(model_path, model)
        report = evaluation()
        audited = fixtures.dataset.audit(self.database, self.inputs, self.boundary, self.inspection)
        report.update(model_sha256=digest(model_path), dataset_manifest={"dataset_id": "a"*64, "checksums": audited["checksums"]})
        write_json(eval_path, report)
        return model_path, eval_path, report

    def test_v2_lineage_round_trip_and_reference(self):
        model, evaluation_path, _ = self.prepare_v2()
        output = self.root/"v2-assessment.json"
        production.produce(self.database, self.inputs, self.boundary, self.inspection, model, evaluation_path,
                           self.weather, weather_fixture.iso(weather_fixture.INIT), "current", output, now=weather_fixture.NOW)
        data = read_json(output)
        meta = contracts.metadata(data["model_metadata"])
        self.assertEqual(meta["evaluation_sha256"], digest(evaluation_path))
        self.assertEqual(meta["training_dataset_id"], "a"*64)
        self.assertEqual(data["windows"][0]["parcels"][0]["model_details"]["fema_mapped_area_fraction"], .4)
        exposure._artifact.cache_clear();exposure._aggregate.cache_clear()
        query = {"from": data["windows"][0]["valid_from"], "to": data["windows"][0]["valid_to"], "mode": "replay", "parcel_ids": "1"}
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_FILE": str(output), "QUASAR_PARCEL_DATABASE": str(self.database), "QUASAR_LINUXONE_API_URL": ""}):
            ready = exposure.exposure(query)
            self.assertEqual(ready["model_metadata"], meta)
            with patch.dict(os.environ, {"QUASAR_EXPOSURE_REQUIRED_MODEL_VERSION": "mapped-susceptibility-v2-different"}):
                result = exposure.exposure(query)
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["parcels"], {})
        with patch.dict(os.environ, {"QUASAR_LINUXONE_API_URL": "https://synthetic.example", "QUASAR_LINUXONE_API_TOKEN": "x"*32}):
            with patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(json.dumps(ready).encode())
                self.assertEqual(exposure.exposure(query)["model_metadata"], meta)
            with patch.dict(os.environ, {"QUASAR_EXPOSURE_REQUIRED_MODEL_VERSION": "mapped-susceptibility-v2-other"}), patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(json.dumps(ready).encode())
                self.assertEqual(exposure.exposure(query)["status"], "unavailable")
            bad = copy.deepcopy(ready);bad["model_metadata"]["evaluation_summary"]["coverage"] = .5
            with patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(json.dumps(bad).encode())
                with self.assertRaises(exposure.SourceUnavailable):exposure.exposure(query)

    def test_incomplete_fema_reference_stays_unknown_without_invented_label(self):
        inputs = fixtures.inputs_record();inputs["fema"]["status"] = "partial"
        result = production.assessment(1, inputs, [{"native_cell_id": "a", "area_fraction": 1}], fixtures.model_fixture(), {"a": 100})
        self.assertIsNotNone(result["score"])
        self.assertIsNone(result["model_details"]["fema_mapped_area_fraction"])
        contracts.details(result["model_details"], result["score"])
        for value in (-1, True, math.nan):
            bad = copy.deepcopy(result["model_details"]);bad["fema_mapped_area_fraction"] = value
            with self.assertRaises(ValueError):contracts.details(bad, result["score"])

    def test_v2_gates_and_hash_tamper_refused_before_publication(self):
        model, evaluation_path, report = self.prepare_v2()
        for mutation in (lambda r: r.update(model_sha256="b"*64),
                         lambda r: r["comparisons"]["candidate"]["parcel"].update(rmse=.9),
                         lambda r: r["dataset_manifest"]["checksums"].update(inputs="d"*64),
                         lambda r: r.update(protocol_sha256="c"*64)):
            bad = copy.deepcopy(report);mutation(bad);write_json(evaluation_path, bad)
            with self.assertRaises(ValueError):
                production.produce(self.database, self.inputs, self.boundary, self.inspection, model, evaluation_path,
                    self.weather, weather_fixture.iso(weather_fixture.INIT), "current", self.root/"refused.json", now=weather_fixture.NOW)
            self.assertFalse((self.root/"refused.json").exists())

    def test_metadata_requires_complete_v2_lineage(self):
        meta = {"schema_version": 1, "target": TARGET, "policy": POLICY, "model_version": "legacy-synthetic",
                "promoted": True, "model_sha256": "a"*64, "notice": NOTICE}
        self.assertEqual(contracts.metadata(meta), meta)
        for addition in ({"evaluation_protocol": v2.PROTOCOL_ID}, {"model_version": "mapped-susceptibility-v2-synthetic"}):
            with self.assertRaises(ValueError):contracts.metadata({**meta, **addition})

    def test_corrupt_source_database_is_an_explicit_review_blocker(self):
        self.database.write_text("synthetic corrupt SQLite")
        write_json(self.database.with_suffix(".sqlite3.manifest.json"), {"county_fips": "12091", "database_sha256": digest(self.database)})
        result = review.review(self.root/"bad-review", database=self.database, inputs=self.inputs,
                               boundary=self.boundary, inspection=self.inspection)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["source_audit"]["status"], "invalid")


@unittest.skipUnless(OPTIONAL, "Optional local ML/GIS environment required")
class NativeSpatialExperimentTests(unittest.TestCase):
    def test_polygon_buffer_excludes_close_neighbor_and_disjoint_blocks(self):
        from shapely.geometry import box
        rows = [{"parcel_id": i, "block": str(i), "target": i/5} for i in range(5)]
        geometry = {i: box(i*10000, 0, i*10000+10, 10) for i in range(5)}
        geometry[3] = box(40000-100, 0, 40000-90, 10)
        fit, held, excluded = v2.buffered_split(rows, [0, 1, 2, 3], [4], geometry)
        self.assertEqual(excluded, [3])
        self.assertEqual([r["parcel_id"] for r in fit], [0, 1, 2])
        rows[0]["block"] = "4"
        with self.assertRaisesRegex(ValueError, "blocks overlap"):
            v2.buffered_split(rows, [0, 1, 2, 3], [4], geometry)

    def test_nested_selection_and_real_native_export_keep_test_locked(self):
        from shapely.geometry import box
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);directory, rows = pool(root)
            geometry = {r["parcel_id"]: box(r["x"], 0, r["x"]+1, 1) for r in rows}
            before = digest(directory/"test-evaluation.json")
            selected, details = v2._select(rows, geometry, True)
            for fold in details["folds"]:
                self.assertFalse(set(fold["fit"]) & set(fold["held"]))
                self.assertEqual(set(fold["held"]), set(fold["supported"]))
            self.assertEqual(len(details["candidates"]), 6)
            # Full outer routing/export with small trees; selection itself ran above.
            fixed = {**selected, "rounds": 2}
            _, manifest = v2.research_rows(directory)
            audited = {"status": "verified", **{k: manifest[k] for k in ("inventory_id", "boundary_version", "checksums")}}
            with patch.object(v2, "audit", return_value=audited), \
                    patch.object(v2, "geometries_and_sources", return_value=geometry), \
                    patch.object(v2, "_select", return_value=(fixed, {"selected": fixed, "candidates": [], "folds": []})):
                result = v2.train_v2(directory, root/"synthetic.sqlite3", root/"inputs", root/"boundary.json", root/"inspection", root/"run")
            self.assertEqual(result["status"], "research_only")
            self.assertFalse(result["gates"]["portable_parity"])
            model = load(root/"run"/"model.json")
            self.assertTrue(model["model_version"].startswith("mapped-susceptibility-v2-"))
            self.assertFalse(model["promoted"])
            folds = read_json(root/"run"/"folds.json")
            self.assertEqual(len(folds), 5)
            self.assertEqual(sorted(i for f in folds for i in f["held"]), [r["parcel_id"] for r in rows])
            for fold in folds:self.assertFalse(set(fold["fit"]) & set(fold["held"]))
            self.assertEqual(before, digest(directory/"test-evaluation.json"))
            self.assertTrue((root/"run"/"MODEL_CARD.md").exists())
            self.assertTrue((root/"run"/"spatial-residuals.svg").exists())
            reviewed = review.review(root/"review", dataset=directory, experiment=root/"run")
            self.assertEqual(reviewed["model_lineage"]["status"], "verified")
            self.assertIn("candidate research-only; not eligible for serving", reviewed["blockers"])
            write_json(root/"run"/"protocol.json", {"id": "changed"})
            bad_protocol = review.review(root/"review-protocol", dataset=directory, experiment=root/"run")
            self.assertEqual(bad_protocol["model_lineage"]["status"], "invalid")
            write_json(root/"run"/"protocol.json", v2.PROTOCOL)
            with (root/"run"/"member-0.json").open("a") as stream:stream.write(" ")
            bad = review.review(root/"review-tampered", dataset=directory, experiment=root/"run")
            self.assertEqual(bad["model_lineage"]["status"], "invalid")
            with self.assertRaises(FileExistsError), patch.object(v2, "audit", return_value=audited), \
                    patch.object(v2, "geometries_and_sources", return_value=geometry):
                v2.train_v2(directory, root/"synthetic.sqlite3", root/"inputs", root/"boundary.json", root/"inspection", root/"second")
            self.assertEqual(before, digest(directory/"test-evaluation.json"))
