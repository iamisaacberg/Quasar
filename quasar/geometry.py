"""Small WGS84 county containment helpers, including complete line segments."""
import math


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def subtract(a, b):
    return a[0] - b[0], a[1] - b[1]


def position(p):
    return (isinstance(p, (list, tuple)) and len(p) == 2
            and all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in p)
            and -180 <= p[0] <= 180 and -90 <= p[1] <= 90)


def on_segment(p, a, b):
    return abs(cross(subtract(p, a), subtract(b, a))) < 1e-12 and all(
        min(a[i], b[i]) - 1e-12 <= p[i] <= max(a[i], b[i]) + 1e-12 for i in (0, 1))


def ring_location(p, ring):
    inside = False
    for a, b in zip(ring, ring[1:]):
        if on_segment(p, a, b):
            return 0
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return 1 if inside else -1


def polygons(geometry):
    if geometry.get('type') == 'Polygon':
        return [geometry['coordinates']]
    if geometry.get('type') == 'MultiPolygon':
        return geometry['coordinates']
    raise ValueError('County boundary must be Polygon or MultiPolygon')


def covers(p, geometry):
    if not position(p):
        return False
    return any(ring_location(p, rings[0]) >= 0 and all(ring_location(p, hole) <= 0 for hole in rings[1:])
               for rings in polygons(geometry))


def line_covered(coordinates, geometry):
    """Split segments at every ring intersection; test each resulting interval.

    Testing only vertices (or a fixed sampling distance) misses narrow holes and
    concavities. Collinear ring segments contribute their endpoint parameters.
    """
    if len(coordinates) < 2 or not all(covers(p, geometry) for p in coordinates):
        return False
    rings = [ring for polygon in polygons(geometry) for ring in polygon]
    for a, b in zip(coordinates, coordinates[1:]):
        direction = subtract(b, a)
        cuts = {0.0, 1.0}
        for ring in rings:
            for c, d in zip(ring, ring[1:]):
                edge = subtract(d, c)
                denominator = cross(direction, edge)
                if abs(denominator) > 1e-15:
                    t = cross(subtract(c, a), edge) / denominator
                    u = cross(subtract(c, a), direction) / denominator
                    if 0 <= t <= 1 and 0 <= u <= 1:
                        cuts.add(t)
                elif abs(cross(subtract(c, a), direction)) < 1e-12:
                    axis = 0 if abs(direction[0]) > abs(direction[1]) else 1
                    if direction[axis]:
                        for p in (c, d):
                            t = (p[axis]-a[axis])/direction[axis]
                            if 0 <= t <= 1:
                                cuts.add(t)
        cuts = sorted(cuts)
        for lo, hi in zip(cuts, cuts[1:]):
            mid = (lo+hi)/2
            if not covers([a[i]+mid*direction[i] for i in (0, 1)], geometry):
                return False
    return True


def distance_m(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def length_m(coordinates):
    return sum(distance_m(a, b) for a, b in zip(coordinates, coordinates[1:]))
