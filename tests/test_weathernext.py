import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from quasar.adapters.weathernext import bq_command, iso, load_forecast, points, query_sql, snapshot, summarize
from quasar.config import load_env, map_settings
from quasar.pipeline import collection, scenarios
from quasar.notifications import preview

TABLE = "team-project.weather.weathernext_3_0_0_0p1deg"
INIT = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
NOW = INIT + timedelta(minutes=30)


def rows():
    return [{"property_id": p["id"], "forecast_time": iso(INIT+timedelta(hours=h)),
             "rainfall_1h_mm": 2.5, "native_cell_wkt": "POLYGON((-86.5 30.5,-86.4 30.5,-86.4 30.6,-86.5 30.5))"}
            for p in points() for h in range(1,7)]


def example(data=None):
    # Synthetic test payload. Never installed as the application's live forecast.
    return snapshot(rows() if data is None else data, table=TABLE, init_time=iso(INIT), valid_from=iso(INIT), now=NOW)


class WeatherNextTests(unittest.TestCase):
    def test_query_is_run_filtered_point_join_with_correct_precipitation_units(self):
        sql = query_sql(TABLE)
        self.assertIn("t.init_time = @init_time", sql)
        self.assertIn("total_precipitation_1hr_mean * 1000", sql)
        self.assertIn("ST_COVERS", sql)
        self.assertIn("INTERVAL 6 HOUR", sql)
        self.assertNotIn("p90", sql)

    def test_query_rejects_unsafe_or_wrong_resolution_table(self):
        for name in ["project.dataset.table`; DROP TABLE t; --", TABLE.replace("0p1deg","0p05deg"), "weather.table"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                query_sql(name)

    def test_bq_defaults_to_dry_run_and_limits_bytes(self):
        args = ("team-project",TABLE,"US",iso(INIT),iso(INIT),1_000_000_000)
        command = bq_command(*args)
        self.assertIn("--dry_run=true",command)
        self.assertIn("--maximum_bytes_billed=1000000000",command)
        self.assertNotIn("--dry_run=true",bq_command(*args,execute=True))
        self.assertTrue(any("demo-001" in p for p in command))

    def test_six_contiguous_hours_are_summed_and_native_grid_preserved(self):
        result = summarize(example(),now=NOW)
        self.assertEqual(result["status"],"ready")
        self.assertEqual(result["records"]["demo-001"]["rainfall_6h_mm"],15)
        self.assertEqual(result["native_resolution"],"0.1 degree")
        self.assertTrue(result["records"]["demo-001"]["native_cells_wkt"])

    def test_missing_hour_and_null_are_unknown_not_zero(self):
        data = rows()[1:]
        data[-1]["rainfall_1h_mm"] = None
        result = summarize(example(data),now=NOW)
        for identifier in ["demo-001","demo-006"]:
            self.assertIsNone(result["records"][identifier]["rainfall_6h_mm"])
            self.assertEqual(result["records"][identifier]["status"],"incomplete")

    def test_duplicate_and_out_of_window_rows_rejected(self):
        for data in [rows()+[rows()[0]], [{**rows()[0],"forecast_time":iso(INIT)}]]:
            with self.subTest(data=data[:1]), self.assertRaises(ValueError):
                example(data)

    def test_bad_rain_and_out_of_scope_site_rejected(self):
        for change in [{"rainfall_1h_mm":-1}, {"rainfall_1h_mm":"nan"}, {"rainfall_1h_mm":True}, {"property_id":"outside-county"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                example([{**rows()[0],**change}])

    def test_stale_import_expired_window_and_old_run_disable_rainfall(self):
        original = example()
        self.assertEqual(summarize(original,now=INIT+timedelta(hours=3))["status"],"stale")
        for age in [6,13]:
            data = copy.deepcopy(original)
            data["retrieved_at"] = iso(INIT+timedelta(hours=age))
            result = summarize(data,now=INIT+timedelta(hours=age))
            self.assertEqual(result["status"],"stale")
            self.assertIsNone(result["records"]["demo-001"]["rainfall_6h_mm"])

    def test_bad_snapshot_units_and_dates_rejected(self):
        for change in [{"units":"m"}, {"county_fips":"12011"}, {"init_time":"2026-10-17T12:30:00Z"},
                       {"retrieved_at":iso(INIT+timedelta(days=1))}, {"init_time":"2026-10-17T12:00:00"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                summarize({**example(),**change},now=NOW)

    def test_invalid_snapshot_has_explicit_status(self):
        with patch.dict(os.environ,{"QUASAR_WEATHERNEXT_FILE":"/nonexistent/quasar-weather.json"}):
            self.assertEqual(load_forecast()["status"],"not_configured")
        with patch.dict(os.environ,{"QUASAR_WEATHERNEXT_FILE":""}):
            self.assertEqual(load_forecast()["status"],"not_configured")

    def test_local_snapshot_connects_to_pipeline_without_cloud_calls(self):
        now = datetime.now(timezone.utc)
        init = now.replace(minute=0,second=0,microsecond=0)
        start = init + timedelta(hours=1)
        raw = [{**row,"forecast_time":iso(start+timedelta(hours=index % 6+1))} for index,row in enumerate(rows())]
        data = snapshot(raw,table=TABLE,init_time=iso(init),valid_from=iso(start),now=now)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"weather.json"
            path.write_text(json.dumps(data))
            with patch.dict(os.environ,{"QUASAR_WEATHERNEXT_FILE":str(path)}):
                self.assertEqual(load_forecast()["status"],"ready")
                self.assertIn("weathernext",[item["id"] for item in scenarios()])
                self.assertEqual(collection("weathernext")["mode"],"mixed_forecast_demo")

    def test_forecast_scenario_is_explicitly_mixed_and_stale_becomes_unknown(self):
        forecast = summarize(example(),now=NOW)
        with patch("quasar.pipeline.load_forecast",return_value=forecast):
            data = collection("weathernext")
            self.assertEqual(data["mode"],"mixed_forecast_demo")
            first = next(f for f in data["features"] if f["id"]=="demo-001")
            self.assertEqual(first["properties"]["risk"]["data_status"],"mixed_demo")
            self.assertEqual(first["properties"]["forecast"]["rainfall_6h_mm"],15)
        stale = summarize(example(),now=INIT+timedelta(hours=3))
        with patch("quasar.pipeline.load_forecast",return_value=stale):
            self.assertTrue(all(f["properties"]["risk"]["score"] is None for f in collection("weathernext")["features"]))
        with self.assertRaises(ValueError):
            preview({"scenario":"weathernext"})


class ConfigTests(unittest.TestCase):
    def test_light_map_is_default_and_custom_styles_are_preserved(self):
        with patch.dict(os.environ, {"MAPBOX_STYLE": ""}):
            self.assertEqual(map_settings()["style"], "mapbox://styles/mapbox/light-v11")
        with patch.dict(os.environ, {"MAPBOX_STYLE": "mapbox://styles/example/custom"}):
            self.assertEqual(map_settings()["style"], "mapbox://styles/example/custom")

    def test_example_configuration_uses_the_light_map_default(self):
        example_env = Path(".env.example").read_text()
        self.assertIn("MAPBOX_STYLE=mapbox://styles/mapbox/light-v11", example_env)

    def test_only_public_mapbox_token_is_returned(self):
        with patch.dict(os.environ,{"MAPBOX_PUBLIC_TOKEN":"pk.test", "MAPBOX_STYLE":""}):
            self.assertEqual(map_settings()["public_token"],"pk.test")
        for token in ["sk.secret", "invalid", "pk.with whitespace"]:
            with patch.dict(os.environ,{"MAPBOX_PUBLIC_TOKEN":token}), self.assertRaises(ValueError):
                map_settings()

    def test_env_loader_does_not_execute_or_override_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/".env"
            path.write_text("# comment\nMAPBOX_PUBLIC_TOKEN=pk.file\nQUASAR_TEST_LITERAL=$(echo harmless)\n")
            with patch.dict(os.environ,{"MAPBOX_PUBLIC_TOKEN":"pk.environment"}):
                load_env(path)
                self.assertEqual(os.environ["MAPBOX_PUBLIC_TOKEN"],"pk.environment")
                self.assertEqual(os.environ["QUASAR_TEST_LITERAL"],"$(echo harmless)")
