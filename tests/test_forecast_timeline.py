"""Synthetic retained-hour snapshots only; no WeatherNext queries."""
import copy
import unittest
from datetime import timedelta
from unittest.mock import patch

from test_county_weather import current, INIT, NOW
from quasar.forecast_timeline import timeline
from quasar.adapters.weathernext import iso, load_forecast
from quasar.pipeline import collection
from quasar.bridge import BridgeUnavailable


class ForecastTimelineTests(unittest.TestCase):
    def frames(self, data=None, now=NOW):
        with patch('quasar.forecast_timeline.read_snapshot', return_value=current() if data is None else data) as read:
            result = timeline(source="current", now=now)
        self.assertEqual(read.call_count, 1)
        return result

    def test_18_hours_produce_13_forward_six_hour_frames_with_provenance(self):
        result = self.frames()
        self.assertEqual(len(result['frames']), 13)
        self.assertEqual(result['frames'][0]['at'], iso(INIT))
        self.assertEqual(result['frames'][-1]['at'], iso(INIT+timedelta(hours=12)))
        for frame in result['frames']:
            data = frame['collection']
            self.assertEqual(data['mode'], 'county_forecast')
            self.assertEqual(data['weather_cells']['features'][0]['properties']['rainfall_6h_mm'], 12)
            self.assertEqual(data['forecast']['init_time'], iso(INIT))
            self.assertEqual(data['forecast']['retrieved_at'], iso(NOW))
            self.assertEqual(data['forecast']['native_resolution'], '0.1 degree')
            self.assertEqual(data['scenario']['valid_from'], frame['at'])
            self.assertEqual(data['features'], [])
            self.assertNotIn('demo-00', str(data))

    def test_hourly_windows_roll_once_and_shorter_horizons_are_derived(self):
        data = current()
        for i, row in enumerate(data['runs'][0]['rows'], 1):
            row['rainfall_1h_mm'] = i
        data['runs'][0]['rows'] = data['runs'][0]['rows'][:9]
        frames = self.frames(data)['frames']
        self.assertEqual(len(frames), 4)
        self.assertEqual([f['collection']['weather_cells']['features'][0]['properties']['rainfall_6h_mm'] for f in frames], [21,27,33,39])

    def test_null_missing_zero_and_expired_snapshots_never_become_low_rainfall(self):
        for missing in (None, 'absent'):
            data = current()
            if missing is None:
                data['runs'][0]['rows'][1]['rainfall_1h_mm'] = None
            else:
                data['runs'][0]['rows'].pop(1)
            frames = self.frames(data)['frames']
            first = frames[0]['collection']['weather_cells']['features'][0]['properties']
            self.assertEqual(first['status'], 'incomplete')
            self.assertIsNone(first['rainfall_6h_mm'])
            self.assertEqual(frames[-1]['collection']['weather_cells']['features'][0]['properties']['rainfall_6h_mm'],12)
        data = current()
        for row in data['runs'][0]['rows']:
            row['rainfall_1h_mm'] = 0
        self.assertEqual(self.frames(data)['frames'][0]['collection']['weather_cells']['features'][0]['properties']['rainfall_6h_mm'],0)
        # Test each global expiry independently, including original-window expiry.
        for age, retrieval_age in ((3,3),(7,0),(13,0)):
            data = current()
            now = INIT+timedelta(hours=age)
            data['retrieved_at'] = iso(now-timedelta(hours=retrieval_age))
            result = self.frames(data, now)
            self.assertEqual(result['status'],'stale')
            for frame in result['frames']:
                self.assertEqual(frame['collection']['forecast']['status'],'stale')
                self.assertTrue(all(f['properties']['risk']['score'] is None for f in frame['collection']['features']))
                self.assertIsNone(frame['collection']['weather_cells']['features'][0]['properties']['rainfall_6h_mm'])

    def test_duplicate_and_invalid_rows_fail_the_entire_timeline(self):
        for change in ('duplicate','negative','county'):
            data = current()
            if change=='duplicate':data['runs'][0]['rows'].append(copy.deepcopy(data['runs'][0]['rows'][-1]))
            if change=='negative':data['runs'][0]['rows'][-1]['rainfall_1h_mm']=-1
            if change=='county':data['county_fips']='12086'
            result = self.frames(data)
            self.assertEqual(result['status'],'invalid')
            self.assertEqual(result['frames'],[])

    def test_missing_and_bridge_failure_states_are_explicit(self):
        with patch('quasar.forecast_timeline.read_snapshot',return_value=None):
            self.assertEqual(timeline(now=NOW)['status'],'not_configured')
        with patch('quasar.forecast_timeline.read_snapshot',side_effect=BridgeUnavailable):
            self.assertEqual(timeline(now=NOW)['status'],'unavailable')

    def test_legacy_six_hour_import_is_unavailable_without_fixture_fallback(self):
        from test_weathernext import example, NOW as legacy_now
        with patch('quasar.forecast_timeline.read_snapshot', return_value=example()):
            result = timeline(now=legacy_now)
        self.assertEqual(result['frames'], [])
        self.assertEqual(result['status'], 'unavailable')

    def test_archive_uses_native_cells_and_cannot_call_fixture_scoring(self):
        from test_county_weather import rows, TABLE, GEOMETRY
        from quasar.adapters.county_weather import normalize
        from quasar.replay import START
        data = normalize(rows(START.replace(hour=0)), TABLE, GEOMETRY, historical=True, now=NOW)
        with patch('quasar.forecast_timeline.read_snapshot', return_value=data), patch('quasar.pipeline.collection', side_effect=AssertionError('Fixture pipeline forbidden')):
            result = timeline(source='archive', now=NOW)
        self.assertEqual(len(result['frames']), 25)
        self.assertEqual(result['frames'][0]['collection']['mode'], 'county_archive')
        first = result['frames'][0]['collection']['weather_cells']['features'][0]
        self.assertEqual(first['properties']['rainfall_6h_mm'], 12)
        self.assertNotIn('synthetic_increment_mm_per_hour', first['properties'])
        self.assertNotIn('demo-00', str(result))
        self.assertNotIn('expires_at', result)

    def test_source_rejects_what_if_and_wrong_snapshot_kind(self):
        with self.assertRaises(ValueError):
            timeline(source='what_if')
        with patch('quasar.forecast_timeline.read_snapshot', return_value=current()):
            self.assertEqual(timeline(source='archive', now=NOW)['status'], 'invalid')

