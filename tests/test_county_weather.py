"""Synthetic county cells only; these tests make no cloud requests."""
import copy
import json
import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from quasar.adapters import county_weather as cw
from quasar.adapters.weathernext import iso,summarize
from quasar import replay
from quasar.config import require_county,COUNTY_FIPS,TIMEZONE

TABLE='test-project.test.weathernext_3_0_0_0p1deg'
GEOMETRY={'type':'Polygon','coordinates':[[[-87,30],[-86,30],[-86,32],[-87,32],[-87,30]]]}
WKT='POLYGON((-87 30,-86 30,-86 32,-87 32,-87 30))'
INIT=datetime(2026,10,17,20,tzinfo=timezone.utc)
NOW=INIT+timedelta(minutes=30)


def rows(init=INIT):
    return [{'init_time':iso(init),'native_cell_wkt':WKT,'native_cell_geojson':json.dumps(GEOMETRY),
             'forecast_time':iso(init+timedelta(hours=h)), 'rainfall_1h_mm':2} for h in range(1,19)]


def current():
    return cw.normalize(rows(),TABLE,GEOMETRY,valid_from=iso(INIT),now=NOW)


class CountyWeatherTests(unittest.TestCase):
    def test_okaloosa_identity_and_central_replay_clock(self):
        self.assertEqual((COUNTY_FIPS,TIMEZONE),('12091','America/Chicago'))
        self.assertEqual(iso(replay.START),'2026-10-09T05:00:00Z')
        self.assertEqual(iso(replay.END),'2026-10-10T05:00:00Z')
        with self.assertRaises(ValueError):require_county('12086')

    def test_four_initializations_cover_the_entire_central_day_without_second_day_scan(self):
        inits=[cw.timestamp(x) for x in cw.replay_initializations()]
        self.assertEqual(len(inits),4)
        self.assertTrue(all(x.date()==replay.START.date() for x in inits))
        for hour in range(25):
            at=replay.START+timedelta(hours=hour)
            selected=max(x for x in inits if x<=at)
            self.assertLessEqual(at-selected,timedelta(hours=12))
            self.assertLessEqual(at+timedelta(hours=6),selected+timedelta(hours=18))

    def test_query_returns_native_cells_once_without_property_join(self):
        sql=cw.query(TABLE)
        self.assertIn('IN UNNEST(@init_times)',sql)
        self.assertIn('ST_INTERSECTS',sql)
        self.assertEqual(sql.count('* 1000'),1)
        self.assertNotIn('points_json',sql)
        with self.assertRaises(ValueError):cw.query('unsafe.table')

    def test_county_current_projects_sites_locally_and_preserves_native_geometry(self):
        d=current();legacy=cw.for_sites(d)
        self.assertEqual(len(legacy['rows']),36)
        self.assertEqual(summarize(legacy,now=NOW)['records']['demo-001']['rainfall_6h_mm'],12)
        fc=cw.collection(d,now=NOW)
        self.assertEqual(fc['features'][0]['geometry'],GEOMETRY)
        self.assertEqual(fc['features'][0]['properties']['rainfall_6h_mm'],12)

    def test_null_missing_zero_and_stale_cell_states(self):
        d=current();d['runs'][0]['rows'][0]['rainfall_1h_mm']=None
        self.assertIsNone(cw.collection(d,now=NOW)['features'][0]['properties']['rainfall_6h_mm'])
        d=current();d['runs'][0]['rows'].pop(0)
        self.assertEqual(cw.collection(d,now=NOW)['features'][0]['properties']['status'],'incomplete')
        d=current()
        for row in d['runs'][0]['rows']:row['rainfall_1h_mm']=0
        self.assertEqual(cw.collection(d,now=NOW)['features'][0]['properties']['rainfall_6h_mm'],0)
        self.assertIsNone(cw.collection(d,now=INIT+timedelta(hours=3))['features'][0]['properties']['rainfall_6h_mm'])

    def test_invalid_and_duplicate_native_rows_rejected(self):
        for change in ('duplicate','negative','bool','wrongcounty','wrongcell'):
            d=current()
            if change=='duplicate':d['runs'][0]['rows'].append(copy.deepcopy(d['runs'][0]['rows'][0]))
            if change=='negative':d['runs'][0]['rows'][0]['rainfall_1h_mm']=-1
            if change=='bool':d['runs'][0]['rows'][0]['rainfall_1h_mm']=True
            if change=='wrongcounty':d['county_fips']='12086'
            if change=='wrongcell':d['runs'][0]['rows'][0]['native_cell_wkt']='POLYGON((0 0,1 0,1 1,0 0))'
            with self.subTest(change=change),self.assertRaises(ValueError):cw.validate(d)

    def test_historical_cells_use_replay_clock_and_presets(self):
        init=replay.START.replace(hour=0)
        d=cw.normalize(rows(init),TABLE,GEOMETRY,historical=True,now=NOW)
        base=cw.collection(d,at=iso(replay.START))['features'][0]['properties']
        self.assertEqual(base['rainfall_6h_mm'],12)
        increased=cw.collection(d,at=iso(replay.START),preset='plus-5',mode='what_if')
        self.assertEqual(increased['features'][0]['properties']['rainfall_6h_mm'],42)
        self.assertEqual(cw.for_sites(d)['schema_version'],2)

    def test_runtime_loader_projects_county_archive(self):
        d=cw.normalize(rows(replay.START.replace(hour=0)),TABLE,GEOMETRY,historical=True,now=NOW)
        with patch('quasar.replay.read_snapshot',return_value=d):
            loaded=replay.load_archive()
            self.assertEqual(loaded['status'],'loaded')
            self.assertEqual(loaded['runs'][0]['rows'][0]['property_id'],'demo-001')
            self.assertEqual(len(replay.collection()['weather_cells']['features']),1)

    def test_budget_rejects_unknown_negative_or_excessive_usage(self):
        self.assertGreater(cw.execution_budget(401511284736,384000000000),0)
        for used,cap in [(None,1),(True,1),(-1,1),(0,0),(900000000000,200000000000)]:
            with self.subTest(used=used,cap=cap),self.assertRaises(ValueError):cw.execution_budget(used,cap)

    def test_empty_or_truncated_result_does_not_create_snapshot(self):
        with self.assertRaises(ValueError):cw.normalize([],TABLE,GEOMETRY,valid_from=iso(INIT))


class IndexedBoundaryTests(unittest.TestCase):
    def test_enclosed_county_holes_and_concavity_are_not_county_containment(self):
        from quasar.geometry_index import CountyBoundaryIndex
        outer=[[0,0],[4,0],[4,4],[0,4],[0,0]]
        hole=[[1,1],[2,1],[2,2],[1,2],[1,1]]
        index=CountyBoundaryIndex({'type':'Polygon','coordinates':[outer,hole]})
        parcel={'type':'Polygon','coordinates':[[[.5,.5],[3,.5],[3,3],[.5,3],[.5,.5]]]}
        self.assertFalse(index.covers_parcel(parcel))
        self.assertFalse(index._line_inside([[.5,1.5],[3,1.5]]))
        self.assertTrue(index._line_inside([[.1,.1],[.5,.5]]))
