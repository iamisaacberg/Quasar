"""Synthetic official-message format fixtures; never actual warnings or an all-clear."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from quasar.adapters import county_alerts as alerts
from quasar.modeling import write_json
import test_api

NOW = datetime(2026, 10, 18, 3, tzinfo=timezone.utc)


def message(identifier="synthetic-message", **updates):
    props = {"id": identifier, "status": "Actual", "messageType": "Alert", "event": "Synthetic format test only",
             "sent": (NOW-timedelta(minutes=5)).isoformat(), "effective": (NOW-timedelta(minutes=5)).isoformat(),
             "expires": (NOW+timedelta(hours=1)).isoformat(), "onset": None, "ends": None,
             "headline": "Synthetic format test only", "description": "Not an actual official alert.",
             "instruction": "Test fixture only", "areaDesc": "Synthetic county query fixture", "references": []}
    props.update(updates)
    return {"type": "Feature", "geometry": None, "properties": props}


def snapshot(features=None):
    return {"schema_version": 1, "county_fips": "12091", "source_url": alerts.SOURCE_URL,
            "retrieved_at": NOW.isoformat(), "complete": True, "pages": 1,
            "coverage": "NWS county UGC FLC091 including intersecting zones", "coverage_reference": alerts.GUIDE,
            "features": features or [], "failure_reason": None}


class CountyAlertTests(unittest.TestCase):
    def test_empty_complete_partial_error_stale_and_disconnected_are_distinct(self):
        self.assertEqual(alerts.interpret(snapshot(), now=NOW)["status"], "empty")
        self.assertIn("not an all-clear", alerts.interpret(snapshot(), now=NOW)["message"])
        data = snapshot()
        data["complete"] = False
        self.assertEqual(alerts.interpret(data, now=NOW)["status"], "partial")
        data["pages"] = 0
        self.assertEqual(alerts.interpret(data, now=NOW)["status"], "error")
        self.assertEqual(alerts.interpret(snapshot(), now=NOW+timedelta(seconds=120))["status"], "stale")
        self.assertEqual(alerts.official_alerts()["status"], "not_connected")

    def test_lifecycle_updates_cancellations_future_expired_and_duplicate_messages(self):
        original = message()
        update = message("synthetic-update", messageType="Update", sent=(NOW-timedelta(minutes=1)).isoformat(),
                         references=[{"identifier": "synthetic-message"}])
        expired = message("synthetic-expired", expires=(NOW-timedelta(minutes=1)).isoformat())
        upcoming = message("synthetic-upcoming", onset=(NOW+timedelta(minutes=10)).isoformat())
        future = message("synthetic-future", sent=(NOW+timedelta(minutes=5)).isoformat())
        data = snapshot([original, original, update, expired, upcoming, future])
        result = alerts.interpret(data, now=NOW)
        self.assertEqual(result["status"], "ready")
        self.assertEqual({a["id"] for a in result["alerts"]}, {"synthetic-update", "synthetic-upcoming"})
        self.assertEqual(next(a for a in result["alerts"] if a["id"] == "synthetic-upcoming")["lifecycle"], "upcoming")
        self.assertEqual(result["alerts"][0]["description"], "Not an actual official alert.")
        data["features"].append(message("synthetic-cancel", messageType="Cancel", sent=NOW.isoformat(), references=[{"identifier": "synthetic-update"}]))
        self.assertEqual([a["id"] for a in alerts.interpret(data, now=NOW)["alerts"]], ["synthetic-upcoming"])

    def test_bad_source_county_future_retrieval_conflicts_and_times_fail_closed(self):
        original = snapshot([message()])
        mutations = [lambda d: d.update(county_fips="12086"), lambda d: d.update(source_url="https://example.test"),
                     lambda d: d.update(retrieved_at=(NOW+timedelta(seconds=1)).isoformat()),
                     lambda d: d["features"][0]["properties"].update(expires="missing"),
                     lambda d: d["features"][0]["properties"].update(status="Exercise"),
                     lambda d: d["features"].append(message(description="conflicting duplicate"))]
        for change in mutations:
            data = copy.deepcopy(original)
            change(data)
            with self.subTest(change=change):
                result = alerts.interpret(data, now=NOW)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["alerts"], [])

    def test_bounded_pagination_requires_same_county_host_filters_and_no_redirects(self):
        calls = []
        def opener(request, timeout):
            calls.append(request)
            self.assertEqual(timeout, 10)
            return BytesIO(json.dumps({"type": "FeatureCollection", "features": [message(str(len(calls)))],
                "pagination": {"next": alerts.SOURCE_URL+"&cursor=second"} if len(calls) == 1 else {}}).encode())
        result = alerts.import_snapshot("Quasar synthetic tests", opener=opener, now=NOW)
        self.assertTrue(result["complete"])
        self.assertEqual((result["pages"], len(result["features"])), (2, 2))
        self.assertEqual(calls[0].get_header("User-agent"), "Quasar synthetic tests")
        for url in ("https://evil.example/alerts", "https://api.weather.gov/alerts?zone=FLZ205",
                    "https://api.weather.gov/alerts?active=true&zone=FLC091&status=actual&zone=FLC113"):
            with self.assertRaises(ValueError):
                alerts.page_url(url)
        def loop(request, timeout):
            return BytesIO(json.dumps({"type": "FeatureCollection", "features": [],
                                      "pagination": {"next": alerts.SOURCE_URL}}).encode())
        result = alerts.import_snapshot("Quasar synthetic tests", opener=loop, now=NOW)
        self.assertFalse(result["complete"])
        self.assertEqual(alerts.interpret(result, now=NOW)["status"], "partial")

    def test_network_error_size_limit_and_bad_identity_never_mean_empty(self):
        def fail(*args, **kwargs):
            raise OSError("Synthetic failure; contact must not be logged")
        data = alerts.import_snapshot("Synthetic identifying contact", opener=fail, now=NOW)
        self.assertEqual(alerts.interpret(data, now=NOW)["status"], "error")
        self.assertNotIn("contact", json.dumps(data))
        data = alerts.import_snapshot("Synthetic tests", opener=lambda *a, **k: BytesIO(b" "*2_000_001), now=NOW)
        self.assertFalse(data["complete"])
        for user_agent in ("", "x\ninjected"):
            with self.assertRaises(ValueError):
                alerts.import_snapshot(user_agent, opener=fail)

    def test_saved_current_snapshot_never_appears_in_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"synthetic-alerts.json"
            write_json(path, snapshot([message()]))
            with patch.dict(os.environ, {"QUASAR_NWS_ALERTS_FILE": str(path)}):
                self.assertEqual(alerts.official_alerts("archive")["status"], "not_connected")
                with patch.object(alerts, "datetime") as clock:
                    clock.now.return_value = NOW
                    self.assertEqual(alerts.official_alerts("current")["status"], "ready")
                path.write_text("corrupt")
                self.assertEqual(alerts.official_alerts("current")["status"], "invalid")


class CountyAlertApiTests(unittest.TestCase):
    setUpClass = classmethod(test_api.ApiTests.setUpClass.__func__)
    tearDownClass = classmethod(test_api.ApiTests.tearDownClass.__func__)
    request = test_api.ApiTests.request

    def test_archive_default_and_explicit_current_only(self):
        self.assertEqual(json.loads(self.request("/api/official-alerts")[1])["status"], "not_connected")
        with patch.dict(os.environ, {"QUASAR_NWS_ALERTS_FILE": ""}):
            self.assertEqual(json.loads(self.request("/api/official-alerts?source=current")[1])["status"], "not_connected")
        self.assertEqual(self.request("/api/official-alerts?source=what_if")[0], 400)
        self.assertEqual(self.request("/api/official-alerts?point=1,2")[0], 400)
