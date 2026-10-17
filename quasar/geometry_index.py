"""Indexed, complete county containment for batch acquisition and runtime validation."""
import math
from .geometry import covers as geometry_covers, position, polygons

BIN_SIZE = 0.002

class CountyBoundaryIndex:
    """Exact point/edge checks with spatial bins for countywide batches."""

    def __init__(self, geometry):
        self.polygons = []
        self.rings = []
        self.latitude_bins = {}
        self.spatial_bins = {}
        self.boundary_points = []
        for polygon in polygons(geometry):
            polygon_rings = []
            for ring in polygon:
                self.boundary_points.extend(ring[:-1])
                edges = list(zip(ring, ring[1:]))
                self.rings.append((ring, edges))
                polygon_rings.append((ring, edges))
                for edge_id, (a, b) in enumerate(edges):
                    edge = (ring, edge_id, a, b)
                    min_x, max_x = sorted((a[0], b[0]))
                    min_y, max_y = sorted((a[1], b[1]))
                    for y_bin in self._bins(min_y, max_y, 90):
                        self.latitude_bins.setdefault((id(ring), y_bin), []).append((a, b))
                    for x_bin in self._bins(min_x, max_x, 180):
                        for y_bin in self._bins(min_y, max_y, 90):
                            self.spatial_bins.setdefault((x_bin, y_bin), []).append(edge)
            self.polygons.append(polygon_rings)

    @staticmethod
    def _bins(lo, hi, offset):
        return range(math.floor((lo + offset) / BIN_SIZE), math.floor((hi + offset) / BIN_SIZE) + 1)

    @staticmethod
    def _bbox_overlap(bounds, a, b):
        return (max(a[0], b[0]) >= bounds[0] and min(a[0], b[0]) <= bounds[2]
                and max(a[1], b[1]) >= bounds[1] and min(a[1], b[1]) <= bounds[3])

    def _candidate_edges(self, bounds):
        cells = [(x, y) for x in self._bins(bounds[0], bounds[2], 180)
                 for y in self._bins(bounds[1], bounds[3], 90)]
        if len(cells) > 10000:
            return [(ring, i, a, b) for ring, edges in self.rings for i, (a, b) in enumerate(edges)]
        unique = {}
        for cell in cells:
            for edge in self.spatial_bins.get(cell, ()):
                unique[(id(edge[0]), edge[1])] = edge
        return list(unique.values())

    def _ring_location(self, point, ring, edges):
        x, y = point
        inside = False
        for a, b in self.latitude_bins.get((id(ring), math.floor((y + 90) / BIN_SIZE)), ()):
            cross = (x - a[0]) * (b[1] - a[1]) - (y - a[1]) * (b[0] - a[0])
            if abs(cross) < 1e-12 and all(min(a[i], b[i]) - 1e-12 <= point[i] <= max(a[i], b[i]) + 1e-12 for i in (0, 1)):
                return 0
            if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
        return 1 if inside else -1

    def covers(self, point):
        if not position(point):
            return False
        return any(
            self._ring_location(point, exterior, exterior_edges) >= 0
            and all(self._ring_location(point, hole, hole_edges) <= 0
                    for hole, hole_edges in polygon_rings[1:])
            for polygon_rings in self.polygons
            for exterior, exterior_edges in polygon_rings[:1]
        )

    def _line_inside(self, coordinates):
        if len(coordinates) < 2 or not all(self.covers(point) for point in coordinates):
            return False
        for a, b in zip(coordinates, coordinates[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            bounds = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            cuts = {0.0, 1.0}
            for _, _, c, d in self._candidate_edges(bounds):
                if not self._bbox_overlap(bounds, c, d):
                    continue
                ex, ey = d[0] - c[0], d[1] - c[1]
                denominator = dx * ey - dy * ex
                qx, qy = c[0] - a[0], c[1] - a[1]
                if abs(denominator) > 1e-15:
                    t = (qx * ey - qy * ex) / denominator
                    u = (qx * dy - qy * dx) / denominator
                    if 0 <= t <= 1 and 0 <= u <= 1:
                        cuts.add(t)
                elif abs(qx * dy - qy * dx) < 1e-12:
                    axis = 0 if abs(dx) > abs(dy) else 1
                    if (dx, dy)[axis]:
                        for point in (c, d):
                            t = (point[axis] - a[axis]) / (dx, dy)[axis]
                            if 0 <= t <= 1:
                                cuts.add(t)
            ordered = sorted(cuts)
            for lo, hi in zip(ordered, ordered[1:]):
                mid = (lo + hi) / 2
                if not self.covers([a[0] + mid * dx, a[1] + mid * dy]):
                    return False
        return True

    def covers_parcel(self, geometry):
        try:
            parts = polygons(geometry)
            if not parts:
                return False
            for part in parts:
                if not part or any(len(ring) < 4 or ring[0] != ring[-1]
                                   or not all(position(point) for point in ring) for ring in part):
                    return False
                points = [point for ring in part for point in ring]
                bounds = (min(p[0] for p in points), min(p[1] for p in points),
                          max(p[0] for p in points), max(p[1] for p in points))
                if not self.covers(part[0][0]):
                    return False
                near_border = any(self._bbox_overlap(bounds, a, b)
                                  for _, _, a, b in self._candidate_edges(bounds))
                if near_border and not all(self._line_inside(ring) for ring in part):
                    return False
            if any(geometry_covers(hole[0], geometry)
                   for poly in self.polygons for hole, _ in poly[1:]):
                return False
            return True
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return False

    def intersects_parcel(self, geometry):
        """Check remaining boundary cases where a parcel crosses county edges."""
        try:
            parts = polygons(geometry)
            if not parts or any(not part or any(len(ring) < 4 or ring[0] != ring[-1]
                                                or not all(position(point) for point in ring) for ring in part)
                                for part in parts):
                return False
            if any(self.covers(point) for part in parts for point in part[0]):
                return True
            if any(geometry_covers(point, geometry) for point in self.boundary_points):
                return True

            def orient(a, b, c):
                return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

            def on_segment(a, b, point):
                return (abs(orient(a, b, point)) < 1e-12
                        and all(min(a[i], b[i]) - 1e-12 <= point[i] <= max(a[i], b[i]) + 1e-12 for i in (0, 1)))

            def segments_intersect(a, b, c, d):
                ab_c, ab_d = orient(a, b, c), orient(a, b, d)
                cd_a, cd_b = orient(c, d, a), orient(c, d, b)
                return (((ab_c > 0 and ab_d < 0) or (ab_c < 0 and ab_d > 0))
                        and ((cd_a > 0 and cd_b < 0) or (cd_a < 0 and cd_b > 0))
                        or on_segment(a, b, c) or on_segment(a, b, d)
                        or on_segment(c, d, a) or on_segment(c, d, b))

            for part in parts:
                for ring in part:
                    for a, b in zip(ring, ring[1:]):
                        bounds = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
                        for _, _, c, d in self._candidate_edges(bounds):
                            if self._bbox_overlap(bounds, c, d) and segments_intersect(a, b, c, d):
                                return True
            return False
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return False
