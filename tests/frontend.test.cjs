// Source-only UI data flow without opening a browser or inspecting rendered visuals.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const h3 = require("../quasar/static/vendor/h3-js.umd.js");
const QuasarSpatial = require("../quasar/static/spatial.js");
const QuasarParcelCache = require("../quasar/static/parcel-cache.js");
const QuasarInspection = require("../quasar/static/inspection.js");
const {IDBFactory}=require("fake-indexeddb");

class Element {
  constructor(tag="div") { this.tag=tag; this.children=[]; this.style={}; this.value=""; this.checked=true; }
  append(...items) { this.children.push(...items); if (this.tag==="select" && !this.value) this.value=items[0].value; }
  replaceChildren(...items) { this.children=items; }
  setAttribute(name,value) { this[name]=value; }
  getAttribute(name) { return this[name]; }
}

async function boot({configured=false, forecastMode="county_archive", mixed=false, scenarioFailure=false, mounted=true, forecastStatus="ready", rainfall=15, riskScore=72, parcelFailure=false, countyWeather=false, parcelCount=101, cacheStorage, inspectionContext, holdPage, manifestFailure=false, holdManifest, pageTransform=page=>page, exposureScores=false, exposureFailure=false, holdExposure, exposureTransform=page=>page}={}) {
  const ids = new Map();
  let exposureRunId="synthetic-run", clock=Date.now(), archiveMissing=false;
  const exposureTimers=new Map();
  class Clock extends Date {static now(){return clock;}}
  const get = (id) => { if (!ids.has(id)) ids.set(id,new Element(id==="scenario" ? "select" : "div")); return ids.get(id); };
  get("map").parentElement = get("map-viewport");
  get("map-layer").value="rainfall";
  const data = {type:"FeatureCollection", county_fips:"12091", mode:forecastMode, notice:"Native forecast test fixture",
    scenario:{id:"isaias-2026",valid_from:"2026-10-09T05:00:00Z",valid_to:"2026-10-09T11:00:00Z"},
    forecast:{status:forecastStatus,init_time:"2026-10-09T05:00:00Z",retrieved_at:"2026-10-17T12:30:00Z",native_resolution:"0.1 degree"},features:[],
    weather_cells:{type:"FeatureCollection",retrieved_at:"2026-10-17T12:30:00Z",features:[
      {type:"Feature",id:"native-test-cell",geometry:{type:"Polygon",coordinates:[[[-86.6,30.4],[-86.4,30.4],[-86.4,30.6],[-86.6,30.6],[-86.6,30.4]]]},properties:{status:forecastStatus,rainfall_6h_mm:forecastStatus==="ready" ? rainfall : null}}
    ]}};
  let map, resizeCallback, resizeCount=0, observed;
  const events=[], requests=[];
  class FakeMap {
    constructor(options) { map=this; this.options=options; this.controls=[]; this.sources={}; this.layers={}; this.handlers={}; }
    resize() { resizeCount++; }
    getZoom() { return this.zoom ?? this.options.zoom; }
    flyTo(options) { this.zoom=options.zoom; this.lastFlight=options; }
    fitBounds(bounds,options) { this.lastBounds={bounds,options}; }
    getCanvas() { return {clientWidth:1200,style:{}}; }
    queryRenderedFeatures() { return []; }
    addControl(control) { this.controls.push(control); }
    addImage(id,image) { (this.images ||= {})[id]=image; }
    on(name,...rest) { this.handlers[`${name}:${rest.length===1 ? "" : rest[0]}`]=rest.at(-1); }
    addSource(id,source) { this.sources[id]={data:source.data,setData(data){this.data=data;}}; }
    getSource(id) { return this.sources[id]; }
    addLayer(layer) { this.layers[layer.id]=layer; }
    setPaintProperty(id,key,value) { this.layers[id].paint[key]=value; }
    setLayoutProperty(id,key,value) { this.layers[id][key]=value; }
  }
  const mapboxgl = {Map:FakeMap,NavigationControl:class {},AttributionControl:class { constructor(options) { this.options=options; } }};
  const context = {console,URLSearchParams,Date:Clock,document:{getElementById:(id)=>mounted ? get(id) : null,dispatchEvent:(event)=>events.push(event.type),createElement:(tag)=>new Element(tag),createTextNode:(text)=>({textContent:text})},
    Event:class { constructor(type) { this.type=type; } },
    window:{setTimeout:(fn,delay)=>{const id=Symbol();exposureTimers.set(id,{fn,delay});return id;},clearTimeout:id=>exposureTimers.delete(id),h3,QuasarSpatial,QuasarInspection,QuasarParcelCache:{create:options=>QuasarParcelCache.create({...options,storage:cacheStorage})},mapboxgl, ResizeObserver:class {
      constructor(callback) { resizeCallback=callback; }
      observe(element) { observed=element; }
    }},h3,QuasarSpatial,mapboxgl,
    fetch:async (url) => {
      requests.push(url);
      if (url.startsWith("/api/exposure?")) {
        if (exposureFailure) return {ok:false,json:async()=>({error:"synthetic exposure outage"})};
        if (!exposureScores) return {ok:true,json:async()=>({status:"not_configured",cells:{},parcels:{},message:"Exposure not configured"})};
        const params=new URLSearchParams(url.split("?")[1]), resolution=Number(params.get("resolution"));
        const cell=h3.latLngToCell(30.55,-86.485,resolution), runId=exposureRunId;
        const score=id=>runId==="second" ? (id===1?30:100) : (id===1?0:90);
        const page=exposureTransform({status:"ready",county_fips:"12091",run_id:runId,inventory_id:"snapshot",method_version:"synthetic-test-only",aggregation:"parcel_p90_linear",aggregation_architecture:"s390x",computed_at:new Date(clock).toISOString(),valid_to:new Date(clock+6*3600000).toISOString(),cells:{[cell]:{parcel_count:3,scored_count:2,unknown_count:1,coverage:2/3,incomplete:true,elevated_count:1,p90_score:runId==="second"?93:81}},parcels:Object.fromEntries((params.get("parcel_ids")||"").split(",").filter(Boolean).map(id=>[id,{score:score(Number(id)),factors:[{name:"synthetic_factor",value:score(Number(id)),contribution:score(Number(id))}],missing:[]}]))},params);
        if(holdExposure) await holdExposure(params);
        return {ok:true,json:async()=>page};
      }
      if(url==="/api/parcels/manifest") {
        if(holdManifest) await holdManifest();
        return {ok:!manifestFailure,json:async()=>manifestFailure ? {error:"source offline"} : {status:"ready",county_fips:"12091",source_mode:"indexed",source_url:"https://example.test/parcels",dataset_version:"snapshot:index",inventory_id:"snapshot",boundary_version:"boundary",crs:"EPSG:4326"}};
      }
      if(/\/api\/(parcels|cells)\/[^/]+\/(context|summary)/.test(url)) {
        const id=url.split("/")[3], isParcel=url.includes("/context");
        return {ok:!!inspectionContext,json:async()=>inspectionContext ? {...inspectionContext,status:"ready",county_fips:"12091",risk_score:null,...(isParcel?{parcel_id:Number(id)}:{cell_id:id})} : {error:"inputs not configured"}};
      }
      if (url.startsWith("/api/parcels?")) {
        const offset=Number(new URLSearchParams(url.split("?")[1]).get("offset"));
        if (parcelFailure) return {ok:false,json:async()=>({error:"GIS unavailable"})};
        if(holdPage) await holdPage(offset);
        const ids=parcelCount===101 ? [offset+1] : Array.from({length:Math.min(100,parcelCount-offset)},(_,i)=>offset+i+1);
        return {ok:true,json:async()=>pageTransform({type:"FeatureCollection",status:"ready",county_fips:"12091",inventory_id:"snapshot",dataset_version:"snapshot:index",features:ids.map(id=>({type:"Feature",id,geometry:{type:"Polygon",coordinates:[[[-86.49,30.55],[-86.489,30.55],[-86.489,30.551],[-86.49,30.55]]]},properties:{parcel_id:id,county_fips:"12091",risk_score:null,risk_band:"unknown"}})),source_total:parcelCount,checked_count:Math.min(offset+100,parcelCount),excluded_count:0,next_offset:offset+100>=parcelCount?null:offset+100,retrieved_at:"2026-10-09T05:00:00Z",source_url:"https://example.test/parcels",crs:"EPSG:4326"})};
      }
      if (url.startsWith("/api/weather/timeline?")) {
        if(scenarioFailure && url.includes("source=archive"))return {ok:false,json:async()=>({error:"forecast offline"})};
        return {ok:true,json:async()=>archiveMissing ? {county_fips:"12091",source:"archive",status:"not_configured",frames:[],default_index:0,message:"Archive not imported"} :
          {county_fips:"12091",source:"archive",status:forecastStatus,frames:[{at:data.scenario.valid_from,collection:data}],default_index:0}};
      }
      const body = url==="/api/county" ? {county_fips:"12091",type:"FeatureCollection",features:[{type:"Feature",geometry:{type:"Polygon",coordinates:[[[-86.6,30.4],[-86.4,30.4],[-86.4,30.6],[-86.6,30.6],[-86.6,30.4]]]}}]} : url==="/api/config" ? {map:{configured,public_token:"pk.test",style:"mapbox://styles/mapbox/satellite-streets-v12"}} :
        url==="/api/scenarios" ? {scenarios:[{id:"baseline",label:"Exercise hour 0"},...(mixed ? [{id:"weathernext",label:"WeatherNext 3 + fictional inputs"}] : [])]} :
        url==="/api/weather/status" ? {status:"not_configured",message:"import not connected"} :
        url==="/api/official-alerts" ? {message:"Not connected; not an all-clear"} : data;
      return {ok:true,json:async()=>body};
    }};
  await vm.runInNewContext(fs.readFileSync("quasar/static/app.js","utf8"),context);
  return {get,map,data,events,requests,setInspectionContext:value=>{inspectionContext=value;},setArchiveMissing:value=>{archiveMissing=value;},setExposureRunId:value=>{exposureRunId=value;},setExposureFailure:value=>{exposureFailure=value;},
    exposureTimerDelays:()=>[...exposureTimers.values()].map(t=>t.delay),
    expireExposure:()=>{const timer=[...exposureTimers.values()].find(t=>t.delay>=7200000);clock+=7200001;timer.fn();},
    mount:async()=>{mounted=true; await context.window.Quasar.start();},
    start:()=>context.window.Quasar.start(),
    resize:()=>resizeCallback(),
    get resizeCount(){return resizeCount;},
    get observed(){return observed;},
  };
}

