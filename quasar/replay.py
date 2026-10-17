"""Hourly initialization-based historical replay. Never makes network calls."""
import json
import math
import os
from datetime import timedelta
from pathlib import Path

from .adapters.weathernext import iso, timestamp, points, query_sql, MAX_INIT_AGE
from .bridge import BridgeUnavailable, read_snapshot
from .config import COUNTY_FIPS
from .scoring import score

# October 9 in Central time: peak intensity and landfall day, not a local flood claim.
START = timestamp('2026-10-09T05:00:00Z')
END = timestamp('2026-10-10T05:00:00Z')
HOURS = int((END - START).total_seconds() // 3600)
PRESETS = {'archived': 0, 'plus-5': 5, 'plus-10': 10}
NOTICE = ('Isaias 2026 archive reconstruction with fictional site and gauge inputs. '
          'Unvalidated illustrative exposure, not flood probability, depth or official guidance.')


def selection(at=None, preset='archived', mode='archive'):
    if at is not None and not isinstance(at, str):
        raise ValueError("Replay time must be an ISO timestamp")
    if not isinstance(preset, str) or not isinstance(mode, str):
        raise ValueError("Replay preset and mode must be strings")
    at = timestamp(iso(START) if at is None else at)
    if at < START or at > END or at.minute or at.second or at.microsecond:
        raise ValueError('Replay time must be a whole UTC hour within the Isaias event')
    if preset not in PRESETS or mode not in ('archive', 'what_if'):
        raise ValueError('Unknown replay preset or mode')
    if preset != 'archived' and mode != 'what_if':
        raise ValueError('Synthetic rainfall presets require what_if mode')
    return {'at': iso(at), 'preset': preset, 'mode': mode, 'county_fips': COUNTY_FIPS}


def load_archive(path=None):
    if path is None:
        try:
            data = read_snapshot('isaias-2026')
        except BridgeUnavailable:
            return {'status': 'unavailable', 'message': 'Historical WeatherNext bridge is unavailable; rainfall remains unknown.', 'runs': []}
        if data is None:
            return {'status': 'not_imported', 'message': 'Historical WeatherNext rainfall has not been imported.', 'runs': []}
        try:
            if data.get('schema_version') == 3:
                from .adapters.county_weather import for_sites
                if data.get('kind') != 'historical_county_forecasts':
                    raise ValueError('Historical county archive required')
                return {'status':'loaded', **for_sites(data), '_county_data':data}
            validate_archive(data)
            return {'status': 'loaded', **data}
        except (ValueError, OSError, TypeError, KeyError, AttributeError):
            return {'status': 'invalid', 'message': 'Historical archive invalid; rainfall remains unknown.', 'runs': []}
    path = Path(path or os.environ.get('QUASAR_REPLAY_FILE', 'data/processed/isaias-2026.json'))
    if not path.exists():
        return {'status': 'not_imported', 'message': 'Historical WeatherNext rainfall has not been imported.', 'runs': []}
    try:
        if path.stat().st_size > 30_000_000:
            raise ValueError('Archive too large')
        data = json.loads(path.read_text())
        if data.get('schema_version') == 3:
            from .adapters.county_weather import for_sites
            if data.get('kind') != 'historical_county_forecasts':
                raise ValueError('Historical county archive required')
            return {'status':'loaded', **for_sites(data), '_county_data':data}
        validate_archive(data)
        return {'status': 'loaded', **data}
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        return {'status': 'invalid', 'message': 'Historical archive invalid; rainfall remains unknown.', 'runs': []}


def validate_archive(data, *, max_rows=10000):
    expected = {'schema_version': 2, 'kind': 'historical_forecasts', 'county_fips': COUNTY_FIPS,
                'model': 'WeatherNext 3', 'native_resolution': '0.1 degree',
                'units': 'mm_per_hour', 'statistic': 'ensemble_mean'}
    if not isinstance(data, dict) or any(data.get(k) != v for k, v in expected.items()):
        raise ValueError('Invalid historical forecast metadata')
    query_sql(data.get('source_table', ''))
    retrieved = timestamp(data.get('retrieved_at'))
    runs = data.get('runs')
    if not isinstance(runs, list) or len(runs) > 200:
        raise ValueError('Invalid archive runs')
    inits = set()
    for run in runs:
        init = timestamp(run.get('init_time'))
        if init.minute or init.second or init.microsecond or init in inits or init > retrieved:
            raise ValueError('Invalid or duplicate historical initialization')
        inits.add(init)
        if run.get('published_at') and not init <= timestamp(run['published_at']) <= retrieved:
            raise ValueError('Invalid historical publication time')
        if not isinstance(run.get('rows'), list) or len(run['rows']) > max_rows:
            raise ValueError('Invalid historical rows')
    return data


def run_rows(run, *, allowed=None):
    allowed = {p['id'] for p in points()} if allowed is None else allowed
    result = {}
    init = timestamp(run['init_time'])
    for row in run['rows']:
        site = row.get('property_id')
        hour = timestamp(row.get('forecast_time'))
        key = (site, iso(hour))
        rain = row.get('rainfall_1h_mm')
        if (site not in allowed or hour <= init or hour > init + timedelta(hours=360)
                or hour.minute or hour.second or hour.microsecond or key in result):
            raise ValueError('Duplicate or invalid historical forecast hour')
        if rain is not None and (isinstance(rain, bool) or not isinstance(rain, (int, float))
                                 or not math.isfinite(rain) or rain < 0):
            raise ValueError('Invalid historical rainfall')
        cell = row.get('native_cell_wkt')
        if not isinstance(cell, str) or not cell.startswith(('POLYGON', 'MULTIPOLYGON')):
            raise ValueError('Missing native forecast geometry')
        result[key] = row
    return result


def rainfall(archive, at, site, preset):
    clock = timestamp(at)
    eligible = [r for r in archive['runs'] if timestamp(r['init_time']) <= clock
                and (not r.get('published_at') or timestamp(r['published_at']) <= clock)]
    base = {'status': archive.get('status', 'not_imported'), 'rainfall_6h_mm': None,
            'available_hours': 0, 'native_cells_wkt': [], 'init_time': None,
            'reconstruction': 'initialization-based archive reconstruction',
            'native_resolution': '0.1 degree', 'units': 'mm', 'synthetic_increment_mm_per_hour': PRESETS[preset],
            'retrieved_at': archive.get('retrieved_at'), 'source_table': archive.get('source_table')}
    if not eligible:
        return {**base, 'status': 'unavailable'}
    run = max(eligible, key=lambda r: timestamp(r['init_time']))
    base.update(init_time=run['init_time'], published_at=run.get('published_at'))
    if run.get('published_at'):
        base['reconstruction'] = 'publication-time constrained archive reconstruction'
    if clock - timestamp(run['init_time']) > MAX_INIT_AGE:
        return {**base, 'status': 'stale_at_replay_time'}
    try:
        index = run_rows(run, allowed=archive.get('cell_ids'))
    except (ValueError, KeyError, TypeError, AttributeError):
        return {**base, 'status': 'invalid_run'}
    rows = [index.get((site, iso(clock+timedelta(hours=h)))) for h in range(1, 7)]
    valid = [r for r in rows if r and r['rainfall_1h_mm'] is not None]
    base['available_hours'] = len(valid)
    base['native_cells_wkt'] = sorted({r['native_cell_wkt'] for r in valid})
    if len(valid) != 6:
        return {**base, 'status': 'incomplete'}
    total = sum(r['rainfall_1h_mm'] + PRESETS[preset] for r in valid)
    if not math.isfinite(total):
        return {**base, 'status': 'invalid_run'}
    return {**base, 'status': 'ready', 'rainfall_6h_mm': round(total, 4)}


def risk_for(site, weather):
    risk = score({**site, 'rainfall_6h_mm': weather['rainfall_6h_mm'], 'gauge_margin_m': 1.2})
    if risk['score'] is not None:
        risk['data_status'] = 'mixed_demo'
    risk['factor_provenance'] = {
        'rainfall_6h_mm': {'source': 'WeatherNext 3 archive', 'status': weather['status'],
                          'synthetic_increment_mm_per_hour': weather['synthetic_increment_mm_per_hour']},
        **{key: {'source': 'fictional exercise input', 'synthetic': True}
           for key in ('elevation_m', 'fema_zone', 'waterway_distance_m', 'gauge_margin_m')}}
    return risk


def context(sel, archive):
    return {**sel, 'scenario': 'isaias-2026', 'source_status': archive['status'],
            'notice': NOTICE, 'source_table': archive.get('source_table'),
            'retrieved_at': archive.get('retrieved_at'), 'native_resolution': '0.1 degree',
            'reconstruction': 'initialization-based unless documented publication timing is present'}


def descriptor():
    archive = load_archive()
    return {'id': 'isaias-2026', 'label': 'Isaias 2026 · historical / what-if',
            'valid_from': iso(START), 'valid_to': iso(END), 'step_hours': 1,
            'county_fips': COUNTY_FIPS, 'display_timezone': 'America/Chicago',
            'modes': ['archive', 'what_if'],
            'hours': HOURS + 1, 'presets': [{'id': p, 'added_mm_per_hour': v} for p, v in PRESETS.items()],
            'source_status': archive['status'], 'advisory_status': advisory_context()['status']}


def collection(at=None, preset='archived', mode='archive'):
    sel = selection(at, preset, mode)
    archive = load_archive()
    weather_cells = None
    if archive.get('_county_data'):
        from .adapters.county_weather import collection as county_collection
        weather_cells = county_collection(archive['_county_data'], at=sel['at'], preset=preset, mode=mode)
    features = []
    for site in points():
        weather = rainfall(archive, sel['at'], site['id'], preset)
        features.append({'type': 'Feature', 'id': site['id'],
                         'geometry': {'type': 'Point', 'coordinates': [site['longitude'], site['latitude']]},
                         'properties': {'id': site['id'], 'label': site['label'], 'county_fips': COUNTY_FIPS,
                                        'risk': risk_for(site, weather), 'forecast': weather}})
    features.sort(key=lambda f: (f['properties']['risk']['score'] is None, -(f['properties']['risk']['score'] or 0)))
    return {'type': 'FeatureCollection', 'county_fips': COUNTY_FIPS, 'county_name': 'Okaloosa County',
            'mode': 'what_if_exercise' if mode == 'what_if' else 'historical_mixed_demo',
            'scenario': {'id': 'isaias-2026', 'valid_from': sel['at'],
                         'valid_to': iso(timestamp(sel['at'])+timedelta(hours=6))},
            'replay': context(sel, archive), 'notice': NOTICE,
            'provenance': 'Historical rainfall when available; all six sites and non-rainfall factors are fictional.',
            'forecast': None, 'weather_cells': weather_cells, 'features': features}


def timeline(site, at=None, preset='archived', mode='archive'):
    sel = selection(at, preset, mode)
    record = next((p for p in points() if p['id'] == site), None)
    if not record:
        raise ValueError('Unknown exercise site')
    archive = load_archive()
    rows, previous = [], None
    for h in range(HOURS + 1):
        hour = iso(START+timedelta(hours=h))
        weather = rainfall(archive, hour, site, preset)
        risk = risk_for(record, weather)
        value = risk['score']
        rows.append({'at': hour, 'risk': risk, 'forecast': weather,
                     'change': round(value-previous, 1) if value is not None and previous is not None else None})
        previous = value
    return {**context(sel, archive), 'site': site, 'points': rows,
            'label': 'Illustrative exposure for the next six hours'}


def advisory_context():
    try:
        data = read_snapshot('isaias-advisories')
        if data is None:
            raise FileNotFoundError
        if not isinstance(data.get('advisories'), list):
            raise ValueError('Invalid advisory metadata')
        return {'status': 'loaded', **data}
    except BridgeUnavailable:
        return {'status': 'unavailable', 'advisories': [],
                'source_url': 'https://www.nhc.noaa.gov/archive/2026/ISAIAS.shtml'}
    except (OSError, ValueError, AttributeError):
        return {'status': 'not_imported', 'advisories': [],
                'source_url': 'https://www.nhc.noaa.gov/archive/2026/ISAIAS.shtml'}
