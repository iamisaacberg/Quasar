"""Acquire minimal Okaloosa parcel geometry pages to an ignored local file.

This is an explicit importer. It requests only OBJECTID and polygon geometry,
validates every complete polygon against the authoritative Census boundary,
and writes a compressed line-delimited GeoJSON snapshot. It never uploads data.
"""

import argparse
import gzip
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quasar.geometry import covers as geometry_covers, position, polygons
from quasar.config import PARCEL_SOURCE_URL, COUNTY_TERMS_URL, PARCEL_LICENSE

LAYER_URL = PARCEL_SOURCE_URL
DEFAULT_BOUNDARY = ROOT / "data/raw/census_okaloosa_county.geojson"
DEFAULT_OUTPUT = ROOT / "data/raw/okaloosa_parcels_wgs84.geojsonl.gz"
USER_AGENT = "Quasar-datathon/0.1 (county parcel data importer)"
BIN_SIZE = 0.002


from quasar.geometry_index import CountyBoundaryIndex


def fetch_json(url, params, attempts=5):
    encoded = urlencode(params)
    headers = {"User-Agent": USER_AGENT}
    if len(encoded) > 1800:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=encoded.encode("ascii"), headers=headers, method="POST")
    else:
        request = Request(url + "?" + encoded, headers=headers)
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=45) as response:
                data = json.load(response)
            if not isinstance(data, dict) or "error" in data:
                raise ValueError(f"ArcGIS returned an error: {data.get('error', 'invalid response')}")
            return data
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            if attempt + 1 == attempts:
                raise RuntimeError(f"County GIS request failed after {attempts} attempts: {exc}") from exc
            time.sleep(min(2 ** attempt, 16))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--pause", type=float, default=0.1, help="seconds between source requests")
    args = parser.parse_args()
    if not 1 <= args.page_size <= 1000:
        parser.error("--page-size must be from 1 through the source's 1000-record limit")
    if args.pause < 0:
        parser.error("--pause cannot be negative")

    boundary_data = json.loads(args.boundary.read_text(encoding="utf-8"))
    boundary_features = boundary_data.get("features", [])
    if (boundary_data.get("type") != "FeatureCollection" or len(boundary_features) != 1
            or (boundary_features[0].get("properties") or {}).get("GEOID") != "12091"):
        raise SystemExit("A single authoritative Census GEOID 12091 boundary is required")
    county_geometry = boundary_features[0].get("geometry")
    if not county_geometry:
        raise SystemExit("Census county boundary geometry is missing")
    boundary_index = CountyBoundaryIndex(county_geometry)

    query_url = LAYER_URL + "/query"
    count_data = fetch_json(query_url, {"where": "1=1", "returnCountOnly": "true", "f": "json"})
    source_count = count_data.get("count")
    if type(source_count) is not int or source_count <= 0:
        raise SystemExit("County parcel service did not return a valid feature count")
    ids_data = fetch_json(query_url, {"where": "1=1", "returnIdsOnly": "true", "f": "json"})
    object_ids = ids_data.get("objectIds")
    if not isinstance(object_ids, list) or len(object_ids) != source_count:
        raise SystemExit("Parcel ID inventory does not match the source's countywide count")
    if any(type(value) is not int or value < 0 for value in object_ids):
        raise SystemExit("Parcel ID inventory contains invalid object IDs")
    if len(set(object_ids)) != source_count:
        raise SystemExit("Parcel ID inventory contains duplicates")
    object_ids.sort()
    inventory_digest = hashlib.sha256(json.dumps(object_ids, separators=(",", ":")).encode()).hexdigest()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    imported = excluded = 0
    page_count = (source_count + args.page_size - 1) // args.page_size
    try:
        with temporary.open("wb") as raw_file:
            with gzip.GzipFile(filename="", fileobj=raw_file, mode="wb", compresslevel=6, mtime=0) as compressed:
                for page_index, start in enumerate(range(0, source_count, args.page_size), start=1):
                    batch_ids = object_ids[start:start + args.page_size]
                    data = fetch_json(query_url, {
                        "objectIds": ",".join(map(str, batch_ids)),
                        "outFields": "OBJECTID",
                        "returnGeometry": "true",
                        "outSR": "4326",
                        "f": "geojson",
                    })
                    features = data.get("features")
                    received_ids = [f.get("properties", {}).get("OBJECTID") for f in features or []]
                    if (not isinstance(features, list) or data.get("exceededTransferLimit")
                            or len(features) != len(batch_ids) or set(received_ids) != set(batch_ids)):
                        raise RuntimeError(f"Incomplete parcel page {page_index}/{page_count}; snapshot was not published")
                    for feature in features:
                        geometry = feature.get("geometry")
                        if not boundary_index.covers_parcel(geometry):
                            excluded += 1
                            continue
                        parcel_id = feature["properties"]["OBJECTID"]
                        row = {
                            "type": "Feature",
                            "id": parcel_id,
                            "geometry": geometry,
                            "properties": {
                                "parcel_id": parcel_id,
                                "county_fips": "12091",
                                "risk_score": None,
                                "risk_band": "unknown",
                            },
                        }
                        compressed.write(json.dumps(row, allow_nan=False, separators=(",", ":")).encode() + b"\n")
                        imported += 1
                    if page_index == 1 or page_index % 25 == 0 or page_index == page_count:
                        print(f"Fetched and county-checked {page_index}/{page_count} pages; {imported:,} included, {excluded:,} excluded", flush=True)
                    if args.pause and page_index < page_count:
                        time.sleep(args.pause)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    boundary_provenance = Path(str(args.boundary).replace(".geojson", ".provenance.json"))
    provenance = json.loads(boundary_provenance.read_text(encoding="utf-8")) if boundary_provenance.exists() else {}
    manifest = {
        "schema_version": 1,
        "county_fips": "12091",
        "source_url": LAYER_URL,
        "terms_url": COUNTY_TERMS_URL,
        "retrieved_at": retrieved_at,
        "source_count": source_count,
        "county_validated_count": imported,
        "excluded_count": excluded,
        "object_id_inventory_sha256": inventory_digest,
        "output": str(output.relative_to(ROOT) if output.is_relative_to(ROOT) else output),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256(output),
        "crs": "EPSG:4326",
        "units": "degrees",
        "fields_requested": ["OBJECTID", "geometry"],
        "license": PARCEL_LICENSE,
        "county_boundary": {
            "source_url": provenance.get("source_url"),
            "retrieved_at": provenance.get("retrieved_at"),
            "sha256": sha256(args.boundary),
        },
                        "processing": "Downloaded complete object-ID inventory in bounded pages; requested only OBJECTID and geometry; retained parcel polygons fully within the authoritative Census Okaloosa county boundary using an in-memory spatial index; excluded polygons crossing or outside the county boundary; retained no folio, owner, mailing or address fields; scores remain unknown.",
        "limitations": ["This is a parcel geometry inventory, not a flood-risk dataset.",
                        "Retain County attribution and its as-is accuracy disclaimer."],
    }
    manifest_path = output.with_name(output.name.removesuffix(".geojsonl.gz") + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "feature_count": imported,
                      "excluded_count": excluded, "compressed_bytes": output.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
