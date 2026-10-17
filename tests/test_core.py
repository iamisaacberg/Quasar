import io
import json
import math
import unittest
from urllib.error import URLError

from quasar.adapters.nws import fetch_for_demo_point
from quasar.notifications import preview
from quasar.pipeline import collection, feature_for, scenarios
from quasar.scoring import WEIGHTS, score


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(rainfall_6h_mm=40, elevation_m=3, fema_zone="AE",
                           waterway_distance_m=200, gauge_margin_m=0.5)

    def test_monotonic_weather_and_terrain(self):
        baseline = score(self.inputs)["score"]
        changes = dict(rainfall_6h_mm=90, elevation_m=1, waterway_distance_m=50, gauge_margin_m=-0.2)
        for key, value in changes.items():
            with self.subTest(key=key):
                self.assertGreater(score({**self.inputs, key: value})["score"], baseline)

    def test_contributions_account_for_score(self):
        result = score(self.inputs)
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1)
        self.assertAlmostEqual(sum(f["contribution"] for f in result["factors"]), result["score"], delta=0.05)

    def test_missing_and_unrecognized_data_are_unknown(self):
        for key in WEIGHTS:
            with self.subTest(key=key):
                result = score({**self.inputs, key: None})
                self.assertIsNone(result["score"])
                self.assertIn(key, result["missing"])
        self.assertEqual(score({**self.inputs, "fema_zone": "UNMAPPED"})["band"], "unknown")

    def test_bad_numeric_values_rejected(self):
        for value in [math.nan, math.inf, -math.inf, True, "40", -1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                score({**self.inputs, "rainfall_6h_mm": value})

    def test_extreme_valid_inputs_are_bounded(self):
        result = score(dict(rainfall_6h_mm=10000, elevation_m=-100, fema_zone="VE",
                            waterway_distance_m=0, gauge_margin_m=-10))
        self.assertEqual(result["score"], 100)


class PipelineTests(unittest.TestCase):
    def test_every_scenario_is_county_scoped_and_json_safe(self):
        for scenario in scenarios():
            data = collection(scenario["id"])
            self.assertEqual(data["county_fips"], "12091")
            self.assertEqual(data["mode"], "historical_mixed_demo" if scenario["id"] == "isaias-2026" else "synthetic_demo")
            self.assertTrue(data["features"])
            self.assertEqual({f["properties"]["county_fips"] for f in data["features"]}, {"12091"})
            json.dumps(data, allow_nan=False)

    def test_out_of_county_record_rejected(self):
        with self.assertRaises(ValueError):
            feature_for({"county_fips": "12011"}, scenarios()[0])

    def test_invalid_coordinates_rejected(self):
        for lon, lat in [(math.nan, 25), (-80, 100), ("-80", 25)]:
            with self.subTest(lon=lon, lat=lat), self.assertRaises(ValueError):
                feature_for({"county_fips": "12091", "longitude": lon, "latitude": lat}, scenarios()[0])

    def test_unknown_scenario_rejected(self):
        with self.assertRaises(ValueError):
            collection("actual-hurricane")

    def test_exercise_progression_changes_scores(self):
        first = {f["id"]: f["properties"]["risk"]["score"] for f in collection("baseline")["features"]}
        last = {f["id"]: f["properties"]["risk"]["score"] for f in collection("peak")["features"]}
        self.assertGreater(last["demo-001"], first["demo-001"])
        self.assertIsNone(last["demo-006"])


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"property_ids": ["demo-001"], "opt_in": True, "scenario": "peak", "channel": "sms"}

    def test_simulation_never_sends_and_deduplicates(self):
        self.payload["property_ids"] *= 2
        result = preview(self.payload)
        self.assertEqual(result["sent_count"], 0)
        self.assertEqual(result["preview_count"], 1)
        self.assertIn("DEMO ONLY", result["messages"][0]["text"])

    def test_opt_in_is_explicit_boolean(self):
        for value in [None, False, "true", 1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                preview({**self.payload, "opt_in": value})

    def test_unknown_site_and_channel_rejected(self):
        for change in [{"property_ids":["real-home"]}, {"channel":"push"}, {"property_ids":[]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                preview({**self.payload, **change})

    def test_unknown_or_lower_risk_does_not_generate_preview(self):
        self.assertEqual(preview({**self.payload, "property_ids":["demo-006"]})["preview_count"], 0)
        self.assertEqual(preview({**self.payload, "scenario":"baseline"})["preview_count"], 0)


class NwsTests(unittest.TestCase):
    def test_point_request_provenance_and_headers(self):
        def opener(request, timeout):
            self.assertIn("point=", request.full_url)
            self.assertEqual(request.get_header("User-agent"), "Quasar-test")
            self.assertEqual(timeout, 15)
            return io.BytesIO(b'{"type":"FeatureCollection","features":[]}')
        result = fetch_for_demo_point("demo-001", "Quasar-test", opener=opener)
        self.assertEqual(result["scope"], "single_demo_point")
        self.assertIn("fetched_at", result)
        self.assertEqual(result["data"]["features"], [])

    def test_outage_not_converted_to_no_alerts(self):
        def broken(*args, **kwargs):
            raise URLError("upstream unavailable")
        with self.assertRaises(URLError):
            fetch_for_demo_point("demo-001", "Quasar-test", opener=broken)

    def test_bad_payload_and_pagination_rejected(self):
        for payload in [{}, {"type":"FeatureCollection", "features":[], "pagination":{"next":"next-page"}}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                fetch_for_demo_point("demo-001", "Quasar-test", opener=lambda *a, **kw: io.BytesIO(json.dumps(payload).encode()))

    def test_unrecognized_point_rejected_before_network(self):
        with self.assertRaises(ValueError):
            fetch_for_demo_point("outside-county", "Quasar-test")
