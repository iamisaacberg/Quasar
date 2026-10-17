import json
import threading
import unittest
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
        for path in ["/health", "/api/config", "/api/scenarios", "/api/weather/status", "/api/properties?scenario=peak"]:
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
        for path in ["/", "/app.js", "/style.css", "/ui/app-shell.js", "/ui/app-shell.css", "/spatial.js", "/vendor/h3-js.umd.js"]:
            with self.subTest(path=path):
                status, body, _ = self.request(path)
                self.assertEqual(status, 200)
                self.assertTrue(body)

    def test_bad_scope_scenario_and_route(self):
        for path, expected in [("/api/properties?county_fips=12011",400),
                               ("/api/properties?scenario=invalid",400),
                               ("/../README.md",404), ("/.env",404), ("/components.json",404),
                               ("/ui/../.env",404), ("/unknown",404)]:
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], expected)

    def test_notification_preview_endpoint(self):
        status, body, _ = self.request("/api/notifications/preview", {
            "opt_in":True, "property_ids":["demo-001"], "scenario":"peak"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["sent_count"], 0)
        self.assertEqual(json.loads(body)["preview_count"], 1)

    def test_invalid_json_body_and_content_type(self):
        for raw, content_type, expected in [("{", "application/json", 400),
                                             ("[]", "application/json",400),
                                             ("{}", "text/plain",415),
                                             (" "*17000,"application/json",413)]:
            with self.subTest(expected=expected):
                self.assertEqual(self.request("/api/notifications/preview", raw=raw, content_type=content_type)[0], expected)


    def test_reports_and_export_routes(self):
        for scenario, count in [("baseline", 6), ("compare", 18)]:
            status, body, _ = self.request(f"/api/reports?scenario={scenario}")
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)["rows"]), count)
            for fmt, mime in [("csv", "text/csv; charset=utf-8"), ("geojson", "application/geo+json"), ("zip", "application/zip")]:
                connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
                try:
                    connection.request("GET", f"/api/exports?scenario={scenario}&format={fmt}")
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
