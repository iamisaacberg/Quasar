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
        self.assertEqual(exposure.summarize([]), {"parcel_count":0,"scored_count":0,"unknown_count":0,"coverage":0,"incomplete":True,"elevated_count":0,"p90_score":None})

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
        for patch_query in ({"parcel_ids": ",".join(str(i) for i in range(101))}, {"parcel_ids": "-1"}, {"parcel_ids":"x"}, {"resolution": "8"}, {"parcel_ids": "1,1"}, {"mode": "what_if"},
                            {"from": "2026-10-09T05:00:00"}, {"to": "2026-10-09T12:00:00Z"}):
            with self.subTest(patch_query=patch_query), self.assertRaises(ValueError):
                exposure.exposure({**self.query, **patch_query})

    # protects: current scores expire by computation age independently of valid window; fails_when: old computation remains ready; seam: none; no_claim: live forecasts; why_new: existing stale case has an expired forecast window.
    def test_current_computation_age_and_query_caps(self):
        now=datetime.now(timezone.utc)
        window=self.data["windows"][0]
        window.update(valid_from=now.isoformat(), valid_to=(now+timedelta(hours=6)).isoformat(), computed_at=(now-timedelta(hours=1)).isoformat())
        self.write()
        query={"from":window["valid_from"],"to":window["valid_to"],"mode":"current"}
        self.assertEqual(exposure.exposure(query)["status"],"ready")
        self.assertEqual(len(exposure.exposure({**query,"parcel_ids":",".join(str(i) for i in range(100))})["parcels"]),100)
        window["computed_at"]=(now-timedelta(hours=3)).isoformat();self.write()
        self.assertEqual(exposure.exposure(query)["status"],"stale")
        with self.assertRaises(ValueError):exposure.exposure({"to":query["to"]})

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

    def test_remote_unknown_assessments_validate_factor_shapes(self):
        remote = exposure.exposure({**self.query, "parcel_ids": "3"})
        remote["parcels"]["3"]["factors"] = [{"name": "synthetic", "value": 0, "contribution": "invalid"}]
        with patch.dict(os.environ, {"QUASAR_LINUXONE_API_URL": "https://linuxone.example", "QUASAR_LINUXONE_API_TOKEN": "x"*32}):
            with patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(json.dumps(remote).encode())
                with self.assertRaises(exposure.SourceUnavailable):
                    exposure.exposure({**self.query, "parcel_ids": "3"})

    # protects: proxy preserves parcel identity and freshness; fails_when: upstream ready data is stale or mis-keyed; seam: none; no_claim: live host; why_new: this exercises upstream trust boundaries.
    def test_remote_rejects_miskeyed_parcels_and_invalid_ready_metadata(self):
        original = exposure.exposure({**self.query, "parcel_ids": "1"})
        mutations = [
            lambda d: d["parcels"]["1"].update(parcel_id=2),
            lambda d: d.update(run_id=""),
            lambda d: d.update(method_version=""),
            lambda d: d.update(inventory_id=""),
            lambda d: d.update(resolution=6),
            lambda d: d.update(aggregation="other"),
            lambda d: d.update(computed_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()),
        ]
        with patch.dict(os.environ, {"QUASAR_LINUXONE_API_URL": "https://linuxone.example", "QUASAR_LINUXONE_API_TOKEN": "x"*32}):
            for mutate in mutations:
                remote=copy.deepcopy(original);mutate(remote)
                with self.subTest(mutate=mutate), patch.object(exposure, "build_opener") as opener:
                    opener.return_value.open.return_value = BytesIO(json.dumps(remote).encode())
                    with self.assertRaises(exposure.SourceUnavailable):
                        exposure.exposure({**self.query, "parcel_ids": "1"})
            remote=copy.deepcopy(original)
            with patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value=BytesIO(json.dumps(remote).encode())
                with self.assertRaises(exposure.SourceUnavailable):
                    exposure.exposure({**self.query, "mode": "current", "parcel_ids": "1"})


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

    # protects: authenticated route and failure status contract; fails_when: upstream failure returns success or local data; seam: none; no_claim: deployed authentication; why_new: previous API cases only covered unconfigured and missing credentials.
    def test_authenticated_success_and_source_failure_statuses(self):
        path="/api/exposure?from=2026-10-09T05:00:00Z&to=2026-10-09T11:00:00Z&mode=replay"
        def authenticated_status():
            connection=test_api.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
            try:
                connection.request("GET",path,headers={"X-Quasar-Parcel-Token":"x"*32})
                response=connection.getresponse();response.read()
                return response.status
            finally:connection.close()
        with patch.dict(os.environ, {"QUASAR_PARCEL_DATABASE":"synthetic.sqlite3","QUASAR_PARCEL_API_TOKEN":""}):
            self.assertEqual(self.request(path)[0],503)
        with patch.dict(os.environ, {"QUASAR_PARCEL_DATABASE":"synthetic.sqlite3","QUASAR_PARCEL_API_TOKEN":"x"*32}):
            with patch("quasar.server.exposure",return_value={"status":"ready","cells":{},"parcels":{}}):
                self.assertEqual(authenticated_status(),200)
            with patch("quasar.server.exposure",side_effect=exposure.SourceUnavailable("synthetic outage")):
                self.assertEqual(authenticated_status(),502)
