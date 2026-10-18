"""Opt-in bounded API measurement, with no credentials or payloads in reports."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
from threading import Event, Lock, Thread
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener

from .parcels import _NoRedirect
from .transport import read_body


def distribution(values):
    result = {"samples": len(values), "median_ms": round(statistics.median(values), 3),
              "first_observed_ms": round(values[0], 3), "max_ms": round(max(values), 3)}
    if len(values) >= 100:
        result["p95_ms"] = round(sorted(values)[math.ceil(.95 * len(values)) - 1], 3)
    return result


class ResourceMonitor:
    """Monitor the serving PID and the Linux host independently of HTTP latency."""
    def __init__(self, pid=None):
        self.pid = pid
        self.stopped = Event()
        self.reason = None
        self.samples = []
        self.lock = Lock()

    def check(self):
        if self.reason:
            raise RuntimeError(self.reason)

    def sample(self):
        if not Path('/proc/meminfo').exists():
            return None
        memory = {k: int(v.split()[0]) * 1024 for k, v in
                  (line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())}
        ticks = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
        sample = {"at": time.monotonic(), "available_bytes": memory["MemAvailable"],
                  "cpu_total": sum(ticks), "cpu_idle": ticks[3] + ticks[4]}
        if self.pid:
            root = Path('/proc') / str(self.pid)
            status = dict(line.split(':', 1) for line in (root/'status').read_text().splitlines() if ':' in line)
            stat = (root/'stat').read_text().rsplit(')', 1)[1].split()
            sample.update(rss_bytes=int(status['VmRSS'].split()[0])*1024,
                          peak_rss_bytes=int(status['VmHWM'].split()[0])*1024,
                          process_cpu_seconds=(int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK'))
        return sample

    def watch(self):
        high_since = None
        previous = None
        while not self.stopped.is_set():
            try:
                sample = self.sample()
                if sample:
                    if sample['available_bytes'] < 1024**3:
                        self.reason = "available memory below 1 GiB"
                    if previous:
                        total = sample['cpu_total']-previous['cpu_total']
                        cpu = 100*(1-(sample['cpu_idle']-previous['cpu_idle'])/total) if total else 0
                        sample['host_cpu_percent'] = cpu
                        high_since = (high_since or sample['at']) if cpu > 90 else None
                        if high_since and sample['at']-high_since >= 30:
                            self.reason = "CPU above 90 percent for 30 seconds"
                    with self.lock:
                        self.samples.append(sample)
                    previous = sample
            except (OSError, KeyError, ValueError):
                self.reason = "resource monitoring failed"
            self.stopped.wait(.5)

    @contextmanager
    def running(self):
        initial = self.sample()
        if initial and initial['available_bytes'] < 1024**3:
            raise RuntimeError("available memory below 1 GiB")
        thread = Thread(target=self.watch, daemon=True)
        thread.start()
        try:
            yield self
        finally:
            self.stopped.set()
            thread.join()

    def report(self):
        samples = self.samples
        result = {"available": bool(samples), "serving_pid_monitored": self.pid is not None,
                  "samples": len(samples)}
        if samples:
            result['min_available_bytes'] = min(s['available_bytes'] for s in samples)
            if self.pid:
                result.update(peak_rss_bytes=max(s['peak_rss_bytes'] for s in samples),
                              rss_first_bytes=samples[0]['rss_bytes'], rss_last_bytes=samples[-1]['rss_bytes'],
                              process_cpu_seconds=samples[-1]['process_cpu_seconds']-samples[0]['process_cpu_seconds'])
            cpu=[s['host_cpu_percent'] for s in samples if 'host_cpu_percent' in s]
            if cpu: result.update(host_cpu_mean_percent=statistics.mean(cpu),host_cpu_max_percent=max(cpu))
        return result


def cases(workload):
    start = workload['starts'][0]
    query = {"from": start, "to": (datetime.fromisoformat(start.replace('Z','+00:00'))+timedelta(hours=6)).isoformat(),
             "mode": "replay", "resolution": "7"}
    ids = workload['parcel_ids']
    return [("summary", "/api/exposure?"+urlencode(query)),
            ("parcel_one", "/api/exposure?"+urlencode({**query,"parcel_ids":str(ids[0])})),
            ("parcel_hundred", "/api/exposure?"+urlencode({**query,"parcel_ids":','.join(map(str,ids))}))]


def run(origin, token, workload, *, samples=100, smoke=False, public=False, pid=None, max_seconds=900):
    parsed = urlsplit(origin)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('','/')
            or (parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1','localhost'))):
        raise ValueError("Use an HTTPS origin, or loopback HTTP")
    if len(workload['parcel_ids']) != 100 or len(set(workload['parcel_ids'])) != 100 or len(workload['starts']) != 25:
        raise ValueError("Workload requires 100 distinct parcels and 25 replay positions")
    report = {"schema_version": 1, "status": "running", "measured_at": datetime.now(timezone.utc).isoformat(),
              "vantage_architecture": platform.machine(), "python": platform.python_version(),
              "identities": workload.get('identities',{}), "cold_process": False,
              "note": "First observed requests are not cold-process startup measurements.", "requests": [], "cycles": []}
    monitor = ResourceMonitor(pid)
    started = time.monotonic()
    rows = report['requests']
    rows_lock = Lock()

    def request(name, path, *, expected='ready', auth=True, snapshot=False):
        monitor.check()
        if time.monotonic()-started > max_seconds:
            raise RuntimeError("benchmark time budget exceeded")
        headers = {"Accept-Encoding":"gzip", "Accept":"application/json"}
        if token and auth:
            headers['Authorization' if snapshot else 'X-Quasar-Parcel-Token'] = ('Bearer '+token) if snapshot else token
        before = time.perf_counter()
        with build_opener(_NoRedirect).open(Request(origin.rstrip('/')+path,headers=headers),timeout=12) as response:
            body = read_body(response,30_000_000 if snapshot or name == 'timeline' else 2_000_000)
            wire_bytes = int(response.headers.get('Content-Length',len(body)))
            timings = {name:float(value) for name,value in re.findall(
                r'(?:^|,\s*)(quasar|source|prepare|query|encode|compress|upstream);dur=([0-9.]+)',
                response.headers.get('Server-Timing',''))}
        data = json.loads(body)
        if not snapshot and data.get('status') != expected:
            raise RuntimeError("unexpected API data state")
        semantic = {k:v for k,v in data.items() if k not in ('aggregation_architecture',)}
        row = {"case":name, "elapsed_ms":(time.perf_counter()-before)*1000,"wire_bytes":wire_bytes,
               "decoded_bytes":len(body), "server_timing":timings,
               "semantic_sha256":hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
        with rows_lock:
            rows.append(row)
        return data

    with monitor.running():
        try:
            for name,path in cases(workload):
                for _ in range(3 if smoke else samples):
                    request(name,path)
            for cycle in range(1 if smoke else 3):
                for start in workload['starts']:
                    for resolution in ((7,) if smoke else (4,5,6,7)):
                        end=(datetime.fromisoformat(start.replace('Z','+00:00'))+timedelta(hours=6)).isoformat()
                        request('replay', '/api/exposure?'+urlencode({'from':start,'to':end,'mode':'replay','resolution':resolution}))
                request('return_first',cases(workload)[0][1])
                report['cycles'].append(monitor.sample())
            common = {'cell':workload['cell'],'ring':json.dumps(workload['ring']), 'inventory_id':workload['inventory_id']}
            for index,offset in enumerate(workload['offsets']):
                path='/api/parcels?'+urlencode({**common,'offset':offset})
                for _ in range(1 if smoke else 10): request('geometry_'+str(index),path)
            for name,path in [('context','/api/parcels/'+str(workload['parcel_ids'][0])+'/context'),
                              ('cell_context','/api/cells/'+workload['cell']+'/summary'),
                              ('timeline','/api/weather/timeline?source=archive')]:
                for _ in range(1 if smoke else 10): request(name,path)
            if not public and os.environ.get('QUASAR_DATA_BRIDGE_TOKEN'):
                saved_token = token
                token = os.environ['QUASAR_DATA_BRIDGE_TOKEN']
                try: request('archive','/bridge/v1/snapshots/isaias-2026',snapshot=True)
                finally: token = saved_token
            if not smoke:
                with ThreadPoolExecutor(max_workers=3) as pool:
                    list(pool.map(lambda item:request('burst_'+item[0],item[1]),cases(workload)))
            monitor.check()
            report['status']='complete'
        except Exception as exc:
            # Exceptions may contain URLs/headers: serialize their class only.
            report.update(status='stopped',error_type=type(exc).__name__)
            if hasattr(exc,'code'): report['error_http_status']=exc.code
            if monitor.reason: report['stop_reason']=monitor.reason
    report['resources']=monitor.report()
    report['elapsed_seconds']=time.monotonic()-started
    report['classes']={name:distribution([r['elapsed_ms'] for r in rows if r['case']==name]) for name in sorted({r['case'] for r in rows})}
    return report


def compare(baseline, candidate):
    result = {}
    for name, stats in candidate['classes'].items():
        if name in baseline['classes']:
            old=baseline['classes'][name]['median_ms']
            old_rows=[r['semantic_sha256'] for r in baseline['requests'] if r['case']==name]
            new_rows=[r['semantic_sha256'] for r in candidate['requests'] if r['case']==name]
            result[name]={'median_change_percent':round(100*(stats['median_ms']/old-1),2) if old else None,
                          'same_payload_set':set(old_rows)==set(new_rows),
                          'same_sample_count':len(old_rows)==len(new_rows)}
    return result


def acceptance(report, baseline=None):
    checks = {'complete_run': report['status']=='complete', 'baseline_available':baseline is not None}
    if report.get('label')=='loopback':
        checks['warm_exposure_p95'] = all(report['classes'].get(name,{}).get('p95_ms',float('inf')) <= 250
                                            for name in ('summary','parcel_one','parcel_hundred'))
    resources=report.get('resources',{})
    checks['peak_rss'] = resources.get('serving_pid_monitored',False) and resources.get('peak_rss_bytes',2**63)<1024**3
    cycles=[c['rss_bytes'] for c in report.get('cycles',[]) if c and 'rss_bytes' in c]
    # Allow allocator/page granularity; require no sustained increase above 8 MiB.
    checks['stable_replay_rss'] = len(cycles)==3 and cycles[-1] <= cycles[0]+8*1024**2
    if baseline:
        matched = (baseline.get('status')=='complete' and baseline.get('label')==report.get('label')
                   and baseline.get('vantage_architecture')==report.get('vantage_architecture')
                   and all(baseline.get('identities',{}).get(k)==report.get('identities',{}).get(k)
                           for k in ('inventory_id','producer_manifest_sha256')))
        changes=compare(baseline,report)
        checks['matched_baseline']=matched
        checks['payload_parity']=bool(changes) and all(v['same_payload_set'] and v['same_sample_count'] for v in changes.values())
        if report.get('label')=='public':
            names={'summary','parcel_one','parcel_hundred','replay','return_first',
                   'burst_summary','burst_parcel_one','burst_parcel_hundred'}
            old=[r['elapsed_ms'] for r in baseline['requests'] if r['case'] in names]
            new=[r['elapsed_ms'] for r in report['requests'] if r['case'] in names]
            change=100*(statistics.median(new)/statistics.median(old)-1) if old and new else None
            checks['public_exposure_improvement']=matched and checks['payload_parity'] and change is not None and change<=-50
        checks['other_endpoints_regression']=all(
            name in changes and changes[name]['median_change_percent'] is not None
            and changes[name]['median_change_percent']<=10
            for name in ('context','cell_context','geometry_0','geometry_1','geometry_2','timeline'))
    return {'checks':checks,'passed':all(checks.values()),'rss_tolerance_bytes':8*1024**2}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--workload',type=Path,required=True)
    parser.add_argument('--label',choices=('loopback','source','public'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pid',type=int)
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'dry_run':True,'label':args.label,'network_requests':0}))
        return
    workload=json.loads(args.workload.read_text())
    report=run(os.environ.get('QUASAR_BENCH_ORIGIN',''),os.environ.get('QUASAR_BENCH_TOKEN',''),workload,
               smoke=args.smoke,public=args.label=='public',pid=args.pid)
    report['label']=args.label
    baseline=json.loads(args.baseline.read_text()) if args.baseline else None
    if baseline: report['comparison']=compare(baseline,report)
    report['acceptance']=acceptance(report,baseline)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','classes','resources')}))
    if report['status']!='complete': raise SystemExit(1)


if __name__=='__main__':
    main()