test("missing map credentials leave source status usable without exercise requests",async()=>{
  const {get,map,requests}=await boot();
  assert.equal(map,undefined);assert.match(get("map-status").textContent,/MAPBOX_PUBLIC_TOKEN/);
  assert.equal(get("mode-badge").textContent,"ISAIAS · ARCHIVED FORECAST");
  assert.ok(requests.every(url=>!/^\/api\/(properties|scenarios|routes|timeline|notifications|replay)/.test(url)));
});

test("county-clipped H3 weather initializes when map loads after data",async()=>{
  const {map,get}=await boot({configured:true});map.handlers["load:"]();
  assert.equal(map.sources.hotspots.data.features.some(f=>f.properties.rainfall_mm!==null),true);
  assert.equal(map.sources.sites,undefined);assert.equal(map.sources["replay-network"],undefined);
  assert.ok(map.sources.hotspots.data.features.length>0);
  assert.equal(get("map-layer").value,"rainfall");
  assert.equal(map.layers["hotspot-fill"].paint["fill-opacity"][3],0.76);
  get("hex-toggle").checked=false;get("hex-toggle").onchange();
  assert.equal(map.layers["hotspot-outline"].visibility,"none");
});

test("source failure clears prior rainfall without restoring synthetic data",async()=>{
  const {map,get}=await boot({configured:true,scenarioFailure:true});map.handlers["load:"]();
  await get("forecast-retry").onclick();
  assert.equal(map.sources.hotspots.data.features.every(f=>f.properties.rainfall_mm===null),true);
  assert.match(get("error").textContent,/forecast offline/);
  assert.equal(get("mode-badge").textContent,"ARCHIVE UNAVAILABLE");
});

