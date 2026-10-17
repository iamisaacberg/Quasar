import unittest
from unittest.mock import patch

from quasar.analysis import compare_scenarios, scenario_report
from quasar.pipeline import collection


class AnalysisTests(unittest.TestCase):
    def test_report_matches_application_scores_and_preserves_provenance(self):
        data = collection("peak")
        report = scenario_report("peak")
        self.assertEqual(report["county_fips"], "12091")
        self.assertEqual(report["mode"], data["mode"])
        self.assertEqual(report["provenance"], data["provenance"])
        scores = {f["id"]: f["properties"]["risk"]["score"] for f in data["features"]}
        self.assertEqual({r["property_id"]: r["score"] for r in report["rows"]}, scores)
        self.assertEqual(report["summary"]["scored_count"] + report["summary"]["unknown_count"], len(scores))

    def test_mean_excludes_unknown_values_and_all_unknown_stays_null(self):
        data = collection("baseline")
        for feature in data["features"]:
            feature["properties"]["risk"].update(score=None, band="unknown", missing=["elevation_m"])
        with patch("quasar.analysis.collection", return_value=data):
            self.assertIsNone(scenario_report()["summary"]["mean_score"])
            data["features"][0]["properties"]["risk"].update(score=80, band="elevated", missing=[])
            self.assertEqual(scenario_report()["summary"]["mean_score"], 80)

    def test_comparison_retains_each_site_and_scenario_without_filling_nulls(self):
        rows = compare_scenarios()
        self.assertEqual({r["scenario"] for r in rows}, {"baseline", "heavy-rain", "peak"})
        unknown = [r for r in rows if r["property_id"] == "demo-006"]
        self.assertEqual(len(unknown), 3)
        self.assertTrue(all(r["score"] is None for r in unknown))

    def test_invalid_scenario_is_an_error(self):
        with self.assertRaises(ValueError):
            scenario_report("unrecognized")
