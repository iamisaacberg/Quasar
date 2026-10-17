"""Hosted gate behavior, including runtimes that dispatch do_* directly."""

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
from urllib.parse import urlencode
from unittest.mock import patch

from api.index import handler
from quasar.access import TeamGate, SESSION_COOKIE
from quasar.server import ASSETS

PASSWORD = "test-only-hosted-passphrase"


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

    def login(self, password=PASSWORD, target="/"):
        body = urlencode({"password": password, "return_to": target})
        return self.request("/_team/access", method="POST", body=body,
                            headers={"Content-Type": "application/x-www-form-urlencoded"})

    def test_missing_weak_or_blank_secret_blocks_even_correct_password(self):
        for password in ["", "short", " " * 20]:
            with self.subTest(password=password), patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": password}):
                status, body, _ = self.request("/api/config")
                self.assertEqual(status, 503)
                self.assertIn(b"Access is temporarily unavailable", body)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.request("/")[0], 503)

    def test_every_app_asset_and_endpoint_shows_the_access_page(self):
        paths = [*ASSETS, "/health", "/api/config", "/api/properties?scenario=peak", "/api/scenarios",
                 "/api/weather/status", "/api/reports", "/api/exports?format=zip", "/api/timeline",
                 "/api/routes", "/api/replay/context", "/api/official-alerts", "/api/index", "/api/index.py",
                 "/quasar/static/index.html", "/quasar/static/ui/app-shell.js", "/data/processed/weathernext.json",
                 "/.env", "/vercel.json", "/_gate-placeholder.txt", "/%2e%2e/.env"]
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            for path in paths:
                with self.subTest(path=path):
                    status, body, headers = self.request(path)
                    self.assertEqual(status, 200)
                    self.assertIn(b"Shared passphrase", body)
                    self.assertIn("private, no-store", headers["Cache-Control"])
                    self.assertEqual(headers["Vary"], "Cookie")
                    self.assertIn("noindex", headers["X-Robots-Tag"])
                    self.assertNotIn("WWW-Authenticate", headers)

    def test_wrong_password_and_bypass_headers_do_not_unlock(self):
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            status, body, _ = self.login("wrong")
            self.assertEqual(status, 401)
            self.assertIn(b"did not match", body)
            for headers in [
                {"Authorization": "Basic dGVhbTp3cm9uZw=="},
                {"Cookie": f"authenticated=true; QUASAR_TEAM_PASSWORD={PASSWORD}"},
                {"X-Vercel-Protection-Bypass": PASSWORD, "X-Forwarded-User": "team"},
            ]:
                with self.subTest(headers=list(headers)):
                    self.assertEqual(self.request(f"/?password={PASSWORD}", headers=headers)[0], 200)
                    status, _, _ = self.request("/api/routes", method="POST", headers=headers, body="{}")
                    self.assertEqual(status, 401)

    def test_login_issues_cookie_and_session_unlocks_app_and_api(self):
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            status, body, headers = self.login(target="/api/config")
            self.assertEqual((status, body), (303, b""))
            self.assertEqual(headers["Location"], "/api/config")
            cookie = headers["Set-Cookie"]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("Secure", cookie)
            self.assertIn("SameSite=Strict", cookie)
            self.assertIn(f"Max-Age=43200", cookie)
            session = cookie.split(";", 1)[0]
            for path in ["/", "/ui/app-shell.js", "/api/config", "/api/properties?scenario=peak"]:
                with self.subTest(path=path):
                    status, body, headers = self.request(path, headers={"Cookie": session})
                    self.assertEqual(status, 200)
                    self.assertNotIn(PASSWORD.encode(), body)
                    self.assertIn("no-store", headers["Cache-Control"])
            for path in ["/.env", "/vercel.json", "/quasar/server.py", "/data/processed/weathernext.json"]:
                with self.subTest(path=path):
                    self.assertEqual(self.request(path, headers={"Cookie": session})[0], 404)
            status, body, _ = self.request("/", method="HEAD", headers={"Cookie": session})
            self.assertEqual((status, body), (200, b""))
            status, result, _ = self.request(
                "/api/notifications/preview", method="POST",
                headers={"Cookie": session, "Content-Type": "application/json"},
                body=json.dumps({"opt_in": True, "property_ids": ["demo-001"], "scenario": "peak"}),
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(result)["sent_count"], 0)

    def test_sessions_expire_and_rotate_with_password(self):
        gate = TeamGate(PASSWORD)
        token, expires = gate.issue_session(now=100)
        self.assertTrue(gate.allows_session(token, now=100))
        self.assertFalse(gate.allows_session(token, now=expires + 1))
        self.assertFalse(TeamGate(PASSWORD + "-rotated").allows_session(token, now=100))

    def test_all_methods_require_a_session(self):
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            for method in ["POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE", "TRACE", "CONNECT"]:
                with self.subTest(method=method):
                    status, body, _ = self.request("/api/routes", method=method, body="{}")
                    self.assertEqual(status, 200 if method == "HEAD" else 401)
                    if method == "HEAD":
                        self.assertEqual(body, b"")

    def test_direct_hosted_dispatch_cannot_skip_gate(self):
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
                result = instance.wfile.getvalue()
                self.assertIn(b"401 Unauthorized" if method not in ("GET", "HEAD") else b"200 OK", result)
                self.assertNotIn(b"WWW-Authenticate", result)
                if method in ("GET", "HEAD"):
                    if method == "GET":
                        self.assertIn(b"Shared passphrase", result)

    def test_login_redirect_cannot_leave_site(self):
        with patch.dict(os.environ, {"QUASAR_TEAM_PASSWORD": PASSWORD}):
            status, _, headers = self.login(target="//evil.example/path")
            self.assertEqual(status, 303)
            self.assertEqual(headers["Location"], "/")

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
