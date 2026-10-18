"""Bounded, exact-window references to immutable single-window assessments.

Catalogs are server-side release files. Loading one never produces assessments,
queries a source, or falls back to a different hour or single-file release.
"""
import re
from datetime import timedelta
from functools import lru_cache
from pathlib import Path, PurePosixPath

from .config import COUNTY_FIPS
from .modeling import read_json
from .adapters.weathernext import timestamp

MAX_CATALOG_BYTES = 1024 * 1024
MAX_WINDOWS = 256


def version(path):
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino


def sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def artifact_path(root, relative):
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("Catalog artifact must be a relative path")
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or ".." in path.parts or ":" in relative:
        raise ValueError("Catalog artifact must stay beneath its root")
    base = Path(root).resolve(strict=True)
    candidate = (base / relative).resolve(strict=True)
    if not candidate.is_relative_to(base) or not candidate.is_file():
        raise ValueError("Catalog artifact escapes its root or is not a file")
    return candidate


@lru_cache(maxsize=2)
def _catalog(path, revision):
    data = read_json(path, MAX_CATALOG_BYTES)
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("county_fips") != COUNTY_FIPS
            or not isinstance(data.get("inventory_id"), str) or not data["inventory_id"]
            or not sha256(data.get("model_sha256"))
            or not isinstance(data.get("entries"), list) or len(data["entries"]) > MAX_WINDOWS):
        raise ValueError("Invalid exposure catalog identity or size")
    keys = set()
    for entry in data["entries"]:
        if (not isinstance(entry, dict) or set(entry) != {"mode", "valid_from", "valid_to", "path", "sha256", "forecast_sha256"}
                or entry.get("mode") not in ("current", "replay")):
            raise ValueError("Invalid catalog entry")
        start, end = timestamp(entry["valid_from"]), timestamp(entry["valid_to"])
        key = (entry["mode"], start, end)
        if (end - start != timedelta(hours=6) or key in keys
                or not sha256(entry.get("sha256")) or not sha256(entry.get("forecast_sha256"))
                or not isinstance(entry.get("path"), str)):
            raise ValueError("Duplicate or invalid catalog window")
        relative = PurePosixPath(entry["path"])
        if (not entry["path"] or relative.is_absolute() or ".." in relative.parts
                or "\\" in entry["path"] or ":" in entry["path"]):
            raise ValueError("Catalog paths must be relative and contained")
        keys.add(key)
    return data


def load(path):
    return _catalog(str(Path(path).resolve()), version(path))


def select(path, root, mode, start, end):
    data = load(path)
    entry = next((e for e in data["entries"] if e["mode"] == mode
                  and timestamp(e["valid_from"]) == start and timestamp(e["valid_to"]) == end), None)
    if entry is None:
        return None
    return data, entry, artifact_path(root, entry["path"])


def verify(data, entry, artifact, start, end):
    """Hash is checked by the decoded artifact cache before this semantic check."""
    source = artifact.get("forecast_provenance", {})
    if (artifact["inventory_id"] != data["inventory_id"]
            or artifact.get("model_metadata", {}).get("model_sha256") != data["model_sha256"]
            or source.get("source_sha256") != entry["forecast_sha256"]
            or source.get("mode") != entry["mode"]
            or len(artifact["windows"]) != 1 or (start, end) not in artifact["windows"]):
        raise ValueError("Catalog model, inventory or forecast/window mismatch")
