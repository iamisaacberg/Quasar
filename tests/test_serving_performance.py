"""Synthetic correctness and resource seams; host timings are recorded separately."""
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import gzip
from io import BytesIO
from contextlib import redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import time
import unittest
from email.message import Message
from urllib.error import URLError
from unittest.mock import patch

from quasar import bridge, exposure, exposure_store as store, forecast_timeline
from quasar.serving_benchmark import distribution, acceptance, compare, ResourceMonitor
from quasar.transport import read_body
from quasar.warm_serving import warm_serving
import test_exposure
import test_forecast_timeline


def response(body, encoding='gzip', **headers):
    stream = BytesIO(body)
    stream.headers = {'Content-Encoding': encoding, **headers}
    return stream


class TransportTests(unittest.TestCase):
    def test_identity_and_gzip_have_the_same_decoded_limit(self):
        payload = b'{"value":' + b'1'*1000 + b'}'
        for body, encoding in ((payload,'identity'),(gzip.compress(payload),'gzip')):
            self.assertEqual(read_body(response(body,encoding),len(payload)),payload)
            with self.assertRaises(ValueError): read_body(response(body,encoding),len(payload)-1)

    def test_malformed_truncated_trailing_and_bomb_responses_fail_closed(self):
        valid=gzip.compress(b'{}')
        for body in (b'bad',valid[:-1],valid+b'trailing',valid+valid,gzip.compress(b'0'*1000000)):
            with self.subTest(body_bytes=len(body)), self.assertRaises(ValueError):
                read_body(response(body),1024)
        with self.assertRaises(ValueError): read_body(response(b'{}','br'),1024)
        with self.assertRaises(ValueError): read_body(response(b'{}','identity',**{'Content-Length':'10000'}),1024)
        self.assertEqual(read_body(response(b'{}','identity'),2),b'{}')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'archive.json'
        self.path.write_text(json.dumps(test_forecast_timeline.ArchivePlaybackTests().archive()))
        env=patch.dict(os.environ,{'QUASAR_REPLAY_FILE':str(self.path),'QUASAR_DATA_BRIDGE_URL':'',
                                  'QUASAR_DATA_BRIDGE_SERVE':'1','QUASAR_DATA_BRIDGE_TOKEN':'x'*32})
        env.start();self.addCleanup(env.stop)
        bridge._local_snapshot.cache_clear();forecast_timeline._prepared.clear()
        self.addCleanup(bridge._local_snapshot.cache_clear)
        self.addCleanup(forecast_timeline._prepared.clear)

    def test_unchanged_archive_does_not_reread_reparse_or_reserialize(self):
        snapshot=bridge.read_snapshot('isaias-2026')
        first=forecast_timeline.timeline()
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Repeated file read')), \
                patch.object(json,'dumps',side_effect=AssertionError('Repeated serialization')):
            self.assertIs(bridge.read_snapshot('isaias-2026'),snapshot)
            self.assertIs(forecast_timeline.timeline(),first)
            self.assertEqual(bridge.serve_snapshot('isaias-2026','Bearer '+'x'*32),(200,snapshot.encoded))

    def test_replacement_same_mtime_and_size_and_missing_source_invalidate(self):
        first=bridge.read_snapshot('isaias-2026')
        stat=self.path.stat()
        self.path.write_bytes(self.path.read_bytes().replace(b'12.0',b'13.0'))
        # Force an in-place, same-size content change even if the fixture has no 12.0.
        raw=self.path.read_bytes()
        raw=raw.replace(b'"rainfall_1h_mm": 2',b'"rainfall_1h_mm": 3',1)
        self.path.write_bytes(raw)
        os.utime(self.path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        second=bridge.read_snapshot('isaias-2026')
        self.assertIsNot(first,second)
        self.assertNotEqual(first.content_identity,second.content_identity)
        self.path.unlink()
        self.assertEqual(forecast_timeline.timeline()['status'],'not_configured')

    def test_concurrent_archive_loads_only_decode_once(self):
        original=bridge._parse_snapshot
        with patch.object(bridge,'_parse_snapshot',wraps=original) as parse:
            with ThreadPoolExecutor(max_workers=3) as pool:
                values=list(pool.map(lambda _:bridge.read_snapshot('isaias-2026'),range(3)))
            self.assertEqual(parse.call_count,1)
            self.assertTrue(all(v is values[0] for v in values))

    def test_current_cached_snapshot_still_expires_and_clears_rainfall(self):
        from test_county_weather import current, NOW
        self.path.write_text(json.dumps(current()))
        with patch.dict(os.environ,{'QUASAR_WEATHERNEXT_FILE':str(self.path)}), \
                patch.object(forecast_timeline,'datetime') as clock:
            clock.now.return_value=NOW
            self.assertEqual(forecast_timeline.timeline(source='current')['status'],'ready')
            clock.now.return_value=NOW+timedelta(hours=3)
            stale=forecast_timeline.timeline(source='current')
            self.assertEqual(stale['status'],'stale')
            self.assertTrue(all(f['collection']['weather_cells']['features'][0]['properties']['rainfall_6h_mm'] is None
                                for f in stale['frames']))

    def test_expired_remote_cache_does_not_mask_an_upstream_failure(self):
        payload=self.path.read_bytes()
        reply=response(gzip.compress(payload))
        reply.headers=Message()
        reply.headers['Content-Type']='application/json'
        reply.headers['Content-Encoding']='gzip'
        bridge._remote_cache.clear()
        self.addCleanup(bridge._remote_cache.clear)
        with patch.dict(os.environ,{'QUASAR_DATA_BRIDGE_URL':'https://source.example/bridge/v1'}), \
                patch.object(bridge,'build_opener') as opener, patch.object(bridge.time,'monotonic') as clock:
            clock.return_value=0
            opener.return_value.open.return_value=reply
            self.assertEqual(forecast_timeline.timeline()['status'],'ready')
            self.assertEqual(opener.return_value.open.call_args.args[0].get_header('Accept-encoding'),'gzip')
            clock.return_value=16
            opener.return_value.open.side_effect=URLError('synthetic outage')
            self.assertEqual(forecast_timeline.timeline()['status'],'unavailable')


class ServingStoreTests(unittest.TestCase):
    setUp=test_exposure.ExposureTests.setUp
    write=test_exposure.ExposureTests.write
    record=staticmethod(test_exposure.ExposureTests.record)

    def test_original_checksum_and_manifest_selection_preserve_previous_output(self):
        self.data['windows'][0]['parcels'].append(self.record(4,None));self.write()
        manifest=self.artifact.parent/'manifest.json'
        manifest.write_text(json.dumps({'status':'verified','windows':[{'artifact':self.artifact.name,
            'from':self.query['from'],'sha256':store.digest(self.artifact)}]}))
        output=self.artifact.parent/'serving.sqlite3'
        store.prepare(self.database,self.artifact.parent,output,manifest)
        previous=output.read_bytes()
        self.data['windows'][0]['parcels'][0]=self.record(1,50);self.write()
        with self.assertRaisesRegex(ValueError,'checksum'):
            store.prepare(self.database,self.artifact.parent,output,manifest)
        self.assertEqual(output.read_bytes(),previous)
        self.assertEqual(list(output.parent.glob('*.tmp')),[])

    def test_concurrent_first_reads_share_database_verification(self):
        output=self.artifact.parent/'serving.sqlite3'
        store.prepare(self.database,self.artifact,output)
        calls=[]
        original=store._verified.__wrapped__
        @lru_cache(maxsize=4)
        def checked(*args):
            calls.append(1);time.sleep(.03)
            return original(*args)
        with patch.object(store,'_verified',checked):
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(lambda _:store.read(str(output),str(self.database),
                    exposure.timestamp(self.query['from']),exposure.timestamp(self.query['to']),7,[]),range(3)))
        self.assertEqual(len(calls),1)

    def test_warmup_validates_all_windows_and_refuses_invalid_inputs(self):
        with closing(sqlite3.connect(self.database)) as db:
            source=json.loads(db.execute("SELECT value FROM metadata WHERE key='source_provenance'").fetchone()[0])
            source.update(source_url='https://synthetic.example',retrieved_at='2026-10-17T00:00:00Z')
            db.execute("UPDATE metadata SET value=? WHERE key='source_provenance'",(json.dumps(source),))
            db.executemany('INSERT INTO metadata VALUES(?,?)',[
                ('h3_resolutions','[4,5,6,7]'),('cell_index_sha256','"synthetic-cell-index"')])
            db.commit()
        archive=test_forecast_timeline.ArchivePlaybackTests().archive()
        archive_path=self.artifact.parent/'archive.json'
        archive_path.write_text(json.dumps(archive))
        first=copy.deepcopy(self.data['windows'][0])
        start=exposure.timestamp(first['valid_from'])
        self.data['windows']=[{**copy.deepcopy(first),'valid_from':(start+timedelta(hours=i)).isoformat(),
            'valid_to':(start+timedelta(hours=i+6)).isoformat()} for i in range(25)]
        self.write()
        output=self.artifact.parent/'serving.sqlite3'
        store.prepare(self.database,self.artifact,output)
        with patch.dict(os.environ,{'QUASAR_EXPOSURE_DATABASE':str(output),'QUASAR_EXPOSURE_FILE':'',
                'QUASAR_REPLAY_FILE':str(archive_path),'QUASAR_DATA_BRIDGE_URL':'','QUASAR_PARCEL_API_TOKEN':'x'*32}):
            self.assertEqual(warm_serving()['windows'],25)
            with patch.dict(os.environ,{'QUASAR_EXPOSURE_DIRECTORY':'conflicting'}):
                with self.assertRaisesRegex(ValueError,'conflicting'): warm_serving()
            output.write_bytes(b'invalid sqlite')
            with self.assertRaises(Exception): warm_serving()

    def test_gzip_exposure_proxy_preserves_unknown_and_requests_compression(self):
        result=exposure.exposure({**self.query,'parcel_ids':'3'})
        with patch.dict(os.environ,{'QUASAR_LINUXONE_API_URL':'https://example.test','QUASAR_LINUXONE_API_TOKEN':'x'*32}), \
                patch.object(exposure,'build_opener') as opener:
            opener.return_value.open.return_value=response(gzip.compress(json.dumps(result).encode()))
            self.assertEqual(exposure.exposure({**self.query,'parcel_ids':'3'})['parcels']['3']['score'],None)
            self.assertEqual(opener.return_value.open.call_args.args[0].get_header('Accept-encoding'),'gzip')