test("React can mount before the controller and starts are idempotent",async()=>{
  const app=await boot({mounted:false});assert.deepEqual(app.events,["quasar:ready"]);
  await app.mount();await app.start();assert.equal(app.requests.filter(url=>url.includes("/api/weather/timeline")).length,1);
});

test("sidebar width changes resize Mapbox while preserving H3 weather",async()=>{
  const app=await boot({configured:true});app.map.handlers["load:"]();app.resize();
  assert.equal(app.observed,app.get("map-viewport"));assert.equal(app.resizeCount,1);
  assert.equal(app.map.sources.hotspots.data.features.some(f=>f.properties.rainfall_mm!==null),true);
});

test("map attribution identifies actual source data",async()=>{
  const {map}=await boot({configured:true});
  assert.equal(map.options.style,"mapbox://styles/mapbox/satellite-streets-v12");
  assert.equal(map.options.cooperativeGestures,false);
  const attribution=map.controls.find(control=>control.options?.customAttribution);
  assert.match(attribution.options.customAttribution,/Okaloosa County source data/);
  assert.doesNotMatch(attribution.options.customAttribution,/fictional|synthetic/i);
});

test("unknown rainfall stays transparent and valid zero remains zero",async()=>{
  for(const options of [{forecastStatus:"stale",rainfall:22},{rainfall:null},{rainfall:0}]){
    const {map,get}=await boot({configured:true,...options});map.handlers["load:"]();
    const value=map.sources.hotspots.data.features.find(f=>f.properties.rainfall_mm!==null)?.properties.rainfall_mm ?? null;
    assert.equal(value,options.rainfall===0 ? 0 : null);
    assert.equal(map.layers["hotspot-fill"].paint["fill-opacity"][2],0);
    assert.match(get("map-data-source").textContent,/initialized.*imported.*0.1 degree/);
  }
});

