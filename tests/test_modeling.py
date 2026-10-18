"""Synthetic modeling fixtures only. No downloads, IBM access or flood validation."""
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
import zlib
from contextlib import closing
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from quasar import exposure
from quasar.modeling import FEATURES, TARGET, POLICY, NOTICE, digest, feature_values, label_value, read_json, write_json
from quasar.modeling import contracts, dataset, portable, production
from quasar.modeling.training import metrics
import test_county_weather as weather_fixture
import test_parcel_context as parcel_fixture

GIS = all(importlib.util.find_spec(name) for name in ("shapely", "pyproj"))
ML = all(importlib.util.find_spec(name) for name in ("xgboost", "sklearn", "numpy"))


def inputs_record(identifier=1):
    return {"parcel_id": identifier, "county_fips": "12091", "geometry_status": "valid", "area_m2": 100,
            "risk_score": None, "terrain": {"status": "complete", "min_m": 1, "mean_m": 2, "max_m": 3,
            "units": "m", "vertical_datum": "NAVD88"}, "fema": {"status": "complete", "mapped_area_fraction": 1,
            "sfha_mapped_area_fraction": .4}, "hydrography": {"status": "partial_reference_coverage",
            "nearest_retained_river_stream_distance_m": 100}}


def model_fixture():
    tree = [{"feature": 0, "threshold": 2, "left": 1, "right": 2, "expected": .05},
            {"leaf": -.1, "expected": -.1}, {"leaf": .2, "expected": .2}]
    return {"schema_version": 1, "county_fips": "12091", "model_version": "synthetic-test-only",
            "target": TARGET, "objective": "reg:squarederror", "features": list(FEATURES),
            "feature_ranges": [[-10, 100]]*6, "training_dataset_id": "synthetic-dataset",
            "inventory_id": "parcel-snapshot", "boundary_version": "synthetic-boundary", "promoted": False,
            "members": [{"bias": .5, "trees": [copy.deepcopy(tree)]} for _ in range(5)]}