class BenchmarkTests(unittest.TestCase):
    def test_warm_startup_failure_never_opens_a_listener_or_prints_private_details(self):
        from quasar import __main__
        error=StringIO()
        with patch.object(sys,'argv',['quasar','--warm-serving']), patch.object(__main__,'load_env'), \
                patch.object(__main__,'map_settings'), patch.object(__main__,'make_server') as server, \
                patch('quasar.warm_serving.warm_serving',side_effect=ValueError('private-path-and-token')), \
                redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
            __main__.main()
        self.assertEqual(stopped.exception.code,1)
        server.assert_not_called()
        self.assertNotIn('private-path-and-token',error.getvalue())

    def test_dry_run_does_not_read_workload_make_requests_or_write_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'report.json'
            result=subprocess.run([sys.executable,'scripts/benchmark_linuxone.py','--workload','missing.json',
                '--label','loopback','--output',str(output)],capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(result.stdout)['network_requests'],0)
            self.assertFalse(output.exists())

    def test_p95_requires_100_samples_and_uses_nearest_rank(self):
        self.assertNotIn('p95_ms',distribution(list(range(99))))
        self.assertEqual(distribution(list(range(100)))['p95_ms'],94)

    def test_incomplete_or_unmeasured_runs_cannot_pass_acceptance(self):
        report={'status':'complete','label':'loopback','classes':{},'resources':{},'cycles':[]}
        self.assertFalse(acceptance(report)['passed'])
        monitor=ResourceMonitor()
        with patch.object(monitor,'sample',return_value={'available_bytes':1}):
            with self.assertRaises(RuntimeError), monitor.running(): pass

    def test_comparison_reports_payload_changes_separately_from_speed(self):
        old={'classes':{'summary':{'median_ms':100}},'requests':[{'case':'summary','semantic_sha256':'original'}]}
        new={'classes':{'summary':{'median_ms':1}},'requests':[{'case':'summary','semantic_sha256':'different'}]}
        result=compare(old,new)['summary']
        self.assertEqual(result['median_change_percent'],-99)
        self.assertFalse(result['same_payload_set'])
