"""Synthetic station/report fixtures validate observation handling, not real floods."""
import copy
import unittest

from quasar.modeling.observations import SELECTED, gauge_series, high_water_marks, local_storm_reports, rainfall_reports, storm_reports

COUNTY = {"type": "Polygon", "coordinates": [
    [[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]],
    [[.5, .5], [1.5, .5], [1.5, 1.5], [.5, 1.5], [.5, .5]]
]}


def station(lon=0, lat=0):
    return {"sourceInfo": {"siteCode": [{"value": "synthetic"}], "siteName": "Synthetic gauge",
                           "geoLocation": {"geogLocation": {"srs": "EPSG:4326", "longitude": lon, "latitude": lat}}},
            "variable": {"variableCode": [{"value": "00065"}], "unit": {"unitCode": "ft"}, "noDataValue": -999999},
            "values": [{"value": [{"dateTime": SELECTED[0], "value": "0", "qualifiers": ["P"]},
                                    {"dateTime": SELECTED[1], "value": "-999999", "qualifiers": []}]}]}


class ObservationTests(unittest.TestCase):
    def test_station_zero_missing_and_gauge_datum_remain_distinct(self):
        rows, rejected = gauge_series({"value": {"timeSeries": [station()]}}, COUNTY, *SELECTED)
        self.assertEqual(rejected, 0)
        self.assertEqual(rows[0]["observations"][0]["value"], 0)
        self.assertIsNone(rows[0]["observations"][1]["value"])
        self.assertEqual(rows[0]["observations"][0]["qualifiers"], ["P"])
        self.assertIn("not parcel NAVD88", rows[0]["vertical_reference"])

    def test_point_in_bounding_box_hole_is_excluded(self):
        rows, rejected = gauge_series({"value": {"timeSeries": [station(1, 1), station(3, 3)]}}, COUNTY, *SELECTED)
        self.assertEqual(rows, [])
        self.assertEqual(rejected, 2)

    def test_duplicate_observations_and_unsupported_units_never_become_valid(self):
        source = station();source["values"][0]["value"].append(copy.deepcopy(source["values"][0]["value"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            gauge_series({"value": {"timeSeries": [source]}}, COUNTY, *SELECTED)
        source = station();source["variable"]["unit"]["unitCode"] = "unknown"
        rows, _ = gauge_series({"value": {"timeSeries": [source]}}, COUNTY, *SELECTED)
        self.assertTrue(all(r["missing"] for r in rows[0]["observations"]))

    def test_county_tag_does_not_replace_report_point_validation_or_create_parcel_label(self):
        row = {"STATE_FIPS": "12", "CZ_TYPE": "C", "CZ_FIPS": "91", "EVENT_TYPE": "Flash Flood",
               "EVENT_ID": "synthetic", "EPISODE_ID": "synthetic", "BEGIN_LON": "0", "BEGIN_LAT": "0"}
        rows, rejected = storm_reports([row, {**row, "BEGIN_LON": "1", "BEGIN_LAT": "1"}], COUNTY)
        self.assertEqual(len(rows), 1);self.assertEqual(rejected, 1)
        self.assertIsNone(rows[0]["parcel_label"])
        self.assertFalse(rows[0]["coverage_backed_negative"])

    def test_trace_missing_and_overlapping_precipitation_periods_are_not_zero_filled_or_summed(self):
        text = "station,valid,lon,lat,p01i\nCEW,2026-10-09 06:53,0,0,T\nCEW,2026-10-09 06:55,0,0,M\nCEW,2026-10-09 07:53,0,0,0.00\n"
        rows, rejected = rainfall_reports(text, COUNTY)
        self.assertEqual(len(rows), 3);self.assertEqual(rejected, 0)
        self.assertTrue(rows[0]["trace"]);self.assertIsNone(rows[0]["precipitation_1h"])
        self.assertTrue(rows[1]["missing"]);self.assertIsNone(rows[1]["precipitation_1h"])
        self.assertEqual(rows[2]["precipitation_1h"], 0)

    def test_invalid_rainfall_and_unrecognized_csv_are_explicit(self):
        text = "station,valid,lon,lat,p01i\n" + "".join(
            f"CEW,2026-10-09 06:53,0,0,{value}\n" for value in ("NaN", "inf", "-1", "bad"))
        rows, _ = rainfall_reports(text, COUNTY)
        self.assertTrue(all(r["missing"] and r["precipitation_1h"] is None for r in rows))
        with self.assertRaisesRegex(ValueError, "required columns"):
            rainfall_reports("unexpected,columns\n1,2\n", COUNTY)
        with self.assertRaisesRegex(ValueError, "required columns"):
            local_storm_reports("unexpected,columns\n1,2\n", COUNTY)

    def test_coastal_hwm_keeps_datum_quality_and_unreviewed_mechanism(self):
        row = {"id": 1, "site_id": 1, "longitude": 0, "latitude": 0, "elev_ft": 3.2,
               "horizontal_datum_name": "WGS84 (from Digital Map)", "environment": "Coastal", "hwm_quality_name": "Good"}
        rows, _ = high_water_marks([row], COUNTY, {"id": 1, "name": "Synthetic coastal storm"})
        self.assertEqual(rows[0]["source_fields"]["hwm_quality_name"], "Good")
        self.assertIn("unreviewed", rows[0]["mechanism"])
        self.assertIsNone(rows[0]["parcel_label"])
        self.assertEqual(high_water_marks([{**row, "horizontal_datum_name": "unknown"}], COUNTY, {})[0], [])

    def test_selected_lsr_keeps_reported_flood_and_excludes_wind_without_parcel_labels(self):
        text = "VALID,LAT,LON,TYPETEXT,SOURCE,CITY,REMARK\n202610100041,0,0,FLASH FLOOD,Public,Synthetic town,Reported street flooding\n202610100041,0,0,TROPICAL CYCLONE,Public,Synthetic town,Wind\n202610100041,1,1,FLASH FLOOD,Public,Synthetic hole,Excluded\n"
        rows, rejected = local_storm_reports(text, COUNTY)
        self.assertEqual(len(rows), 1);self.assertEqual(rejected, 1)
        self.assertEqual(rows[0]["at"], "2026-10-10T00:41:00+00:00")
        self.assertFalse(rows[0]["association_verified"])
        self.assertIsNone(rows[0]["parcel_label"])
