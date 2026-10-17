"""WeatherNext 3 BigQuery importer. No cloud calls during dashboard requests.

Uses locally authenticated bq CLI; dry-run is the default. An explicit --execute
imports one run and one six-hour window for the curated Okaloosa demo points.
"""

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import COUNTY_FIPS
from ..bridge import BridgeUnavailable, read_snapshot

TABLE_PATTERN = r"[a-zA-Z0-9_-]+\.[a-zA-Z0-9_]+\.weathernext_3_0_0_0p1deg"
MAX_INIT_AGE = timedelta(hours=12)
MAX_DOWNLOAD_AGE = timedelta(hours=2)
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "properties.json"


def points() -> list[dict]:
    """Never accept user-supplied property coordinates through this import path."""
    return json.loads(FIXTURE_PATH.read_text())["properties"]


def timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Expected an ISO 8601 timestamp with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_window(init_time: str, valid_from: str):
    init, start = timestamp(init_time), timestamp(valid_from)
    if any(t.minute or t.second or t.microsecond for t in (init, start)):
        raise ValueError("Forecast initialization and window start must align to whole UTC hours")
    if start < init:
        raise ValueError("Forecast window cannot start before the selected initialization")
    return init, start


def query_sql(table: str) -> str:
    if not re.fullmatch(TABLE_PATTERN, table):
        raise ValueError("Use the fully qualified WeatherNext 3 0.1-degree precipitation table")
    return f"""-- WeatherNext 3: ensemble-mean hourly precipitation, native 0.1-degree grid.
WITH points AS (
  SELECT JSON_VALUE(p, '$.id') AS property_id,
    ST_GEOGPOINT(CAST(JSON_VALUE(p, '$.longitude') AS FLOAT64),
                 CAST(JSON_VALUE(p, '$.latitude') AS FLOAT64)) AS point
  FROM UNNEST(JSON_QUERY_ARRAY(@points_json)) AS p
)
SELECT p.property_id,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', f.time) AS forecast_time,
  f.total_precipitation_1hr_mean * 1000 AS rainfall_1h_mm,
  ST_ASTEXT(t.geography_polygon) AS native_cell_wkt
FROM `{table}` AS t
CROSS JOIN UNNEST(t.forecast) AS f
JOIN points AS p ON ST_COVERS(t.geography_polygon, p.point)
WHERE t.init_time = @init_time
  AND f.time > @window_start
  AND f.time <= TIMESTAMP_ADD(@window_start, INTERVAL 6 HOUR)
ORDER BY p.property_id, f.time
"""


def bq_command(project: str, table: str, location: str, init_time: str,
               valid_from: str, maximum_bytes: int, execute=False) -> list[str]:
    query_sql(table)
    init, start = validate_window(init_time, valid_from)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", project) or not re.fullmatch(r"[a-zA-Z0-9_-]+", location):
        raise ValueError("Invalid Google Cloud project ID or BigQuery location")
    if maximum_bytes <= 0:
        raise ValueError("maximum_bytes must be positive")
    coordinates = [{k: p[k] for k in ("id", "longitude", "latitude")} for p in points()]
    command = ["bq", f"--project_id={project}", f"--location={location}", "--format=json", "query",
               "--use_legacy_sql=false", "--max_rows=1000", f"--maximum_bytes_billed={maximum_bytes}",
               f"--parameter=init_time:TIMESTAMP:{iso(init)}",
               f"--parameter=window_start:TIMESTAMP:{iso(start)}",
               "--parameter=points_json:STRING:" + json.dumps(coordinates, separators=(",", ":"))]
    if not execute:
        command.append("--dry_run=true")
    return command


def snapshot(rows: list, *, table: str, init_time: str, valid_from: str, now=None) -> dict:
    """Normalize the CLI result and validate before saving; preserve raw hourly data."""
    init, start = validate_window(init_time, valid_from)
    result = {"schema_version": 1, "model": "WeatherNext 3", "county_fips": COUNTY_FIPS,
              "source_table": table, "native_resolution": "0.1 degree", "statistic": "ensemble_mean",
              "units": "mm_per_hour", "init_time": iso(init), "valid_from": iso(start),
              "valid_to": iso(start + timedelta(hours=6)),
              "retrieved_at": iso(now or datetime.now(timezone.utc)), "rows": rows}
    summarize(result, now=now)
    return result