test("coarse cells open summaries with explicit drill-down, and parcel panel returns to the cell", async()=>{
  const {map,get}=await boot({configured:true});map.handlers['load:']();
  assert.ok(map.sources.hotspots.data.features.length>1);
  const cell=h3.latLngToCell(30.55,-86.485,7);
  const click=resolution=>map.handlers['click:hotspot-fill']({point:{},features:[{properties:{h3_index:resolution===7?cell:h3.cellToParent(cell,resolution),resolution}}]});
  click(6);assert.equal(get('selection-title').textContent,'Cell overview');
  assert.equal(get('cell-zoom').hidden,false);
  get('cell-zoom').onclick();assert.equal(map.lastFlight.zoom,11.25);
  click(7);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(map.lastFlight.zoom,13.5);
  assert.equal(map.sources.parcels.data.features.length,2);
  assert.match(get('parcel-status').textContent,/All 101 source matches checked/);
  assert.equal(get('selection-content').children.length,2);
  get('selection-content').children[0].onclick();
  assert.equal(get('selection-title').textContent,'Parcel details');
  assert.equal(get('selection-back').hidden,false);
  assert.equal(map.sources['selected-parcel'].data.features.length,1);
  get('selection-back').onclick();
  assert.equal(get('selection-title').textContent,'Cell overview');
  assert.equal(get('selection-content').children.length,2);
  assert.equal(map.sources['selected-parcel'].data.features.length,0);
  get('selection-close').onclick();
  assert.equal(get('map-selection-panel').hidden,true);
  assert.equal(map.sources.parcels.data.features.length,0);
});

test("parcel failure is unavailable, and closing a selection discards late pages",async()=>{
  const {map,get}=await boot({configured:true,parcelFailure:true});map.handlers['load:']();
  const event={point:{},features:[{properties:{h3_index:h3.latLngToCell(30.55,-86.485,7),resolution:7}}]};
  map.handlers['click:hotspot-fill'](event);await new Promise(resolve=>setImmediate(resolve));
  assert.match(get('parcel-status').textContent,/unavailable or incomplete.*GIS unavailable/);
  assert.equal(get('parcel-retry').hidden,false);
  const other=await boot({configured:true});other.map.handlers['load:']();
  other.map.handlers['click:hotspot-fill'](event);
  other.get('selection-close').onclick();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(other.map.sources.parcels.data.features.length,0);
  assert.equal(other.get('map-selection-panel').hidden,true);
});

test("H3 rainfall replaces native rectangles and never paints stale values as zero", async () => {
  for (const status of ["ready","stale"]) {
    const {map,get} = await boot({configured:true,mixed:true,countyWeather:true,forecastStatus:status,rainfall:0});
    map.handlers["load:"]();
    assert.equal(map.sources["native-rainfall"],undefined);
    assert.equal(map.sources.hotspots.data.features.find(f=>f.properties.rainfall_mm!==null)?.properties.rainfall_mm ?? null,status==="ready" ? 0 : null);
    assert.match(get("map-data-values").textContent,/native cells available|Rainfall unavailable/);
    assert.match(get("map-data-source").textContent,/0.1 degree.*parcel flood risk/);
    get("map-layer").value="exposure";get("map-layer").onchange();
    assert.equal(map.layers["native-rainfall-fill"],undefined);
  }
});

