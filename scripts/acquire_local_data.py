"""Acquire public Okaloosa boundary and USGS stream monitoring metadata.

Downloads stay under ignored data/raw and data/processed directories. This does
not query BigQuery or fetch parcel, address, or owner records.
"""

import argparse
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
BOUNDARY_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query"
USGS_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items"
FEMA_URL = "https://msc.fema.gov/portal/downloadProduct?productID=NFHL_12091C"
TNM_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
COUNTY = "12091"
HEADERS = {"User-Agent": "Quasar-datathon/0.1 (local public-data acquisition)"}


def get_json(url: str) -> bytes:
    last_error = None
    for attempt in range(4):
        try:
            request = Request(url, headers=HEADERS)
            with urlopen(request, timeout=90) as response:
                return response.read()
        except Exception as error:
            last_error = error
            if attempt < 3:
                time.sleep(1 + attempt * 2)
    raise last_error


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for index, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(index + 1) % len(ring)]
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def point_in_geometry(point, geometry):
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    elif geometry["type"] == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        return False
    for rings in polygons:
        if rings and point_in_ring(point, rings[0]) and not any(
            point_in_ring(point, hole) for hole in rings[1:]
        ):
            return True
    return False


def save(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": str(path.relative_to(ROOT)), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


def describe_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def download_file(url: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=180) as response, path.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return {"path": str(path.relative_to(ROOT)), "bytes": size, "sha256": digest.hexdigest()}


def geometry_positions(geometry):
    if isinstance(geometry, list):
        if len(geometry) >= 2 and all(isinstance(value, (int, float)) for value in geometry[:2]):
            yield geometry
        else:
            for child in geometry:
                yield from geometry_positions(child)


def acquire():
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    boundary_query = urlencode({
        "where": "GEOID='12091'", "outFields": "GEOID,NAME,STATE,COUNTY",
        "returnGeometry": "true", "outSR": "4326", "f": "geojson",
    })
    boundary_bytes = get_json(f"{BOUNDARY_URL}?{boundary_query}")
    boundary = json.loads(boundary_bytes)
    features = boundary.get("features", [])
    if len(features) != 1 or features[0].get("properties", {}).get("GEOID") != COUNTY:
        raise ValueError("Census response did not contain exactly Okaloosa County (12091)")
    boundary_info = save(RAW / "census_okaloosa_county.geojson", boundary_bytes)
    save(RAW / "census_okaloosa_county.provenance.json", json.dumps({
        "source_url": f"{BOUNDARY_URL}?{boundary_query}", "source_identifier": "GEOID 12091",
        "retrieved_at": retrieved, "county_fips": COUNTY, "crs": "EPSG:4326",
        "license": "US Census public data", "sha256": boundary_info["sha256"],
    }, indent=2).encode())
    county_geometry = features[0]["geometry"]

    usgs_query = urlencode({"f": "json", "limit": "50000", "state_code": "12",
                            "county_code": "091", "site_type_code": "ST"})
    usgs_bytes = get_json(f"{USGS_URL}?{usgs_query}")
    usgs = json.loads(usgs_bytes)
    usgs_info = save(RAW / "usgs_okaloosa_stream_locations.geojson", usgs_bytes)
    local_features = []
    rejected = 0
    for feature in usgs.get("features", []):
        properties = feature.get("properties", {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if (properties.get("state_code") != "12" or properties.get("county_code") != "091"
                or len(coordinates) < 2
                or not point_in_geometry(coordinates[:2], county_geometry)):
            rejected += 1
            continue
        local_features.append(feature)
    filtered = {"type": "FeatureCollection", "county_fips": COUNTY,
                "source": USGS_URL, "retrieved_at": retrieved,
                "crs": "EPSG:4326", "units": None,
                "notice": "USGS stream monitoring locations; site tags and points checked against Census county geometry. This is site metadata, not current stage observations or a gauge-to-property linkage.",
                "features": local_features}
    processed_bytes = json.dumps(filtered, indent=2, allow_nan=False).encode()
    processed_info = save(PROCESSED / "usgs_okaloosa_stream_locations.geojson", processed_bytes)

    # FEMA's official direct download supplies the complete county database and
    # avoids the transfer limits on its polygon query endpoint.
    fema_path = RAW / "fema_nfhl_okaloosa_12091c.zip"
    if fema_path.exists():
        with zipfile.ZipFile(fema_path) as archive:
            bad_member = archive.testzip()
            archive_names = archive.namelist()
        if bad_member:
            raise ValueError(f"Existing FEMA NFHL archive failed CRC validation at {bad_member}")
        flood_info = describe_file(fema_path)
    else:
        fema_bytes = get_json(FEMA_URL)
        with zipfile.ZipFile(io.BytesIO(fema_bytes)) as archive:
            bad_member = archive.testzip()
            archive_names = archive.namelist()
        if bad_member:
            raise ValueError(f"FEMA NFHL archive failed CRC validation at {bad_member}")
        flood_info = save(fema_path, fema_bytes)
    if not any("S_FLD_HAZ_AR" in name.upper() for name in archive_names):
        raise ValueError("FEMA NFHL archive is missing the flood hazard area feature class")

    # Download the latest seamless 10 m DEM tile(s) intersecting the actual
    # county polygon, rather than a larger rectangle or a countywide state file.
    positions = list(geometry_positions(county_geometry["coordinates"]))
    bbox = ",".join(str(value) for value in (
        min(p[0] for p in positions), min(p[1] for p in positions),
        max(p[0] for p in positions), max(p[1] for p in positions)))
    dem_query = urlencode({
        "datasets": "National Elevation Dataset (NED) 1/3 arc-second",
        "bbox": bbox, "prodFormats": "GeoTIFF", "outputFormat": "JSON", "max": "100",
    })
    dem_catalog_url = f"{TNM_URL}?{dem_query}"
    dem_catalog_bytes = get_json(dem_catalog_url)
    dem_catalog = json.loads(dem_catalog_bytes)
    dem_candidates = [item for item in dem_catalog.get("items", [])
                      if "1/3 Arc Second" in item.get("title", "")]
    latest_by_tile = {}
    for item in dem_candidates:
        match = re.search(r"\b(n\d+w\d+) (\d{8})$", item.get("title", ""))
        if match and (match.group(1) not in latest_by_tile
                      or match.group(2) > latest_by_tile[match.group(1)][0]):
            latest_by_tile[match.group(1)] = (match.group(2), item)
    if not latest_by_tile:
        raise ValueError("TNMAccess returned no 1/3 arc-second GeoTIFF tiles for Okaloosa")
    dem_products = []
    for tile, (_, item) in sorted(latest_by_tile.items()):
        dem_path = RAW / "usgs_3dep_10m" / Path(item["downloadURL"]).name
        if dem_path.exists() and dem_path.stat().st_size == item.get("sizeInBytes"):
            dem_file = describe_file(dem_path)
        else:
            dem_file = download_file(item["downloadURL"], dem_path)
        if dem_file["bytes"] != item.get("sizeInBytes"):
            raise ValueError(f"3DEP tile size mismatch for {tile}")
        metadata_path = dem_path.with_suffix(".xml")
        metadata_bytes = get_json(item["vendorMetaUrl"])
        metadata_info = save(metadata_path, metadata_bytes)
        dem_products.append({
            "name": item["title"], "identifier": item["sourceId"],
            "url": item["downloadURL"], "metadata_url": item["vendorMetaUrl"],
            "license": "USGS 3DEP public elevation product; verify applicable current terms before redistribution.",
            "crs": "Original GeoTIFF CRS retained; inspect vendor XML before transformations (NAD83 geographic is EPSG:4269).",
            "units": "Elevation meters; NAVD 88 vertical datum for CONUS, per USGS product metadata.",
            "processing": "Selected latest catalog tile by tile name from the county-bound intersection query; downloaded the original 1/3 arc-second GeoTIFF and vendor metadata. Not clipped or resampled.",
            "tile_extent": item.get("extent"), "published": item.get("publicationDate"),
            "catalog_last_updated": item.get("lastUpdated"),
            "size_reported": item.get("sizeInBytes"), **dem_file,
            "metadata": metadata_info,
        })

    manifest = {
        "retrieved_at": retrieved,
        "county_fips": COUNTY,
        "notice": "Research inputs; not a validated flood model or operational alert feed.",
        "sources": [
            {"name": "Census TIGERweb county geometry", "identifier": "GEOID 12091",
             "url": BOUNDARY_URL, "license": "U.S. Census Bureau public TIGERweb geographic data; verify applicable current terms before redistribution.",
             "crs": "EPSG:4326", "units": "decimal degrees", "processing": "Requested only GEOID 12091; preserved the original response as the authoritative county-boundary validation geometry.",
             **boundary_info},
            {"name": "USGS Water Data monitoring locations", "identifier": "state_code 12, county_code 091, site_type_code ST",
             "url": USGS_URL, "license": "USGS public water data; verify applicable current terms before redistribution.",
             "crs": "EPSG:4326", "units": "coordinates in decimal degrees; station metadata units vary by field and are not observations.",
             "processing": f"Preserved the county-filtered API response, then retained only records tagged to FIPS 12091 whose point geometry falls inside the Census county polygon; rejected {rejected} records.",
             **usgs_info},
            {"name": "County-validated USGS stream monitoring locations", "identifier": "local filtered feature set",
             "url": USGS_URL, "license": "USGS public water data; verify applicable current terms before redistribution.",
             "crs": "EPSG:4326", "units": "coordinates in decimal degrees; no water-level values included.",
             "processing": "Filtered by exact county tags and point-in-polygon against the saved Census TIGERweb county boundary.",
             "feature_count": len(local_features), **processed_info},
            {"name": "FEMA National Flood Hazard Layer Okaloosa county database", "identifier": "NFHL_12091C",
             "url": FEMA_URL, "license": "Federal Emergency Management Agency NFHL public map service; verify applicable current terms before redistribution.",
             "crs": "Original NFHL geodatabase coordinate reference systems; inspect feature-class metadata before analysis.",
             "units": "BFE/depth units and vertical datum are stored in the corresponding NFHL feature attributes.",
             "processing": f"Downloaded the direct FEMA county product; verified ZIP integrity and presence of S_FLD_HAZ_AR; archive members: {len(archive_names)}.",
             "archive_members": archive_names, **flood_info},
            *dem_products,
        ],
        "not_loaded": {
            "weathernext": "Acquired separately with the explicit capped county WeatherNext importer; this acquisition command never queries BigQuery.",
            "parcels": "Acquired separately by scripts/acquire_county_parcels.py, requesting only IDs and geometry.",
            "elevation": "Latest available seamless 1/3 arc-second (about 10 m) tiles intersecting the county downloaded. Original rasters still need clipping and NoData/vertical-datum review before any use as parcel terrain.",
            "fema": "Current county NFHL package downloaded. Inspect feature-class CRS, BFE units and vertical datum before spatial joins; NFHL is not a forecast or a complete flood-risk model.",
            "historical_storm": "Isaias October 9, 2026, Central time replay selected; forecasts and NHC context are separate imports. Observed flood outcomes remain unavailable.",
        },
    }
    save(PROCESSED / "source_manifest.json", json.dumps(manifest, indent=2).encode())
    print(json.dumps({"retrieved_at": retrieved, "county_boundary": boundary_info,
                      "usgs_raw": usgs_info, "usgs_county_validated": processed_info,
                      "usgs_count": len(local_features), "rejected": rejected,
                      "manifest": "data/processed/source_manifest.json"}, indent=2))


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    for attempt in range(3):
        try:
            acquire()
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


if __name__ == "__main__":
    main()
