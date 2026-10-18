"""County native-cell forecasts. Cloud imports are explicit; runtime reads snapshots only."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import COUNTY_FIPS
from ..geometry import covers, polygons, position
from .weathernext import iso, timestamp, query_sql, points, summarize

MAX_ROWS = 200_000
MONTHLY_CEILING = 1_000_000_000_000  # Deliberately below the 1 TiB Sandbox allowance.


def execution_budget(used, cap):
    if (type(used) is not int or type(cap) is not int or used < 0 or cap <= 0
            or used + cap > MONTHLY_CEILING):
        raise ValueError('Refreshed monthly usage plus the query cap must stay within 1,000,000,000,000 bytes')
    return MONTHLY_CEILING-used-cap


def replay_initializations():
    # Eighteen-hour runs cover six-hour windows for clocks up to init + 12h.
    # Stop once the final replay endpoint is covered, avoiding a second UTC day.
    from ..replay import START, END
    init=START.replace(hour=START.hour//6*6)
    result=[]
    while True:
        result.append(iso(init))
        if init + timedelta(hours=12) >= END:
            return result
        init += timedelta(hours=6)


def query(table):
    query_sql(table)  # Use the same strict allowlist for table identifiers.
    return f'''SELECT FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', t.init_time) AS init_time,
  ST_ASTEXT(t.geography_polygon) AS native_cell_wkt,
  ST_ASGEOJSON(t.geography_polygon) AS native_cell_geojson,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', f.time) AS forecast_time,
  f.total_precipitation_1hr_mean * 1000 AS rainfall_1h_mm
FROM `{table}` AS t CROSS JOIN UNNEST(t.forecast) AS f
WHERE t.init_time IN UNNEST(@init_times)
  AND ST_INTERSECTS(t.geography_polygon, ST_GEOGFROMGEOJSON(@county_geojson))
  AND f.time > t.init_time AND f.time <= TIMESTAMP_ADD(t.init_time, INTERVAL 18 HOUR)
ORDER BY t.init_time, native_cell_wkt, f.time'''


def boundary(path):
    data = json.loads(Path(path).read_text())
    if len(data.get('features', [])) != 1 or data['features'][0]['properties'].get('GEOID') != COUNTY_FIPS:
        raise ValueError('An authoritative Census Okaloosa boundary is required')
    return data['features'][0]['geometry']


def normalize(rows, table, geometry, *, historical=False, valid_from=None, now=None):
    if not isinstance(rows, list) or not rows or len(rows) >= MAX_ROWS:
        raise ValueError('Empty or possibly truncated county query result')
    cells, runs = {}, {}
    for raw in rows:
        wkt = raw['native_cell_wkt']
        cell_id = hashlib.sha256(wkt.encode()).hexdigest()
        geom = json.loads(raw['native_cell_geojson'])
        cell = {'id': cell_id, 'geometry': geom, 'native_cell_wkt': wkt}
        if cell_id in cells and cells[cell_id] != cell:
            raise ValueError('Native cell geometry changed between forecast runs')
        cells[cell_id] = cell
        rain = raw['rainfall_1h_mm']
        if isinstance(rain, bool):
            raise ValueError('Boolean rainfall is invalid')
        runs.setdefault(raw['init_time'], []).append({'property_id': cell_id, 'forecast_time': raw['forecast_time'],
            'rainfall_1h_mm': float(rain) if rain is not None else None, 'native_cell_wkt': wkt})
    result = {'schema_version': 3, 'kind': 'historical_county_forecasts' if historical else 'current_county_forecasts',
              'county_fips': COUNTY_FIPS, 'model': 'WeatherNext 3', 'source_table': table,
              'native_resolution': '0.1 degree', 'statistic': 'ensemble_mean', 'units': 'mm_per_hour',
              'retrieved_at': iso(now or datetime.now(timezone.utc)), 'county_geometry': geometry,
              'native_cells': list(cells.values()), 'runs': [{'init_time': k, 'rows': v} for k,v in sorted(runs.items())],
              'license': 'Historical: CC BY 4.0; current/future: Google GDM experimental real-time terms. Retain source attribution.',
              'publication_timing': 'Unknown; initialization-based reconstruction only',
              'archive_policy': 'Selected runs only; omitted later initializations are not evidence that no later forecast existed. Final six-hour window must fit the selected run horizon and 12-hour replay age.',
              'processing': 'Exact initialization filters; native-cell/county intersection; hourly ensemble mean meters multiplied by 1000 once. No H3 resampling.'}
    if historical:
        from ..replay import START, END
        result.update(replay_start=iso(START), replay_end=iso(END))
    else:
        if len(runs) != 1 or valid_from is None:
            raise ValueError('Current forecast requires one initialization and a window start')
        result.update(init_time=next(iter(runs)), valid_from=iso(timestamp(valid_from)),
                      valid_to=iso(timestamp(valid_from)+timedelta(hours=6)))
    validate(result)
    return result


def validate(data, *, now=None):
    from ..replay import validate_archive, run_rows
    expected = {'schema_version': 3, 'county_fips': COUNTY_FIPS, 'model': 'WeatherNext 3',
                'native_resolution': '0.1 degree', 'statistic': 'ensemble_mean', 'units': 'mm_per_hour'}
    if not isinstance(data, dict) or any(data.get(k) != v for k,v in expected.items()):
        raise ValueError('Invalid county weather metadata')
    if data.get('kind') not in ('current_county_forecasts', 'historical_county_forecasts'):
        raise ValueError('Invalid county forecast kind')
    query_sql(data.get('source_table', ''))
    cells = data.get('native_cells')
    if not isinstance(cells, list) or not 1 <= len(cells) <= 2000:
        raise ValueError('Invalid native cell inventory')
    ids = set()
    wkts = {c['id']:c['native_cell_wkt'] for c in cells}
    for cell in cells:
        wkt, geom = cell['native_cell_wkt'], cell['geometry']
        if cell['id'] in ids or hashlib.sha256(wkt.encode()).hexdigest() != cell['id']:
            raise ValueError('Duplicate or invalid native cell ID')
        parts = polygons(geom)
        if not wkt.startswith(('POLYGON', 'MULTIPOLYGON')) or not parts or any(
            not poly or any(len(ring)<4 or ring[0]!=ring[-1] or not all(position(p) for p in ring) for ring in poly) for poly in parts):
            raise ValueError('Invalid native polygon')
        ids.add(cell['id'])
    legacy = {**data, 'schema_version': 2, 'kind': 'historical_forecasts'}
    validate_archive(legacy, max_rows=MAX_ROWS)
    for run in data['runs']:
        run_rows(run, allowed=ids)
        if any(row['native_cell_wkt'] != wkts[row['property_id']] for row in run['rows']):
            raise ValueError('Row geometry mismatches native cell')
    if not data['runs']:
        raise ValueError('County archive has no runs')
    if data['kind'] == 'current_county_forecasts':
        current = current_snapshot(data)
        summarize(current, allowed=ids, now=now)
    return data


def current_snapshot(data):
    if len(data['runs']) != 1 or data['runs'][0]['init_time'] != data['init_time']:
        raise ValueError('Current forecast initialization mismatch')
    start = timestamp(data['valid_from'])
    rows = [r for r in data['runs'][0]['rows'] if start < timestamp(r['forecast_time']) <= start+timedelta(hours=6)]
    return {**data, 'schema_version':1, 'rows': rows}


def for_sites(data, *, now=None):
    """Associate fictional sites locally with native polygons; never query per parcel."""
    validate(data, now=now)
    associations = {}
    for site in points():
        hits = [c for c in data['native_cells'] if covers([site['longitude'],site['latitude']], c['geometry'])]
        if len(hits) > 1:
            raise ValueError('Exercise site ambiguously overlaps native forecast cells')
        if hits:
            associations.setdefault(hits[0]['id'], []).append(site['id'])
    def rows(items):
        return [{**r, 'property_id':site} for r in items for site in associations.get(r['property_id'], [])]
    if data['kind'] == 'current_county_forecasts':
        base = current_snapshot(data)
        return {**base, 'rows':rows(base['rows'])}
    return {**data, 'schema_version':2, 'kind':'historical_forecasts',
            'runs':[{**run,'rows':rows(run['rows'])} for run in data['runs']]}


def collection(data, *, at=None, preset='archived', mode='archive', now=None):
    return PreparedForecast(data, now=now).collection(at=at, preset=preset, mode=mode)


class PreparedForecast:
    """Request-local validated snapshot; index archive rows once for all frames."""

    def __init__(self, data, *, now=None):
        from ..replay import run_rows
        validate(data, now=now)
        self.data, self.now = data, now
        self.ids = {c['id'] for c in data['native_cells']}
        self.indexes = {run['init_time']: run_rows(run, allowed=self.ids) for run in data['runs']}

    def collection(self, *, at=None, preset='archived', mode='archive', window=None):
        return _collection(window or self.data, at=at, preset=preset, mode=mode,
                           now=self.now, ids=self.ids, indexes=self.indexes)


def _collection(data, *, at, preset, mode, now, ids, indexes):
    from ..replay import rainfall, selection
    if data['kind'] == 'historical_county_forecasts':
        sel = selection(at, preset, mode)
        archive = {**data,'status':'loaded','cell_ids':ids}
        records = {identifier:rainfall(archive,sel['at'],identifier,preset,indexes=indexes) for identifier in ids}
        start = sel['at']
    else:
        summary = summarize(current_snapshot(data), allowed=ids, now=now)
        records, start = summary['records'], data['valid_from']
    return {'type':'FeatureCollection','county_fips':COUNTY_FIPS,'native_resolution':'0.1 degree',
            'source_table':data['source_table'],'retrieved_at':data['retrieved_at'], 'valid_from':start,
            'valid_to':iso(timestamp(start)+timedelta(hours=6)), 'units':'mm / 6h',
            'coverage':'Native forecast cells intersecting the authoritative county; cells may extend beyond the boundary.',
            'notice':'Forecast rainfall, not observed rain, flood depth, probability or parcel risk.',
            'features':[{'type':'Feature','id':c['id'],'geometry':c['geometry'],
                         'properties':{'native_cell_id':c['id'],**records[c['id']]}} for c in data['native_cells']]}


def main():
    from .historical import write_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True); parser.add_argument('--table',required=True)
    parser.add_argument('--location',default='US')
    parser.add_argument('--boundary',type=Path,default=Path('data/raw/census_okaloosa_county.geojson'))
    parser.add_argument('--historical',action='store_true'); parser.add_argument('--init-time');parser.add_argument('--window-start')
    parser.add_argument('--maximum-bytes-billed',type=int,default=1_000_000_000)
    parser.add_argument('--verified-month-bytes',type=int)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--print-query',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    sql=query(args.table)
    if args.print_query: print(sql);return
    geom=boundary(args.boundary)
    if args.historical:
        from ..replay import START,END
        inits=replay_initializations()
    else:
        if not args.init_time or not args.window_start: parser.error('Current imports require --init-time and --window-start')
        inits=[iso(timestamp(args.init_time))]
    if args.maximum_bytes_billed<=0:parser.error('Byte cap must be positive')
    if args.execute:
        from .query_budget import audit
        report=audit(args.project,args.location)
        write_json(Path('data/processed/okaloosa/weathernext-budget.json'),report)
        used=max(report['bytes_reserved_or_billed'],args.verified_month_bytes or 0)
        try: execution_budget(used,args.maximum_bytes_billed)
        except ValueError as exc: parser.error(str(exc))
    cmd=['bq',f'--project_id={args.project}',f'--location={args.location}','--format=json','query',
         '--use_legacy_sql=false',f'--max_rows={MAX_ROWS}',f'--maximum_bytes_billed={args.maximum_bytes_billed}',
         '--parameter=init_times:ARRAY<TIMESTAMP>:'+json.dumps(inits),
         '--parameter=county_geojson:STRING:'+json.dumps(geom,separators=(',',':'))]
    if not args.execute:cmd.append('--dry_run=true')
    if args.execute:
        dry=subprocess.run(cmd+['--dry_run=true'],input=sql,text=True,capture_output=True,check=True,timeout=120)
        estimate=int(json.loads(dry.stdout)['statistics']['totalBytesProcessed'])
        write_json(Path('data/processed/okaloosa/weathernext-dryrun.json'),json.loads(dry.stdout))
        if estimate>args.maximum_bytes_billed:
            parser.error('Fresh dry-run estimate exceeds this query cap; no query executed')
    job_id=None
    if args.execute:
        job_id='quasar_okaloosa_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        cmd.append('--job_id='+job_id)
    result=subprocess.run(cmd,input=sql,text=True,capture_output=True,check=True,timeout=600)
    if not args.execute:print(result.stdout or result.stderr);return
    raw=Path('data/raw/weathernext/okaloosa-historical-rows.json' if args.historical else 'data/raw/weathernext/okaloosa-current-rows.json')
    rows=json.loads(result.stdout)
    write_json(raw,rows)  # Keep completed query results even if normalization fails.
    data=normalize(rows,args.table,geom,historical=args.historical,valid_from=args.window_start)
    data['job_id']=job_id
    data['source_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
    data['county_boundary_sha256']=hashlib.sha256(args.boundary.read_bytes()).hexdigest()
    output=args.output or Path('data/processed/isaias-2026.json' if args.historical else 'data/processed/weathernext.json')
    write_json(output,data)
    from .query_budget import audit
    write_json(Path('data/processed/okaloosa/weathernext-budget.json'),audit(args.project,args.location))
    print(f'Wrote {output}: {len(data["native_cells"])} native cells, {len(data["runs"])} runs.')


if __name__=='__main__':
    try:
        main()
    except FileNotFoundError:
        raise SystemExit('bq CLI is unavailable. Run in authenticated Google Cloud Shell; no forecast was imported.')
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
        raise SystemExit('BigQuery operation failed. Check job history and retrieve any completed job results before retrying; prior snapshots are preserved on query failure.')
    except (ValueError,TypeError,KeyError,OSError) as exc:
        raise SystemExit(f'County import failed: {exc}')
