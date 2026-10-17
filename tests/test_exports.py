import csv
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from quasar.analysis import report
from quasar.exports import SITE_FIELDS, csv_bytes, export
from quasar.pipeline import collection


class ExportTests(unittest.TestCase):
    def test_report_and_exports_match_application_scores(self):
        for scenario in ("baseline", "heavy-rain", "peak"):
            with self.subTest(scenario=scenario):
                expected = {f['id']: f['properties']['risk']['score'] for f in collection(scenario)['features']}
                data = report(scenario)
                self.assertEqual({r['property_id']: r['score'] for r in data['rows']}, expected)
                payload, mime, filename = export(scenario, 'geojson')
                geo = json.loads(payload)
                self.assertEqual(mime, 'application/geo+json')
                self.assertEqual(filename, f'quasar-{scenario}.geojson')
                self.assertEqual({f['properties']['property_id']: f['properties']['score'] for f in geo['features']}, expected)
                self.assertTrue(all(f['geometry']['type'] == 'Point' and len(f['geometry']['coordinates']) == 2 for f in geo['features']))

    def test_compare_bundle_grain_contents_and_nulls(self):
        body, mime, filename = export('compare', 'zip')
        self.assertEqual(mime, 'application/zip')
        self.assertEqual(filename, 'quasar-compare.zip')
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            self.assertEqual(set(bundle.namelist()), {'sites.csv', 'factors.csv', 'sites.geojson', 'metadata.json', 'README.txt'})
            rows = list(csv.DictReader(io.StringIO(bundle.read('sites.csv').decode())))
            factors = list(csv.DictReader(io.StringIO(bundle.read('factors.csv').decode())))
            metadata = json.loads(bundle.read('metadata.json'))
            geo = json.loads(bundle.read('sites.geojson'))
            self.assertEqual(len(rows), 18)
            self.assertEqual(len({(r['property_id'], r['scenario']) for r in rows}), 18)
            unknown = [r for r in rows if r['property_id'] == 'demo-006']
            self.assertEqual(len(unknown), 3)
            self.assertTrue(all(r['score'] == '' and r['band'] == 'unknown' and r['missing'] == 'elevation_m' for r in unknown))
            self.assertTrue(all(f['properties']['score'] is None for f in geo['features'] if f['properties']['property_id'] == 'demo-006'))
            self.assertEqual(len({f['id'] for f in geo['features']}), 18)
            self.assertEqual(len(factors), 75)
            self.assertFalse(any(r['property_id'] == 'demo-006' for r in factors))
            self.assertEqual(metadata['row_count'], 18)
            self.assertEqual(len(metadata['scenarios']), 3)
            self.assertTrue(set(SITE_FIELDS).issubset(metadata['fields']))
            self.assertEqual({r['generated_at'] for r in rows + factors}, {metadata['generated_at']})
            for row in rows:
                actual = sum(float(f['contribution']) for f in factors if (f['property_id'], f['scenario']) == (row['property_id'], row['scenario']))
                if row['score']:
                    self.assertAlmostEqual(actual, float(row['score']), delta=0.051)

    def test_all_unknown_remains_null_not_zero(self):
        data = collection('baseline')
        for feature in data['features']:
            feature['properties']['risk'].update(score=None, band='unknown', factors=[], missing=['elevation_m'])
        with patch('quasar.analysis.collection', return_value=data):
            result = report()
            self.assertIsNone(result['summary']['mean_score'])
            self.assertEqual(result['summary']['unknown_count'], 6)
            body, _, _ = export(file_format='csv')
            self.assertTrue(all(row['score'] == '' for row in csv.DictReader(io.StringIO(body.decode()))))

    def test_csv_quotes_text_and_preserves_numeric_null_and_negatives(self):
        payload = csv_bytes([{'label': 'Comma, quote " and\nnewline', 'score': None, 'longitude': -86.4},
                             {'label': '=HYPERLINK("example")', 'score': 0, 'longitude': -86.5}],
                            ('label', 'score', 'longitude'))
        rows = list(csv.DictReader(io.StringIO(payload.decode())))
        self.assertEqual(rows[0]['label'], 'Comma, quote " and\nnewline')
        self.assertEqual(rows[0]['score'], '')
        self.assertEqual(rows[0]['longitude'], '-86.4')
        self.assertEqual(rows[1]['score'], '0')
        self.assertTrue(rows[1]['label'].startswith("'="))

    def test_invalid_requests_fail(self):
        for scenario, fmt in [('invalid', 'csv'), ('baseline', 'xlsx'), ('', 'zip')]:
            with self.subTest(scenario=scenario, fmt=fmt), self.assertRaises(ValueError):
                export(scenario, fmt)

    def test_mixed_stale_and_incomplete_preserve_forecast_provenance(self):
        for status in ('stale', 'incomplete'):
            data = collection('baseline')
            data.update(mode='mixed_forecast_demo', forecast={
                'status': status, 'source_table': 'project.dataset.table',
                'init_time': '2026-10-17T12:00:00Z', 'retrieved_at': '2026-10-17T12:15:00Z',
                'native_resolution': '0.1 degree', 'statistic': 'ensemble_mean'})
            data['scenario']['id'] = 'weathernext'
            for feature in data['features']:
                feature['properties']['forecast'] = {'status': status, 'rainfall_6h_mm': None, 'available_hours': 5}
                feature['properties']['risk'].update(score=None, band='unknown', factors=[], missing=['rainfall_6h_mm'])
            with self.subTest(status=status), patch('quasar.analysis.collection', return_value=data):
                body, _, _ = export('weathernext', 'zip')
                with zipfile.ZipFile(io.BytesIO(body)) as bundle:
                    rows = list(csv.DictReader(io.StringIO(bundle.read('sites.csv').decode())))
                    self.assertTrue(all(r['forecast_status'] == status and r['rainfall_6h_mm'] == '' and r['score'] == '' for r in rows))
                    self.assertTrue(all(r['source_table'] == 'project.dataset.table' and r['native_resolution'] == '0.1 degree' for r in rows))
                    self.assertEqual(json.loads(bundle.read('metadata.json'))['forecast'], data['forecast'])
