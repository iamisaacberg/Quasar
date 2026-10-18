const {test}=require('node:test');
const assert=require('node:assert/strict');
const {forecastRows,parcelRows}=require('../quasar/static/inspection.js');
const geometry={type:'Polygon',coordinates:[[[0,0],[1,0],[1,1],[0,0]]]};
const context={forecast_overlaps:[{native_cell_id:'a',geometry,area_fraction:.4},{native_cell_id:'b',geometry,area_fraction:.6}],
 inputs:{terrain:{status:'no_pixel_centers',min_m:null,mean_m:null,max_m:null,representative_point_m:0},fema:{status:'partial',mapped_area_fraction:.3,unmapped_area_fraction:.7,zones:['AE','X'],overlaps:[{FLD_ZONE:'X',ZONE_SUBTY:'AREA OF MINIMAL FLOOD HAZARD',parcel_area_fraction:.2}]}}};
function current(status='ready',rain=0){return {mode:'mixed_forecast_demo',forecast:{init_time:'init'},weather_cells:{valid_from:'start',valid_to:'end',retrieved_at:'import',native_resolution:'0.1 degree',features:[{id:'a',geometry,properties:{status,rainfall_6h_mm:rain}},{id:'b',geometry,properties:{status:'incomplete',rainfall_6h_mm:null}}]}};}
test('native overlaps remain separate; valid zero, missing and stale rainfall differ',()=>{
 const rows=forecastRows(context,current());assert.match(rows[0][1],/^0.0 mm/);assert.match(rows[1][1],/incomplete/);
 assert.match(forecastRows(context,current('stale',0))[0][1],/Unavailable.*stale/);
 assert.match(forecastRows(context,{mode:'synthetic_demo'})[0][1],/Exercise rainfall is not applied/);
 const changed=current();changed.weather_cells.features[0].geometry={type:'Polygon',coordinates:[]};
 assert.match(forecastRows(context,changed)[0][1],/not matched/);
});
test('changing replay values updates context without a geometry join or score',()=>{
 assert.match(forecastRows(context,current('ready',7))[0][1],/^7.0 mm/);
 const replay={...current('ready',12),mode:'what_if_exercise'};
 assert.match(forecastRows(context,replay)[0][1],/^12.0 mm/);
 assert.match(forecastRows(context,replay).at(-1)[1],/synthetic what-if/);
});
test('partial FEMA, X subtypes and a zero point sample do not fill polygon terrain or establish safety',()=>{
 const rows=parcelRows(context,current()), byLabel=new Map(rows);
 assert.match(byLabel.get('Terrain minimum / mean / maximum'),/Unknown \/ Unknown \/ Unknown/);
 assert.equal(byLabel.get('Interior point sample (separate)'),'0.00 m');
 assert.equal(byLabel.get('FEMA mapped / unmapped'),'30.00% / 70.00%');
 assert.ok(rows.some(([label])=>label.includes('AREA OF MINIMAL')));
 assert.equal(byLabel.get('Hydrologic connectivity / gauge linkage'),'Unknown; mapped proximity is descriptive only');
});

test('parcel rainfall headline preserves zero, partial overlap and geometry mismatches',()=>{
 const {rainfallSummary}=require('../quasar/static/inspection.js');
 const partial=rainfallSummary(context,current());
 assert.equal(partial.value,'0.0');assert.match(partial.detail,/1\/2.*Partial coverage/);
 assert.equal(rainfallSummary(context,current('stale',4)).value,'Unavailable');
 const both=current();both.weather_cells.features[1].properties={status:'ready',rainfall_6h_mm:12};
 assert.equal(rainfallSummary(context,both).value,'0.0–12.0');
 both.weather_cells.features[1].geometry={type:'Polygon',coordinates:[]};
 assert.equal(rainfallSummary(context,both).value,'0.0');
 assert.equal(rainfallSummary(null,current()).value,'Unavailable');
});
