import base64
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
from unittest.mock import patch

from quasar.server import ASSETS, make_server
from quasar.wifi import TeamGate, lan_address, main, tls_context, wifi_address


PASSWORD = "test-only-shared-passphrase"


def authorization(username="team", password=PASSWORD):
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


class GateTests(unittest.TestCase):
    def test_only_correct_credentials_unlock(self):
        gate = TeamGate(PASSWORD)
        self.assertTrue(gate.allows(authorization()))
        self.assertTrue(gate.allows(authorization().replace("Basic", "basic")))
        for header in ["", "Bearer secret", "Basic !!!", "Basic ☃",
                       authorization("other"), authorization(password="wrong")]:
            with self.subTest(header=header):
                self.assertFalse(gate.allows(header))

    def test_unicode_password(self):
        gate = TeamGate("A long shared ☃ passphrase")
        self.assertTrue(gate.allows(authorization(password="A long shared ☃ passphrase")))

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

    def request(self, path, *, method="GET", auth=None, body=None, context=None):
        connection = HTTPSConnection(
            "127.0.0.1", self.server.server_port, timeout=5,
            context=context or self.client_context,
        )
        headers = {"Content-Type": "application/json"}
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
                self.assertEqual(status, 401)
                self.assertEqual(body, b"Team sign-in required.\n")
                self.assertIn('Basic realm="Quasar team"', headers["WWW-Authenticate"])
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_bad_password_does_not_return_app_or_configuration(self):
        for auth in [authorization(password="wrong"), "Basic !!!", "Bearer secret"]:
            with self.subTest(auth=auth):
                status, body, _ = self.request("/api/config", auth=auth)
                self.assertEqual(status, 401)
                self.assertNotIn(b"public_token", body)
                self.assertNotIn(PASSWORD.encode(), body)

    def test_authenticated_page_and_api_work_over_tls(self):
        for path in ["/", "/ui/app-shell.js", "/api/config", "/api/properties?scenario=peak"]:
            with self.subTest(path=path):
                status, body, _ = self.request(path, auth=authorization())
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertNotIn(PASSWORD.encode(), body)

    def test_post_cannot_bypass_gate(self):
        body = json.dumps({"opt_in": True, "property_ids": ["demo-001"], "scenario": "peak"})
        with patch("quasar.server.preview") as preview:
            status, _, _ = self.request("/api/notifications/preview", method="POST", body=body)
            self.assertEqual(status, 401)
            preview.assert_not_called()
        status, result, _ = self.request(
            "/api/notifications/preview", method="POST", body=body, auth=authorization(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(result)["sent_count"], 0)

    def test_head_and_unimplemented_methods_cannot_bypass_gate(self):
        for method in ["HEAD", "OPTIONS", "PUT"]:
            with self.subTest(method=method):
                status, body, _ = self.request("/api/config", method=method)
                self.assertEqual(status, 401)
                if method == "HEAD":
                    self.assertEqual(body, b"")
