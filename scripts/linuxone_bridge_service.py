"""Small LinuxONE HTTP bridge for snapshots and indexed parcel pages."""

import hmac
import json
import os
import re
import sqlite3
import sys
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quasar.bridge import serve_snapshot


DATABASE = os.environ.get(
    "QUASAR_PARCEL_DATABASE",
    "/srv/quasar/data/processed/okaloosa/linuxone/quasar-parcels.sqlite3",
)
PAGE_SIZE = 100
MAX_RESPONSE_BYTES = 2_000_000


def parcel_page(query):
    cell_id = query.get("cell", [""])[0]
    offset_text = query.get("offset", ["0"])[0]
    inventory_id = query.get("inventory_id", [None])[0]
    if not re.fullmatch(r"[0-9a-f]{15}", cell_id):
        return 400, {"error": "A county resolution-7 cell is required"}
    try:
        offset = int(offset_text)
    except ValueError:
        return 400, {"error": "Invalid parcel offset"}
    if offset < 0 or offset % PAGE_SIZE:
        return 400, {"error": "Invalid parcel offset"}

    try:
        connection = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        metadata = {
            key: json.loads(value)
            for key, value in connection.execute("SELECT key,value FROM metadata")
        }
        source = metadata["source_provenance"]
        if (metadata.get("county_fips") != "12091"
                or metadata.get("h3_resolutions") != [4, 5, 6, 7]):
            connection.close()
            return 503, {"status": "unavailable", "error": "Parcel inventory metadata is invalid"}
        source_id = source["output_sha256"]
        if inventory_id is not None and inventory_id != source_id:
            connection.close()
            return 409, {"status": "changed", "error": "Parcel inventory changed; retry the cell"}
        cell = connection.execute(
            "SELECT resolution FROM county_cells WHERE cell_id=?", (cell_id,)
        ).fetchone()
        if cell is None or cell[0] != 7:
            connection.close()
            return 400, {"error": "Cell is outside Okaloosa resolution-7 coverage"}
        total = connection.execute(
            "SELECT count(*) FROM cell_parcels WHERE cell_id=?", (cell_id,)
        ).fetchone()[0]
        if offset > total:
            connection.close()
            return 400, {"error": "Invalid parcel offset"}
        rows = connection.execute(
            "SELECT p.feature_z FROM cell_parcels cp JOIN parcels p USING(parcel_id) "
            "WHERE cp.cell_id=? ORDER BY cp.parcel_id LIMIT ? OFFSET ?",
            (cell_id, PAGE_SIZE, offset),
        ).fetchall()
        connection.close()
        features = [json.loads(zlib.decompress(row[0])) for row in rows]
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        return 503, {"status": "unavailable", "error": "Parcel inventory is unavailable"}

    next_offset = offset + len(features)
    response = {
        "type": "FeatureCollection",
        "county_fips": "12091",
        "features": features,
        "status": "ready",
        "source_total": total,
        "checked_count": next_offset,
        "excluded_count": 0,
        "inventory_id": source_id,
        "next_offset": next_offset if next_offset < total else None,
        "source_url": source["source_url"],
        "terms_url": source["terms_url"],
        "retrieved_at": source["retrieved_at"],
        "inventory_at": source["retrieved_at"],
        "county_boundary_retrieved_at": source["county_boundary"]["retrieved_at"],
        "crs": source["crs"],
        "units": source["units"],
        "license": source["license"],
        "processing": "County-boundary-validated parcel polygons indexed to overlapping H3 resolution 7 cell; no scoring joins",
        "notice": "County parcel geometry only. Flood inputs and scores unavailable; every parcel score remains unknown.",
    }
    encoded = json.dumps(response, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_RESPONSE_BYTES:
        return 503, {"status": "unavailable", "error": "Parcel response exceeds its size limit"}
    return 200, encoded


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(len(values) != 1 for values in query.values()):
            return self.reply(400, {"error": "Duplicate query parameters are not supported"})
        if parsed.path == "/api/parcels":
            expected = os.environ.get("QUASAR_PARCEL_API_TOKEN", "")
            supplied = self.headers.get("X-Quasar-Parcel-Token", "")
            if len(expected) < 32 or not hmac.compare_digest(supplied, expected):
                return self.reply(401, {"error": "Parcel bridge authentication required"})
            status, payload = parcel_page(query)
            return self.reply(status, payload)
        prefix = "/bridge/v1/snapshots/"
        if parsed.path.startswith(prefix) and parsed.path[len(prefix):] and "/" not in parsed.path[len(prefix):]:
            status, payload = serve_snapshot(parsed.path[len(prefix):], self.headers.get("Authorization", ""))
            return self.reply(status, payload)
        return self.reply(404, {"error": "Route not found"})

    def reply(self, status, payload):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        super().log_message(fmt, *args)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
