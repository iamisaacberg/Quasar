"""Synthetic source-contract tests; no network, cloud queries or host access."""
import copy
import io
import json
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

import test_api
from test_county_weather import current, INIT, NOW
from quasar import data_dashboard, parcels
from quasar.adapters.weathernext import iso
from quasar.bridge import BridgeUnavailable


class DataWeatherTests(unittest.TestCase):
    def read(self, data=None, now=NOW):
        with patch.object(data_dashboard, 'read_snapshot', return_value=data if data is not None else current()) as read:
            result = data_dashboard.weather_data(now=now)
        read.assert_called_once_with('weathernext')
        return result

    def test_native_cells_only_with_retained_windows_and_provenance(self):
        with patch('quasar.pipeline.collection', side_effect=AssertionError('No fixture scoring')):
            result = self.read()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['frames']), 13)
        self.assertEqual(result['frames'][-1]['at'], iso(INIT + timedelta(hours=12)))
        self.assertEqual(result['source_table'], current()['source_table'])
        self.assertEqual(result['retrieved_at'], iso(NOW))
        for frame in result['frames']:
            self.assertEqual(frame['rows'], [{
                'native_cell_id': current()['native_cells'][0]['id'], 'status': 'ready',
                'rainfall_6h_mm': 12, 'available_hours': 6}])
        self.assertNotIn('demo-00', json.dumps(result))
        self.assertNotIn('score', json.dumps(result))

    def test_missing_null_and_zero_are_distinct(self):
        for change in ('missing', 'null', 'zero'):
            data = current()
            if change == 'missing': data['runs'][0]['rows'].pop(0)
            if change == 'null': data['runs'][0]['rows'][0]['rainfall_1h_mm'] = None
            if change == 'zero':
                for row in data['runs'][0]['rows']: row['rainfall_1h_mm'] = 0
            row = self.read(data)['frames'][0]['rows'][0]
            self.assertEqual(row['rainfall_6h_mm'], 0 if change == 'zero' else None)
            self.assertEqual(row['available_hours'], 6 if change == 'zero' else 5)

    def test_stale_original_snapshot_keeps_every_playback_frame_unknown(self):
        result = self.read(now=INIT + timedelta(hours=3))
        self.assertEqual(result['status'], 'stale')
        for frame in result['frames']:
            self.assertEqual(frame['rows'][0]['status'], 'stale')
            self.assertIsNone(frame['rows'][0]['rainfall_6h_mm'])

    def test_invalid_county_duplicates_and_negative_values_fail_closed(self):
        for change in ('county', 'duplicate', 'negative'):
            data = current()
            if change == 'county': data['county_fips'] = '12086'
            if change == 'duplicate': data['runs'][0]['rows'].append(copy.deepcopy(data['runs'][0]['rows'][0]))
            if change == 'negative': data['runs'][0]['rows'][0]['rainfall_1h_mm'] = -1
            result = self.read(data)
            self.assertEqual(result['status'], 'invalid')
            self.assertEqual(result['frames'], [])

    def test_missing_bridge_and_legacy_do_not_fall_back_to_fictional_sites(self):
        for value, expected in ((None, 'not_configured'), ({'schema_version': 1}, 'unavailable')):
            with patch.object(data_dashboard, 'read_snapshot', return_value=value):
                result = data_dashboard.weather_data(now=NOW)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['frames'], [])
        with patch.object(data_dashboard, 'read_snapshot', side_effect=BridgeUnavailable):
            self.assertEqual(data_dashboard.weather_data()['status'], 'unavailable')


class DataApiTests(test_api.ApiTests):
    def test_native_data_route_and_scope(self):
        with patch.object(data_dashboard, 'read_snapshot', return_value=current()):
            status, body, _ = self.request('/api/data/weather')
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['county_fips'], '12091')
        self.assertNotIn('demo-00', body.decode())
        self.assertEqual(self.request('/api/data/weather?county_fips=12086')[0], 400)
        self.assertEqual(self.request('/api/data/weather?county_fips=12091&county_fips=12091')[0], 400)


class ParcelCountTests(unittest.TestCase):
    def test_indexed_manifest_count_is_optional_and_validated(self):
        meta = {'source_provenance': {'output_sha256': 'parcels', 'county_boundary': {'sha256': 'county'},
                                    'source_url': 'https://example.test', 'retrieved_at': iso(NOW)},
                'cell_index_sha256': 'cells'}
        with patch.dict(os.environ, {'QUASAR_LINUXONE_API_URL': '', 'QUASAR_PARCEL_DATABASE': 'test'}):
            for value in (None, 0, 1234, -1, True, '1234'):
                with patch('quasar.parcel_context.inventory_metadata', return_value={**meta, 'parcel_count': value}):
                    if value is None or type(value) is int and value >= 0:
                        self.assertEqual(parcels.parcel_manifest()['parcel_count'], value)
                    else:
                        with self.assertRaises(parcels.SourceUnavailable): parcels.parcel_manifest()

    def test_remote_manifest_rejects_invalid_counts_but_supports_older_hosts(self):
        base = {'county_fips': '12091', 'status': 'ready', 'source_mode': 'indexed',
                'dataset_version': 'version', 'inventory_id': 'inventory', 'boundary_version': 'county',
                'source_url': 'https://example.test/parcels', 'crs': 'EPSG:4326'}
        with patch.dict(os.environ, {'QUASAR_LINUXONE_API_URL': 'https://example.test', 'QUASAR_LINUXONE_API_TOKEN': 'x' * 32}):
            for count in (None, 1234, -1, True):
                with patch.object(parcels, 'build_opener') as opener:
                    opener.return_value.open.return_value = io.BytesIO(json.dumps({**base, 'parcel_count': count}).encode())
                    if count is None or type(count) is int and count >= 0:
                        self.assertEqual(parcels.remote_inspection('/api/parcels/manifest')['parcel_count'], count)
                    else:
                        with self.assertRaises(parcels.SourceUnavailable): parcels.remote_inspection('/api/parcels/manifest')
