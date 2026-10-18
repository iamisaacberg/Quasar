const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const h3 = require("../quasar/static/vendor/h3-js.umd.js");
const {aggregate} = require("../quasar/static/spatial.js");

test("exposure labels use fixed thresholds, smooth colors and a distinct unknown", () => {
  const {exposureBand,exposureColor,exposureExpression}=require('../quasar/static/spatial.js');
  assert.deepEqual([0,34,35,64,65,84,85,100].map(x=>exposureBand(x).key),
    ['lower_relative','lower_relative','moderate','moderate','elevated','elevated','highest','highest']);
  assert.deepEqual([0,35,65,85,100].map(exposureColor),['#16a34a','#eab308','#f97316','#dc2626','#dc2626']);
  assert.notEqual(exposureColor(50),exposureColor(51));
  for (const x of [null,undefined,NaN,Infinity,-1,101,'85',true]) {
    assert.equal(exposureBand(x).key,'unknown');
    assert.equal(exposureColor(x),'#9ca3af');
  }
  const expression=exposureExpression('exposure_score');
  assert.equal(expression[0],'case');
  assert.equal(expression[2][0],'interpolate');
  assert.equal(expression[2][1][0],'linear');
});

test("parcel colors use their own assessment and cell colors use server p90 only", () => {
  const {exposureFeature,exposureCoverage}=require('../quasar/static/spatial.js');
  const parcel={id:1,properties:{risk_score:null,risk_band:'unknown'}};
  assert.equal(exposureFeature(parcel,{score:0,missing:[]}).properties.exposure_score,0);
  assert.equal(exposureFeature(parcel,{score:90,missing:['terrain']}).properties.exposure_score,null);
  assert.equal(exposureFeature(parcel,null).properties.exposure_incomplete,true);
  const grid={features:[{id:'a',properties:{}},{id:'b',properties:{}}]};
  const output=exposureCoverage(grid,{a:{p90_score:81,parcel_count:100,scored_count:20,incomplete:true}});
  assert.equal(output.features[0].properties.exposure_score,81);
  assert.equal(output.features[0].properties.exposure_incomplete,true);
  assert.equal(output.features[1].properties.exposure_score,null);
  assert.equal(output.features[1].properties.exposure_incomplete,true);
  assert.equal(parcel.properties.exposure_score,undefined);
});

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

const rectangle=(x0,y0,x1,y1)=>({type:'Polygon',coordinates:[[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]});
const weatherCell=(id,geometry,rain,status='ready')=>({type:'Feature',id,geometry,properties:{status,rainfall_6h_mm:rain}});
test('county clipping preserves holes and islands and leaves no H3 area outside the boundary',()=>{
  const {countyCells}=require('../quasar/static/spatial.js');
  const clipping=require('polygon-clipping');
  const outer=rectangle(-86.6,30.4,-86.4,30.6).coordinates;
  const hole=rectangle(-86.54,30.46,-86.48,30.52).coordinates[0];
  const county={type:'MultiPolygon',coordinates:[[outer[0],hole],rectangle(-86.7,30.7,-86.69,30.71).coordinates]};
  for(const resolution of [4,5,6,7]) {
    const grid=countyCells(county,h3,resolution);
    assert.ok(grid.features.length>0);
    for(const hex of grid.features) assert.deepEqual(clipping.difference(hex.geometry.coordinates,county.coordinates),[]);
    const union=clipping.union(...grid.features.map(f=>f.geometry.coordinates));
    assert.deepEqual(clipping.difference(county.coordinates,union),[]);
  }
});
test('H3 weather uses maximum overlapping native rainfall and retains the original geometries',()=>{
  const {rainfallCoverage}=require('../quasar/static/spatial.js');
  const grid={type:'FeatureCollection',features:[{id:'hex',geometry:rectangle(0,0,2,1),properties:{}}]};
  const cells={features:[weatherCell('west',rectangle(0,0,1,1),10),weatherCell('east',rectangle(1,0,2,1),25),weatherCell('touch',rectangle(2,0,3,1),99)]};
  const p=rainfallCoverage(grid,cells).features[0].properties;
  assert.equal(p.rainfall_mm,25);
  assert.deepEqual(p.forecast_overlaps.map(o=>o.native_cell_id),['west','east']);
  assert.deepEqual(p.forecast_overlaps[0].geometry,cells.features[0].geometry);
  assert.equal(p.forecast_coverage_complete,true);
  assert.equal(grid.features[0].properties.rainfall_mm,undefined);
  // Same geometries, next hour: joins are reused but rainfall is not cached.
  cells.features[1].properties.rainfall_6h_mm=0;
  assert.equal(rainfallCoverage(grid,cells).features[0].properties.rainfall_mm,10);
});
test('partial geometry, stale, missing and invalid hours never paint known H3 rainfall; zero does',()=>{
  const {rainfallCoverage}=require('../quasar/static/spatial.js');
  const geometry=rectangle(0,0,2,1), grid={features:[{id:'hex',geometry,properties:{}}]};
  const get=cells=>rainfallCoverage(grid,{features:cells}).features[0].properties;
  assert.equal(get([weatherCell('a',geometry,0)]).rainfall_mm,0);
  for(const value of [null,undefined,NaN,Infinity,-1,'5']) assert.equal(get([weatherCell('a',geometry,value)]).rainfall_mm,null);
  assert.equal(get([weatherCell('a',geometry,12,'stale')]).rainfall_mm,null);
  assert.equal(get([weatherCell('a',geometry,12,'incomplete')]).rainfall_mm,null);
  assert.equal(get([]).rainfall_mm,null);
  const partial=get([weatherCell('a',rectangle(0,0,1,1),12)]);
  assert.equal(partial.rainfall_mm,null);assert.equal(partial.forecast_coverage_complete,false);
  const missing=get([weatherCell('a',rectangle(0,0,1,1),12),weatherCell('b',rectangle(1,0,2,1),null,'incomplete')]);
  assert.equal(missing.rainfall_mm,null);assert.equal(missing.rainfall_available,1);
  // Changing source geometry with the same ID invalidates the geometry join.
  assert.equal(get([weatherCell('a',rectangle(3,0,4,1),12)]).rainfall_total,0);
});
