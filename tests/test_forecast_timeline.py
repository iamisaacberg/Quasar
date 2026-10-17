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
            result = timeline(now=now)
        self.assertEqual(read.call_count, 1)
        return result

    def test_18_hours_produce_13_forward_six_hour_frames_with_provenance(self):
        result = self.frames()
        self.assertEqual(len(result['frames']), 13)
        self.assertEqual(result['frames'][0]['at'], iso(INIT))
        self.assertEqual(result['frames'][-1]['at'], iso(INIT+timedelta(hours=12)))
        for frame in result['frames']:
            data = frame['collection']
            self.assertEqual(data['mode'], 'mixed_forecast_demo')
            self.assertEqual(data['weather_cells']['features'][0]['properties']['rainfall_6h_mm'], 12)
            self.assertEqual(data['forecast']['init_time'], iso(INIT))
            self.assertEqual(data['forecast']['retrieved_at'], iso(NOW))
            self.assertEqual(data['forecast']['native_resolution'], '0.1 degree')
            self.assertEqual(data['scenario']['valid_from'], frame['at'])
            missing = next(f for f in data['features'] if f['properties']['risk']['missing'])
            self.assertIsNone(missing['properties']['risk']['score'])

    def test_default_frame_matches_existing_properties_without_changing_default_window(self):
        data = current()
        result = self.frames(data)
        with patch('quasar.adapters.weathernext.read_snapshot', return_value=data):
            forecast = load_forecast(now=NOW)
        with patch('quasar.pipeline.load_forecast', return_value=forecast):
            original = collection('weathernext')
        self.assertEqual(result['frames'][result['default_index']]['collection'], original)

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

    def test_legacy_six_hour_import_remains_a_single_frame(self):
        from test_weathernext import example, NOW as legacy_now
        with patch('quasar.forecast_timeline.read_snapshot', return_value=example()):
            result = timeline(now=legacy_now)
        self.assertEqual(len(result['frames']), 1)
        self.assertEqual(result['status'], 'ready')
        self.assertIsNone(result['frames'][0]['collection']['weather_cells'])
