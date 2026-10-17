"""Deterministic resident routing over a county-validated exercise graph."""
import heapq
import json
import os
from functools import lru_cache
from pathlib import Path

from .adapters.weathernext import points, timestamp
from .geometry import covers, line_covered, length_m
from .geometry_index import CountyBoundaryIndex
from .replay import START, selection
from .bridge import BridgeUnavailable, read_snapshot

NOTICE = ('EXERCISE ROUTE · 30 km/h assumed speed; two-way exercise topology; '
          'fictional destinations and restrictions. Not navigation, a verified open shelter or a guarantee of safety.')


def validate_graph(data):
    if data.get('county_fips') != '12091' or data.get('schema_version') != 1:
        raise ValueError('Invalid routing graph county/version')
    boundary, nodes = data['county_geometry'], data['nodes']
    if not isinstance(nodes, dict) or len(nodes) > 10000 or not data.get('provenance'):
        raise ValueError('Invalid routing nodes/provenance')
    county_index = CountyBoundaryIndex(boundary)
    if not all(county_index.covers(p) for p in nodes.values()):
        raise ValueError('Routing node outside authoritative county geometry')
    if len(data['edges']) > 10000 or len(data['destinations']) != 3:
        raise ValueError('Invalid routing graph size')
    seen = set()
    for edge in data['edges']:
        coords = edge['coordinates']
        if (edge['id'] in seen or edge['from'] not in nodes or edge['to'] not in nodes
                or coords[0] != nodes[edge['from']] or coords[-1] != nodes[edge['to']]
                or not county_index._line_inside(coords) or length_m(coords) <= 0):
            raise ValueError('Invalid, duplicate or outside-county complete road geometry')
        if edge.get('kind') not in ('road', 'simulated_access'):
            raise ValueError('Missing road geometry classification')
        seen.add(edge['id'])
    sites = {p['id']: p for p in points()}
    if set(data['sites']) != set(sites):
        raise ValueError('Graph must connect all six exercise sites')
    for site, node in data['sites'].items():
        if nodes[node] != [sites[site]['longitude'], sites[site]['latitude']]:
            raise ValueError('Exercise site connector coordinates mismatch')
    destination_ids = set()
    for dest in data['destinations']:
        if dest['id'] in destination_ids or dest['node'] not in nodes:
            raise ValueError('Invalid exercise destination')
        destination_ids.add(dest['id'])
    return data


@lru_cache(maxsize=2)
def _read_graph(path, mtime, size):
    if size > 8_000_000:
        raise ValueError('Routing graph too large')
    return validate_graph(json.loads(Path(path).read_text()))