async function until(predicate) {
  for(let i=0;i<1000;i++) {
    if(predicate()) return;
    await new Promise(resolve=>setImmediate(resolve));
  }
  assert.fail('Expected asynchronous UI state was never reached');
}
const parcelClick=(app,cell=h3.latLngToCell(30.55,-86.485,7))=>app.map.handlers['click:hotspot-fill']({point:{},features:[{properties:{h3_index:cell,resolution:7}}]});
const geometryRequests=app=>app.requests.filter(url=>url.startsWith('/api/parcels?'));

test('3,165 parcels load completely, render 50 rows, and restore across visits without geometry requests',async()=>{
  const storage=QuasarParcelCache.disk(new IDBFactory());
  const app=await boot({configured:true,parcelCount:3165,cacheStorage:storage});app.map.handlers['load:']();
  parcelClick(app);await until(()=>app.get('parcel-status').textContent.includes('All 3,165'));
  assert.equal(geometryRequests(app).length,32);
  assert.equal(app.map.sources.parcels.data.features.length,3165);
  assert.equal(app.get('selection-content').children.length,50);
  app.get('parcel-next').onclick();assert.match(app.get('parcel-page').textContent,/51–100/);
  app.get('parcel-search').value='3165';app.get('parcel-search').oninput();
  assert.equal(app.get('selection-content').children.length,1);
  app.get('selection-close').onclick();parcelClick(app);
  await until(()=>app.get('parcel-status').textContent.includes('All 3,165'));
  assert.equal(geometryRequests(app).length,32);
  const reloaded=await boot({configured:true,parcelCount:3165,cacheStorage:storage});reloaded.map.handlers['load:']();
  parcelClick(reloaded);await until(()=>reloaded.get('parcel-status').textContent.includes('All 3,165'));
  assert.equal(geometryRequests(reloaded).length,0);
  assert.equal(reloaded.get('selection-content').children.length,50);
});

test('closing during an in-flight page preserves progress and retry resumes rather than starting over',async()=>{
  const storage=QuasarParcelCache.disk(new IDBFactory());let release;
  const app=await boot({configured:true,parcelCount:250,cacheStorage:storage,holdPage:offset=>offset===100?new Promise(resolve=>release=resolve):Promise.resolve()});
  app.map.handlers['load:']();parcelClick(app);await until(()=>release);
  app.get('selection-close').onclick();release();
  // Wait until the abandoned page is actually committed, not just the first page.
  await until(()=>app.requests.some(url=>url.includes('offset=100')));
  const cell=h3.latLngToCell(30.55,-86.485,7);
  let saved;
  for(let i=0;i<1000;i++){saved=await QuasarParcelCache.create({storage}).get(cell);if(saved?.next_offset===200)break;await new Promise(r=>setImmediate(r));}
  assert.equal(saved.next_offset,200);assert.equal(app.map.sources.parcels.data.features.length,0);
  const revisit=await boot({configured:true,parcelCount:250,cacheStorage:storage});revisit.map.handlers['load:']();parcelClick(revisit);
  await until(()=>revisit.get('parcel-status').textContent.includes('All 250'));
  assert.equal(geometryRequests(revisit).length,1);assert.match(geometryRequests(revisit)[0],/offset=200/);
});

test('failed revalidation retains cached shapes with an explicit source-unavailable label',async()=>{
  const storage=QuasarParcelCache.disk(new IDBFactory());
  const first=await boot({configured:true,cacheStorage:storage});first.map.handlers['load:']();parcelClick(first);
  await until(()=>first.get('parcel-status').textContent.includes('All 101'));
  const offline=await boot({configured:true,cacheStorage:storage,manifestFailure:true});offline.map.handlers['load:']();parcelClick(offline);
  await until(()=>offline.get('parcel-status').textContent.includes('Source unavailable; cached inventory'));
  assert.equal(offline.map.sources.parcels.data.features.length,2);assert.equal(geometryRequests(offline).length,0);
});

test('cached shapes display before a slow source version check finishes',async()=>{
  const storage=QuasarParcelCache.disk(new IDBFactory());
  const first=await boot({configured:true,cacheStorage:storage});first.map.handlers['load:']();parcelClick(first);
  await until(()=>first.get('parcel-status').textContent.includes('All 101'));
  let release;const held=new Promise(resolve=>release=resolve);
  const next=await boot({configured:true,cacheStorage:storage,holdManifest:()=>held});next.map.handlers['load:']();parcelClick(next);
  await until(()=>next.map.sources.parcels.data.features.length===2);
  assert.match(next.get('parcel-status').textContent,/Checking source version/);
  assert.equal(geometryRequests(next).length,0);
  release();await until(()=>!next.get('parcel-status').textContent.includes('Checking source version'));
});

