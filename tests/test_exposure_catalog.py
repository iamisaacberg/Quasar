"""Synthetic catalog releases only; no data acquisition or host access."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from quasar import exposure, exposure_catalog
from quasar.modeling import POLICY, TARGET, NOTICE, digest, read_json, write_json
from quasar.modeling import production, replay_batch
from quasar.modeling.evidence import compare_assessments, verify_bundle
import test_county_weather as weather_fixture
import test_exposure as exposure_fixture
from test_modeling import model_fixture, inputs_record, complete_fixture


class CatalogTests(unittest.TestCase):
    record = staticmethod(exposure_fixture.ExposureTests.record)
    write = exposure_fixture.ExposureTests.write

    def setUp(self):
        exposure_fixture.ExposureTests.setUp(self)
        self.root = self.artifact.parent
        self.catalog = self.root / "catalog.json"
        self.second = self.root / "second.json"
        now = datetime.now(timezone.utc)
        weather = weather_fixture.cw.normalize(weather_fixture.rows(weather_fixture.replay.START.replace(hour=0)),
                    weather_fixture.TABLE, weather_fixture.GEOMETRY, historical=True, now=now)
        _, source = production.weather_window(weather, self.query["from"], "replay", now)
        source["source_sha256"] = "b"*64
        self.data.update(model_metadata={"schema_version": 1, "model_version": "synthetic-test-only", "target": TARGET,
            "policy": POLICY, "promoted": True, "model_sha256": "a"*64, "notice": NOTICE}, forecast_provenance=source)
        self.data["windows"][0]["parcels"] = [production.assessment(1, inputs_record(),
            [{"native_cell_id": "synthetic", "area_fraction": 1}], model_fixture(), {"synthetic": 20}), self.record(2, None)]
        self.write()
        second = copy.deepcopy(self.data)
        second["run_id"] = "synthetic-second-run"
        for owner in (second["windows"][0], second["forecast_provenance"]):
            owner.update(valid_from="2026-10-09T06:00:00Z", valid_to="2026-10-09T12:00:00Z")
        second["windows"][0]["parcels"][0] = production.assessment(1, inputs_record(),
            [{"native_cell_id": "synthetic", "area_fraction": 1}], model_fixture(), {"synthetic": 40})
        write_json(self.second, second)
        self.entries = []
        for path in (self.artifact, self.second):
            data = read_json(path)
            self.entries.append({"mode": "replay", "valid_from": data["windows"][0]["valid_from"],
                "valid_to": data["windows"][0]["valid_to"], "path": path.name,
                "sha256": digest(path), "forecast_sha256": "b"*64})
        self.definition = {"schema_version": 1, "county_fips": "12091", "inventory_id": "synthetic-inventory",
                           "model_sha256": "a"*64, "entries": self.entries}
        write_json(self.catalog, self.definition)
        env = patch.dict(os.environ, {"QUASAR_EXPOSURE_CATALOG": str(self.catalog),
                                     "QUASAR_EXPOSURE_ARTIFACT_ROOT": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(exposure_catalog._catalog.cache_clear)

    def test_two_windows_select_distinct_parcels_and_unsupported_never_falls_back(self):
        first = exposure.exposure({**self.query, "parcel_ids": "1,2"})
        second_query = {**self.query, "from": self.entries[1]["valid_from"], "to": self.entries[1]["valid_to"]}
        second = exposure.exposure({**second_query, "parcel_ids": "1,2"})
        self.assertEqual((first["status"], second["status"]), ("ready", "ready"))
        self.assertNotEqual(first["parcels"]["1"]["score"], second["parcels"]["1"]["score"])
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertIsNone(second["parcels"]["2"]["score"])
        self.assertEqual(exposure.exposure({**second_query, "run_id": first["run_id"]})["status"], "changed")
        self.assertEqual(exposure.exposure({**self.query, "from": "2026-10-09T07:00:00Z",
            "to": "2026-10-09T13:00:00Z"})["status"], "unavailable")
        self.assertEqual(exposure.exposure({**self.query, "mode": "current"})["status"], "unavailable")
        # Summary caches retain only tiny aggregates, never another parcel map.
        summary = exposure._aggregate(str(self.database), self.database.stat().st_size,
            self.database.stat().st_mtime_ns, str(self.artifact), self.artifact.stat().st_size,
            self.artifact.stat().st_mtime_ns, exposure.timestamp(self.query["from"]), exposure.timestamp(self.query["to"]), 7)
        self.assertNotIn("records", summary)
        self.assertEqual(exposure._artifact.cache_info().maxsize, 1)

    def test_catalog_corruption_precedence_and_atomic_rollback(self):
        previous = self.catalog.read_bytes()
        self.assertEqual(exposure.exposure(self.query)["status"], "ready")
        self.catalog.write_text('{"schema_version":1,"schema_version":1}')
        self.assertEqual(exposure.exposure(self.query)["status"], "invalid")
        # No fallback to the otherwise valid QUASAR_EXPOSURE_FILE.
        replacement = self.root/"rollback.json"
        replacement.write_bytes(previous)
        os.replace(replacement, self.catalog)
        self.assertEqual(exposure.exposure(self.query)["status"], "ready")
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_ARTIFACT_ROOT": ""}):
            self.assertEqual(exposure.exposure(self.query)["status"], "invalid")

    def test_rejects_duplicate_paths_county_model_inventory_and_forecast_conflicts(self):
        changes = [lambda d: d["entries"].append(copy.deepcopy(d["entries"][0])),
                   lambda d: d.update(county_fips="12086"), lambda d: d.update(model_sha256="c"*64),
                   lambda d: d.update(inventory_id="different"),
                   lambda d: d["entries"][0].update(forecast_sha256="c"*64),
                   lambda d: d["entries"][0].update(path="../synthetic.json"),
                   lambda d: d["entries"][0].update(path=str(self.artifact)),
                   lambda d: d.update(entries=d["entries"]*129)]
        for change in changes:
            data = copy.deepcopy(self.definition)
            change(data)
            write_json(self.catalog, data)
            with self.subTest(change=change):
                self.assertEqual(exposure.exposure(self.query)["status"], "invalid")
        write_json(self.catalog, self.definition)
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)/"outside.json"
            outside.write_bytes(self.artifact.read_bytes())
            link = self.root/"escape.json"
            link.symlink_to(outside)
            self.definition["entries"][0]["path"] = link.name
            write_json(self.catalog, self.definition)
            self.assertEqual(exposure.exposure(self.query)["status"], "invalid")

    def test_checksum_cached_once_and_replaced_artifacts_rechecked(self):
        exposure._artifact.cache_clear()
        from quasar import modeling
        with patch.object(modeling, "digest", wraps=digest) as hashed:
            for _ in range(3):
                self.assertEqual(exposure.exposure(self.query)["status"], "ready")
            self.assertEqual(hashed.call_count, 1)
            self.artifact.write_text(self.artifact.read_text()+" ")
            self.assertEqual(exposure.exposure(self.query)["status"], "invalid")
            self.assertEqual(hashed.call_count, 2)

    def test_parity_ignores_host_metadata_and_detects_unknown_source_and_score_changes(self):
        copy_path = self.root/"copy.json"
        data = read_json(self.artifact)
        data["run_id"] = "synthetic-other-host"
        data["windows"][0]["computed_at"] = datetime.now(timezone.utc).isoformat()
        write_json(copy_path, data)
        self.assertEqual(compare_assessments(self.artifact, copy_path)["status"], "matched")
        data["windows"][0]["parcels"][1]["missing"] = ["different-reason"]
        data["forecast_provenance"]["source_sha256"] = "c"*64
        write_json(copy_path, data)
        result = compare_assessments(self.artifact, copy_path)
        self.assertEqual((result["status"], result["mismatch_count"]), ("mismatch", 2))
        data = read_json(self.artifact)
        data["windows"][0]["parcels"][0] = production.assessment(1, inputs_record(),
            [{"native_cell_id": "synthetic", "area_fraction": 1}], model_fixture(), {"synthetic": 25})
        write_json(copy_path, data)
        result = compare_assessments(self.artifact, copy_path)
        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(any(m.endswith(":score") for m in result["first_mismatches"]))

    def test_bundle_checks_file_hashes_without_confusing_inventory_identity(self):
        manifest = self.root/"transfer.json"
        definition = {"schema_version": 1, "county_fips": "12091", "files": [
            {"path": self.artifact.name, "role": "synthetic assessment", "required": True, "sha256": digest(self.artifact)},
            {"path": "missing.json", "role": "optional", "required": False, "sha256": "a"*64}]}
        write_json(manifest, definition)
        self.assertEqual(verify_bundle(manifest, self.root)["status"], "matched")
        definition["files"][0]["sha256"] = "b"*64
        write_json(manifest, definition)
        self.assertEqual(verify_bundle(manifest, self.root)["status"], "incomplete")
        definition["files"][0]["path"] = "../outside.json"
        write_json(manifest, definition)
        with self.assertRaises(ValueError):
            verify_bundle(manifest, self.root)


class ReplayBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        database, inputs, boundary, inspection, weather_path = complete_fixture(self.root)
        weather = weather_fixture.cw.normalize([row for init in weather_fixture.cw.replay_initializations()
            for row in weather_fixture.rows(exposure.timestamp(init))], weather_fixture.TABLE,
            read_json(boundary)["features"][0]["geometry"], historical=True)
        write_json(weather_path, weather)
        manifest = read_json(inspection/"manifest.json")
        manifest["provenance"]["weather"] = [{"sha256": digest(weather_path)}]
        write_json(inspection/"manifest.json", manifest)
        model = model_fixture()
        model.update(boundary_version=digest(boundary), promoted=True)
        model_path, evaluation = self.root/"model.json", self.root/"evaluation.json"
        write_json(model_path, model)
        write_json(evaluation, {"promoted": True, "model_sha256": digest(model_path),
                               "dataset_manifest": {"dataset_id": "synthetic-dataset"}})
        self.args = database, inputs, boundary, inspection, model_path, evaluation, weather_path, self.root/"release"
        self.addCleanup(exposure._artifact.cache_clear)
        self.addCleanup(exposure._aggregate.cache_clear)

    def test_dry_run_has_all_25_forward_windows_and_no_writes(self):
        with patch.object(replay_batch, "produce", side_effect=AssertionError("dry run produced data")):
            report = replay_batch.assess_replay(*self.args)
        self.assertEqual(len(report["windows"]), 25)
        self.assertTrue(all(w["status"] == "eligible" for w in report["windows"]))
        self.assertEqual(report["windows"][-1]["valid_to"], "2026-10-10T11:00:00Z")
        self.assertFalse(self.args[-1].exists())
        weather = read_json(self.args[-2])
        weather["runs"] = weather["runs"][2:]
        write_json(self.args[-2], weather)
        report = replay_batch.assess_replay(*self.args)
        self.assertEqual(report["windows"][0]["reason"], "no_eligible_forecast_initialization")
        self.assertEqual(report["windows"][7]["status"], "eligible")
        self.assertFalse(self.args[-1].exists())

    def test_real_producer_publishes_25_synthetic_windows_and_bounds_cache(self):
        report = replay_batch.assess_replay(*self.args, execute=True)
        self.assertEqual(report["status"], "produced")
        catalog = exposure_catalog.load(self.args[-1]/"catalog.json")
        self.assertEqual(len(catalog["entries"]), 25)
        self.assertEqual(exposure._artifact.cache_info().currsize, 0)
        self.assertLessEqual(exposure._aggregate.cache_info().currsize, 8)
        for entry in catalog["entries"]:
            self.assertEqual(entry["sha256"], digest(self.args[-1]/entry["path"]))
        with self.assertRaises(ValueError):
            replay_batch.assess_replay(*self.args, execute=True)

    def test_gaps_are_recorded_and_failure_never_publishes_catalog(self):
        weather = read_json(self.args[-2])
        for run in weather["runs"]:
            for row in run["rows"]:
                row["rainfall_1h_mm"] = None
        write_json(self.args[-2], weather)
        report = replay_batch.assess_replay(*self.args, execute=True)
        self.assertEqual(report["status"], "source_gap")
        self.assertTrue(all(w["status"] == "source_gap" for w in report["windows"]))
        self.assertFalse((self.args[-1]/"catalog.json").exists())
        # Restore valid weather, then inject a producer error after preflight.
        weather = weather_fixture.cw.normalize([row for init in weather_fixture.cw.replay_initializations()
            for row in weather_fixture.rows(exposure.timestamp(init))], weather_fixture.TABLE,
            weather["county_geometry"], historical=True)
        write_json(self.args[-2], weather)
        args = (*self.args[:-1], self.root/"failed-release")
        with patch.object(replay_batch, "produce", side_effect=ValueError("synthetic identity failure")):
            with self.assertRaisesRegex(ValueError, "identity failure"):
                replay_batch.assess_replay(*args, execute=True)
        self.assertFalse((args[-1]/"catalog.json").exists())
        self.assertEqual(read_json(args[-1]/"coverage.json")["status"], "failed")

    def test_failure_after_a_complete_window_retains_evidence_without_publishing_release(self):
        original = replay_batch.produce
        calls = 0
        def fail_after_first(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("synthetic second-window failure")
            return original(*args, **kwargs)
        with patch.object(replay_batch, "produce", side_effect=fail_after_first):
            with self.assertRaisesRegex(ValueError, "second-window"):
                replay_batch.assess_replay(*self.args, execute=True)
        self.assertTrue((self.args[-1]/"window-00.json").exists())
        self.assertFalse((self.args[-1]/"catalog.json").exists())
        report = read_json(self.args[-1]/"coverage.json")
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["windows"][0]["status"], "produced")