def summarize(data: dict, *, now=None, allowed=None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("model") != "WeatherNext 3":
        raise ValueError("Unrecognized WeatherNext snapshot")
    expected = {"county_fips": COUNTY_FIPS, "native_resolution": "0.1 degree",
                "statistic": "ensemble_mean", "units": "mm_per_hour"}
    if any(data.get(k) != v for k, v in expected.items()):
        raise ValueError("Unexpected county, grid, statistic or rainfall units")
    query_sql(data.get("source_table", ""))
    init, start = validate_window(data.get("init_time"), data.get("valid_from"))
    end = start + timedelta(hours=6)
    if timestamp(data.get("valid_to")) != end:
        raise ValueError("Expected a six-hour forecast window")
    retrieved = timestamp(data.get("retrieved_at"))
    if init > now + timedelta(minutes=5) or retrieved > now + timedelta(minutes=5) or retrieved < init:
        raise ValueError("Invalid forecast initialization or retrieval time")
    expected_hours = {start + timedelta(hours=h) for h in range(1, 7)}
    county_mode = allowed is not None
    allowed = set(allowed) if county_mode else {p["id"] for p in points()}
    by_site = {identifier: {} for identifier in allowed}
    rows = data.get("rows")
    if not isinstance(rows, list) or len(rows) > (200000 if county_mode else 1000):
        raise ValueError("Invalid WeatherNext rows")
    for row in rows:
        if not isinstance(row, dict) or row.get("property_id") not in allowed:
            raise ValueError("WeatherNext row must reference a curated Okaloosa demo point")
        identifier = row["property_id"]
        hour = timestamp(row.get("forecast_time"))
        if hour not in expected_hours or hour in by_site[identifier]:
            raise ValueError("Duplicate or out-of-window forecast hour; do not double-count overlapping cells")
        rainfall = row.get("rainfall_1h_mm")
        if rainfall is not None:
            try:
                rainfall = float(rainfall) if not isinstance(rainfall, bool) else math.nan
            except (ValueError, TypeError) as exc:
                raise ValueError("Rainfall must be non-negative finite mm or null") from exc
            if not math.isfinite(rainfall) or rainfall < 0:
                raise ValueError("Rainfall must be non-negative finite mm or null")
        native_cell = row.get("native_cell_wkt")
        if not isinstance(native_cell, str) or not native_cell.startswith(("POLYGON", "MULTIPOLYGON")):
            raise ValueError("Original forecast grid geometry is required for provenance")
        by_site[identifier][hour] = (rainfall, native_cell)
    stale = now - init > MAX_INIT_AGE or now - retrieved > MAX_DOWNLOAD_AGE or end <= now
    records = {}
    for identifier, hours in by_site.items():
        complete = set(hours) == expected_hours and all(rain is not None for rain, _ in hours.values())
        status = "stale" if stale else "ready" if complete else "incomplete"
        total = sum(rain for rain, _ in hours.values()) if complete else None
        if total is not None and not math.isfinite(total):
            raise ValueError("Non-finite six-hour rainfall total")
        records[identifier] = {"status": status, "rainfall_6h_mm": round(total, 4) if complete and not stale else None,
                               "available_hours": sum(rain is not None for rain, _ in hours.values()),
                               "native_cells_wkt": sorted({cell for _, cell in hours.values()})}
    return {"status": "stale" if stale else "ready" if all(r["status"] == "ready" for r in records.values()) else "incomplete",
            **{k: data[k] for k in ("model", "source_table", "init_time", "retrieved_at", "valid_from", "valid_to", "native_resolution", "statistic")},
            "records": records}


def load_forecast(*, now=None) -> dict:
    try:
        data = read_snapshot("weathernext")
        if data is None:
            return {"status": "not_configured", "message": "Import a WeatherNext snapshot to connect forecasts."}
        if data.get("schema_version") == 3:
            from .county_weather import for_sites, collection
            result = summarize(for_sites(data), now=now)
            result["county_cells"] = collection(data, now=now)
            result["coverage"] = "County native forecast cells; site scores still use fictional inputs"
            return result
        return summarize(data, now=now)
    except BridgeUnavailable:
        return {"status": "unavailable", "message": "The configured WeatherNext data bridge is unavailable."}
    except (OSError, ValueError, TypeError, KeyError):
        return {"status": "invalid", "message": "WeatherNext snapshot is unavailable or invalid. Re-import before use."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Google Cloud project used to run/bill the query")
    parser.add_argument("--table", required=True, help="PROJECT.DATASET.weathernext_3_0_0_0p1deg")
    parser.add_argument("--location", required=True, help="Linked dataset location, for example US")
    parser.add_argument("--init-time", required=True, help="Exact available WeatherNext run, ISO 8601 UTC")
    parser.add_argument("--window-start", required=True, help="Six-hour window begins here, ISO 8601 UTC")
    parser.add_argument("--maximum-bytes-billed", type=int, default=1_000_000_000)
    parser.add_argument("--execute", action="store_true", help="Execute a billable query; otherwise dry-run only")
    parser.add_argument("--print-query", action="store_true", help="Print SQL without authentication or cloud calls")
    parser.add_argument("--output", type=Path, default=Path("data/processed/weathernext.json"))
    args = parser.parse_args()
    try:
        sql = query_sql(args.table)
        command = bq_command(args.project, args.table, args.location, args.init_time,
                             args.window_start, args.maximum_bytes_billed, args.execute)
        if args.print_query:
            print(sql)
            return
        result = subprocess.run(command, input=sql, text=True, capture_output=True, check=True, timeout=180)
        if not args.execute:
            print(result.stdout or result.stderr or "BigQuery dry-run completed. No snapshot written.")
            return
        data = snapshot(json.loads(result.stdout), table=args.table, init_time=args.init_time, valid_from=args.window_start)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # A failed import never replaces a previously usable snapshot.
        with tempfile.NamedTemporaryFile("w", dir=args.output.parent, delete=False) as output:
            json.dump(data, output, indent=2, allow_nan=False)
            temporary = Path(output.name)
        temporary.replace(args.output)
        print(f"WeatherNext snapshot written to {args.output}. Set QUASAR_WEATHERNEXT_FILE to this path.")
    except FileNotFoundError:
        parser.exit(1, "Install Google Cloud CLI with bq and authenticate your approved account locally.\n")
    except subprocess.CalledProcessError:
        parser.exit(1, "BigQuery query failed. Check account access, linked table schema, location and byte budget using bq.\n")
    except (ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Import failed: {exc}\n")


if __name__ == "__main__":
    main()
