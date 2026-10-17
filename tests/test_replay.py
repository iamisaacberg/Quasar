"""Synthetic unit fixtures only; no archive access or historical observations."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import timedelta
from http.client import HTTPConnection
from unittest.mock import patch

from quasar import replay, routing
from quasar.adapters.historical import historical_command, historical_sql, normalize
from quasar.adapters.weathernext import iso, points
from quasar.geometry import covers, line_covered
from quasar.server import make_server

TABLE = 'quasar-ibm-z-datathon.weathernext_3.weathernext_3_0_0_0p1deg'
CELL = 'POLYGON((-87 30,-86 30,-86 32,-87 32,-87 30))'


def archive():
    rows = [{'init_time':iso(replay.START), 'property_id':p['id'],
             'forecast_time':iso(replay.START+timedelta(hours=h)),
             'rainfall_1h_mm':float(h), 'native_cell_wkt':CELL} for p in points() for h in range(1,19)]
    return normalize(rows,TABLE)


def graph():
    nodes = {p['id']:[p['longitude'],p['latitude']] for p in points()}
    nodes.update(hub=[-86.5,30.55], north=[-86.51,30.55], detour=[-86.505,30.56], west=[-86.54,30.55], south=[-86.52,30.51])
    edges = [{'id':'access-'+p['id'],'from':p['id'],'to':'hub','coordinates':[nodes[p['id']],nodes['hub']],
              'label':'Synthetic test access','kind':'simulated_access'} for p in points()]
    for a,b,key in [('hub','north','direct'),('hub','detour','alternate-a'),('detour','north','alternate-b'),('north','west','west-road'),('west','south','south-road')]:
        edges.append({'id':key,'from':a,'to':b,'coordinates':[nodes[a],nodes[b]],'label':key,'kind':'road'})
    return {'schema_version':1,'county_fips':'12091','nodes':nodes,'edges':edges,
            'county_geometry':{'type':'Polygon','coordinates':[[[-87,30],[-86,30],[-86,32],[-87,32],[-87,30]]]},
            'sites':{p['id']:p['id'] for p in points()},'destinations':[{'id':n,'node':n,'label':n} for n in ('north','west','south')],
            'provenance':{'source':'synthetic test geometry, not actual roads'}}


class ReplayTests(unittest.TestCase):
    def test_forward_window_uses_exact_hours_and_preserves_native_grid(self):
        r=replay.rainfall(archive(),iso(replay.START),'demo-001','archived')
        self.assertEqual(r['rainfall_6h_mm'],21)
        self.assertEqual(r['available_hours'],6)
        self.assertEqual(r['native_cells_wkt'],[CELL])
        self.assertIn('initialization-based',r['reconstruction'])
        self.assertEqual(replay.rainfall(archive(),iso(replay.START+timedelta(hours=1)),'demo-001','archived')['rainfall_6h_mm'],27)

    def test_latest_run_and_publication_cutoff(self):
        d=archive();new=copy.deepcopy(d['runs'][0]);new['init_time']=iso(replay.START+timedelta(hours=1))
        new['rows']=[r for r in new['rows'] if r['forecast_time']>new['init_time']]
        for r in new['rows']:r['rainfall_1h_mm']=20
        new['published_at']=iso(replay.START+timedelta(hours=2));d['runs'].append(new)
        at=iso(replay.START+timedelta(hours=1))
        self.assertEqual(replay.rainfall(d,at,'demo-001','archived')['rainfall_6h_mm'],27)
        at=iso(replay.START+timedelta(hours=2))
        self.assertEqual(replay.rainfall(d,at,'demo-001','archived')['rainfall_6h_mm'],120)

    def test_missing_null_duplicate_and_invalid_rows_never_zero_fill(self):
        for change in ('missing','null','duplicate','negative','bool','wrong_site','no_cell'):
            d=archive();rows=d['runs'][0]['rows']
            if change=='missing':rows.pop(0)
            elif change=='null':rows[0]['rainfall_1h_mm']=None
            elif change=='duplicate':rows.append(dict(rows[0]))
            elif change=='negative':rows[0]['rainfall_1h_mm']=-1
            elif change=='bool':rows[0]['rainfall_1h_mm']=True
            elif change=='wrong_site':rows[0]['property_id']='real-parcel'
            else:rows[0]['native_cell_wkt']=None
            with self.subTest(change=change):
                self.assertIsNone(replay.rainfall(d,iso(replay.START),'demo-001','plus-10')['rainfall_6h_mm'])

    def test_invalid_latest_run_does_not_fall_back(self):
        d=archive();new=copy.deepcopy(d['runs'][0]);new['init_time']=iso(replay.START+timedelta(hours=1));d['runs'].append(new)
        self.assertEqual(replay.rainfall(d,iso(replay.START+timedelta(hours=1)),'demo-001','archived')['status'],'invalid_run')

    def test_age_uses_replay_clock_and_presets_only_add_to_complete_inputs(self):
        d=archive()
        self.assertEqual(replay.rainfall(d,iso(replay.START),'demo-001','plus-5')['rainfall_6h_mm'],51)
        self.assertEqual(replay.rainfall(d,iso(replay.START),'demo-001','plus-10')['rainfall_6h_mm'],81)
        self.assertEqual(replay.rainfall(d,iso(replay.START+timedelta(hours=13)),'demo-001','archived')['status'],'stale_at_replay_time')

    def test_timeline_null_gaps_delta_and_factor_provenance(self):
        with patch('quasar.replay.load_archive',return_value={'status':'loaded',**archive()}):
            t=replay.timeline('demo-001')
            self.assertEqual(len(t['points']),25)
            self.assertIsNone(t['points'][0]['change'])
            self.assertGreater(t['points'][1]['change'],0)
            self.assertIsNone(t['points'][13]['change'])
            self.assertTrue(t['points'][0]['risk']['factor_provenance']['elevation_m']['synthetic'])
            self.assertIsNone(replay.timeline('demo-006')['points'][0]['risk']['score'])
            self.assertEqual(replay.collection()['mode'],'historical_mixed_demo')

    def test_unavailable_archive_and_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'archive.json'
            self.assertEqual(replay.load_archive(p)['status'],'not_imported')
            d=archive();d['units']='inches';p.write_text(json.dumps(d))
            self.assertEqual(replay.load_archive(p)['status'],'invalid')
        for values in [{'at':''},{'at':'2026-10-07T00:30:00Z'},{'at':'2026-10-12T00:00:00Z'},{'preset':'plus-5'},{'mode':'live'},{'preset':[]},{'at':False}]:
            with self.subTest(values=values),self.assertRaises(ValueError):replay.selection(**values)

    def test_importer_partition_filter_caps_no_double_conversion_and_dry_run(self):
        sql=historical_sql(TABLE)
        self.assertIn('t.init_time BETWEEN',sql);self.assertIn('INTERVAL 18 HOUR',sql)
        self.assertEqual(sql.count('* 1000'),1)
        cmd=historical_command('quasar-ibm-z-datathon',TABLE,'US',1000)
        self.assertEqual(replay.END-replay.START,timedelta(hours=24))
        self.assertIn('--parameter=init_start:TIMESTAMP:2026-10-09T00:00:00Z',cmd)
        self.assertIn('--parameter=window_end:TIMESTAMP:2026-10-10T05:00:00Z',cmd)
        self.assertIn('MOD(EXTRACT(HOUR FROM t.init_time), 6) = 0',sql)
        self.assertIn('--dry_run=true',cmd);self.assertIn('--maximum_bytes_billed=1000',cmd)
        self.assertNotIn('--dry_run=true',historical_command('quasar-ibm-z-datathon',TABLE,'US',1000,True))
        with self.assertRaises(ValueError):historical_sql('invalid.table')
        with self.assertRaises(ValueError):historical_command('bad project',TABLE,'US',1000)

    def test_no_cloud_calls_in_replay_requests(self):
        with patch('subprocess.run',side_effect=AssertionError('cloud subprocess')),patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            replay.collection();replay.timeline('demo-001')


class GeometryTests(unittest.TestCase):
    def test_hole_and_concavity_crossings_rejected_even_with_inside_endpoints(self):
        outer=[[0,0],[4,0],[4,4],[0,4],[0,0]]
        hole=[[1,1],[2,1],[2,2],[1,2],[1,1]]
        geom={'type':'Polygon','coordinates':[outer,hole]}
        self.assertTrue(covers([.5,1.5],geom));self.assertTrue(covers([3,1.5],geom))
        self.assertFalse(line_covered([[.5,1.5],[3,1.5]],geom))
        concave={'type':'Polygon','coordinates':[[[0,0],[4,0],[4,4],[3,4],[3,1],[1,1],[1,4],[0,4],[0,0]]]}
        self.assertFalse(line_covered([[.5,3],[3.5,3]],concave))
        self.assertTrue(line_covered([[0,0],[4,0]],geom))


class RoutingTests(unittest.TestCase):
    def test_full_graph_county_validation(self):
        d=graph();routing.validate_graph(d)
        d['edges'][0]['coordinates'].insert(1,[-82,30.2])
        with self.assertRaises(ValueError):routing.validate_graph(d)

    def test_shortest_closed_unknown_and_deterministic_ties(self):
        d=graph();start=d['sites']['demo-001'];dests=d['destinations']
        first=routing.shortest(d,start,dests)
        self.assertEqual(first['destination'],'north');self.assertIn('direct',first['edge_ids'])
        other=routing.shortest(d,start,dests,{'direct':'closed'})
        self.assertNotIn('direct',other['edge_ids']);self.assertGreater(other['duration_minutes'],first['duration_minutes'])
        self.assertEqual(other,routing.shortest(d,start,dests,{'direct':'unknown'}))
        self.assertIsNone(routing.shortest(d,start,dests,{'access-demo-001':'unknown'}))
        twins=[{'id':i,'node':'north','label':i} for i in ['z','a']]
        self.assertEqual(routing.shortest(d,start,twins)['destination'],'a')
        self.assertGreater(first['duration_minutes'],0)

    def test_restriction_phases_destination_override_and_archive_unavailable(self):
        with patch('quasar.routing.load_graph',return_value=graph()):
            outputs=[routing.route('demo-001',iso(replay.START+timedelta(hours=h)),mode='what_if') for h in [0,6,12,18]]
            self.assertFalse(outputs[0]['route_changed']);self.assertTrue(outputs[1]['route_changed'])
            self.assertTrue(outputs[2]['destination_changed']);self.assertEqual(outputs[3]['status'],'no_route')
            self.assertEqual(routing.route('demo-001')['status'],'historical_conditions_unavailable')
            r=routing.route('demo-001',mode='what_if',destinations={'north':False,'west':False,'south':False})
            self.assertEqual(r['status'],'no_route')
            for values in [{'roads':{'bad':'closed'}},{'destinations':{'north':'yes'}},{'roads':{'direct':'flooded'}},{'roads':[]},{'site':[]}]:
                with self.subTest(values=values),self.assertRaises(ValueError):routing.route(**{'site':'demo-001','mode':'what_if',**values})
            with self.assertRaises(ValueError):routing.route('demo-001',roads={'direct':'closed'})

    def test_missing_network_is_not_no_route(self):
        with patch('quasar.routing.load_graph',return_value=None):
            self.assertEqual(routing.route('demo-001',mode='what_if')['status'],'network_unavailable')


class ReplayApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(port=0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path,payload=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            conn.request('POST' if payload is not None else 'GET',path,json.dumps(payload) if payload is not None else None,{'Content-Type':'application/json'})
            r=conn.getresponse();return r.status,json.loads(r.read())
        finally:conn.close()
    def test_consistent_selection_across_interfaces(self):
        with patch('quasar.routing.load_graph',return_value=graph()),patch('quasar.replay.load_archive',return_value={'status':'loaded',**archive()}):
            params='at=2026-10-09T05:00:00Z&preset=plus-5&mode=what_if'
            a=self.request('/api/properties?scenario=isaias-2026&'+params)
            b=self.request('/api/timeline?site=demo-001&'+params)
            c=self.request('/api/routes?site=demo-001&'+params)
            self.assertEqual([a[0],b[0],c[0]],[200,200,200]);self.assertEqual(a[1]['replay']['at'],b[1]['at']);self.assertEqual(b[1]['at'],c[1]['at'])
            self.assertEqual(self.request('/api/routes',{'site':'demo-001','mode':'what_if','roads':{'direct':'closed'}})[0],200)
    def test_invalid_requests_are_json_errors(self):
        for url in ['/api/timeline?site=bad','/api/routes?site=demo-001&at=bad','/api/properties?scenario=baseline&mode=what_if','/api/timeline?site=demo-001&site=demo-002']:
            with self.subTest(url=url):self.assertEqual(self.request(url)[0],400)
        for payload in [{},{'site':[]},{'site':'demo-001','preset':[]},{'site':'demo-001','unexpected':True},{'site':'demo-001','roads':{'bad':'closed'}}]:
            with self.subTest(payload=payload):self.assertEqual(self.request('/api/routes',payload)[0],400)