test('a prematurely completed page cannot claim the full inventory was checked',async()=>{
  const app=await boot({configured:true,pageTransform:page=>({...page,next_offset:null})});
  app.map.handlers['load:']();parcelClick(app);
  await until(()=>app.get('parcel-status').textContent.includes('unavailable or incomplete'));
  assert.doesNotMatch(app.get('parcel-status').textContent,/All 101/);
  assert.equal(app.map.sources.parcels.data.features.length,0);
});

test('selection survives zoom and source changes, and parcel details stay stable while pages arrive',async()=>{
  let release;
  const context={inventory_id:'snapshot',forecast_overlaps:[],inputs:{terrain:{status:'partial',min_m:0,mean_m:1,max_m:2}},parcel_count:250};
  const app=await boot({configured:true,parcelCount:250,inspectionContext:context,holdPage:offset=>offset===100?new Promise(resolve=>release=resolve):Promise.resolve()});
  app.map.handlers['load:']();parcelClick(app);await until(()=>release);
  app.get('selection-content').children[0].onclick();await new Promise(r=>setImmediate(r));
  assert.equal(app.get('selection-title').textContent,'Parcel details');
  app.map.zoom=8;app.map.handlers['zoomend:']();
  assert.equal(app.get('map-selection-panel').hidden,false);
  const before=geometryRequests(app).length;
  app.setArchiveMissing(true);await app.get('forecast-retry').onclick();
  assert.equal(geometryRequests(app).length,before);
  release();await until(()=>app.get('parcel-status').textContent.includes('All 250'));
  assert.equal(app.get('selection-title').textContent,'Parcel details');
  assert.equal(app.get('selection-content').children.length,1);
  assert.ok(app.get('selection-inputs').children.some(row=>row.children.some(node=>node.textContent?.includes('0.00 / 1.00 / 2.00'))));
});

test("unknown parcels and cells have transparent interiors and no hatch layers",async()=>{
  const {map,get}=await boot({configured:true});map.handlers['load:']();
  get('map-layer').value='exposure';get('map-layer').onchange();
  assert.equal(map.images,undefined);assert.equal(map.layers['hotspot-hatch'],undefined);assert.equal(map.layers['parcel-hatch'],undefined);
  assert.equal(map.layers['hotspot-fill'].paint['fill-opacity'][2],0);
  assert.equal(map.layers['parcel-fill'].paint['fill-opacity'][2],0);
  map.handlers['click:hotspot-fill']({point:{},features:[{properties:{h3_index:h3.latLngToCell(30.55,-86.485,7),resolution:7}}]});
  await new Promise(resolve=>setImmediate(resolve));
  assert.ok(map.sources.parcels.data.features.every(f=>f.properties.exposure_score===null));
  assert.equal(get('selection-score').textContent,'Unscored');
  assert.notEqual(map.layers['selected-parcel-outline'].paint['line-color'],map.layers['parcel-outline'].paint['line-color']);
});

test("server parcel indices and complete-inventory p90 drive colors and accessible inspection",async()=>{
  const app=await boot({configured:true,mixed:true,exposureScores:true});const {map,get}=app;map.handlers['load:']();
  await new Promise(resolve=>setImmediate(resolve));
  map.zoom=12;map.handlers['zoomend:']();
  await new Promise(resolve=>setImmediate(resolve));
  const cell=h3.latLngToCell(30.55,-86.485,7);
  const summary=map.sources.hotspots.data.features.find(f=>f.id===cell).properties;
  assert.equal(summary.exposure_score,81);
  assert.equal(summary.exposure_incomplete,true);
  map.handlers['click:hotspot-fill']({point:{},features:[{properties:{h3_index:cell,resolution:7}}]});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('selection-score').textContent,'81.0 / 100');
  assert.match(get('selection-exposure').children[0].textContent,/2\/3 parcels scored/);
  assert.deepEqual(Array.from(map.sources.parcels.data.features,f=>f.properties.exposure_score),[0,90]);
  get('selection-content').children[1].onclick();
  assert.equal(get('selection-score').textContent,'90.0 / 100');
  assert.ok(get('selection-exposure').children.some(node=>/synthetic_factor.*90.0/.test(node.textContent)));
  // A different hour retains cached geometry and inspection, but clears old indices.
  app.setArchiveMissing(true);await get('forecast-retry').onclick();
  assert.equal(map.sources.parcels.data.features.length,2);
  assert.equal(map.sources['selected-parcel'].data.features.length,1);
  assert.equal(get('selection-title').textContent,'Parcel details');
  assert.ok(map.sources.parcels.data.features.every(f=>f.properties.exposure_score===null));
  assert.equal(get('selection-stat-one').textContent,'Unknown');
});

