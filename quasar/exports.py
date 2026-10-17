"""Offline BI serialization of shared report snapshots; standard library only."""

import csv
import io
import json
import zipfile

from .analysis import report

SITE_FIELDS = (
    "property_id", "scenario", "label", "county_fips", "longitude", "latitude",
    "rainfall_6h_mm", "score", "band", "missing", "data_status", "mode", "model_version",
    "valid_from", "valid_to", "generated_at", "forecast_status", "available_hours",
    "source_table", "init_time", "retrieved_at", "native_resolution", "statistic",
    "notice", "provenance",
)
FACTOR_FIELDS = (
    "property_id", "scenario", "name", "value", "weight", "contribution",
    "county_fips", "mode", "data_status", "model_version", "valid_from", "valid_to",
    "generated_at", "forecast_status", "source_table", "init_time", "retrieved_at",
    "native_resolution", "statistic", "notice", "provenance",
)
FIELDS = {
    "property_id": "Stable fictional site identifier; text. Join factors on property_id AND scenario.",
    "scenario": "Exercise window ID or weathernext. Distinct windows are not distinct sites.",
    "label": "Fictional display label; not an owner or address.",
    "county_fips": "Text county identifier, fixed to 12086. Curated fictional points only.",
    "longitude": "WGS84 longitude, decimal degrees (EPSG:4326).",
    "latitude": "WGS84 latitude, decimal degrees (EPSG:4326).",
    "rainfall_6h_mm": "Total rainfall in mm over valid_from to valid_to; null if unavailable/stale.",
    "score": "Unvalidated relative heuristic, 0–100. Null means unknown, never zero or safe.",
    "band": "lower_relative, moderate, elevated, or unknown. No depth/probability meaning.",
    "missing": "Required missing input names; JSON array in JSON, semicolon-separated in CSV.",
    "data_status": "synthetic, mixed_demo, or incomplete (risk input status).",
    "mode": "synthetic_demo or mixed_forecast_demo; site inputs remain fictional in both.",
    "model_version": "Identifier of the unchanged illustrative scoring heuristic.",
    "valid_from": "Inclusive window start, ISO 8601 UTC; exercise time is fictional.",
    "valid_to": "Window end, ISO 8601 UTC. Six-hour accumulation ends here.",
    "generated_at": "Report/export generation time, ISO 8601 UTC; not observation time.",
    "forecast_status": "ready, incomplete, stale, or not_applicable for synthetic exercise rows.",
    "available_hours": "Number of complete hourly forecast inputs, of six; null for synthetic rows.",
    "source_table": "WeatherNext BigQuery source identifier; null for synthetic rows.",
    "init_time": "Forecast initialization in UTC; null for synthetic rows.",
    "retrieved_at": "Forecast retrieval/import time in UTC; null for synthetic rows.",
    "native_resolution": "Original WeatherNext grid resolution; assignment to sites does not refine it.",
    "statistic": "Forecast statistic (ensemble_mean); null for synthetic rows.",
    "notice": "Required demonstration limitations and official-guidance notice.",
    "provenance": "Fictional site source description; not evidence of real parcel coverage.",
    "name": "Input name: rainfall_6h_mm, elevation_m, fema_zone, waterway_distance_m, gauge_margin_m.",
    "value": "Original input: mm for rainfall, m for elevation/distance/gauge margin, code for FEMA zone. Terrain datum and gauge linkage are fictional.",
    "weight": "Illustrative factor weight, fraction of 1; not a trained coefficient.",
    "contribution": "Weighted relative score points; rounded contributions sum to rounded score within rounding tolerance.",
}
IMPORT_GUIDE = """Quasar — synthetic / mixed demonstration BI bundle

1. Power BI: Get data > Text/CSV > sites.csv. Tableau: connect to sites.csv.
   Set property_id, scenario and county_fips to Text. Set score/rainfall and
   coordinates to decimal numbers. Preserve empty numeric cells as null.
2. Load factors.csv separately. Join/relate on BOTH property_id and scenario.
   It contains available contributions for scored sites only. Unknown scores
   have no factor rows; use a relationship/left join to retain unknown sites.
   Never sum site scores or counts after a one-to-many factor join.
3. Tableau can connect to sites.geojson as a spatial file. Geometry is WGS84
   [longitude, latitude]. Compare contains repeated points, one per window;
   filter scenario before mapping or count distinct property_id.
4. Start with the compare bundle: 6 fictional sites x 3 windows = 18 rows.
   Power BI: compare windows and completeness. Tableau: spatial patterns and
   unknowns. Neither analysis validates a flood model or countywide coverage.
5. Use mode, forecast_status, data_status and missing alongside numeric values.
   A blank score is unknown. Do not fill blanks with 0 or interpolate gaps.
   Synthetic dates are a fictional clock. Mixed mode has actual imported
   forecast rainfall plus invented site/FEMA/terrain/gauge inputs. It may be stale.
6. Rainfall is mm / 6h, aggregated once from six hourly ensemble means.
   Forecast initialization, import time, validity and native grid are separate.
   Forecast assignment and H3 do not increase native weather resolution.
7. metadata.json documents units, field meanings and source metadata. No source
   license is implied for future real datasets. This bundle has only curated
   fictional sites and explicitly imported rainfall; no real owners/opt-ins.
8. Refresh manually by downloading and replacing all bundle files together.
   Generation time does not refresh forecast data. No workbook queries Google.

Unvalidated illustrative heuristic, not trained AI, flood depth, probability,
evacuation advice or a guarantee of safety. Follow official NWS/local guidance.
The NWS feed is not connected; this is not an all-clear. No messages are sent.
"""


