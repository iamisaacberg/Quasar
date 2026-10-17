"""Hosted gate behavior, including runtimes that dispatch do_* directly."""

import base64
from email.message import Message
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from api.index import handler
from quasar.server import ASSETS

PASSWORD = "test-only-hosted-passphrase"
AUTH = "Basic " + base64.b64encode(f"team:{PASSWORD}".encode()).decode()


class HostedGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, *, method="GET", headers=None, body=None):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            client.request(method, path, body, headers or {})
            response = client.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            client.close()

    def test_missing_weak_or_blank_secret_blocks_even_valid_credentials(self):
        for password in ["", "short", " " * 20]:
            with self.subTest(password=password), patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": password}):
                status, body, _ = self.request("/api/config", headers={"Authorization": AUTH})
                self.assertEqual(status, 503)
                self.assertNotIn(b"public_token", body)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.request("/")[0], 503)

    def test_every_app_asset_and_endpoint_requires_credentials(self):
        paths = [*ASSETS, "/health", "/api/config", "/api/properties?scenario=peak", "/api/scenarios",
                 "/api/weather/status", "/api/reports", "/api/exports?format=zip", "/api/timeline",
                 "/api/routes", "/api/replay/context", "/api/official-alerts", "/api/index", "/api/index.py",
                 "/quasar/static/index.html", "/quasar/static/ui/app-shell.js", "/data/processed/weathernext.json",
                 "/.env", "/vercel.json", "/_gate-placeholder.txt", "/%2e%2e/.env"]
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            for path in paths:
                with self.subTest(path=path):
                    status, body, headers = self.request(path)
                    self.assertEqual(status, 401)
                    self.assertEqual(body, b"Team sign-in required.\n")
                    self.assertEqual(headers["Cache-Control"], "private, no-store")
                    self.assertEqual(headers["Vary"], "Authorization")
                    self.assertIn("noindex", headers["X-Robots-Tag"])
                    self.assertIn("Quasar team", headers["WWW-Authenticate"])

    def test_wrong_password_and_bypass_headers_do_not_unlock(self):
        attempts = [
            {"Authorization": "Basic dGVhbTp3cm9uZw=="},
            {"Authorization": "Basic !!!"},
            {"Cookie": f"authenticated=true; QUASAR_TEAM_PASSWORD={PASSWORD}"},
            {"X-Vercel-Protection-Bypass": PASSWORD, "X-Forwarded-User": "team"},
        ]
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            for headers in attempts:
                with self.subTest(headers=list(headers)):
                    self.assertEqual(self.request(f"/?password={PASSWORD}", headers=headers)[0], 401)

    def test_all_methods_are_gated(self):
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            for method in ["GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE", "TRACE", "CONNECT"]:
                with self.subTest(method=method):
                    status, body, _ = self.request("/api/routes", method=method, body="{}")
                    self.assertEqual(status, 401)
                    if method == "HEAD":
                        self.assertEqual(body, b"")

    def test_correct_credentials_unlock_app_and_api_but_never_source_or_secrets(self):
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            for path in ["/", "/ui/app-shell.js", "/api/config", "/api/properties?scenario=peak"]:
                with self.subTest(path=path):
                    status, body, headers = self.request(path, headers={"Authorization": AUTH})
                    self.assertEqual(status, 200)
                    self.assertNotIn(PASSWORD.encode(), body)
                    self.assertIn("no-store", headers["Cache-Control"])
            for path in ["/.env", "/vercel.json", "/quasar/server.py", "/data/processed/weathernext.json"]:
                with self.subTest(path=path):
                    self.assertEqual(self.request(path, headers={"Authorization": AUTH})[0], 404)
            status, body, _ = self.request("/", method="HEAD", headers={"Authorization": AUTH})
            self.assertEqual((status, body), (200, b""))
            status, body, _ = self.request(
                "/api/notifications/preview", method="POST",
                headers={"Authorization": AUTH, "Content-Type": "application/json"},
                body=json.dumps({"opt_in": True, "property_ids": ["demo-001"], "scenario": "peak"}),
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["sent_count"], 0)

    def test_password_rotation_invalidates_previous_password(self):
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD + "-rotated"}):
            self.assertEqual(self.request("/", headers={"Authorization": AUTH})[0], 401)

    def test_direct_hosted_dispatch_cannot_skip_gate(self):
        # Some hosted adapters invoke do_GET/do_POST without parse_request.
        for method in ["GET", "POST", "HEAD", "OPTIONS"]:
            instance = object.__new__(handler)
            instance.command = method
            instance.headers = Message()
            instance.wfile = io.BytesIO()
            instance.requestline = f"{method} / HTTP/1.1"
            instance.request_version = "HTTP/1.1"
            instance.path = "/"
            instance.log_request = lambda *args: None
            with self.subTest(method=method), patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
                getattr(instance, f"do_{method}")()
                self.assertIn(b"401 Unauthorized", instance.wfile.getvalue())

    def test_deployment_has_no_static_output_bypass(self):
        config = json.loads(Path("vercel.json").read_text())
        self.assertIsNone(config["framework"])
        self.assertEqual(config["routes"], [{"src": "/(.*)", "dest": "/api/index"}])
        self.assertEqual(config["outputDirectory"], "vercel-output")
        with tempfile.TemporaryDirectory() as root:
            scripts = Path(root) / "scripts"
            scripts.mkdir()
            script = scripts / "prepare_vercel.py"
            script.write_text(Path("scripts/prepare_vercel.py").read_text())
            subprocess.run([sys.executable, str(script)], check=True, capture_output=True)
            (Path(root) / "vercel-output" / "app.js").write_text("private content")
            result = subprocess.run([sys.executable, str(script)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
