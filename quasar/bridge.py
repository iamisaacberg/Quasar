"""Authenticated, allow-listed snapshot bridge for IBM LinuxONE and Vercel.

The LinuxONE process serves normalized snapshots from its local data directory.
The Vercel process can fetch those snapshots over HTTPS using a server-only token.
Raw downloads and property datasets are intentionally not bridgeable.
"""

import hmac
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class BridgeUnavailable(Exception):
    """The configured remote snapshot source could not provide usable data."""


# Keep this list explicit: paths cannot come from a request, and property datasets
# are not exposed through the bridge.
SNAPSHOTS = {
    "weathernext": ("QUASAR_WEATHERNEXT_FILE", "data/processed/weathernext.json", 5_000_000),
    "isaias-2026": ("QUASAR_REPLAY_FILE", "data/processed/isaias-2026.json", 30_000_000),
    "isaias-advisories": (None, "data/processed/isaias-advisories.json", 2_000_000),
    "evacuation-network": ("QUASAR_ROUTES_FILE", "data/processed/evacuation-network.json", 8_000_000),
}
REMOTE_CACHE_SECONDS = 15
_remote_cache = {}


def _path_for(name):
    if name not in SNAPSHOTS:
        raise ValueError("Unknown bridge snapshot")
    env_key, default, limit = SNAPSHOTS[name]
    if env_key:
        configured = os.environ.get(env_key, "").strip()
        if not configured:
            return None, limit
        return Path(configured), limit
    return Path(default), limit


def _parse_snapshot(payload, limit):
    if len(payload) > limit:
        raise ValueError("Snapshot exceeds its size limit")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Snapshot must be a JSON object")
    return data


def _bridge_url():
    base = os.environ.get("QUASAR_DATA_BRIDGE_URL", "").strip()
    if not base:
        return None
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise BridgeUnavailable("The data bridge URL must be an HTTPS base URL")
    token = os.environ.get("QUASAR_DATA_BRIDGE_TOKEN", "")
    if len(token) < 32 or not token.isascii():
        raise BridgeUnavailable("The data bridge is not configured")
    return base.rstrip("/"), token


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_snapshot(name):
    """Read a snapshot locally or from the configured HTTPS bridge.

    Returns None only when local mode has no imported snapshot. Remote failures
    raise BridgeUnavailable so callers can preserve an explicit unavailable state.
    """
    path, limit = _path_for(name)
    upstream = _bridge_url()
    if upstream is None:
        if path is None:
            return None
        try:
            if path.stat().st_size > limit:
                raise ValueError("Snapshot exceeds its size limit")
            return _parse_snapshot(path.read_bytes(), limit)
        except FileNotFoundError:
            return None

    base, token = upstream
    cache_key = (base, name)
    cached = _remote_cache.get(cache_key)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    request = Request(f"{base}/snapshots/{name}", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Quasar-data-bridge/1",
    })
    try:
        with build_opener(_NoRedirect).open(request, timeout=8) as response:
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise BridgeUnavailable("The data bridge returned an unexpected content type")
            length = response.headers.get("Content-Length")
            if length and int(length) > limit:
                raise BridgeUnavailable("The data bridge snapshot exceeds its size limit")
            payload = response.read(limit + 1)
        data = _parse_snapshot(payload, limit)
    except HTTPError as exc:
        if exc.code == 404:
            try:
                missing = json.loads(exc.read(limit + 1))
            except (ValueError, OSError):
                missing = None
            if isinstance(missing, dict) and missing.get("status") == "not_imported":
                return None
        raise BridgeUnavailable("The data bridge snapshot is unavailable") from exc
    except BridgeUnavailable:
        raise
    except (URLError, TimeoutError, OSError, ValueError, TypeError) as exc:
        raise BridgeUnavailable("The data bridge snapshot is unavailable") from exc
    _remote_cache[cache_key] = (now + REMOTE_CACHE_SECONDS, data)
    return data


def serve_snapshot(name, authorization):
    """Return (status, payload) for the LinuxONE-only bridge endpoint."""
    if os.environ.get("QUASAR_DATA_BRIDGE_SERVE") != "1":
        return 404, {"error": "Route not found"}
    token = os.environ.get("QUASAR_DATA_BRIDGE_TOKEN", "")
    if len(token) < 32 or not token.isascii():
        return 503, {"status": "unavailable", "error": "Data bridge is not configured"}
    supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    if not hmac.compare_digest(supplied, token):
        return 401, {"error": "Bridge authentication required"}
    try:
        path, limit = _path_for(name)
        if path is None:
            return 404, {"status": "not_imported", "error": "Snapshot is not available"}
        if path.stat().st_size > limit:
            raise ValueError("Snapshot exceeds its size limit")
        payload = path.read_bytes()
        data = _parse_snapshot(payload, limit)
        # Emit canonical JSON and reject NaN/Infinity before sending it upstream.
        encoded = json.dumps(data, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > limit:
            raise ValueError("Snapshot exceeds its size limit")
        return 200, encoded
    except FileNotFoundError:
        return 404, {"status": "not_imported", "error": "Snapshot is not available"}
    except (OSError, ValueError, TypeError):
        return 503, {"status": "unavailable", "error": "Snapshot is unavailable or invalid"}
