"""Authenticated, allow-listed snapshot bridge for IBM LinuxONE and Vercel.

The LinuxONE process serves normalized snapshots from its local data directory.
The Vercel process can fetch those snapshots over HTTPS using a server-only token.
Raw downloads and property datasets are intentionally not bridgeable.
"""

import hmac
import hashlib
import json
import os
import time
from pathlib import Path
from functools import lru_cache
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .timing import phase
from .transport import read_body


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
_source_lock = RLock()


def file_version(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


class _Snapshot(dict):
    """Internal read-only-by-contract snapshot with a once-computed identity."""
    def __init__(self, data, limit):
        super().__init__(data)
        self.encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(self.encoded) > limit:
            raise ValueError("Snapshot exceeds its size limit")
        self.content_identity = hashlib.sha256(self.encoded).digest()


@lru_cache(maxsize=4)
def _local_snapshot(path, version, limit):
    data = _Snapshot(_parse_snapshot(Path(path).read_bytes(), limit), limit)
    if file_version(path) != version:
        raise ValueError("Snapshot changed during loading")
    return data


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
    with phase("source"), _source_lock:
        return _read_snapshot(name)


def _read_snapshot(name):
    path, limit = _path_for(name)
    upstream = _bridge_url()
    if upstream is None:
        if path is None:
            return None
        try:
            version = file_version(path)
            if version[2] > limit:
                raise ValueError("Snapshot exceeds its size limit")
            return _local_snapshot(str(path.resolve()), version, limit)
        except FileNotFoundError:
            return None

    base, token = upstream
    cache_key = (base, name, hashlib.sha256(token.encode()).digest())
    cached = _remote_cache.get(cache_key)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    request = Request(f"{base}/snapshots/{name}", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "User-Agent": "Quasar-data-bridge/1",
    })
    try:
        with phase("upstream"), build_opener(_NoRedirect).open(request, timeout=8) as response:
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise BridgeUnavailable("The data bridge returned an unexpected content type")
            payload = read_body(response, limit)
        data = _Snapshot(_parse_snapshot(payload, limit), limit)
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
    if cached and cached[1] == data:
        data = cached[1]
    _remote_cache[cache_key] = (now + REMOTE_CACHE_SECONDS, data)
    while len(_remote_cache) > 4:
        del _remote_cache[next(iter(_remote_cache))]
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
        version = file_version(path)
        if version[2] > limit:
            raise ValueError("Snapshot exceeds its size limit")
        with phase("source"), _source_lock:
            data = _local_snapshot(str(path.resolve()), version, limit)
        return 200, data.encoded
    except FileNotFoundError:
        return 404, {"status": "not_imported", "error": "Snapshot is not available"}
    except (OSError, ValueError, TypeError):
        return 503, {"status": "unavailable", "error": "Snapshot is unavailable or invalid"}
