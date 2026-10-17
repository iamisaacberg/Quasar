"""Fetch public NHC context and curate a county-contained exercise road network.

No cloud queries or credentials. Source downloads and graph stay ignored/local.
Roads follow county centerlines; traversal, connectors and destinations are
simulated. Current geometry is not proof of historical 2026 road conditions.
"""
import argparse
import hashlib
import heapq
import json
import sys
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quasar.adapters.historical import write_json
from quasar.adapters.weathernext import points, iso
from quasar.geometry import covers, line_covered, distance_m, length_m
from quasar.routing import validate_graph
from quasar.geometry_index import CountyBoundaryIndex

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/isaias'
PROCESSED = ROOT / 'data/processed'
ROADS_URL = 'https://okgis.myokaloosa.com/arcgis/rest/services/Infrastructure/Transportation/MapServer/120/query'
BOUNDARY_URL = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'


def fetch(url, path):
    with urlopen(Request(url, headers={'User-Agent': 'Quasar-datathon/0.1 public-data research'}), timeout=60) as response:
        data = response.read(20_000_001)
    if len(data) > 20_000_000:
        raise ValueError('Public source response too large')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def advisories():
    records, failures = [], []
    for n in range(1, 15):
        url = f'https://www.nhc.noaa.gov/archive/2026/al09/al092026.public.{n:03d}.shtml'
        try:
            source_path = RAW / f'nhc-public-{n:03d}.html'
            raw = source_path.read_bytes() if source_path.exists() else fetch(url, source_path)
            text = raw.decode('utf-8', errors='replace')
            pre = re.search(r'<pre[^>]*>(.*?)</pre>', text, flags=re.I | re.S)
            if not pre:
                raise ValueError('NHC advisory text not found')
            text = unescape(re.sub('<[^>]+>', '', pre.group(1)))
            if 'AL092026' not in text:
                raise ValueError('Wrong storm identity')
            issued_line = re.search(r'(\d{3,4}) (AM|PM) (CDT|CST|EDT|EST) \w{3} (\w{3}) (\d{1,2}) (2026)', text)
            if not issued_line:
                raise ValueError('Unrecognized original advisory issue timestamp')
            clock, ampm, zone, month, day, year = issued_line.groups()
            offset = {'CDT': -5, 'CST': -6, 'EDT': -4, 'EST': -5}[zone]
            issued = datetime.strptime(f'{clock.zfill(4)} {ampm} {month} {day} {year}', '%I%M %p %b %d %Y').replace(tzinfo=timezone(timedelta(hours=offset)))
            records.append({'number': n, 'issued_at': iso(issued), 'source_url': url,
                            'text': text.strip(), 'retrieved_at': iso(datetime.fromtimestamp(source_path.stat().st_mtime, timezone.utc)), 'sha256': hashlib.sha256(raw).hexdigest()})
        except Exception as exc:
            failures.append({'number': n, 'error': str(exc)})
    if not records:
        raise ValueError('No NHC advisories acquired')
    data = {'advisories': records, 'failures': failures, 'retrieved_at': iso(datetime.now(timezone.utc)),
            'source_url': 'https://www.nhc.noaa.gov/archive/2026/ISAIAS.shtml',
            'license': 'NOAA/NWS public information; preserve attribution', 'crs': 'not applicable',
            'units': 'Original advisory units retained', 'source_identifier': 'AL092026',
            'processing': 'Extracted original public-advisory PRE text; original advisory issue timestamp parsed and normalized to UTC. No local flood observations inferred.'}
    write_json(PROCESSED / 'isaias-advisories.json', data)
    print(f'NHC: {len(records)} advisories acquired; {len(failures)} unavailable', flush=True)


def boundary():
    path = ROOT / 'data/raw/census_okaloosa_county.geojson'
    if not path.exists():
        params = {'where': "GEOID='12091'", 'outFields': 'GEOID,NAME', 'outSR': '4326', 'f': 'geojson'}
        fetch(BOUNDARY_URL+'?'+urlencode(params), path)
    data = json.loads(path.read_text())
    f = data['features'][0]
    if str(f['properties']['GEOID']) != '12091':
        raise ValueError('Unexpected county boundary')
    return f['geometry'], hashlib.sha256(path.read_bytes()).hexdigest()


def source_roads():
    path = ROOT / 'data/processed/okaloosa/roads.geojson'
    if not path.exists():
        raise ValueError('Run scripts/acquire_supporting_data.py first')
    data = json.loads(path.read_text())
    if data.get('county_fips') != '12091':
        raise ValueError('Wrong road county')
    return data['features']