def load_graph():
    if os.environ.get('QUASAR_DATA_BRIDGE_URL', '').strip():
        try:
            data = read_snapshot('evacuation-network')
            return validate_graph(data) if data is not None else None
        except (BridgeUnavailable, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return None
    path = Path(os.environ.get('QUASAR_ROUTES_FILE', 'data/processed/evacuation-network.json'))
    try:
        stat = path.stat()
        return _read_graph(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return None


def shortest(graph, start, destinations, states=None):
    """Time then distance then stable edge IDs; destinations tie by ID."""
    states = states or {}
    adjacent = {node: [] for node in graph['nodes']}
    edges = {edge['id']: edge for edge in graph['edges']}
    for edge in graph['edges']:
        if states.get(edge['id'], 'open') != 'open':
            continue
        distance = length_m(edge['coordinates'])
        for origin, target in ((edge['from'], edge['to']), (edge['to'], edge['from'])):
            adjacent[origin].append((target, edge['id'], distance))
    queue, best = [(0.0, 0.0, (), start)], {}
    while queue:
        seconds, distance, path, node = heapq.heappop(queue)
        rank = (seconds, distance, path)
        if node in best and best[node] <= rank:
            continue
        best[node] = rank
        for target, edge_id, meters in adjacent[node]:
            if target not in best:
                heapq.heappush(queue, (seconds+meters/ (30000/3600), distance+meters, path+(edge_id,), target))
    candidates = [(best[d['node']][0], best[d['node']][1], d['id'], best[d['node']][2], d)
                  for d in destinations if d['node'] in best]
    if not candidates:
        return None
    seconds, meters, _, ids, dest = min(candidates)
    features, node = [], start
    for edge_id in ids:
        edge = edges[edge_id]
        coords = edge['coordinates'] if edge['from'] == node else list(reversed(edge['coordinates']))
        features.append({'type': 'Feature', 'id': edge_id, 'geometry': {'type': 'LineString', 'coordinates': coords},
                         'properties': {'id': edge_id, 'label': edge['label'], 'kind': edge['kind']}})
        node = edge['to'] if edge['from'] == node else edge['from']
    return {'destination': dest['id'], 'destination_label': dest['label'], 'edge_ids': list(ids),
            'distance_m': round(meters, 1), 'duration_minutes': round(seconds/60, 1),
            'geometry': {'type': 'FeatureCollection', 'features': features}}


def states_for(graph, site, at):
    """Fixed event phases. A per-site baseline supplies a demonstrable closure."""
    baseline = shortest(graph, graph['sites'][site], graph['destinations'])
    states = {e['id']: 'open' for e in graph['edges']}
    destinations = {d['id']: True for d in graph['destinations']}
    phase = int((timestamp(at)-START).total_seconds()//3600)
    message = 'All network segments assumed open for this exercise.'
    if baseline and phase >= 6:
        # Pick the first baseline road that has an alternate route to the same
        # destination. A bridge closure can instead demonstrate disconnection.
        candidates = [i for i in baseline['edge_ids'] if next(e for e in graph['edges'] if e['id'] == i)['kind'] == 'road']
        destination = [d for d in graph['destinations'] if d['id'] == baseline['destination']]
        blocked = next((i for i in candidates if shortest(graph, graph['sites'][site], destination, {i:'closed'})), None)
        if blocked:
            states[blocked] = 'closed'
        message = 'Hour 6+: one route segment is closed in the exercise.'
    if baseline and phase >= 12:
        destinations[baseline['destination']] = False
        message = 'Hour 12+: the original exercise destination is unavailable.'
    if phase >= 18:
        states = dict.fromkeys(states, 'closed')
        message = 'Hour 18+: all segments are closed in the exercise; no route is available.'
    return states, destinations, baseline, message


def route(site, at=None, preset='archived', mode='archive', roads=None, destinations=None, **unknown):
    if unknown:
        raise ValueError('Unknown routing fields')
    sel = selection(at, preset, mode)
    if not isinstance(site, str) or site not in {p['id'] for p in points()}:
        raise ValueError('Unknown exercise site')
    roads = {} if roads is None else roads
    destinations = {} if destinations is None else destinations
    if not isinstance(roads, dict) or len(roads) > 100 or not isinstance(destinations, dict) or len(destinations) > 3:
        raise ValueError('Invalid or oversized routing overrides')
    if any(v not in ('open', 'closed', 'unknown') for v in roads.values()) or any(type(v) is not bool for v in destinations.values()):
        raise ValueError('Invalid road or destination state')
    if (roads or destinations) and mode != 'what_if':
        raise ValueError('Routing overrides require what_if mode')
    base = {**sel, 'site': site, 'notice': NOTICE, 'route': None, 'unrestricted': None,
            'assumed_speed_kmh': 30, 'provenance': 'Exercise restrictions, topology, speeds, access connectors and destinations.',
            'network': {'type': 'FeatureCollection', 'features': []}, 'destinations': [], 'excluded_roads': []}
    graph = load_graph()
    if not graph:
        if roads or destinations:
            raise ValueError('Cannot override an unavailable road network')
        return {**base, 'status': 'network_unavailable', 'message': 'County-validated road network not loaded. Run the public-data preparation script.'}
    if set(roads) - {e['id'] for e in graph['edges']} or set(destinations) - {d['id'] for d in graph['destinations']}:
        raise ValueError('Unknown road or exercise destination')
    states, available, baseline, message = states_for(graph, site, at or sel['at']) if mode == 'what_if' else (
        dict.fromkeys((e['id'] for e in graph['edges']), 'unknown'),
        dict.fromkeys((d['id'] for d in graph['destinations']), False), None,
        'Historical road restrictions and shelter opening records are not sourced. Switch to What-if exercise for simulated routing.')
    states.update(roads)
    available.update(destinations)
    features = [{'type': 'Feature', 'id': e['id'], 'geometry': {'type': 'LineString', 'coordinates': e['coordinates']},
                 'properties': {'id': e['id'], 'label': e['label'], 'kind': e['kind'], 'state': states[e['id']]}}
                for e in graph['edges']]
    destination_features = [{**d, 'available': available[d['id']], 'coordinates': graph['nodes'][d['node']]} for d in graph['destinations']]
    result = shortest(graph, graph['sites'][site], [d for d in graph['destinations'] if available[d['id']]], states) if mode == 'what_if' else None
    return {**base, 'status': ('ready' if result else 'no_route') if mode == 'what_if' else 'historical_conditions_unavailable',
            'route': result, 'unrestricted': baseline, 'network': {'type':'FeatureCollection', 'features': features},
            'destinations': destination_features, 'excluded_roads': [{'id': k, 'state': v, 'reason': f'Exercise segment {v}'} for k, v in states.items() if v != 'open'],
            'route_changed': bool(result and baseline and (result['edge_ids'] != baseline['edge_ids'] or result['destination'] != baseline['destination'])),
            'destination_changed': bool(result and baseline and result['destination'] != baseline['destination']),
            'source': graph['provenance'], 'message': message}
