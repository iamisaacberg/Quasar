import contextlib
from http.client import HTTPSConnection
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

from quasar.server import ASSETS, make_server
from quasar.access import SESSION_COOKIE
from quasar.wifi import TeamGate, lan_address, main, tls_context, wifi_address


PASSWORD = "test-only-shared-passphrase"


class GateTests(unittest.TestCase):
    def test_only_correct_passphrase_and_signed_session_unlock(self):
        gate = TeamGate(PASSWORD)
        self.assertTrue(gate.allows_password(PASSWORD))
        self.assertFalse(gate.allows_password("wrong"))
        token, _ = gate.issue_session()
        self.assertTrue(gate.allows_cookie_header(f"{SESSION_COOKIE}={token}"))
        for header in ["", "authenticated=true", f"{SESSION_COOKIE}=invalid"]:
            with self.subTest(header=header):
                self.assertFalse(gate.allows_cookie_header(header))

    def test_unicode_password(self):
        gate = TeamGate("A long shared ☃ passphrase")
        self.assertTrue(gate.allows_password("A long shared ☃ passphrase"))

    def test_empty_and_short_passwords_are_refused(self):
        for password in ["", "short", " " * 12, "a" * 257, "long-password\n"]:
            with self.subTest(length=len(password)):
                with self.assertRaises(ValueError):
                    TeamGate(password)

    def test_invalid_bind_addresses_are_refused(self):
        for host in ["0.0.0.0", "127.0.0.1", "224.0.0.1", "localhost", "::1"]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                lan_address(host)
        self.assertEqual(lan_address("192.168.1.42"), "192.168.1.42")

    def test_macos_wifi_device_does_not_assume_en0(self):
        ports = "Hardware Port: Ethernet\nDevice: en0\n\nHardware Port: Wi-Fi\nDevice: en7\n"
        from subprocess import CompletedProcess
        with patch("quasar.wifi.sys.platform", "darwin"), patch(
            "quasar.wifi.subprocess.run", side_effect=[
                CompletedProcess([], 0, stdout=ports),
                CompletedProcess([], 0, stdout="192.168.1.42\n"),
            ]
        ) as run:
            self.assertEqual(wifi_address(), "192.168.1.42")
            self.assertEqual(run.call_args.args[0][-1], "en7")

    def test_empty_configured_password_never_starts_a_server(self):
        with patch.dict(os.environ, {"QUASAR_WIFI_PASSWORD": ""}), patch(
            "quasar.wifi.load_env"
        ), patch("quasar.wifi.map_settings"), patch("quasar.wifi.make_server") as start, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["--host", "192.168.1.42"])
            self.assertEqual(error.exception.code, 1)
            start.assert_not_called()

    def test_missing_openssl_fails_closed(self):
        with patch("quasar.wifi.shutil.which", return_value=None), self.assertRaises(ValueError):
            tls_context("unused", "192.168.1.42")


@unittest.skipUnless(shutil.which("openssl"), "HTTPS integration needs OpenSSL")
class ProtectedHttpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="quasar-wifi-test-")
        context, cls.fingerprint = tls_context(cls.directory.name, "127.0.0.1")
        cls.client_context = ssl.create_default_context(
            cafile=str(Path(cls.directory.name) / "certificate.pem")
        )
        cls.server = make_server(port=0, access_gate=TeamGate(PASSWORD))
        cls.server.socket = context.wrap_socket(
            cls.server.socket, server_side=True, do_handshake_on_connect=False,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def request(self, path, *, method="GET", auth=None, body=None, context=None, headers=None):
        connection = HTTPSConnection(
            "127.0.0.1", self.server.server_port, timeout=5,
            context=context or self.client_context,
        )
        headers = {"Content-Type": "application/json", **(headers or {})}
        if auth is not None:
            headers["Authorization"] = auth
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_certificate_must_be_trusted_explicitly(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("/", context=ssl.create_default_context())

    def test_all_static_and_api_paths_are_protected(self):
        for path in [*ASSETS, "/health", "/api/config", "/api/properties?scenario=peak",
                     "/api/scenarios", "/api/weather/status", "/api/official-alerts",
                     "/api/timeline", "/api/routes", "/api/replay/context", "/api/reports",
                     "/api/exports", "/unknown"]:
            with self.subTest(path=path):
                status, body, headers = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(b"Shared passphrase", body)
                self.assertNotIn("WWW-Authenticate", headers)
                self.assertEqual(headers["Cache-Control"], "private, no-store")

    def test_passphrase_page_creates_a_protected_session(self):
        body = urlencode({"password": PASSWORD, "return_to": "/api/config"})
        status, result, headers = self.request(
            "/_team/access", method="POST", body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual((status, result), (303, b""))
        self.assertEqual(headers["Location"], "/api/config")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertTrue(cookie.startswith(f"{SESSION_COOKIE}="))
        status, result, _ = self.request("/api/config", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertIn(b"county_fips", result)
        status, _, _ = self.request("/api/config", headers={"Authorization": "Basic dGVhbTpwYXNz"})
        self.assertEqual(status, 200)

    def test_bad_password_does_not_return_app_or_configuration(self):
        for auth in ["Basic dGVhbTp3cm9uZw==", "Basic !!!", "Bearer secret"]:
            with self.subTest(auth=auth):
                status, body, _ = self.request("/api/config", auth=auth)
                self.assertEqual(status, 200)
                self.assertIn(b"Shared passphrase", body)
                self.assertNotIn(b"public_token", body)
                self.assertNotIn(PASSWORD.encode(), body)

    def test_wrong_passphrase_shows_inline_error(self):
        body = urlencode({"password": "wrong-passphrase", "return_to": "/"})
        status, result, _ = self.request(
            "/_team/access", method="POST", body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(status, 401)
        self.assertIn(b"did not match", result)

    def test_authenticated_page_and_api_work_over_tls(self):
        body = urlencode({"password": PASSWORD, "return_to": "/"})
        status, _, headers = self.request(
            "/_team/access", method="POST", body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(status, 303)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        for path in ["/", "/ui/app-shell.js", "/api/config", "/api/properties?scenario=peak"]:
            with self.subTest(path=path):
                status, body, _ = self.request(path, headers={"Cookie": cookie})
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertNotIn(PASSWORD.encode(), body)

    def test_post_cannot_bypass_gate(self):
        body = json.dumps({"opt_in": True, "property_ids": ["demo-001"], "scenario": "peak"})
        with patch("quasar.server.preview") as preview:
            status, _, _ = self.request("/api/notifications/preview", method="POST", body=body)
            self.assertEqual(status, 401)
            preview.assert_not_called()
        login_body = urlencode({"password": PASSWORD, "return_to": "/"})
        _, _, headers = self.request("/_team/access", method="POST", body=login_body,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, result, _ = self.request("/api/notifications/preview", method="POST", body=body,
                                         headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(result)["sent_count"], 0)

    def test_head_and_unimplemented_methods_cannot_bypass_gate(self):
        for method in ["HEAD", "OPTIONS", "PUT"]:
            with self.subTest(method=method):
                status, body, _ = self.request("/api/config", method=method)
                self.assertEqual(status, 200 if method == "HEAD" else 401)
                if method == "HEAD":
                    self.assertEqual(body, b"")