def curate():
    county, boundary_hash = boundary()
    county_index = CountyBoundaryIndex(county)
    roads = source_roads()
    nodes, edges, adjacent = {}, {}, {}
    def node(p):
        p = [round(p[0], 6), round(p[1], 6)]
        key = f'{p[0]:.6f},{p[1]:.6f}'
        nodes[key] = p
        return key
    for f in roads:
        geom = f['geometry']
        parts = [geom['coordinates']] if geom['type'] == 'LineString' else geom['coordinates']
        for n, coords in enumerate(parts):
            coords = [[round(c[0],6),round(c[1],6)] for c in coords]
            a, b = node(coords[0]), node(coords[-1])
            if a == b:
                continue
            props = f['properties']
            key = f'road-{props["OBJECTID"]}-{n}'
            edge = {'id': key, 'from': a, 'to': b, 'coordinates': coords, 'kind': 'road',
                    'source_identifier': props['OBJECTID'],
                    'label': ' '.join(str(props.get(k) or '').strip() for k in ('PREDIR','NAME','TYPE','SUFDIR')).strip()}
            edges[key] = edge
            meters = length_m(coords)
            for u,v in ((a,b),(b,a)):
                adjacent.setdefault(u, []).append((v,key,meters))
    # Use the largest endpoint-connected component. Do not invent junctions at
    # overpasses. Equal rounded endpoints are an explicitly exercise-only topology.
    unvisited, components = set(adjacent), []
    while unvisited:
        todo, comp = [min(unvisited)], set()
        while todo:
            u = todo.pop()
            if u in comp:
                continue
            comp.add(u); unvisited.discard(u)
            todo.extend(v for v,_,_ in adjacent[u] if v not in comp)
        components.append(comp)
    component = max(components, key=len)
    print(f'Largest exercise component: {len(component)} junctions', flush=True)
    def nearest(p):
        return min(component, key=lambda k: distance_m(p,nodes[k]))
    dests = [{'id': 'exercise-north', 'label': 'Exercise destination North', 'node': nearest([-86.48,30.52])},
             {'id': 'exercise-west', 'label': 'Exercise destination West', 'node': nearest([-86.62,30.43])},
             {'id': 'exercise-south', 'label': 'Exercise destination Inland', 'node': nearest([-86.57,30.76])}]
    def path(start,end,blocked=None):
        queue, seen = [(0,(),start)], set()
        while queue:
            cost, route, u = heapq.heappop(queue)
            if u in seen:
                continue
            seen.add(u)
            if u == end:
                return route
            for v,k,meters in adjacent[u]:
                if v not in seen and k != blocked:
                    heapq.heappush(queue,(cost+meters,route+(k,),v))
        return ()
    chosen, origins = set(), {}
    for p in points():
        coords = [p['longitude'],p['latitude']]
        start = nearest(coords)
        identifier = p['id']
        origins[identifier] = identifier
        nodes[identifier] = coords
        key = 'access-'+identifier
        connector = {'id':key,'from':identifier,'to':start,'coordinates':[coords,nodes[start]],
                     'kind':'simulated_access','label':p['label']+' · simulated access connector'}
        if length_m(connector['coordinates']) <= 0 or not county_index._line_inside(connector['coordinates']):
            raise ValueError('Invalid exercise access connector')
        edges[key] = connector
        chosen.add(key)
        for d in dests:
            route = path(start,d['node'])
            if not route:
                raise ValueError('Unable to connect exercise destination')
            chosen.update(route)
            alternate = path(start,d['node'],route[len(route)//2])
            chosen.update(alternate)
    selected = [edges[k] for k in sorted(chosen)]
    print(f'Validating complete county containment for {len(selected)} curated segments',flush=True)
    for e in selected:
        if not county_index._line_inside(e['coordinates']):
            raise ValueError('Curated road leaves county; must recurate: '+e['id'])
    used = {e[k] for e in selected for k in ('from','to')}
    data = {'schema_version':1,'county_fips':'12091','county_geometry':county,
            'nodes':{k:nodes[k] for k in sorted(used)},'edges':selected,'sites':origins,'destinations':dests,
            'provenance':{'source_url':ROADS_URL,'source_identifier':'Okaloosa street centerlines, layer 120',
                          'retrieved_at':iso(datetime.fromtimestamp((ROOT/'data/processed/okaloosa/roads.geojson').stat().st_mtime,timezone.utc)),'crs':'EPSG:4326','units':'decimal degrees; haversine meters',
                          'license':'Okaloosa public GIS service; local research use. Review county terms before redistributing source geometry.',
                          'boundary_source':BOUNDARY_URL,'boundary_sha256':boundary_hash,
                          'source_sha256':{'roads.geojson':hashlib.sha256((ROOT/'data/processed/okaloosa/roads.geojson').read_bytes()).hexdigest()},
                          'processing':'Curated shortest and alternative paths on endpoint-connected road geometry; rounded 6 decimals; two-way exercise topology. Polygon and full-segment containment checked. Simulated access lines and three fictional destinations; no historical road claims.'}}
    validate_graph(data)
    write_json(PROCESSED/'evacuation-network.json',data)
    print(f'Network ready: {len(selected)} edges; six sites; three exercise destinations',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',choices=('advisories','roads','all'),default='all')
    args=parser.parse_args()
    failures=[]
    for label, fn in [('advisories',advisories),('roads',curate)]:
        if args.only in ('all',label):
            try: fn()
            except Exception as exc:
                failures.append(label)
                print(f'{label} preparation failed: {exc}', file=sys.stderr,flush=True)
    if failures:
        sys.exit(1)


if __name__=='__main__':
    main()
