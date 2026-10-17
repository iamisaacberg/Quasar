const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const h3 = require("../quasar/static/vendor/h3-js.umd.js");
const {aggregate} = require("../quasar/static/spatial.js");

function point(id, score, lat=30.55, lon=-86.485) {
  return {type:"Feature", id, geometry:{type:"Point", coordinates:[lon,lat]},
    properties:{id, risk:{score, band:score === null ? "unknown" : "elevated"}}};
}

test("H3 buckets nearby sites, excludes unknowns from statistics and preserves provenance", () => {
  const input = {type:"FeatureCollection", mode:"synthetic_demo", features:[point("a",80),point("b",40),point("c",null)]};
  const result = aggregate(input,h3);
  assert.equal(result.cells.features.length,1);
  const cell = result.cells.features[0];
  assert.equal(cell.properties.site_count,3);
  assert.equal(cell.properties.unknown_count,1);
  assert.equal(cell.properties.mean_score,60);
  assert.equal(cell.properties.max_score,80);
  assert.equal(cell.properties.risk_band,"elevated");
  assert.equal(result.points.mode,"synthetic_demo");
  assert.equal(result.points.features[0].properties.h3_index,h3.latLngToCell(30.55,-86.485,7));
  assert.equal(input.features[0].properties.h3_index,undefined);
});

test("GeoJSON hexagon uses longitude first and a closed ring", () => {
  const cell = aggregate({features:[point("a",null)]},h3).cells.features[0];
  const ring = cell.geometry.coordinates[0];
  assert.deepEqual(ring[0],ring.at(-1));
  assert.ok(ring.every(([lon,lat]) => lon < -86 && lat > 30 && lat < 32));
  assert.equal(cell.properties.max_score,null);
  assert.equal(cell.properties.mean_score,null);
  assert.equal(cell.properties.risk_band,"unknown");
});

test("distant sites remain in distinct cells and no empty-area cells are invented", () => {
  const result = aggregate({features:[point("a",70),point("b",60,30.174,-86.778)]},h3);
  assert.equal(result.cells.features.length,2);
  assert.equal(aggregate({features:[]},h3).cells.features.length,0);
});

test("vendored H3 matches the pinned npm artifact", () => {
  assert.equal(fs.readFileSync(require.resolve("h3-js/dist/h3-js.umd.js"),"utf8"),
    fs.readFileSync("quasar/static/vendor/h3-js.umd.js","utf8"));
});

test('zoom thresholds match TrialSmiles and county grid includes unoccupied areas and coastal slivers',()=>{
  const {resolutionForZoom,childZoom,countyCells,coverage}=require('../quasar/static/spatial.js');
  assert.deepEqual([6,7,9,11].map(resolutionForZoom),[4,5,6,7]);
  assert.deepEqual([4,5,6].map(childZoom),[7.25,9.25,11.25]);
  const ring=[[-86.6,30.4],[-86.4,30.4],[-86.4,30.6],[-86.6,30.6],[-86.6,30.4]];
  const grid=countyCells({type:'Polygon',coordinates:[ring]},h3,7);
  assert.ok(grid.features.length>20);
  const filled=coverage(grid,{features:[point('a',70)]},h3,7);
  assert.equal(filled.features.filter(f=>f.properties.site_count===1).length,1);
  assert.ok(filled.features.some(f=>f.properties.site_count===0 && f.properties.max_score===null));
  assert.ok(filled.features.every(f=>f.geometry.coordinates[0][0][0]===f.geometry.coordinates[0].at(-1)[0]));
  // A tiny island crossing a hex corner must not disappear in center-only filling.
  const tiny=[[[-86.5,30.5],[-86.49999,30.5],[-86.49999,30.50001],[-86.5,30.5]]];
  assert.ok(countyCells({type:'MultiPolygon',coordinates:[tiny,tiny]},h3,7).features.length>=1);
});
