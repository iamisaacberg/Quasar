/* H3 is an index/summary, not hydrologic downscaling or county containment. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.QuasarSpatial = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function aggregate(collection, h3, resolution = 7) {
    const groups = new Map();
    const points = collection.features.map((feature) => {
      const [lon, lat] = feature.geometry.coordinates;
      const cell = h3.latLngToCell(lat, lon, resolution);
      const p = feature.properties;
      if (!groups.has(cell)) groups.set(cell, {sites:[], scores:[], unknown:0});
      const group = groups.get(cell);
      group.sites.push(p.id);
      if (p.risk.score === null) group.unknown += 1;
      else group.scores.push(p.risk.score);
      return {...feature, properties:{...p, property_id:p.id, h3_index:cell, risk_band:p.risk.band, risk_score:p.risk.score}};
    });
    const cells = Array.from(groups, ([cell, group]) => {
      // The GeoJSON option puts longitude first. Close the ring explicitly.
      const boundary = h3.cellToBoundary(cell, true);
      if (boundary[0][0] !== boundary.at(-1)[0] || boundary[0][1] !== boundary.at(-1)[1]) boundary.push([...boundary[0]]);
      const max = group.scores.length ? Math.max(...group.scores) : null;
      return {type:"Feature", id:cell, geometry:{type:"Polygon", coordinates:[boundary]}, properties:{
        h3_index:cell, resolution, site_count:group.sites.length, unknown_count:group.unknown,
        scored_count:group.scores.length, max_score:max,
        mean_score:group.scores.length ? group.scores.reduce((a,b) => a+b,0)/group.scores.length : null,
        risk_band:max === null ? "unknown" : max >= 65 ? "elevated" : max >= 35 ? "moderate" : "lower_relative"
      }};
    });
    return {points:{...collection, features:points}, cells:{type:"FeatureCollection", features:cells}};
  }
  // Same zoom thresholds and click targets as TrialSmiles' zoomScoreCells.
  function resolutionForZoom(zoom) {
    return zoom < 6.75 ? 4 : zoom < 8.5 ? 5 : zoom < 10.75 ? 6 : 7;
  }
  function childZoom(resolution) { return resolution <= 4 ? 7.25 : resolution === 5 ? 9.25 : 11.25; }
  function countyCells(geometry, h3, resolution) {
    const polygons = geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates];
    // Overlap mode includes shorelines, islands and slivers whose centers fall outside the county.
    const indexes = new Set(polygons.flatMap(rings => h3.polygonToCellsExperimental(
      rings, resolution, h3.POLYGON_TO_CELLS_FLAGS.containmentOverlapping, true)));
    return {type:"FeatureCollection", features:Array.from(indexes, cell => ({
      type:"Feature", id:cell,
      geometry:{type:"Polygon", coordinates:[h3.cellToBoundary(cell, true)]},
      properties:{h3_index:cell, resolution, site_count:0, unknown_count:0, scored_count:0,
        max_score:null, mean_score:null, risk_band:"unknown"}
    }))};
  }
  function coverage(grid, collection, h3, resolution) {
    const occupied = new Map(aggregate(collection, h3, resolution).cells.features.map(f => [f.id, f.properties]));
    return {...grid, features:grid.features.map(f => ({...f, properties:occupied.get(f.id) || f.properties}))};
  }
  return {aggregate, resolutionForZoom, childZoom, countyCells, coverage};
});