// protects: hourly scores never enter the persistent geometry cache; fails_when: a late lookup recolors the next window; seam: none; no_claim: browser pixels or live LinuxONE.
test('late exposure lookups cannot recolor retained geometry after a scenario change',async()=>{
  let release;
  const app=await boot({configured:true,mixed:true,exposureScores:true,holdExposure:params=>params.has('parcel_ids')?new Promise(resolve=>{release=resolve;}):Promise.resolve()});
  app.map.handlers['load:']();parcelClick(app);await until(()=>release);
  app.setArchiveMissing(true);await app.get('forecast-retry').onclick();
  release();await new Promise(resolve=>setImmediate(resolve));
  assert.ok(app.map.sources.parcels.data.features.length>0);
  assert.ok(app.map.sources.parcels.data.features.every(f=>f.properties.exposure_score===null));
  assert.equal(app.get('map-selection-panel').hidden,false);
});

// protects: switching assessment runs replaces every cached index; fails_when: old indices are reused under a new run; seam: none; no_claim: real model accuracy.
test('a new server run replaces indices without reloading parcel geometry',async()=>{
  const app=await boot({configured:true,mixed:true,exposureScores:true});app.map.handlers['load:']();parcelClick(app);
  await until(()=>app.map.sources.parcels.data.features.some(f=>f.properties.exposure_score===90));
  const before=geometryRequests(app).length;
  app.setExposureRunId('second');app.map.zoom=8;app.map.handlers['zoomend:']();
  await until(()=>app.map.sources.parcels.data.features.some(f=>f.properties.exposure_score===100));
  assert.equal(geometryRequests(app).length,before);
  assert.deepEqual(Array.from(app.map.sources.parcels.data.features,f=>f.properties.exposure_score),[30,100]);
});

// protects: bounded lookup and unknown-state handling; fails_when: oversized lookup, missing record painted, or source error leaves prior colors; seam: none; no_claim: operational data completeness.
test('exposure lookups batch at 100 IDs and failures or missing assessments remain unknown',async()=>{
  const batched=await boot({configured:true,mixed:true,exposureScores:true,parcelCount:250});batched.map.handlers['load:']();parcelClick(batched);
  await until(()=>batched.map.sources.parcels.data.features.filter(f=>f.properties.exposure_score!==null).length===250);
  const requests=batched.requests.filter(url=>url.startsWith('/api/exposure?')&&url.includes('parcel_ids'));
  assert.ok(requests.length>=3);
  assert.ok(requests.every(url=>new URLSearchParams(url.split('?')[1]).get('parcel_ids').split(',').length<=100));
  for(const options of [
    {exposureFailure:true},
    {exposureTransform:page=>({...page,parcels:{}})},
    {exposureTransform:(page,params)=>params.has('parcel_ids')?{...page,run_id:'changed'}:page},
    {exposureTransform:page=>({...page,aggregation:'invalid-summary'})}
  ]) {
    const app=await boot({configured:true,mixed:true,exposureScores:true,...options});app.map.handlers['load:']();parcelClick(app);
    await until(()=>app.get('parcel-status').textContent.includes('All 101'));
    await new Promise(resolve=>setImmediate(resolve));
    assert.ok(app.map.sources.parcels.data.features.every(f=>f.properties.exposure_score===null));
  }
});

// protects: expired estimates revert to unknown without user navigation; fails_when: a cached current result survives two hours; seam: none; no_claim: real forecast accuracy; why_new: lifecycle expiry is distinct from forecast playback.
test('archived exposure does not expire against today while parcel geometry remains',async()=>{
  const app=await boot({configured:true,exposureScores:true});app.map.handlers['load:']();parcelClick(app);
  await until(()=>app.map.sources.parcels.data.features.some(f=>f.properties.exposure_score===90));
  assert.ok(app.requests.filter(url=>url.startsWith('/api/exposure?')).every(url=>url.includes('mode=replay')));
  assert.equal(app.get('map-selection-panel').hidden,false);
});