class FeatureAndRuntimeTests(unittest.TestCase):
    def test_features_exclude_target_identity_location_and_gauge(self):
        record = inputs_record()
        x, missing = feature_values(record)
        self.assertEqual(missing, [])
        self.assertEqual(x, [1, 2, 3, 2, math.log1p(100), math.log1p(100)])
        record.update(parcel_id=999, longitude=99, h3="test", gauge_margin_m=999)
        record["fema"]["sfha_mapped_area_fraction"] = .99
        self.assertEqual(feature_values(record)[0], x)
        for key, value in (("status", "partial"), ("mean_m", None), ("units", "ft"), ("vertical_datum", "unknown")):
            bad = inputs_record(); bad["terrain"][key] = value
            self.assertIsNone(feature_values(bad)[0])

    def test_labels_preserve_unmapped_conflicting_and_invalid_states(self):
        self.assertEqual(label_value(inputs_record()), .4)
        for key, value in (("status", "partial"), ("sfha_reference_status", "conflicting_source_flags"),
                           ("mapped_area_fraction", None), ("sfha_mapped_area_fraction", True),
                           ("sfha_mapped_area_fraction", -1)):
            bad = inputs_record();bad["fema"][key] = value
            self.assertIsNone(label_value(bad))

    def test_portable_signed_paths_sum_to_raw_and_clip_only_predictions(self):
        model = portable.validate(model_fixture())
        low, high = portable.predict(model, [1]*6), portable.predict(model, [2]*6)
        self.assertAlmostEqual(low["susceptibility"], .4)
        self.assertAlmostEqual(high["susceptibility"], .7)
        self.assertLess(low["attributions"][FEATURES[0]], 0)
        for result in (low, high):
            self.assertAlmostEqual(result["baseline"]+sum(result["attributions"].values()), result["raw_susceptibility"])
        model["members"][0]["bias"] = 5
        result = portable.predict(model, [1]*6)
        self.assertLessEqual(result["susceptibility"], 1)
        self.assertGreater(result["raw_susceptibility"], result["susceptibility"])

    def test_portable_rejects_topology_objectives_categories_and_feature_mismatch(self):
        changes = [lambda m: m.update(objective="binary:logistic"), lambda m: m["features"].reverse(),
                   lambda m: m["members"][0]["trees"][0][0].update(left=0),
                   lambda m: m["members"][0]["trees"][0][0].update(feature=99),
                   lambda m: m["members"][0]["trees"][0].append({"leaf": 0, "expected": 0}),
                   lambda m: m["members"][0]["trees"][0][0].update(categories=[1]),
                   lambda m: m["feature_ranges"][0].__setitem__(0, float("nan"))]
        for change in changes:
            model = model_fixture();change(model)
            with self.subTest(change=change), self.assertRaises(ValueError):portable.validate(model)
        model = model_fixture()
        self.assertEqual(portable.predict(model, [101]*6)["missing"], ["outside_training_ranges"])
        self.assertIsNone(portable.predict(model, [None]*6)["susceptibility"])

    def test_composite_monotonic_bounds_diagnostics_and_unknowns(self):
        model = model_fixture()
        overlaps = [{"native_cell_id": "synthetic", "area_fraction": 1}]
        values = []
        for rain in (0, 1, 50, 120, 1000):
            record = production.assessment(1, inputs_record(), overlaps, model, {"synthetic": rain})
            self.assertEqual(exposure.validate_assessment(record), record)
            self.assertEqual(sum(f["contribution"] for f in record["factors"]), record["score"])
            values.append(record["score"])
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 0)
        self.assertLess(values[-1], 100)
        record = production.assessment(1, inputs_record(), overlaps, model, {"synthetic": None})
        self.assertIsNone(record["score"])
        bad = inputs_record();bad["terrain"]["status"] = "no_pixel_centers"
        self.assertIsNone(production.assessment(1, bad, overlaps, model, {"synthetic": 12})["score"])

    def test_partial_duplicate_and_missing_native_coverage_never_zero_fill(self):
        self.assertEqual(production.parcel_rainfall([{"native_cell_id":"a","area_fraction":.25},
            {"native_cell_id":"b","area_fraction":.75}], {"a": 0, "b": 20}), 15)
        for overlaps in ([], [{"native_cell_id":"a","area_fraction":.5}],
                         [{"native_cell_id":"a","area_fraction":.5}]*2,
                         [{"native_cell_id":"b","area_fraction":1}]):
            self.assertIsNone(production.parcel_rainfall(overlaps, {"a": 0}))

    def test_weather_window_contiguous_one_init_stale_null_and_duplicate(self):
        data = weather_fixture.current()
        start = data["valid_from"]
        values, source = production.weather_window(data, start, "current", weather_fixture.NOW)
        self.assertEqual(list(values.values()), [12])
        self.assertEqual(source["units"], "mm / 6h")
        stale, _ = production.weather_window(data, start, "current", weather_fixture.NOW+timedelta(hours=3))
        self.assertEqual(list(stale.values()), [None])
        for mutation in ("null", "missing", "duplicate"):
            bad = copy.deepcopy(data)
            if mutation == "null":bad["runs"][0]["rows"][0]["rainfall_1h_mm"] = None
            if mutation == "missing":bad["runs"][0]["rows"].pop(0)
            if mutation == "duplicate":bad["runs"][0]["rows"].append(bad["runs"][0]["rows"][0])
            if mutation == "duplicate":
                with self.assertRaises(ValueError):production.weather_window(bad, start, "current", weather_fixture.NOW)
            else:
                values, _ = production.weather_window(bad, start, "current", weather_fixture.NOW)
                self.assertEqual(list(values.values()), [None])

    def test_metrics_equal_blocks_not_parcel_counts_and_source_unchanged(self):
        rows = [{"target": 0, "block":"a"}]*9+[{"target":1,"block":"b"}]
        result = metrics(rows, [0]*10)
        self.assertAlmostEqual(result["parcel"]["mae"], .1)
        self.assertAlmostEqual(result["equal_block"]["mae"], .5)

    def test_atomic_writes_missing_audit_and_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            file = root/"artifact.json"
            write_json(file, {"old": True})
            with self.assertRaises(ValueError):write_json(file, {"bad": math.nan})
            self.assertEqual(read_json(file), {"old": True})
            file.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):read_json(file)
            result = dataset.audit(root/"db", root/"inputs", root/"county")
            self.assertEqual(result["status"], "missing")
            self.assertFalse(result["training_ready"])

    def test_cli_and_runtime_do_not_import_optional_libraries(self):
        run = subprocess.run([sys.executable, "-c", "import sys; from quasar.modeling import portable, production; "
                              "assert not any(x in sys.modules for x in ('xgboost','sklearn','shapely','numpy','pyproj'))"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        run = subprocess.run([sys.executable, "-m", "quasar.modeling", "--help"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        self.assertIn("validate-outcomes", run.stdout)

    # Value: protects=training dataset checksum and feature schema; fails_when=tampered training inputs are accepted; why_new=preparation tests load only intact manifests; seam=none; no_claim=source authenticity.
    def test_dataset_rejects_checksum_or_schema_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = synthetic_dataset(Path(directory))
            manifest = read_json(prepared/"manifest.json")
            for field, value in (("dataset_id", "tampered"), ("features", list(reversed(FEATURES)))):
                with self.subTest(field=field):
                    write_json(prepared/"manifest.json", {**manifest, field: value})
                    with self.assertRaisesRegex(ValueError, "checksum/schema"):
                        dataset.load_dataset(prepared)
            write_json(prepared/"manifest.json", manifest)
            self.assertEqual(dataset.load_dataset(prepared)[1]["dataset_id"], manifest["dataset_id"])


def complete_fixture(root):
    database, inputs, boundary, meta = parcel_fixture.fixture(root)
    with closing(sqlite3.connect(inputs/"parcel-inputs.sqlite3")) as db:
        for identifier in (1, 2):
            db.execute("UPDATE parcel_inputs SET inputs_json=? WHERE parcel_id=?", (json.dumps(inputs_record(identifier)), identifier))
        db.commit()
    parent = read_json(inputs/"manifest.json")
    parent["terrain"].update(units="m", vertical_datum="North American Vertical Datum of 1988")
    parent["artifacts"][0]["sha256"] = digest(inputs/"parcel-inputs.sqlite3")
    write_json(inputs/"manifest.json", parent)
    weather = weather_fixture.current()
    weather["county_geometry"] = read_json(boundary)["features"][0]["geometry"]
    path = root/"weather.json";write_json(path, weather)
    inspection = root/"inspection";inspection.mkdir()
    cell = weather["native_cells"][0]["id"]
    with closing(sqlite3.connect(inspection/"inspection.sqlite3")) as db:
        db.execute("CREATE TABLE inspection(kind TEXT, identifier TEXT, context_json TEXT, PRIMARY KEY(kind,identifier))")
        for identifier in (1, 2):
            context = {"county_fips": "12091", "parcel_id": identifier, "inputs": inputs_record(identifier),
                       "forecast_overlaps": [{"native_cell_id": cell, "area_fraction": 1}]}
            db.execute("INSERT INTO inspection VALUES ('parcel',?,?)", (str(identifier), json.dumps(context)))
        db.commit()
    im = {"county_fips": "12091", "inventory_id": "parcel-snapshot", "boundary_version": digest(boundary),
          "cell_index_version": "cell-index", "parent_manifest_sha256": digest(inputs/"manifest.json"),
          "database_sha256": digest(inspection/"inspection.sqlite3"), "provenance": {"weather": [{"sha256": digest(path)}]}}
    write_json(inspection/"manifest.json", im)
    return database, inputs, boundary, inspection, path


class AuditAndProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database, self.inputs, self.boundary, self.inspection, self.weather = complete_fixture(self.root)

    def test_audit_checks_hash_units_inventory_and_inspection(self):
        report = dataset.audit(self.database, self.inputs, self.boundary, self.inspection)
        self.assertEqual(report["coverage"]["label_eligible"], 2)
        parent = read_json(self.inputs/"manifest.json");parent["terrain"]["units"] = "ft"
        write_json(self.inputs/"manifest.json", parent)
        with self.assertRaises(ValueError):dataset.audit(self.database, self.inputs, self.boundary)

    # Value: protects=missing forecast initialization cannot publish assessments; fails_when=an unusable artifact is published; why_new=weather tests have an eligible initialization; seam=none; no_claim=live forecast availability.
    def test_no_eligible_initialization_never_publishes_an_artifact(self):
        model = model_fixture();model.update(boundary_version=digest(self.boundary), promoted=True)
        model_path, evaluation = self.root/"model.json", self.root/"evaluation.json"
        write_json(model_path, model)
        write_json(evaluation, {"promoted": True, "model_sha256": digest(model_path),
                               "dataset_manifest": {"dataset_id": "synthetic-dataset"}})
        output = self.root/"unavailable.json"
        start = weather_fixture.iso(weather_fixture.INIT-timedelta(hours=1))
        with self.assertRaises(ValueError):
            production.produce(self.database, self.inputs, self.boundary, self.inspection, model_path,
                               evaluation, self.weather, start, "replay", output, now=weather_fixture.NOW)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob("*.partial")))

    # Value: protects=assessment publication never overwrites a competing output; fails_when=a race replaces existing bytes; why_new=existing rejection only checks a file present before production; seam=none; no_claim=distributed filesystem semantics.
    def test_publication_preserves_output_created_during_audit(self):
        model = model_fixture();model.update(boundary_version=digest(self.boundary), promoted=True)
        model_path, evaluation = self.root/"model.json", self.root/"evaluation.json"
        write_json(model_path, model)
        write_json(evaluation, {"promoted": True, "model_sha256": digest(model_path),
                               "dataset_manifest": {"dataset_id": "synthetic-dataset"}})
        output = self.root/"competing.json"
        sentinel = b"another process owns this artifact\n"
        original_audit = production.audit
        def concurrent_publication(*args):
            result = original_audit(*args)
            output.write_bytes(sentinel)
            return result
        with patch.object(production, "audit", side_effect=concurrent_publication):
            try:
                production.produce(self.database, self.inputs, self.boundary, self.inspection, model_path,
                                   evaluation, self.weather, weather_fixture.iso(weather_fixture.INIT),
                                   "current", output, now=weather_fixture.NOW)
            except (OSError, ValueError):
                pass
        self.assertEqual(output.read_bytes(), sentinel)
        self.assertFalse(list(self.root.glob("*.partial")))

    # Value: protects=model forecast freshness and window agreement at API boundaries; fails_when=invalid model context returns known scores; why_new=legacy expiry tests lack model provenance; seam=none; no_claim=live host or rendered UI.
    def test_model_source_expiry_window_and_status_fail_closed_locally_and_remotely(self):
        model = model_fixture();model.update(boundary_version=digest(self.boundary), promoted=True)
        model_path, evaluation = self.root/"model.json", self.root/"evaluation.json"
        write_json(model_path, model)
        write_json(evaluation, {"promoted": True, "model_sha256": digest(model_path),
                               "dataset_manifest": {"dataset_id": "synthetic-dataset"}})
        output = self.root/"api.json"
        production.produce(self.database, self.inputs, self.boundary, self.inspection, model_path,
                           evaluation, self.weather, weather_fixture.iso(weather_fixture.INIT),
                           "current", output, now=weather_fixture.NOW)
        baseline = read_json(output)
        now = datetime.now(timezone.utc)
        start = now.replace(minute=0, second=0, microsecond=0)
        end = start+timedelta(hours=6)
        baseline["windows"][0].update(valid_from=start.isoformat(), valid_to=end.isoformat(), computed_at=now.isoformat())
        baseline["forecast_provenance"].update(init_time=start.isoformat(), retrieved_at=now.isoformat(),
            published_at=None, valid_from=start.isoformat(), valid_to=end.isoformat(), expires_at=(start+timedelta(hours=1)).isoformat())
        query = {"from": start.isoformat(), "to": end.isoformat(), "mode": "current", "parcel_ids": "1"}
        mutations = {
            "expiry": lambda source: source.update(expires_at=(now-timedelta(minutes=1)).isoformat()),
            "window": lambda source: source.update(valid_from=(start+timedelta(hours=1)).isoformat(), valid_to=(end+timedelta(hours=1)).isoformat()),
            "status": lambda source: source.update(status="stale"),
            "mode": lambda source: source.update(mode="replay"),
        }
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_FILE": str(output), "QUASAR_PARCEL_DATABASE": str(self.database), "QUASAR_LINUXONE_API_URL": ""}):
            write_json(output, baseline);exposure._artifact.cache_clear();exposure._aggregate.cache_clear()
            remote_baseline = exposure.exposure(query)
            self.assertEqual(remote_baseline["status"], "ready")
            for name, mutate in mutations.items():
                with self.subTest(boundary="local", mutation=name):
                    bad = copy.deepcopy(baseline);mutate(bad["forecast_provenance"])
                    write_json(output, bad);exposure._artifact.cache_clear();exposure._aggregate.cache_clear()
                    result = exposure.exposure(query)
                    self.assertIn(result["status"], ("invalid", "stale"))
                    self.assertEqual(result["parcels"], {})
                with self.subTest(boundary="proxy", mutation=name), patch.dict(os.environ,
                        {"QUASAR_LINUXONE_API_URL": "https://synthetic.example", "QUASAR_LINUXONE_API_TOKEN": "x"*32}):
                    bad = copy.deepcopy(remote_baseline);mutate(bad["forecast_provenance"])
                    with patch.object(exposure, "build_opener") as opener:
                        opener.return_value.open.return_value = BytesIO(json.dumps(bad).encode())
                        with self.assertRaises(exposure.SourceUnavailable):exposure.exposure(query)
            # A replay bypasses today's expiry, never the initialization age at its decision time.
            aged = copy.deepcopy(baseline)
            aged["forecast_provenance"].update(mode="replay", init_time=(start-timedelta(hours=24)).isoformat(),
                                               expires_at=(start-timedelta(hours=12)).isoformat())
            replay_query = {**query, "mode": "replay"}
            write_json(output, aged);exposure._artifact.cache_clear();exposure._aggregate.cache_clear()
            self.assertEqual(exposure.exposure(replay_query)["status"], "invalid")
            remote = copy.deepcopy(remote_baseline);remote["forecast_provenance"] = aged["forecast_provenance"]
            with patch.dict(os.environ, {"QUASAR_LINUXONE_API_URL": "https://synthetic.example", "QUASAR_LINUXONE_API_TOKEN": "x"*32}):
                with patch.object(exposure, "build_opener") as opener:
                    opener.return_value.open.return_value = BytesIO(json.dumps(remote).encode())
                    with self.assertRaises(exposure.SourceUnavailable):exposure.exposure(replay_query)
        exposure._artifact.cache_clear();exposure._aggregate.cache_clear()

    def test_streaming_producer_api_round_trip_and_unpromoted_rejection(self):
        model = model_fixture();model.update(boundary_version=digest(self.boundary), promoted=True)
        model_path, eval_path = self.root/"model.json", self.root/"evaluation.json"
        write_json(model_path, model)
        write_json(eval_path, {"promoted": True, "model_sha256": digest(model_path),
                              "dataset_manifest": {"dataset_id": "synthetic-dataset"}})
        output = self.root/"exposure.json"
        benchmark = production.produce(self.database, self.inputs, self.boundary, self.inspection, model_path,
                                       eval_path, self.weather, weather_fixture.iso(weather_fixture.INIT), "current",
                                       output, now=weather_fixture.NOW)
        self.assertEqual(benchmark["counts"]["scored"], 2)
        self.assertEqual(benchmark["host_budget"]["vcpus"], 3)
        measured=production.benchmark(self.database,output,self.root/"benchmark.json")
        self.assertEqual(set(measured["summaries"]),{"4","5","6","7"})
        data = read_json(output)
        self.assertEqual(data["model_metadata"]["target"], TARGET)
        for record in data["windows"][0]["parcels"]:exposure.validate_assessment(record)
        exposure._artifact.cache_clear();exposure._aggregate.cache_clear()
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_FILE": str(output), "QUASAR_PARCEL_DATABASE": str(self.database), "QUASAR_LINUXONE_API_URL": ""}):
            result = exposure.exposure({"from": data["windows"][0]["valid_from"], "to": data["windows"][0]["valid_to"], "mode":"replay", "parcel_ids":"1"})
            self.assertEqual(result["status"], "ready")
            self.assertIn("model_details", result["parcels"]["1"])
            self.assertIn("forecast_provenance", result)
            query={"from":data["windows"][0]["valid_from"],"to":data["windows"][0]["valid_to"],"mode":"replay","parcel_ids":"1"}
            with patch.dict(os.environ,{"QUASAR_LINUXONE_API_URL":"https://synthetic.example","QUASAR_LINUXONE_API_TOKEN":"x"*32}):
                with patch.object(exposure,"build_opener") as opener:
                    opener.return_value.open.return_value=BytesIO(json.dumps(result).encode())
                    proxied=exposure.exposure(query)
                    self.assertEqual(proxied["parcels"]["1"]["model_details"],result["parcels"]["1"]["model_details"])
                bad=copy.deepcopy(result);bad["parcels"]["1"]["model_details"]["baseline"]=42
                with patch.object(exposure,"build_opener") as opener:
                    opener.return_value.open.return_value=BytesIO(json.dumps(bad).encode())
                    with self.assertRaises(exposure.SourceUnavailable):exposure.exposure(query)
        model["promoted"] = False;write_json(model_path, model)
        with self.assertRaises(ValueError):production.produce(self.database, self.inputs, self.boundary, self.inspection,
            model_path, eval_path, self.weather, weather_fixture.iso(weather_fixture.INIT), "current", self.root/"refused.json", now=weather_fixture.NOW)
        self.assertFalse((self.root/"refused.json").exists())

    def test_bad_diagnostics_and_metadata_fail_closed(self):
        record = production.assessment(1, inputs_record(), [{"native_cell_id":"a","area_fraction":1}], model_fixture(), {"a":20})
        for key, value in (("susceptibility", math.nan), ("rainfall_stress", .99), ("baseline", 42), ("model_instability", True)):
            bad = copy.deepcopy(record);bad["model_details"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):exposure.validate_assessment(bad)
        with self.assertRaises(ValueError):contracts.metadata({"promoted": False})
        self.assertEqual(exposure.model_context({}), {})


@unittest.skipUnless(GIS, "Optional local GIS modeling environment not installed")
class SpatialPreparationTests(unittest.TestCase):
    def test_preparation_persists_spatial_split_and_excludes_near_holdout(self):
        from pyproj import Transformer
        from shapely.geometry import box, mapping
        from shapely.ops import transform
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);database,inputs,boundary,_,_=complete_fixture(root)
            write_json(boundary,{"features":[{"properties":{"GEOID":"12091"},"geometry":weather_fixture.GEOMETRY}]})
            parent=read_json(inputs/"manifest.json")
            parent["sources"]["boundary_sha256"]=digest(boundary)
            parent["sources"]["parcels"]["county_boundary"]["sha256"]=digest(boundary)
            project=Transformer.from_crs("EPSG:26916","EPSG:4326",always_xy=True)
            blocks=[f"{x}:{y}" for x in range(53,58) for y in range(336,341)]
            assignments=dataset.block_splits(blocks)
            pairs=[(b,f"{int(b.split(':')[0])+1}:{b.split(':')[1]}") for b in blocks]
            left,right=next((a,b) for a,b in pairs if b in assignments and
                            "development" in {assignments[a],assignments[b]} and assignments[a]!=assignments[b])
            points=[((int(b.split(':')[0])+.5)*10000,(int(b.split(':')[1])+.5)*10000) for b in blocks]
            edge=(int(left.split(':')[0])+1)*10000; north=(int(left.split(':')[1])+.5)*10000
            points += [(edge-100,north),(edge+100,north)]
            with closing(sqlite3.connect(database)) as db, closing(sqlite3.connect(inputs/"parcel-inputs.sqlite3")) as descriptions:
                db.execute("DELETE FROM parcels");descriptions.execute("DELETE FROM parcel_inputs")
                for i,(x,y) in enumerate(points,1):
                    feature={"geometry":mapping(transform(project.transform,box(x-1,y-1,x+1,y+1)))}
                    db.execute("INSERT INTO parcels VALUES (?,?)",(i,zlib.compress(json.dumps(feature).encode())))
                    record=inputs_record(i);record["fema"]["sfha_mapped_area_fraction"]=(i%3)/2
                    descriptions.execute("INSERT INTO parcel_inputs VALUES (?,?,?)",(i,"12091",json.dumps(record)))
                db.execute("UPDATE metadata SET value=? WHERE key='source_provenance'",(json.dumps(parent["sources"]["parcels"]),))
                db.commit();descriptions.commit()
            parent["artifacts"][0]["sha256"]=digest(inputs/"parcel-inputs.sqlite3")
            write_json(inputs/"manifest.json",parent)
            write_json(database.with_suffix(".sqlite3.manifest.json"),{"county_fips":"12091","database_sha256":digest(database)})
            report=dataset.prepare(database,inputs,boundary,root/"prepared")
            self.assertGreaterEqual(report["splits"]["buffer_excluded"],1)
            prepared,_=dataset.load_dataset(root/"prepared")
            rows=list(dataset.samples(prepared))
            self.assertEqual(len(rows),len(points))
            self.assertTrue(all(r["split"]==report["assignments"][r["block"]] for r in rows if r["split"]!="buffer_excluded"))

    def test_real_containment_is_checked_even_with_matching_fips_and_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root);database, inputs, boundary, _, _ = complete_fixture(root)
            # Outside geometry, while all supplied provenance/FIPS still looks correct.
            with closing(sqlite3.connect(database)) as db:
                feature = {"geometry": {"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}}
                db.execute("UPDATE parcels SET feature_z=? WHERE parcel_id=1", (zlib.compress(json.dumps(feature).encode()),));db.commit()
            write_json(database.with_suffix(".sqlite3.manifest.json"), {"county_fips":"12091","database_sha256":digest(database)})
            with self.assertRaisesRegex(ValueError, "outside authoritative"):
                dataset.prepare(database, inputs, boundary, root/"prepared")

    def test_geographic_split_is_deterministic_and_disjoint(self):
        blocks = [f"{i}:0" for i in range(100)]
        assignment = dataset.block_splits(blocks)
        self.assertEqual(assignment, dataset.block_splits(list(reversed(blocks))))
        self.assertEqual({s: list(assignment.values()).count(s) for s in set(assignment.values())},
                         {"development":70,"validation":15,"test":15})


@unittest.skipUnless(ML, "Optional local ML environment not installed")
class NativeExportTests(unittest.TestCase):
    def test_10000_synthetic_rows_and_split_boundaries_match_native(self):
        import numpy as np
        import xgboost as xgb
        rng = np.random.default_rng(42)
        X = rng.uniform(-1, 1, size=(10000, 6)).astype(np.float32)
        y = np.clip(.5+.2*X[:, 0]-.1*X[:, 1]*X[:, 2], 0, 1)
        matrix = xgb.DMatrix(X, label=y, feature_names=FEATURES)
        model = xgb.train({"objective":"reg:squarederror","max_depth":3,"nthread":3,"seed":42}, matrix, num_boost_round=5)
        saved = json.loads(model.save_raw(raw_format="json"))
        metadata = {k:v for k,v in model_fixture().items() if k not in ("members", "schema_version", "features", "target", "objective")}
        portable_model = portable.export_saved([saved]*5, metadata)
        native = np.clip(model.predict(matrix), 0, 1)
        delta = [abs(portable.predict(portable_model, row.tolist())["susceptibility"]-float(p)) for row,p in zip(X,native)]
        self.assertLessEqual(max(delta), 1e-6)
        split = next(n for tree in portable_model["members"][0]["trees"] for n in tree if "feature" in n)
        threshold = np.float32(split["threshold"])
        edge = np.zeros((3,6),dtype=np.float32)
        edge[:,split["feature"]] = [np.nextafter(threshold, np.float32(-np.inf)), threshold, np.nextafter(threshold,np.float32(np.inf))]
        expected = model.predict(xgb.DMatrix(edge, feature_names=FEATURES))
        for row, value in zip(edge, expected):
            self.assertAlmostEqual(portable.predict(portable_model,row.tolist())["susceptibility"],float(value),places=6)
        bad = copy.deepcopy(saved);bad["learner"]["gradient_booster"]["model"]["trees"][0]["split_type"][0] = 1
        with self.assertRaises(ValueError):portable.export_saved([bad]*5, metadata)

    # Value: protects=evaluated native export identity and directory confinement; fails_when=tampered or external native members export; why_new=existing experiment only exercises a valid export; seam=none; no_claim=real-data parity or model accuracy.
    def test_full_research_experiment_exports_and_locks_heldout_test(self):
        from quasar.modeling.training import train, export
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = synthetic_dataset(root, 600)
            result = train(prepared, root/"experiment")
            self.assertEqual(len(result["candidates"]), 6)
            self.assertFalse(result["promoted"], "Small synthetic research runs must not activate the app")
            self.assertLessEqual(result["parity"]["max_absolute_error"], 1e-6)
            self.assertEqual(result["test"]["scored_count"]+result["test"]["unknown_count"], result["test"]["test_total"])
            export(root/"experiment", root/"exported.json")
            self.assertEqual(read_json(root/"exported.json"), read_json(root/"experiment/model.json"))
            self.assertTrue((root/"experiment/spatial-residuals.svg").exists())
            with self.assertRaises(FileExistsError):train(prepared, root/"retry")
            native = root/"experiment/member-0.json"
            original_native = native.read_bytes()
            native.write_bytes(original_native+b" ")
            with self.assertRaisesRegex(ValueError, "checksum/path"):
                export(root/"experiment", root/"tampered-export.json")
            self.assertFalse((root/"tampered-export.json").exists())
            native.write_bytes(original_native)
            report_path = root/"experiment/evaluation.json"
            report = read_json(report_path)
            outside = root/"outside-member.json";outside.write_bytes(original_native)
            report["native_models"][0].update(path="../outside-member.json", sha256=digest(outside))
            write_json(report_path, report)
            with self.assertRaisesRegex(ValueError, "checksum/path"):
                export(root/"experiment", root/"external-export.json")
            self.assertFalse((root/"external-export.json").exists())


def synthetic_dataset(root, count=40):
    """A visibly synthetic modeling dataset, not acquired or county-validated source data."""
    target = root/"synthetic-dataset";target.mkdir()
    assignment = dataset.block_splits([f"{i}:0" for i in range(20)])
    with closing(sqlite3.connect(target/"dataset.sqlite3")) as db:
        db.execute("CREATE TABLE samples(parcel_id INTEGER PRIMARY KEY,block TEXT,split TEXT,target REAL,row_json TEXT)")
        for i in range(count):
            block = f"{(i//2)%20}:0"
            # Repeated predictor support across blocks permits an honest holdout scoring comparison.
            x = (i%2)*.5+.25
            row = {"parcel_id":i+1,"block":block,"split":assignment[block],"features":[x]*6,
                   "target": .2 if i%2 else .8, "x":500000+(i//2)*10000,"y":3400000+i%2,"missing":[]}
            db.execute("INSERT INTO samples VALUES (?,?,?,?,?)", (i+1,block,row["split"],row["target"],json.dumps(row)))
        db.commit()
    write_json(target/"manifest.json", {"schema_version":1,"county_fips":"12091","features":FEATURES,"target":TARGET,
        "dataset_id":digest(target/"dataset.sqlite3"),"inventory_id":"parcel-snapshot","boundary_version":"synthetic-boundary",
        "assignments":assignment,"notice":"Synthetic test data only"})
    return target


class OutcomeReadinessTests(unittest.TestCase):
    def make_outcomes(self, root):
        prepared = synthetic_dataset(root)
        inspection = root/"contexts";inspection.mkdir()
        weather_files = []
        records = []
        for episode in range(10):
            init = weather_fixture.INIT-timedelta(days=15-episode)
            weather = weather_fixture.cw.normalize(weather_fixture.rows(init),weather_fixture.TABLE,weather_fixture.GEOMETRY,
                                                   valid_from=weather_fixture.iso(init),now=init+timedelta(minutes=30))
            path = root/f"synthetic-weather-{episode}.json";write_json(path,weather);weather_files.append(path)
            cell = weather["native_cells"][0]["id"]
            for parcel in range(1,41):
                records.append({"parcel_id":parcel,"episode_id":f"synthetic-{episode}","at":weather_fixture.iso(init),
                    "label":parcel%2,"association_verified":True,"observed_coverage":True,"mechanism":"rainfall_driven",
                    "spatial_uncertainty_m":1,"source_id":"synthetic-test-only","source_url":"https://example.test/synthetic",
                    "source_retrieved_at":weather_fixture.iso(weather_fixture.NOW),"labeling_policy":"synthetic-test-only",
                    "coverage_evidence":"synthetic complete coverage","observation_from":weather_fixture.iso(init),
                    "observation_to":weather_fixture.iso(init+timedelta(hours=6)),
                    "reference_mode":"current_reference_retrospective","forecast_sha256":digest(path)})
        with closing(sqlite3.connect(inspection/"inspection.sqlite3")) as db:
            db.execute("CREATE TABLE inspection(kind TEXT,identifier TEXT,context_json TEXT,PRIMARY KEY(kind,identifier))")
            for parcel in range(1,41):
                db.execute("INSERT INTO inspection VALUES ('parcel',?,?)",(str(parcel),json.dumps({"forecast_overlaps":[{"native_cell_id":cell,"area_fraction":1}]})))
            db.commit()
        write_json(inspection/"manifest.json", {"county_fips":"12091","inventory_id":"parcel-snapshot",
            "boundary_version":"synthetic-boundary","database_sha256":digest(inspection/"inspection.sqlite3"),
            "provenance":{"weather":[{"sha256":digest(p)} for p in weather_files]}})
        labels = root/"synthetic-outcomes.json"
        write_json(labels,{"schema_version":1,"county_fips":"12091","inventory_id":"parcel-snapshot",
                           "boundary_version":"synthetic-boundary","records":records})
        return prepared, labels, inspection, weather_files

    def test_outcomes_require_observed_negatives_and_do_not_train_on_absence(self):
        from quasar.modeling.outcomes import prepare_outcomes
        with tempfile.TemporaryDirectory() as directory:
            args = self.make_outcomes(Path(directory))
            rows, result = prepare_outcomes(*args)
            self.assertEqual(result["status"],"ready")
            self.assertEqual((result["positive_count"],result["negative_count"]),(200,200))
            self.assertEqual(len(result["test_episodes"]),3)
            self.assertTrue(all(len({r["split"] for r in rows if r["episode"]==episode})==1 for episode in {r["episode"] for r in rows}))
            labels=read_json(args[1])
            for record in labels["records"]:
                if record["label"]==0:record["observed_coverage"]=False
            write_json(args[1],labels)
            _, result=prepare_outcomes(*args)
            self.assertEqual(result["status"],"insufficient_evidence")
            self.assertEqual(result["negative_count"],0)

    def test_outcome_future_reference_duplicate_and_partial_negative_are_rejected(self):
        from quasar.modeling.outcomes import prepare_outcomes
        with tempfile.TemporaryDirectory() as directory:
            args=self.make_outcomes(Path(directory));labels=read_json(args[1]);original=copy.deepcopy(labels)
            labels["records"][0].update(reference_mode="as_issued",reference_available_at=weather_fixture.iso(weather_fixture.NOW))
            write_json(args[1],labels)
            with self.assertRaisesRegex(ValueError,"Future reference"):prepare_outcomes(*args)
            labels=copy.deepcopy(original);labels["records"].append(labels["records"][0]);write_json(args[1],labels)
            with self.assertRaisesRegex(ValueError,"Duplicate"):prepare_outcomes(*args)
            labels=copy.deepcopy(original)
            for record in labels["records"]:
                if record["label"]==0:record["observation_to"]=record["observation_from"]
            write_json(args[1],labels)
            _,result=prepare_outcomes(*args)
            self.assertEqual(result["exclusions"]["negative_window_not_fully_observed"],200)

    @unittest.skipUnless(ML,"Optional local ML environment not installed")
    def test_conditional_outcome_experiment_is_research_only(self):
        from quasar.modeling.outcomes import train_outcomes
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=self.make_outcomes(root)
            report=train_outcomes(*args,root/"experiment")
            self.assertFalse(report["promoted"])
            self.assertIn("event_holdout",report["evaluations"])
            self.assertIn("spatial_holdout",report["evaluations"])
            self.assertEqual(len(report["validation_candidates"]),6)
