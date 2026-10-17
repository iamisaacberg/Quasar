"""Read-only, minimal-field county GIS browsing. No model inputs are inferred."""
import json
import hashlib
import os
import re
import sqlite3
import time
import zlib
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from .geometry import covers, line_covered, polygons, position
from .config import COUNTY_FIPS, COUNTY_BOUNDARY_URL, PARCEL_SOURCE_URL, COUNTY_TERMS_URL, PARCEL_LICENSE

COUNTY_URL = COUNTY_BOUNDARY_URL
PARCEL_URL = PARCEL_SOURCE_URL
TERMS_URL = COUNTY_TERMS_URL
PAGE_SIZE = 100
_ids_cache = OrderedDict()


def indexed_version(metadata):
    return metadata["source_provenance"]["output_sha256"] + ":" + metadata["cell_index_sha256"]


def parcel_manifest():
    if os.environ.get("QUASAR_LINUXONE_API_URL"):
        return remote_inspection("/api/parcels/manifest")
    if os.environ.get("QUASAR_PARCEL_DATABASE"):
        from .parcel_context import inventory_metadata
        meta = inventory_metadata()
        source = meta["source_provenance"]
        return {"status": "ready", "county_fips": COUNTY_FIPS, "source_mode": "indexed",
                "source_url": source["source_url"], "dataset_version": indexed_version(meta),
                "inventory_id": source["output_sha256"],
                "boundary_version": source["county_boundary"]["sha256"],
                "retrieved_at": source["retrieved_at"], "crs": "EPSG:4326", "geometry_valid_until": None}
    boundary = county_boundary()
    boundary_version = hashlib.sha256(json.dumps(boundary["features"][0]["geometry"], sort_keys=True).encode()).hexdigest()
    day = int(time.time() // 86400)
    return {"status": "ready", "county_fips": COUNTY_FIPS, "source_mode": "live_gis",
            "source_url": PARCEL_URL, "dataset_version": f"gis-day-{day}", "inventory_id": None,
            "boundary_version": boundary_version, "retrieved_at": _now(), "crs": "EPSG:4326",
            "geometry_valid_until": datetime.fromtimestamp((day + 1) * 86400, timezone.utc).isoformat()}


def remote_inspection(path, inventory_id=None):
    """Only fixed inspection routes can cross the existing server-only proxy."""
    if not (path == "/api/parcels/manifest" or re.fullmatch(r"/api/parcels/[0-9]{1,16}/context", path)
            or re.fullmatch(r"/api/cells/8[4-7][0-9a-f]{13}/summary", path)):
        raise ValueError("Invalid parcel inspection route")
    base = os.environ.get("QUASAR_LINUXONE_API_URL", "").rstrip("/")
    token = os.environ.get("QUASAR_LINUXONE_API_TOKEN", "")
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or len(token) < 32):
        raise SourceUnavailable("LinuxONE parcel service is not configured.")
    query = "?" + urlencode({"inventory_id": inventory_id}) if inventory_id else ""
    request = Request(base + path + query, headers={"X-Quasar-Parcel-Token": token})
    try:
        with build_opener(_NoRedirect).open(request, timeout=12) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Inspection response too large")
        data = json.loads(body)
        if data.get("county_fips") != COUNTY_FIPS or data.get("status") != "ready":
            raise ValueError("Invalid county inspection")
        if path.endswith("manifest"):
            if (data.get("source_mode") != "indexed" or not all(isinstance(data.get(k), str) and data[k]
                    for k in ("dataset_version", "inventory_id", "boundary_version", "source_url", "crs"))):
                raise ValueError("Invalid inventory manifest")
        elif (data.get("risk_score") is not None or data.get("risk_band") != "unknown"
              or (inventory_id and data.get("inventory_id") != inventory_id)):
            raise ValueError("Unsupported score or mismatched inventory")
        return data
    except Exception as exc:
        raise SourceUnavailable("LinuxONE parcel inspection unavailable; inputs remain unknown.") from exc


