"""Small local demo server using the Python standard library.

Bind to localhost by default. Put behind a production application server and
add authentication, request limits, monitoring, and persistence before public use.
"""

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .config import COUNTY_FIPS, COUNTY_NAME, NOTICE, TIMEZONE, map_settings, require_county
from .adapters.weathernext import load_forecast
from .notifications import preview
from .pipeline import collection, scenarios
from .analysis import report
from .exports import export

STATIC = Path(__file__).parent / "static"
ASSETS = {"/ui/app-shell.js": ("ui/app-shell.js", "text/javascript; charset=utf-8"),
          "/ui/app-shell.css": ("ui/app-shell.css", "text/css; charset=utf-8"),
          "/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/spatial.js": ("spatial.js", "text/javascript; charset=utf-8"),
          "/vendor/h3-js.umd.js": ("vendor/h3-js.umd.js", "text/javascript; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
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
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query, keep_blank_values=True)
        try:
            require_county(query.get("county_fips", [COUNTY_FIPS])[0])
            if url.path in ASSETS:
                filename, content_type = ASSETS[url.path]
                return self.send(200, (STATIC / filename).read_bytes(), content_type)
            if url.path == "/health":
                return self.send(200, {"status": "ok", "mode": "synthetic_demo", "county_fips": COUNTY_FIPS})
            if url.path == "/api/config":
                return self.send(200, {"county_fips": COUNTY_FIPS, "county_name": COUNTY_NAME,
                                       "timezone": TIMEZONE, "notice": NOTICE, "mode": "synthetic_demo",
                                       "map": map_settings()})
            if url.path == "/api/weather/status":
                forecast = load_forecast()
                return self.send(200, {k: v for k, v in forecast.items() if k != "records"})
            if url.path == "/api/scenarios":
                return self.send(200, {"scenarios": scenarios(), "historical_replay": False})
            if url.path == "/api/properties":
                return self.send(200, collection(query.get("scenario", ["baseline"])[0]))
            if url.path == "/api/reports":
                return self.send(200, report(query.get("scenario", ["baseline"])[0]))
            if url.path == "/api/exports":
                body, content_type, filename = export(query.get("scenario", ["baseline"])[0],
                                                      query.get("format", ["csv"])[0])
                return self.send(200, body, content_type, filename=filename)
            if url.path == "/api/official-alerts":
                return self.send(200, {"status": "not_connected", "alerts": [],
                                       "message": "Official NWS alerts are not loaded. This is not an all-clear.",
                                       "source_url": "https://www.weather.gov/mfl/"})
            self.send(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
        except ValueError as exc:
            self.send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self):
        if self.path != "/api/notifications/preview":
            return self.send(404, {"error": "Route not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                return self.send(413, {"error": "Body must be 1-16384 bytes"})
            if self.headers.get_content_type() != "application/json":
                return self.send(415, {"error": "Use application/json"})
            payload = json.loads(self.rfile.read(length))
            self.send(200, preview(payload))
        except (ValueError, UnicodeDecodeError) as exc:
            self.send(400, {"error": str(exc)})


def make_server(host="127.0.0.1", port=8000):
    return ThreadingHTTPServer((host, port), Handler)
