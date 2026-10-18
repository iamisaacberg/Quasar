"""Small local demo server using the Python standard library.

Bind to localhost by default. Put behind a production application server and
add individual authentication, request limits, monitoring, and persistence before public use.
"""

import json
import hmac
import os
import re
import ssl
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .access import SESSION_COOKIE, SESSION_TTL, access_page, safe_return_to

from .config import COUNTY_FIPS, COUNTY_NAME, TIMEZONE, map_settings, require_county
from .source_exports import report, export
from .parcels import county_boundary, parcel_page, parcel_manifest, remote_inspection, SourceUnavailable
from .parcel_context import inspection
from .bridge import serve_snapshot
from .exposure import exposure, SCALE as EXPOSURE_SCALE

STATIC = Path(__file__).parent / "static"
ASSETS = {"/map-ui.js": ("map-ui.js", "text/javascript; charset=utf-8"),
          "/ui/app-shell.js": ("ui/app-shell.js", "text/javascript; charset=utf-8"),
          "/ui/app-shell.css": ("ui/app-shell.css", "text/css; charset=utf-8"),
          "/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/spatial.js": ("spatial.js", "text/javascript; charset=utf-8"),
          "/parcel-cache.js": ("parcel-cache.js", "text/javascript; charset=utf-8"),
          "/inspection.js": ("inspection.js", "text/javascript; charset=utf-8"),
          "/vendor/h3-js.umd.js": ("vendor/h3-js.umd.js", "text/javascript; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except ssl.SSLError:
            # Browsers may reject the local certificate before sending HTTP.
            self.close_connection = True

    def parse_request(self):
        if not super().parse_request():
            return False
        gate = getattr(self.server, "access_gate", None)
        if gate is not None and not self._team_authorized(gate):
            if self.command in ("GET", "HEAD"):
                self._access_response(access_page(return_to=self.path).encode("utf-8"), 200)
            else:
                self._access_response(b"Team sign-in required.\n", HTTPStatus.UNAUTHORIZED,
                                      "text/plain; charset=utf-8")
            self.close_connection = True
            return False
        return True

    def _team_authorized(self, gate):
        if getattr(self, "_team_gate_checked", False):
            return getattr(self, "_team_gate_allowed", False)
        self._team_gate_checked = True
        self._team_gate_allowed = (
            (self.command == "POST" and urlsplit(self.path).path == "/_team/access")
            or gate.allows_cookie_header(self.headers.get("Cookie", ""))
        )
        return self._team_gate_allowed

    def _access_response(self, body, status, content_type="text/html; charset=utf-8", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _team_login(self):
        gate = getattr(self.server, "access_gate", None)
        if gate is None:
            return False
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            self._access_response(access_page(error="Use the sign-in form to continue.").encode("utf-8"), 415)
            return True
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 4096:
            self._access_response(access_page(error="Please enter your passphrase and try again.").encode("utf-8"), 400)
            return True
        fields = parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
        password = fields.get("password", [""])[0]
        if not gate.allows_password(password):
            target = safe_return_to(fields.get("return_to", ["/"])[0])
            self._access_response(access_page(return_to=target, error="That passphrase did not match. Try again.").encode("utf-8"), 401)
            return True
        token, _ = gate.issue_session()
        target = safe_return_to(fields.get("return_to", ["/"])[0])
        self.send_response(303)
        self.send_header("Location", target)
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; Secure; SameSite=Strict")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def send(self, status: int, payload, content_type="application/json", *, filename=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query, keep_blank_values=True)
        try:
            if any(len(values) != 1 for values in query.values()):
                raise ValueError("Duplicate query parameters are not supported")
            if url.path.startswith("/bridge/v1/snapshots/"):
                name = url.path.removeprefix("/bridge/v1/snapshots/")
                if "/" in name or not name:
                    return self.send(404, {"error": "Route not found"})
                status, payload = serve_snapshot(name, self.headers.get("Authorization", ""))
                if isinstance(payload, bytes):
                    return self.send(status, payload, "application/json; charset=utf-8")
                return self.send(status, payload)
            require_county(query.get("county_fips", [COUNTY_FIPS])[0])
            if url.path in ASSETS:
                filename, content_type = ASSETS[url.path]
                return self.send(200, (STATIC / filename).read_bytes(), content_type)
            if url.path == "/health":
                return self.send(200, {"status": "ok", "mode": "county_sources", "county_fips": COUNTY_FIPS})
            if url.path == "/api/config":
                return self.send(200, {"county_fips": COUNTY_FIPS, "county_name": COUNTY_NAME,
                                       "timezone": TIMEZONE, "notice": "County source data; missing inputs remain unknown. Follow official NWS/local guidance.", "mode": "county_sources",
                                       "map": map_settings(), "exposure_scale": EXPOSURE_SCALE})
            if url.path == "/api/weather/status":
                from .data_dashboard import weather_data
                forecast = weather_data()
                return self.send(200, {k: v for k, v in forecast.items() if k != "frames"})
            if url.path == "/api/weather/timeline":
                from .forecast_timeline import timeline as forecast_timeline
                if set(query) - {"source", "county_fips"}:
                    raise ValueError("Only current or archive source selection is supported")
                return self.send(200, forecast_timeline(source=query.get("source", ["archive"])[0]))
            if url.path == "/api/data/weather":
                from .data_dashboard import weather_data
                if set(query) - {"source", "county_fips"}:
                    raise ValueError("Only current or archive source selection is supported")
                return self.send(200, weather_data(source=query.get("source", ["archive"])[0]))
            if url.path == "/api/county":
                return self.send(200, county_boundary())
            if url.path == "/api/exposure" or url.path.startswith(("/api/parcels", "/api/cells/")):
                parcel_token = os.environ.get("QUASAR_PARCEL_API_TOKEN", "")
                parcel_database = os.environ.get("QUASAR_PARCEL_DATABASE", "")
                if parcel_database and len(parcel_token) < 32:
                    return self.send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Parcel API authentication is not configured"})
                if parcel_token and not hmac.compare_digest(self.headers.get("X-Quasar-Parcel-Token", ""), parcel_token):
                    return self.send(HTTPStatus.UNAUTHORIZED, {"error": "Parcel API authentication required"})
                if url.path == "/api/exposure":
                    return self.send(200, exposure({key: values[0] for key, values in query.items()}))
                if url.path == "/api/parcels/manifest":
                    return self.send(200, parcel_manifest())
                match = re.fullmatch(r"/api/(parcels|cells)/([^/]+)/(context|summary)", url.path)
                if match:
                    group, identifier, action = match.groups()
                    if (group, action) not in (("parcels", "context"), ("cells", "summary")):
                        raise ValueError("Invalid inspection route")
                    inventory = query.get("inventory_id", [None])[0]
                    result = (remote_inspection(url.path, inventory) if os.environ.get("QUASAR_LINUXONE_API_URL")
                              else inspection("parcel" if group == "parcels" else "cell", identifier, inventory))
                    return self.send(200, result)
                if url.path != "/api/parcels":
                    return self.send(404, {"error": "Route not found"})
                return self.send(200, parcel_page(query.get("ring", [""])[0], query.get("offset", ["0"])[0],
                                                 query.get("inventory_id", [None])[0], query.get("cell", [None])[0]))
            if url.path in ("/api/scenarios", "/api/properties", "/api/timeline", "/api/routes", "/api/replay/context"):
                return self.send(410, {"status": "unavailable", "error": "Exercise endpoints are retired. Use native county forecast and parcel APIs."})
            if url.path == "/api/reports":
                if set(query) - {"source", "frame", "county_fips"}:
                    raise ValueError("Reports support imported county sources only")
                return self.send(200, report(query.get("source", ["archive"])[0], query.get("frame", [None])[0]))
            if url.path == "/api/exports":
                if set(query) - {"source", "frame", "format", "county_fips"}:
                    raise ValueError("Exports support imported county sources only")
                body, content_type, filename = export(query.get("source", ["archive"])[0], query.get("frame", [None])[0],
                                                      query.get("format", ["csv"])[0])
                return self.send(200, body, content_type, filename=filename)
            if url.path == "/api/official-alerts":
                return self.send(200, {"status": "not_connected", "alerts": [],
                                       "message": "Official NWS alerts are not loaded. This is not an all-clear.",
                                       "source_url": "https://www.weather.gov/mob/"})
            self.send(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
        except SourceUnavailable as exc:
            self.send(HTTPStatus.BAD_GATEWAY, {"status": "unavailable", "error": str(exc)})
        except ValueError as exc:
            self.send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self):
        if urlsplit(self.path).path == "/_team/access" and self._team_login():
            return
        if self.path in ("/api/notifications/preview", "/api/routes"):
            return self.send(410, {"status": "unavailable", "error": "Simulation endpoints are retired. No messages or routes are generated."})
        return self.send(404, {"error": "Route not found"})


def make_server(host="127.0.0.1", port=8000, *, access_gate=None):
    server = ThreadingHTTPServer((host, port), Handler)
    server.access_gate = access_gate
    return server