class ArchivePlaybackTests(unittest.TestCase):
    def archive(self):
        from test_county_weather import rows, TABLE, GEOMETRY
        from quasar.adapters.county_weather import normalize, replay_initializations
        from quasar.adapters.weathernext import timestamp
        raw = []
        for init in replay_initializations():
            for i in range(5):
                for row in rows(timestamp(init)):
                    # Synthetic distinct native IDs only, not a real spatial inventory.
                    row['native_cell_wkt'] = row['native_cell_wkt'].replace('-87 30', f'{-87+i/1000} 30')
                    raw.append(row)
        return normalize(raw, TABLE, GEOMETRY, historical=True, now=NOW)

    def test_default_archive_indexes_once_per_run_not_per_cell_and_frame(self):
        from quasar import replay
        data = self.archive()
        with patch.object(replay, 'run_rows', wraps=replay.run_rows) as index:
            result = timeline(reader=lambda name: data if name == 'isaias-2026' else None)
        self.assertEqual(result['source'], 'archive')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['frames']), 25)
        self.assertLessEqual(index.call_count, len(data['runs']) * 2)
        for frame in result['frames']:
            self.assertEqual(len(frame['collection']['weather_cells']['features']), 5)
            for feature in frame['collection']['weather_cells']['features']:
                self.assertEqual(feature['properties']['rainfall_6h_mm'], 12)

    def test_archive_publication_null_and_duplicate_constraints_survive_indexing(self):
        data = self.archive()
        # At 06 UTC the newer run is not yet published, so select 00 UTC.
        data['runs'][1]['published_at'] = '2026-10-09T07:00:00Z'
        result = timeline(reader=lambda _: data)
        self.assertEqual(result['frames'][1]['collection']['forecast']['init_time'], '2026-10-09T00:00:00Z')
        self.assertEqual(result['frames'][2]['collection']['forecast']['init_time'], '2026-10-09T06:00:00Z')
        data['runs'][0]['rows'][5]['rainfall_1h_mm'] = None
        result = timeline(reader=lambda _: data)
        first = result['frames'][0]['collection']['weather_cells']['features'][0]['properties']
        self.assertEqual(first['status'], 'incomplete')
        self.assertIsNone(first['rainfall_6h_mm'])
        data['runs'][-1]['rows'].append(copy.deepcopy(data['runs'][-1]['rows'][0]))
        self.assertEqual(timeline(reader=lambda _: data)['status'], 'invalid')

    def test_data_report_and_export_use_the_same_archive_window_and_initialization(self):
        import csv, io, json, zipfile
        from quasar.data_dashboard import weather_data
        from quasar.source_exports import report, export
        data = self.archive()
        with patch('quasar.data_dashboard.read_snapshot', return_value=data):
            table = weather_data()
        with patch('quasar.forecast_timeline.read_snapshot', return_value=data):
            selected = report(frame=24)
            body, _, _ = export(frame=24, format='zip')
        self.assertEqual(len(selected['windows']), 25)
        self.assertEqual(table['frames'][24]['at'], selected['rows'][0]['valid_from'])
        self.assertEqual(table['frames'][24]['rows'][0]['init_time'], selected['rows'][0]['init_time'])
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            rows = list(csv.DictReader(io.StringIO(archive.read('rainfall.csv').decode())))
            self.assertEqual(rows[0]['init_time'], selected['init_time'])
            self.assertEqual(rows[0]['valid_from'], selected['windows'][24]['at'])
            self.assertEqual(json.loads(archive.read('provenance.json'))['source'], 'archive')
