"""Synthetic performance seams; no network, real parcels, host access or training."""
import copy
import gzip
import json
import os
import sqlite3
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import test_exposure
import test_api
from test_county_weather import current
from quasar import exposure, forecast_timeline
from quasar.exposure_store import prepare, _verified
from quasar.server import built_assets


class PreparedExposureTests(unittest.TestCase):
    record = staticmethod(test_exposure.ExposureTests.record)
    write = test_exposure.ExposureTests.write
    def setUp(self):
        test_exposure.ExposureTests.setUp(self)
        self.serving = self.artifact.parent / "serving.sqlite3"
        self.addCleanup(_verified.cache_clear)

    def test_indexed_results_equal_legacy_for_every_resolution_and_record(self):
        expected = {resolution: exposure.exposure({**self.query, "resolution": str(resolution)}) for resolution in range(4, 8)}
        records = exposure.exposure({**self.query, "parcel_ids": "1,2,3,4"})
        self.assertEqual(prepare(self.database, self.artifact, self.serving)["windows"], 1)
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_DATABASE": str(self.serving)}), \
                patch.object(exposure, "_artifact", side_effect=AssertionError("No runtime JSON parse")), \
                patch.object(exposure, "_aggregate", side_effect=AssertionError("No runtime county aggregation")):
            for resolution in range(4, 8):
                self.assertEqual(exposure.exposure({**self.query, "resolution": str(resolution)}), expected[resolution])
            self.assertEqual(exposure.exposure({**self.query, "parcel_ids": "1,2,3,4"}), records)
            self.assertEqual(exposure.exposure({**self.query, "run_id": "old"})["status"], "changed")
            self.assertEqual(exposure.exposure({**self.query, "mode": "current"})["status"], "stale")
            self.assertEqual(exposure.exposure({**self.query, "from": "2026-10-09T06:00:00Z", "to": "2026-10-09T12:00:00Z"})["status"], "unavailable")

    def test_invalid_preparation_never_replaces_previous_database(self):
        prepare(self.database, self.artifact, self.serving)
        previous = self.serving.read_bytes()
        self.data["windows"][0]["parcels"][0]["score"] = 101
        self.write()
        with self.assertRaises(ValueError):
            prepare(self.database, self.artifact, self.serving)
        self.assertEqual(self.serving.read_bytes(), previous)
        self.assertEqual(list(self.serving.parent.glob("*.tmp")), [])

    def test_invalid_configured_database_never_falls_back_to_legacy(self):
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_DATABASE": str(self.serving)}):
            self.assertEqual(exposure.exposure(self.query)["status"], "invalid")
        prepare(self.database, self.artifact, self.serving)
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE metadata SET value=? WHERE key='source_provenance'", (json.dumps({"output_sha256": "replacement", "county_boundary": {"sha256": "different"}}),))
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_DATABASE": str(self.serving)}):
            self.assertEqual(exposure.exposure(self.query)["status"], "invalid")

    def test_multiple_windows_and_duplicate_windows(self):
        other = copy.deepcopy(self.data["windows"][0])
        other.update(valid_from="2026-10-09T06:00:00Z", valid_to="2026-10-09T12:00:00Z")
        other["parcels"][0] = self.record(1, 65)
        self.data["windows"].append(other)
        self.write()
        self.assertEqual(prepare(self.database, self.artifact, self.serving)["windows"], 2)
        with patch.dict(os.environ, {"QUASAR_EXPOSURE_DATABASE": str(self.serving)}):
            result = exposure.exposure({**self.query, "from": other["valid_from"], "to": other["valid_to"], "parcel_ids": "1"})
            self.assertEqual(result["parcels"]["1"]["score"], 65)


class ForecastCacheTests(unittest.TestCase):
    def setUp(self):
        forecast_timeline._prepared.clear()

    def tearDown(self):
        forecast_timeline._prepared.clear()

    def test_shared_preparation_detects_changed_content_and_failed_source(self):
        from test_forecast_timeline import ArchivePlaybackTests
        data = ArchivePlaybackTests().archive()
        with patch.object(forecast_timeline, "read_snapshot", return_value=data), \
                patch.object(forecast_timeline.county, "PreparedForecast", wraps=forecast_timeline.county.PreparedForecast) as prepare_forecast:
            first = forecast_timeline.timeline()
            self.assertIs(forecast_timeline.timeline(), first)
            self.assertEqual(prepare_forecast.call_count, 1)
            data["runs"][0]["rows"][0]["rainfall_1h_mm"] = None
            self.assertIsNot(forecast_timeline.timeline(), first)
            self.assertEqual(prepare_forecast.call_count, 2)
        with patch.object(forecast_timeline, "read_snapshot", side_effect=forecast_timeline.BridgeUnavailable):
            self.assertEqual(forecast_timeline.timeline()["status"], "unavailable")


class LoadingHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_api.ApiTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_api.ApiTests.tearDownClass.__func__(cls)

    def get_headers(self, path, encoding="", method="GET"):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, headers={"Accept-Encoding": encoding})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_hashed_assets_only_manifest_files_are_public(self):
        assets, javascript, stylesheet = built_assets()
        self.assertTrue(assets)
        _, body, headers = self.get_headers("/")
        self.assertIn(javascript.encode(), body)
        self.assertIn(stylesheet.encode(), body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        for path in assets:
            status, body, headers = self.get_headers(path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
            self.assertIn("immutable", headers["Cache-Control"])
        for path in ("/ui/.vite/manifest.json", "/ui/assets.json", "/ui/assets/unknown.js", "/ui/assets/../../.env"):
            self.assertEqual(self.get_headers(path)[0], 404)

    def test_compression_negotiation_and_head(self):
        _, original, headers = self.get_headers("/app.js")
        self.assertNotIn("Content-Encoding", headers)
        _, compressed, headers = self.get_headers("/app.js", "br, gzip")
        self.assertEqual(headers["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(compressed), original)
        self.assertEqual(len(compressed), int(headers["Content-Length"]))
        self.assertEqual(headers["Vary"], "Accept-Encoding")
        self.assertIn("quasar;dur=", headers["Server-Timing"])
        _, uncompressed, headers = self.get_headers("/app.js", "gzip;q=0, *;q=1")
        self.assertEqual(uncompressed, original)
        self.assertNotIn("Content-Encoding", headers)