// protects: failed refresh cannot mix old parcel indices with a new run; fails_when: a recovered summary reuses prior assessments; seam: none; no_claim: browser rendering; why_new: recovery crosses two distinct API outcomes.
test('summary failure clears parcel indices before a different run recovers',async()=>{
  const app=await boot({configured:true,mixed:true,exposureScores:true});app.map.handlers['load:']();parcelClick(app);
  await until(()=>app.map.sources.parcels.data.features.some(f=>f.properties.exposure_score===90));
  const before=geometryRequests(app).length;
  app.setExposureFailure(true);app.map.zoom=8;app.map.handlers['zoomend:']();
  await until(()=>app.map.sources.parcels.data.features.every(f=>f.properties.exposure_score===null));
  app.setExposureFailure(false);app.setExposureRunId('second');app.map.zoom=6;app.map.handlers['zoomend:']();
  await until(()=>app.map.sources.parcels.data.features.some(f=>f.properties.exposure_score===100));
  assert.deepEqual(Array.from(app.map.sources.parcels.data.features,f=>f.properties.exposure_score),[30,100]);
  assert.equal(geometryRequests(app).length,before);
});

for (const forecastMode of ['county_archive', 'county_forecast']) {
test(`model inspection separates susceptibility and rainfall with ${forecastMode} expiry`,async()=>{
  const app=await boot({configured:true,forecastMode,mixed:true,exposureScores:true,exposureTransform:page=>({
    ...page,forecast_provenance:{init_time:'synthetic-init',retrieved_at:'synthetic-import',native_resolution:'0.1 degree',availability_basis:'initialization-based reconstruction',expires_at:new Date(Date.parse(page.computed_at)+60000).toISOString()},
    parcels:Object.fromEntries(Object.entries(page.parcels || {}).map(([id,record])=>[id,{...record,
      model_details:{susceptibility:.7,rainfall_6h_mm:50,rainfall_stress:.5,model_instability:.02,baseline:.6,attributions:{terrain_min_m:-.1,terrain_mean_m:.2}}}]))
  })});
  app.map.handlers['load:']();parcelClick(app);
  await until(()=>app.map.sources.parcels.data.features.some(f=>f.properties.exposure_score===90));
  app.get('selection-content').children[1].onclick();
  const text=app.get('selection-exposure').children.map(node=>node.textContent).join('\n');
  assert.match(text,/Model: synthetic-test-only/);
  assert.match(text,/Learned mapped susceptibility: 0.700/);
  assert.match(text,/FEMA mapping proxy, not observed flood skill/);
  assert.match(text,/Forecast rainfall: 50.0 mm/);
  assert.match(text,/not a confidence interval/);
  assert.match(text,/terrain_min_m: -0.1000/);
  if (forecastMode === "county_forecast") {
    assert.ok(app.exposureTimerDelays().some(delay=>delay>0 && delay<=60001));
  } else {
    assert.equal(app.exposureTimerDelays().length,0);
  }
});
}

test('H3 rainfall survives missing parcel context and refresh recovers prepared inputs',async()=>{
  const app=await boot({configured:true,rainfall:86.4});app.map.handlers['load:']();
  parcelClick(app);await until(()=>app.get('context-retry').hidden===false);
  assert.equal(app.get('selection-rainfall').textContent,'86.4');
  assert.match(app.get('context-status').textContent,/unavailable/);
  assert.equal(app.get('selection-stat-two').textContent,'Unknown');
  app.setInspectionContext({inventory_id:'snapshot',parcel_count:101,terrain_complete_count:90,fema_complete_count:101,forecast_overlaps:[]});
  await app.get('forecast-retry').onclick();
  assert.equal(app.get('selection-rainfall').textContent,'86.4');
  assert.equal(app.get('selection-stat-two').textContent,'90');
  assert.equal(app.get('context-retry').hidden,true);
  app.setArchiveMissing(true);await app.get('forecast-retry').onclick();
  assert.equal(app.get('selection-rainfall').textContent,'No rainfall data');
  assert.ok(app.map.sources.hotspots.data.features.every(f=>f.properties.rainfall_mm===null));
});
