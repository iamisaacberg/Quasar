import json
import threading
import unittest
from unittest.mock import patch
from test_county_weather import current
from http.client import HTTPConnection

from quasar.server import make_server


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, payload=None, *, raw=None, content_type="application/json"):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            method = "GET" if payload is None and raw is None else "POST"
            body = json.dumps(payload) if payload is not None else raw
            connection.request(method, path, body, {"Content-Type":content_type})
            response = connection.getresponse()
            return response.status, response.read(), response.getheader("Content-Type")
        finally:
            connection.close()

    def test_api_routes(self):
        for path in ["/health", "/api/config", "/api/weather/status", "/api/weather/timeline", "/api/reports"]:
            with self.subTest(path=path):
                status, body, content_type = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(content_type, "application/json")
                json.loads(body)

    def test_official_feed_does_not_claim_all_clear(self):
        status, body, _ = self.request("/api/official-alerts")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "not_connected")

    def test_static_assets(self):
        for path in ["/", "/app.js", "/map-ui.js", "/style.css", "/ui/app-shell.js", "/ui/app-shell.css", "/spatial.js", "/parcel-cache.js", "/inspection.js", "/vendor/h3-js.umd.js"]:
            with self.subTest(path=path):
                status, body, _ = self.request(path)
                self.assertEqual(status, 200)
                self.assertTrue(body)

    def test_bad_scope_scenario_and_route(self):
        for path, expected in [("/api/properties?county_fips=12011",400),
                               ("/api/properties?scenario=invalid",410),
                               ("/../README.md",404), ("/.env",404), ("/components.json",404),
                               ("/ui/../.env",404), ("/unknown",404)]:
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], expected)

    def test_simulation_endpoints_are_retired(self):
        for path in ("/api/properties", "/api/scenarios", "/api/timeline", "/api/routes", "/api/replay/context"):
            self.assertEqual(self.request(path)[0], 410)
        for path in ("/api/routes", "/api/notifications/preview"):
            self.assertEqual(self.request(path, payload={})[0], 410)

    @patch("quasar.forecast_timeline.read_snapshot", side_effect=lambda name: current() if name == "weathernext" else None)
    def test_reports_and_export_routes(self, read):
        for scenario, count in [("current", 1)]:
            status, body, _ = self.request(f"/api/reports?source={scenario}")
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)["rows"]), count)
            for fmt, mime in [("csv", "text/csv; charset=utf-8"), ("geojson", "application/geo+json"), ("zip", "application/zip")]:
                connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
                try:
                    connection.request("GET", f"/api/exports?source={scenario}&format={fmt}")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.getheader("Content-Type"), mime)
                    self.assertEqual(response.getheader("Content-Disposition"), f'attachment; filename="quasar-{scenario}.{fmt}"')
                    self.assertEqual(response.getheader("Cache-Control"), "no-store")
                    self.assertTrue(response.read())
                finally:
                    connection.close()

    def test_report_export_errors_are_json_not_downloads(self):
        for path in ["/api/reports?scenario=invalid", "/api/exports?scenario=invalid",
                     "/api/exports?format=exe", "/api/exports?county_fips=12011",
                     "/api/reports?county_fips=12011", "/api/exports?format="]:
            with self.subTest(path=path):
                status, body, mime = self.request(path)
                self.assertEqual(status, 400)
                self.assertEqual(mime, "application/json")
                self.assertIn("error", json.loads(body))

    def test_map_timeline_rejects_synthetic_parameters(self):
        for query in ('source=what_if', 'source=current&preset=plus-5', 'source=archive&mode=what_if'):
            self.assertEqual(self.request('/api/weather/timeline?' + query)[0], 400)

    @patch("quasar.forecast_timeline.read_snapshot", side_effect=lambda name: current())
    def test_real_exports_preserve_unknown_values_source_and_geometry(self, read):
        import csv, io
        data = current()
        data['runs'][0]['rows'][0]['rainfall_1h_mm'] = None
        read.side_effect = lambda name: data
        status, body, _ = self.request('/api/exports?source=current&frame=0&format=csv')
        self.assertEqual(status, 200)
        row = next(csv.DictReader(io.StringIO(body.decode())))
        self.assertEqual(row['rainfall_6h_mm'], '')
        self.assertEqual(row['units'], 'mm / 6h')
        self.assertEqual(row['county_fips'], '12091')
        self.assertEqual(row['native_resolution'], '0.1 degree')
        status, body, _ = self.request('/api/exports?source=current&frame=0&format=geojson')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['features'][0]['geometry'], data['native_cells'][0]['geometry'])
        self.assertNotIn('demo-00', body.decode())
