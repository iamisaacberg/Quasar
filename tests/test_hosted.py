"""Public hosted reads retain source-secret and filesystem boundaries."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
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


class PublicHostedTests(unittest.TestCase):
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

    def request(self, path, *, method="GET", body=None):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            client.request(method, path, body)
            response = client.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            client.close()

    def test_app_assets_and_api_are_public_with_or_without_old_password(self):
        for password in ("", "old-test-only-passphrase"):
            with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": password}), patch('quasar.forecast_timeline.read_snapshot', return_value=None):
                for path in [*ASSETS, "/health", "/api/config", "/api/weather/timeline?source=archive", "/api/reports", "/api/official-alerts"]:
                    with self.subTest(path=path, password_present=bool(password)):
                        status, body, headers = self.request(path)
                        self.assertEqual(status, 200)
                        self.assertNotIn(b"Shared passphrase", body)
                        self.assertNotIn("Set-Cookie", headers)
                        self.assertIn("no-store", headers["Cache-Control"])
                        self.assertEqual(headers["Content-Security-Policy"], "frame-ancestors 'none'")
        self.assertEqual(self.request("/", method="HEAD")[:2], (200, b""))

    def test_public_app_does_not_publish_private_files_or_server_credentials(self):
        secret = "test-only-private-bridge-token-000000000"
        with patch.dict(os.environ, {"QUASAR_DATA_BRIDGE_TOKEN": secret, "QUASAR_LINUXONE_API_TOKEN": secret}):
            for path in ["/.env", "/api/index.py", "/quasar/server.py", "/.context/linuxone/identity.pem",
                         "/data/processed/isaias-2026.json", "/vercel.json", "/%2e%2e/.env"]:
                self.assertEqual(self.request(path)[0], 404)
            self.assertNotIn(secret.encode(), self.request("/api/config")[1])
        with patch.dict(os.environ, {"QUASAR_DATA_BRIDGE_SERVE": "1", "QUASAR_DATA_BRIDGE_TOKEN": secret}):
            self.assertEqual(self.request("/bridge/v1/snapshots/isaias-2026")[0], 401)
        with patch.dict(os.environ, {"QUASAR_PARCEL_DATABASE": "test.sqlite", "QUASAR_PARCEL_API_TOKEN": secret}):
            self.assertEqual(self.request("/api/parcels/manifest")[0], 401)

    def test_login_is_removed_and_retired_actions_stay_retired(self):
        self.assertEqual(self.request("/_team/access", method="POST", body="password=test")[0], 404)
        self.assertEqual(self.request("/api/notifications/preview", method="POST", body="{}")[0], 410)
        self.assertEqual(self.request("/api/routes", method="POST", body="{}")[0], 410)

    def test_deployment_keeps_private_files_out_of_static_output(self):
        config = json.loads(Path("vercel.json").read_text())
        self.assertEqual(config["routes"], [{"src": "/(.*)", "dest": "/api/index"}])
        with tempfile.TemporaryDirectory() as root:
            scripts = Path(root) / "scripts"
            scripts.mkdir()
            script = scripts / "prepare_vercel.py"
            script.write_text(Path("scripts/prepare_vercel.py").read_text())
            subprocess.run([sys.executable, str(script)], check=True, capture_output=True)
            (Path(root) / "vercel-output" / "private.json").write_text("not an app asset")
            result = subprocess.run([sys.executable, str(script)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