def csv_bytes(rows, fields):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        values = {key: ";".join(value) if isinstance(value, list) else value
                  for key, value in row.items() if key in fields}
        # Keep text inert when opened in spreadsheet software. Numeric negatives
        # remain numbers; quoting alone does not prevent formula interpretation.
        values = {key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
                  else value for key, value in values.items()}
        writer.writerow(values)
    return buffer.getvalue().encode("utf-8")


def geojson(data):
    return {"type": "FeatureCollection", "county_fips": data["county_fips"],
            "mode": data["mode"], "generated_at": data["generated_at"],
            "notice": data["notice"], "provenance": data["provenance"],
            "forecast": data["forecast"],
            "features": [{"type": "Feature", "id": f'{row["property_id"]}:{row["scenario"]}',
                          "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
                          "properties": {key: row[key] for key in SITE_FIELDS}} for row in data["rows"]]}


def json_bytes(data):
    return json.dumps(data, indent=2, allow_nan=False).encode("utf-8")


def export(scenario_id="baseline", file_format="csv"):
    """Return bytes, MIME type and fixed safe filename from one report snapshot."""
    if file_format not in ("csv", "geojson", "zip"):
        raise ValueError("Export format must be csv, geojson, or zip")
    data = report(scenario_id)
    filename = f"quasar-{scenario_id}.{file_format}"
    if file_format == "csv":
        return csv_bytes(data["rows"], SITE_FIELDS), "text/csv; charset=utf-8", filename
    if file_format == "geojson":
        return json_bytes(geojson(data)), "application/geo+json", filename
    factors = [{**{key: row[key] for key in FACTOR_FIELDS if key in row}, **factor}
               for row in data["rows"] for factor in row["factors"]]
    metadata = {"schema_version": 1, "county_fips": data["county_fips"],
                "mode": data["mode"], "generated_at": data["generated_at"],
                "notice": data["notice"], "provenance": data["provenance"],
                "forecast": data["forecast"], "scenarios": data.get("scenarios") or [
                    {"scenario": data["scenario"], "summary": data["summary"]}],
                "crs": "EPSG:4326", "display_timezone": "America/New_York",
                "row_count": len(data["rows"]), "site_fields": list(SITE_FIELDS),
                "factor_fields": list(FACTOR_FIELDS), "fields": FIELDS,
                "null_policy": "Empty numeric CSV cells and JSON null are unknown/not applicable; consult status fields.",
                "source_terms": "Hand-authored fictional fixtures. Forecast source, if present, is identified above; confirm redistribution terms before publication.",
                "processing": "Existing Quasar pipeline scoring, flattened by shared analysis; no cloud query, resampling or additional scoring."}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, body in (("sites.csv", csv_bytes(data["rows"], SITE_FIELDS)),
                           ("factors.csv", csv_bytes(factors, FACTOR_FIELDS)),
                           ("sites.geojson", json_bytes(geojson(data))),
                           ("metadata.json", json_bytes(metadata)),
                           ("README.txt", IMPORT_GUIDE.encode("utf-8"))):
            bundle.writestr(name, body)
    return buffer.getvalue(), "application/zip", filename