class SourceUnavailable(Exception):
    """Source failures must never masquerade as an empty inventory."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get(url, params):
    try:
        request = Request(url + "?" + urlencode(params), headers={"User-Agent": "Quasar-datathon/0.1"})
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        if not isinstance(data, dict) or "error" in data:
            raise ValueError("Invalid GIS response")
        return data
    except Exception as exc:
        raise SourceUnavailable("County GIS source unavailable. Parcel coverage is unknown; retry later.") from exc


def _now():
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=2)
def _county(day):
    data = _get(COUNTY_URL + "/query", {"where": "GEOID='12091'", "outFields": "GEOID,NAME",
                                          "outSR": 4326, "f": "geojson"})
    features = data.get("features", [])
    if len(features) != 1 or features[0].get("properties", {}).get("GEOID") != "12091":
        raise SourceUnavailable("Authoritative Okaloosa boundary unavailable.")
    try:
        geometry = features[0]["geometry"]
        parts = polygons(geometry)
        if not parts or not all(poly and all(len(ring) >= 4 and ring[0] == ring[-1] and all(position(p) for p in ring)
                                             for ring in poly) for poly in parts):
            raise ValueError("Empty or malformed county polygon")
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise SourceUnavailable("Authoritative Okaloosa boundary invalid.") from exc
    return {"type": "FeatureCollection", "features": features, "county_fips": "12091",
            "source_url": COUNTY_URL, "retrieved_at": _now(), "crs": "EPSG:4326",
            "units": "degrees", "license": "US Census public data",
            "processing": "GEOID 12091 query; native county geometry transformed by TIGERweb to WGS84"}


def county_boundary():
    return _county(int(time.time() // 86400))


def validate_ring(value):
    try:
        ring = json.loads(value)
    except (ValueError, TypeError):
        raise ValueError("A resolution-7 cell ring is required") from None
    if (not isinstance(ring, list) or len(ring) not in (6, 7, 8) or not all(position(p) for p in ring)
            or ring[0] != ring[-1]):
        raise ValueError("A closed resolution-7 cell ring is required")
    for axis in (0, 1):
        span = max(p[axis] for p in ring) - min(p[axis] for p in ring)
        if not 0 < span <= 0.05:
            raise ValueError("Select a resolution-7 cell before loading parcels")
    # A fixed pilot envelope limits queries; authoritative geometry validates every result below.
    if not all(-87.0 <= p[0] <= -86.2 and 30.1 <= p[1] <= 31.1 for p in ring):
        raise ValueError("Cell is outside the Okaloosa pilot")
    return ring


def _covered(geometry, county):
    """Validate complete parcel edges, with a fast path away from county borders."""
    try:
        parts = polygons(geometry)
        if not parts:
            return False
        county_rings = [ring for poly in polygons(county) for ring in poly]
        for part in parts:
            if not part or any(len(ring) < 4 or ring[0] != ring[-1]
                               or not all(position(p) for p in ring) for ring in part):
                return False
            points = [p for ring in part for p in ring]
            lo = [min(p[i] for p in points) for i in (0, 1)]
            hi = [max(p[i] for p in points) for i in (0, 1)]
            near_border = any(all(max(a[i], b[i]) >= lo[i] and min(a[i], b[i]) <= hi[i] for i in (0, 1))
                              for ring in county_rings for a, b in zip(ring, ring[1:]))
            if not covers(part[0][0], county):
                return False
            if near_border:
                if not all(line_covered(ring, county) for ring in part):
                    return False
                # A parcel cannot fill a hole in the county polygon.
                if any(covers(hole[0], {"type": "Polygon", "coordinates": part})
                       for poly in polygons(county) for hole in poly[1:]):
                    return False
        return True
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return False


def _database_page(cell_id, offset, inventory_id):
    database = os.environ.get("QUASAR_PARCEL_DATABASE")
    if not database:
        raise SourceUnavailable("Parcel database is not configured.")
    if not isinstance(cell_id, str) or not re.fullmatch(r"[0-9a-f]{15}", cell_id):
        raise ValueError("A county H3 cell at resolution 4 through 7 is required")
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        metadata = {key: json.loads(value) for key, value in connection.execute("SELECT key,value FROM metadata")}
        source = metadata["source_provenance"]
        if metadata.get("county_fips") != "12091" or metadata.get("h3_resolutions") != [4, 5, 6, 7]:
            raise ValueError("Parcel database metadata is incompatible")
        if inventory_id is not None and inventory_id != source["output_sha256"]:
            raise SourceUnavailable("Parcel snapshot changed while paging. Retry this cell.")
        cell = connection.execute("SELECT resolution FROM county_cells WHERE cell_id=?", (cell_id,)).fetchone()
        if cell is None:
            raise ValueError("Cell is outside Okaloosa county coverage")
        if cell[0] != 7:
            raise ValueError("Zoom to an H3 resolution-7 cell to inspect parcels")
        total = connection.execute("SELECT count(*) FROM cell_parcels WHERE cell_id=?", (cell_id,)).fetchone()[0]
        if offset > total:
            raise ValueError("Invalid parcel offset")
        rows = connection.execute(
            "SELECT p.feature_z FROM cell_parcels cp JOIN parcels p USING(parcel_id) "
            "WHERE cp.cell_id=? ORDER BY cp.parcel_id LIMIT ? OFFSET ?",
            (cell_id, PAGE_SIZE, offset),
        ).fetchall()
        connection.close()
        features = [json.loads(zlib.decompress(row[0])) for row in rows]
    except sqlite3.Error as exc:
        raise SourceUnavailable("Parcel database unavailable. Parcel coverage is unknown; retry later.") from exc
    next_offset = offset + len(features)
    return {"type": "FeatureCollection", "features": features, "status": "ready",
            "county_fips": COUNTY_FIPS,
            "source_total": total, "checked_count": next_offset, "excluded_count": 0,
            "inventory_id": source["output_sha256"], "next_offset": next_offset if next_offset < total else None,
            "dataset_version": indexed_version(metadata),
            "source_url": source["source_url"], "terms_url": source["terms_url"],
            "retrieved_at": source["retrieved_at"], "inventory_at": source["retrieved_at"],
            "county_boundary_retrieved_at": source["county_boundary"]["retrieved_at"],
            "crs": source["crs"], "units": source["units"], "license": source["license"],
            "processing": f"County-boundary-validated parcel polygons indexed to overlapping H3 resolution {cell[0]} cell; no scoring joins",
            "notice": "County parcel geometry only. Flood inputs and scores unavailable; every parcel score remains unknown."}


def _remote_page(cell_id, offset, inventory_id):
    base_url = os.environ.get("QUASAR_LINUXONE_API_URL", "").rstrip("/")
    token = os.environ.get("QUASAR_LINUXONE_API_TOKEN", "")
    if not base_url or len(token) < 32:
        raise SourceUnavailable("LinuxONE parcel service is not configured.")
    if urlsplit(base_url).scheme != "https" or not urlsplit(base_url).hostname:
        raise SourceUnavailable("LinuxONE parcel service must use an HTTPS origin.")
    params = {"cell": cell_id or "", "offset": str(offset)}
    if inventory_id is not None:
        params["inventory_id"] = inventory_id
    request = Request(f"{base_url}/api/parcels?{urlencode(params)}",
                      headers={"X-Quasar-Parcel-Token": token, "User-Agent": "Quasar-Vercel-Proxy/0.1"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=12) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Parcel page exceeded the response size limit")
        page = json.loads(body)
        if not isinstance(page, dict) or page.get("status") != "ready" or not isinstance(page.get("features"), list):
            raise ValueError("LinuxONE returned an invalid parcel page")
        validate_remote_page(page)
        return page
    except Exception as exc:
        raise SourceUnavailable("LinuxONE parcel service unavailable. Parcel coverage is unknown; retry later.") from exc


def validate_remote_page(page):
    if page.get("county_fips") != COUNTY_FIPS or len(page["features"]) > PAGE_SIZE:
        raise ValueError("Remote parcel page has the wrong county or size")
    county = county_boundary()["features"][0]["geometry"]
    for feature in page["features"]:
        props = feature.get("properties", {})
        if (props.get("county_fips") != COUNTY_FIPS or props.get("risk_score") is not None
                or props.get("risk_band") != "unknown" or not _covered(feature.get("geometry"), county)):
            raise ValueError("Remote parcel is outside the county or contains unsupported scores")
        feature["properties"] = {key: props[key] for key in ("parcel_id", "county_fips", "risk_score", "risk_band")}


def parcel_page(ring_value, offset_value="0", inventory_id=None, cell_id=None):
    ring = validate_ring(ring_value)
    try:
        offset = int(offset_value)
    except (ValueError, TypeError):
        raise ValueError("Invalid parcel offset") from None
    if offset < 0 or offset % PAGE_SIZE:
        raise ValueError("Invalid parcel offset")
    if os.environ.get("QUASAR_LINUXONE_API_URL"):
        return _remote_page(cell_id, offset, inventory_id)
    if os.environ.get("QUASAR_PARCEL_DATABASE"):
        return _database_page(cell_id, offset, inventory_id)
    county = county_boundary()
    key = json.dumps(ring, separators=(",", ":"))
    cached = _ids_cache.get(key)
    if cached is None or time.time() - cached[0] > 300:
        # Clockwise exterior ring for the Esri polygon query.
        area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(ring, ring[1:]))
        query_ring = ring if area < 0 else list(reversed(ring))
        data = _get(PARCEL_URL + "/query", {"where": "1=1", "geometry": json.dumps({"rings": [query_ring], "spatialReference": {"wkid": 4326}}),
                    "geometryType": "esriGeometryPolygon", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
                    "returnIdsOnly": "true", "f": "json"})
        ids = data.get("objectIds")
        if not isinstance(ids, list) or any(type(i) is not int or i < 0 for i in ids):
            raise SourceUnavailable("Parcel ID inventory unavailable; coverage is unknown.")
        cached = (time.time(), sorted(set(ids)), _now())
        _ids_cache[key] = cached
        _ids_cache.move_to_end(key)
        while len(_ids_cache) > 64:
            _ids_cache.popitem(last=False)
    _, ids, queried_at = cached
    fingerprint = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
    if inventory_id is not None and inventory_id != fingerprint:
        raise SourceUnavailable("Parcel inventory changed while paging. Retry this cell.")
    if offset > len(ids):
        raise ValueError("Invalid parcel offset")
    batch = ids[offset:offset + PAGE_SIZE]
    features, excluded = [], 0
    if batch:
        data = _get(PARCEL_URL + "/query", {"objectIds": ",".join(map(str, batch)),
                    "outFields": "OBJECTID", "returnGeometry": "true", "outSR": 4326, "f": "geojson"})
        rows = data.get("features")
        if not isinstance(rows, list) or data.get("exceededTransferLimit"):
            raise SourceUnavailable("Parcel page incomplete. Retry this cell.")
        returned = [f.get("properties", {}).get("OBJECTID") for f in rows]
        if len(returned) != len(batch) or set(returned) != set(batch):
            _ids_cache.pop(key, None)
            raise SourceUnavailable("Parcel inventory changed or a page is incomplete. Retry this cell.")
        for feature in rows:
            if not _covered(feature.get("geometry"), county["features"][0]["geometry"]):
                excluded += 1
                continue
            p = feature["properties"]
            features.append({"type": "Feature", "id": p["OBJECTID"], "geometry": feature["geometry"],
                             "properties": {"parcel_id": p["OBJECTID"],
                                            "county_fips": "12091", "risk_score": None, "risk_band": "unknown"}})
    next_offset = offset + len(batch)
    return {"type": "FeatureCollection", "features": features, "status": "ready",
            "county_fips": COUNTY_FIPS,
            "source_total": len(ids), "checked_count": next_offset, "excluded_count": excluded,
            "inventory_id": fingerprint,
            "dataset_version": f"gis-day-{int(time.time() // 86400)}",
            "next_offset": next_offset if next_offset < len(ids) else None,
            "source_url": PARCEL_URL, "terms_url": TERMS_URL, "retrieved_at": _now(), "inventory_at": queried_at,
            "county_boundary_retrieved_at": county["retrieved_at"], "crs": "EPSG:4326", "units": "degrees",
            "license": PARCEL_LICENSE,
            "processing": "Parcels intersecting selected cell; OBJECTID/geometry only; complete polygon county containment; no scoring joins",
            "notice": "Real county parcel geometry. Flood inputs and scores unavailable. Fictional exercise scores do not apply to these parcels."}
