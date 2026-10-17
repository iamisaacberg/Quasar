"""Synthetic assessments exercise rendering contracts, not flood validation."""
import copy
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

from quasar import exposure
import test_api


class ExposureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.database, self.artifact = root / "synthetic.sqlite3", root / "synthetic.json"
        with sqlite3.connect(self.database) as connection:
            connection.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE parcels(parcel_id INTEGER PRIMARY KEY);
                CREATE TABLE county_cells(cell_id TEXT PRIMARY KEY,resolution INTEGER);
                CREATE TABLE cell_parcels(cell_id TEXT,parcel_id INTEGER,PRIMARY KEY(cell_id,parcel_id));
                INSERT INTO parcels VALUES(1),(2),(3),(4);
                INSERT INTO county_cells VALUES('synthetic-r7',7),('synthetic-r4',4);
                INSERT INTO cell_parcels VALUES('synthetic-r7',1),('synthetic-r7',2),('synthetic-r7',3),('synthetic-r7',4),('synthetic-r4',1),('synthetic-r4',2),('synthetic-r4',3),('synthetic-r4',4);
            """)
            connection.executemany("INSERT INTO metadata VALUES(?,?)", [
                ("county_fips", json.dumps("12091")),
                ("source_provenance", json.dumps({"output_sha256": "synthetic-inventory",
                                                 "county_boundary": {"sha256": "synthetic-boundary"}}))])
        self.data = {"schema_version": 1, "county_fips": "12091", "run_id": "synthetic-run",
                     "inventory_id": "synthetic-inventory", "method_version": "synthetic-test-only",
                     "windows": [{"valid_from": "2026-10-09T05:00:00Z", "valid_to": "2026-10-09T11:00:00Z",
                                  "computed_at": datetime.now(timezone.utc).isoformat(),
                                  "parcels": [self.record(1, 0), self.record(2, 100), self.record(3, None)]}]}
        self.write()
        self.query = {"from": "2026-10-09T05:00:00Z", "to": "2026-10-09T11:00:00Z", "mode": "replay"}
        env = patch.dict(os.environ, {"QUASAR_EXPOSURE_FILE": str(self.artifact),
                                     "QUASAR_PARCEL_DATABASE": str(self.database), "QUASAR_LINUXONE_API_URL": ""})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(exposure._artifact.cache_clear)
        self.addCleanup(exposure._aggregate.cache_clear)

    @staticmethod
    def record(parcel_id, score):
        return {"parcel_id": parcel_id, "score": score, "missing": [] if score is not None else ["terrain"],
                "factors": [] if score is None else [{"name": "synthetic_factor", "value": score, "contribution": score}]}

    def write(self):
        self.artifact.write_text(json.dumps(self.data))
        exposure._artifact.cache_clear()
        exposure._aggregate.cache_clear()

    def test_complete_inventory_p90_coverage_and_both_elevated_bands(self):
        result = exposure.exposure(self.query)
        self.assertEqual(result["status"], "ready")
        cell = result["cells"]["synthetic-r7"]
        self.assertEqual(cell, {"parcel_count": 4, "scored_count": 2, "unknown_count": 2,
                                "coverage": .5, "incomplete": True, "elevated_count": 1, "p90_score": 90.0})
        # Only one parcel is requested; coverage still uses every inventory member.
        page = exposure.exposure({**self.query, "parcel_ids": "1", "run_id": "synthetic-run"})
        self.assertEqual(page["parcels"]["1"]["score"], 0)
        self.assertEqual(page["cells"], {})
        coarse = exposure.exposure({**self.query, "resolution": "4"})
        self.assertEqual(coarse["cells"]["synthetic-r4"], cell)

    def test_unknowns_are_never_zero_and_run_changes_are_explicit(self):
        result = exposure.exposure({**self.query, "parcel_ids": "3,4"})
        self.assertIsNone(result["parcels"]["3"]["score"])
        self.assertEqual(result["parcels"]["4"]["missing"], ["assessment_unavailable"])
        self.assertEqual(exposure.exposure({**self.query, "run_id": "old"})["status"], "changed")
        self.assertEqual(exposure.summarize([None, None])["p90_score"], None)
        self.assertEqual(exposure.summarize([65, 85, 100])["elevated_count"], 3)

    def test_bad_scores_explanations_inventory_and_windows_fail_closed(self):
        original = copy.deepcopy(self.data)
        mutations = [
            lambda d: d.update(county_fips="12086"),
            lambda d: d.update(inventory_id="different-inventory"),
            lambda d: d["windows"][0]["parcels"].append(self.record(9, 50)),
            lambda d: d["windows"][0]["parcels"].append(self.record(1, 50)),
            lambda d: d["windows"][0]["parcels"][0].update(score=True),
            lambda d: d["windows"][0]["parcels"][0].update(score=101),
            lambda d: d["windows"][0]["parcels"][0].update(score=50),
            lambda d: d["windows"][0]["parcels"][1].update(missing=["terrain"]),
            lambda d: d["windows"].append(copy.deepcopy(d["windows"][0])),
        ]
        for mutate in mutations:
            self.data = copy.deepcopy(original)
            mutate(self.data)
            self.write()
            with self.subTest(mutate=mutate):
                self.assertEqual(exposure.exposure(self.query)["status"], "invalid")

    def test_freshness_and_exact_window_preserve_unknown(self):
        self.assertEqual(exposure.exposure({**self.query, "mode": "current"})["status"], "stale")
        shifted = {**self.query, "from": "2026-10-09T06:00:00Z", "to": "2026-10-09T12:00:00Z"}
        self.assertEqual(exposure.exposure(shifted)["status"], "unavailable")
        self.data["windows"][0]["computed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.write()
        self.assertEqual(exposure.exposure(self.query)["status"], "invalid")

    def test_invalid_queries_are_not_source_failures(self):
        for patch_query in ({"resolution": "8"}, {"parcel_ids": "1,1"}, {"mode": "what_if"},
                            {"from": "2026-10-09T05:00:00"}, {"to": "2026-10-09T12:00:00Z"}):
            with self.subTest(patch_query=patch_query), self.assertRaises(ValueError):
                exposure.exposure({**self.query, **patch_query})

    def test_remote_summary_is_proxied_and_failure_never_uses_local_assessments(self):
        remote = exposure.exposure(self.query)
        remote["parcels"] = {}
        with patch.dict(os.environ, {"QUASAR_LINUXONE_API_URL": "https://linuxone.example", "QUASAR_LINUXONE_API_TOKEN": "x"*32}):
            with patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(json.dumps(remote).encode())
                result = exposure.exposure(self.query)
                self.assertEqual(result["cells"], remote["cells"])
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header("X-quasar-parcel-token"), "x"*32)
            with patch.object(exposure, "build_opener", side_effect=OSError("synthetic outage")):
                with self.assertRaises(exposure.SourceUnavailable):
                    exposure.exposure(self.query)
            remote["cells"]["synthetic-r7"]["coverage"] = 1
            with patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(json.dumps(remote).encode())
                with self.assertRaises(exposure.SourceUnavailable):
                    exposure.exposure(self.query)


class ExposureApiTests(unittest.TestCase):
    setUpClass = classmethod(test_api.ApiTests.setUpClass.__func__)
    tearDownClass = classmethod(test_api.ApiTests.tearDownClass.__func__)
    request = test_api.ApiTests.request

    def test_scale_and_unconfigured_api(self):
        status, body, _ = self.request("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["exposure_scale"], exposure.SCALE)
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_FILE": "", "QUASAR_PARCEL_DATABASE": "", "QUASAR_LINUXONE_API_URL": ""}):
            status, body, _ = self.request("/api/exposure?from=2026-10-09T05:00:00Z&to=2026-10-09T11:00:00Z&mode=replay")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "not_configured")
        self.assertEqual(self.request("/api/exposure?county_fips=12086")[0], 400)
        self.assertEqual(self.request("/api/exposure?from=x&from=y")[0], 400)

    def test_local_database_endpoint_requires_existing_parcel_token(self):
        with patch.dict(os.environ, {"QUASAR_PARCEL_DATABASE": "synthetic.sqlite3", "QUASAR_PARCEL_API_TOKEN": "x"*32}):
            self.assertEqual(self.request("/api/exposure")[0], 401)
