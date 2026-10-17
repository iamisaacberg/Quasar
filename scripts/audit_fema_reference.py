"""Compare local FEMA reference attributes with live public NFHL metadata.

This explicit research command performs public REST reads, never BigQuery.
It does not replace local geometry, establish a legal determination, or enable scores.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quasar.geometry_index import CountyBoundaryIndex

BASE = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
FIELDS = ["DFIRM_ID", "FLD_AR_ID", "STUDY_TYP", "FLD_ZONE", "ZONE_SUBTY", "SFHA_TF",
          "STATIC_BFE", "V_DATUM", "DEPTH", "LEN_UNIT", "SOURCE_CIT"]


def main():
    import fiona  # optional local GIS environment only
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse", type=Path, help="Replay a saved audit's checksum-verified raw responses without network access")
    args = parser.parse_args()
    retrieved = datetime.now(timezone.utc).isoformat()
    saved = json.loads(args.reuse.read_text()) if args.reuse else None
    if saved and saved.get("county_fips") != "12091":
        raise ValueError("Saved audit belongs to another county")
    saved_receipts = {Path(r["path"]).name: r for r in saved["receipts"]} if saved else {}
    output = ROOT / "data/raw/okaloosa/fema-live-audit" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not saved:
        output.mkdir(parents=True, exist_ok=False)
    receipts = []

    def get(layer, params, filename):
        url = f"{BASE}/{layer}/query?{urlencode(params)}"
        if saved:
            receipt = saved_receipts[filename]
            path = ROOT / receipt["path"]
            payload = path.read_bytes()
            if receipt["url"] != url or hashlib.sha256(payload).hexdigest() != receipt["sha256"]:
                raise ValueError("Saved audit request or checksum mismatch")
            receipts.append(receipt)
            return json.loads(payload)
        request = Request(url, headers={"User-Agent": "Quasar local flood-reference research"})
        with urlopen(request, timeout=45) as source:
            payload = source.read()
        data = json.loads(payload)
        if "error" in data or data.get("exceededTransferLimit"):
            raise ValueError("NFHL response failed or was truncated")
        path = output / filename
        path.write_bytes(payload)
        receipts.append({"path": str(path.relative_to(ROOT)), "url": url,
                         "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
                         "retrieved_at": datetime.now(timezone.utc).isoformat()})
        return data

    where = "DFIRM_ID='12091C'"
    inventory = get(28, {"f": "json", "where": where, "returnIdsOnly": "true"}, "zone-ids.json")
    ids = inventory.get("objectIds")
    if not isinstance(ids, list) or len(ids) != len(set(ids)) or not ids:
        raise ValueError("NFHL object-ID inventory is unavailable")
    attributes = []
    for offset in range(0, len(ids), 1000):
        page_ids = sorted(ids)[offset:offset+1000]
        page = get(28, {"f": "json", "objectIds": ",".join(map(str, page_ids)),
                        "outFields": "OBJECTID," + ",".join(FIELDS), "returnGeometry": "false"}, f"zones-{offset}.json")
        rows = [f["attributes"] for f in page["features"]]
        if {r["OBJECTID"] for r in rows} != set(page_ids) or len(rows) != len(page_ids):
            raise ValueError("NFHL attribute page incomplete")
        attributes.extend(rows)
    # Check that the ID inventory did not change during pagination.
    final_ids = get(28, {"f": "json", "where": where, "returnIdsOnly": "true"}, "zone-ids-final.json")
    if sorted(final_ids.get("objectIds", [])) != sorted(ids):
        raise ValueError("NFHL zone inventory changed during audit; retry")
    with fiona.open(f"zip://{ROOT / 'data/raw/fema_nfhl_okaloosa_12091c.zip'}!S_FLD_HAZ_AR.shp") as source:
        local = {f["properties"]["FLD_AR_ID"]: {k: f["properties"].get(k) for k in FIELDS} for f in source}
    remote = {r["FLD_AR_ID"]: {k: r.get(k) for k in FIELDS} for r in attributes}
    if len(remote) != len(attributes):
        raise ValueError("NFHL duplicated stable flood-area IDs")
    shared = set(local) & set(remote)
    def comparable(value):
        return value.strip() or None if isinstance(value, str) else value
    differences = []
    representation_differences = 0
    for key in sorted(shared):
        fields = [field for field in FIELDS if comparable(local[key][field]) != comparable(remote[key][field])]
        if fields:
            differences.append({"source_id": key, "fields": fields,
                                "values": {field: {"package": local[key][field], "live": remote[key][field]} for field in fields}})
        representation_differences += sum(local[key][field] != remote[key][field]
                                          and comparable(local[key][field]) == comparable(remote[key][field]) for field in FIELDS)
    boundary_path = ROOT / "data/raw/census_okaloosa_county.geojson"
    boundary = json.loads(boundary_path.read_text())["features"][0]
    if boundary["properties"]["GEOID"] != "12091":
        raise ValueError("Wrong county geometry")
    # The envelope only shortlists; the full authoritative county validates hits.
    geometry = boundary["geometry"]
    points = [p for ring in geometry["coordinates"] for p in ring] if geometry["type"] == "Polygon" else [p for poly in geometry["coordinates"] for ring in poly for p in ring]
    envelope = ",".join(str(v) for v in (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)))
    params = {"where": "1=1", "geometry": envelope, "geometryType": "esriGeometryEnvelope", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects"}
    count = get(1, {**params, "f": "json", "returnCountOnly": "true"}, "lomr-count.json")["count"]
    lomrs = get(1, {**params, "f": "geojson", "outSR": 4326, "returnGeometry": "true",
                    "outFields": "OBJECTID,DFIRM_ID,LOMR_ID,EFF_DATE,CASE_NO,STATUS,SOURCE_CIT"}, "lomr-candidates.geojson")
    if len(lomrs.get("features", [])) != count:
        raise ValueError("LOMR candidate response incomplete")
    county = CountyBoundaryIndex(geometry)
    intersecting = [f["properties"] for f in lomrs["features"] if county.intersects_parcel(f["geometry"])]
    for props in intersecting:
        if isinstance(props.get("EFF_DATE"), (int, float)):
            props["effective_at_utc"] = datetime.fromtimestamp(props["EFF_DATE"] / 1000, timezone.utc).isoformat()
    result = {"county_fips": "12091", "retrieved_at": saved["retrieved_at"] if saved else retrieved,
              "audit_prepared_at": datetime.now(timezone.utc).isoformat(), "source_url": BASE,
              "source_identifier": "public NFHL flood hazard zones layer 28 and LOMR layer 1",
              "license": "FEMA public reference mapping; retain source attribution and usage limitations.",
              "crs": "EPSG:4326 for LOMR geometry", "units": "Original FEMA units retained in attributes; no length transformations",
              "boundary_sha256": hashlib.sha256(boundary_path.read_bytes()).hexdigest(),
              "local_package_sha256": hashlib.sha256((ROOT / 'data/raw/fema_nfhl_okaloosa_12091c.zip').read_bytes()).hexdigest(),
              "local_zone_count": len(local), "live_zone_count": len(remote),
              "local_only_ids": sorted(set(local)-set(remote)), "live_only_ids": sorted(set(remote)-set(local)),
              "attribute_differences": differences,
              "blank_null_representation_differences": representation_differences,
              "comparison_normalization": "Trim text whitespace and treat empty strings and null as equivalent; raw responses preserved unchanged.",
              "compared_fields": FIELDS, "lomr_envelope_candidates": count,
              "county_intersecting_lomrs": intersecting,
              "processing": "Complete stable-ID inventory and bounded attribute pages; compare source IDs/fields; exact authoritative county geometry filters envelope LOMR candidates.",
              "limitations": ["Zone geometry itself was not compared. Equal counts/attributes do not prove identical polygons.",
                              "LOMA point amendments and every individual revision document were not reconciled.",
                              "This is a current-service audit, not proof of what was published on the replay date. No legal determination or score."],
              "receipts": receipts}
    target = ROOT / "data/processed/okaloosa/fema-reference-audit.json"
    temporary = target.with_suffix(".partial")
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    temporary.replace(target)
    print(json.dumps({k: v for k, v in result.items() if k not in ("receipts", "compared_fields")}, indent=2))


if __name__ == "__main__":
    main()
