"""Explicit, capped WeatherNext historical import; dry-run unless --execute.

python3 -m quasar.adapters.historical --project PROJECT --table TABLE --location US
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .weathernext import bq_command, iso, query_sql
from ..config import COUNTY_FIPS
from ..replay import START, END, validate_archive, run_rows


def historical_sql(table):
    sql = query_sql(table)
    sql = sql.replace("SELECT p.property_id,", "SELECT FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', t.init_time) AS init_time, p.property_id,")
    sql = sql.replace('t.init_time = @init_time',
                      't.init_time BETWEEN @init_start AND @window_end\n  AND MOD(EXTRACT(HOUR FROM t.init_time), 6) = 0')
    sql = sql.replace('f.time > @window_start', 'f.time > t.init_time')
    sql = sql.replace('TIMESTAMP_ADD(@window_start, INTERVAL 6 HOUR)', 'TIMESTAMP_ADD(t.init_time, INTERVAL 18 HOUR)')
    return sql.replace('ORDER BY p.property_id, f.time', 'ORDER BY t.init_time, p.property_id, f.time')


def historical_command(project, table, location, maximum_bytes, execute=False):
    cmd = bq_command(project, table, location, iso(START), iso(START), maximum_bytes, execute)
    cmd = [c for c in cmd if not c.startswith(('--parameter=init_time:', '--parameter=window_start:', '--max_rows='))]
    init_start = START.replace(hour=(START.hour // 6) * 6)
    return cmd + ['--max_rows=100000', '--parameter=window_end:TIMESTAMP:' + iso(END),
                  '--parameter=init_start:TIMESTAMP:' + iso(init_start)]


def normalize(rows, table, now=None):
    if not isinstance(rows, list) or len(rows) > 100000:
        raise ValueError('Invalid historical query result')
    runs = {}
    for raw in rows:
        row = dict(raw)
        init = row.pop('init_time')
        if row.get('rainfall_1h_mm') is not None:
            if isinstance(row['rainfall_1h_mm'], bool):
                raise ValueError('Invalid rainfall')
            row['rainfall_1h_mm'] = float(row['rainfall_1h_mm'])
        runs.setdefault(init, []).append(row)
    data = {'schema_version': 2, 'kind': 'historical_forecasts', 'county_fips': COUNTY_FIPS,
            'model': 'WeatherNext 3', 'source_table': table, 'native_resolution': '0.1 degree',
            'statistic': 'ensemble_mean', 'units': 'mm_per_hour',
            'retrieved_at': iso(now or datetime.now(timezone.utc)),
            'license': 'CC BY 4.0 (Google WeatherNext historical data); retain attribution',
            'publication_timing': 'Unknown; initialization-based reconstruction only',
            'replay_start': iso(START), 'replay_end': iso(END),
            'runs': [{'init_time': k, 'rows': v} for k, v in sorted(runs.items())]}
    validate_archive(data)
    for run in data['runs']:
        run_rows(run)
    return data


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        tmp = Path(handle.name)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--table', required=True)
    parser.add_argument('--location', required=True)
    parser.add_argument('--maximum-bytes-billed', type=int, default=1_000_000_000)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--print-query', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('data/processed/isaias-2026.json'))
    args = parser.parse_args()
    try:
        sql = historical_sql(args.table)
        cmd = historical_command(args.project, args.table, args.location, args.maximum_bytes_billed, args.execute)
        if args.print_query:
            print(sql)
            return
        result = subprocess.run(cmd, input=sql, text=True, capture_output=True, check=True, timeout=180)
        if not args.execute:
            print(result.stdout or result.stderr or 'Dry-run completed; no snapshot written.')
            return
        data = normalize(json.loads(result.stdout), args.table)
        if not data['runs']:
            raise ValueError('No historical runs returned; previous archive preserved')
        raw = Path('data/raw/weathernext/isaias-2026-rows.json')
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(result.stdout)
        data['source_sha256'] = hashlib.sha256(raw.read_bytes()).hexdigest()
        data['processing'] = 'Six curated points; native-cell ST_COVERS; six-hourly initializations; hourly mean meters multiplied by 1000 exactly once. Missing hours preserved.'
        write_json(args.output, data)
        print(f'Historical snapshot: {args.output}; {len(data["runs"])} runs. Publication timing unverified.')
    except FileNotFoundError:
        parser.exit(1, 'Google Cloud bq CLI unavailable. Run this importer in authenticated Cloud Shell or install/authenticate bq locally. No historical query ran.\n')
    except subprocess.CalledProcessError:
        parser.exit(1, 'Historical query failed; check access, byte cap, location and schema. Existing archive preserved.\n')
    except (ValueError, TypeError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f'Historical import failed: {exc}\n')


if __name__ == '__main__':
    main()
