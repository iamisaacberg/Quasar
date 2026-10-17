// Exercise UI data flow without opening a browser or inspecting rendered visuals.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const h3 = require("../quasar/static/vendor/h3-js.umd.js");
const QuasarSpatial = require("../quasar/static/spatial.js");

class Element {
  constructor(tag="div") { this.tag=tag; this.children=[]; this.style={}; this.value=""; this.checked=true; }
  append(...items) { this.children.push(...items); if (this.tag==="select" && !this.value) this.value=items[0].value; }
  replaceChildren(...items) { this.children=items; }
  setAttribute(name,value) { this[name]=value; }
  getAttribute(name) { return this[name]; }
}

async function boot({configured=false, mixed=false, scenarioFailure=false, mounted=true, forecastStatus="ready", rainfall=15, riskScore=72, parcelFailure=false, countyWeather=false}={}) {
  const ids = new Map();
  const get = (id) => { if (!ids.has(id)) ids.set(id,new Element(id==="scenario" ? "select" : "div")); return ids.get(id); };
  const data = {type:"FeatureCollection", mode:mixed ? "mixed_forecast_demo" : "synthetic_demo", notice:"demo notice",
    scenario:{id:mixed ? "weathernext" : "baseline",rainfall_6h_mm:15,valid_from:"2026-10-17T12:00:00Z",valid_to:"2026-10-17T18:00:00Z"},
    forecast:mixed ? {status:forecastStatus,init_time:"2026-10-17T12:00:00Z",retrieved_at:"2026-10-17T12:30:00Z",native_resolution:"0.1 degree"} : null,
    features:[{type:"Feature",id:"demo-001",geometry:{type:"Point",coordinates:[-86.485,30.55]},
      properties:{id:"demo-001",label:"Fictional site",risk:{score:riskScore,band:"elevated",factors:[],missing:[]},
        ...(mixed ? {forecast:{status:forecastStatus,available_hours:6,rainfall_6h_mm:rainfall}} : {})}}]};
  if (countyWeather) data.weather_cells = {type:"FeatureCollection",retrieved_at:"2026-10-17T12:30:00Z",features:[
    {type:"Feature",id:"native-test-cell",geometry:{type:"Polygon",coordinates:[[[-86.6,30.5],[-86.5,30.5],[-86.5,30.6],[-86.6,30.5]]]},properties:{status:forecastStatus,rainfall_6h_mm:forecastStatus==="ready" ? rainfall : null}}
  ]};
  let map, resizeCallback, resizeCount=0, observed;
  const events=[];
  class FakeMap {
    constructor(options) { map=this; this.options=options; this.controls=[]; this.sources={}; this.layers={}; this.handlers={}; }
    resize() { resizeCount++; }
    getZoom() { return this.zoom ?? this.options.zoom; }
    flyTo(options) { this.zoom=options.zoom; this.lastFlight=options; }
    fitBounds(bounds,options) { this.lastBounds={bounds,options}; }
    getCanvas() { return {clientWidth:1200,style:{}}; }
    queryRenderedFeatures() { return []; }
    addControl(control) { this.controls.push(control); }
    on(name,...rest) { this.handlers[`${name}:${rest.length===1 ? "" : rest[0]}`]=rest.at(-1); }
    addSource(id,source) { this.sources[id]={data:source.data,setData(data){this.data=data;}}; }
    getSource(id) { return this.sources[id]; }
    addLayer(layer) { this.layers[layer.id]=layer; }
    setPaintProperty(id,key,value) { this.layers[id].paint[key]=value; }
    setLayoutProperty(id,key,value) { this.layers[id][key]=value; }
  }
  const mapboxgl = {Map:FakeMap,NavigationControl:class {},AttributionControl:class { constructor(options) { this.options=options; } }};
  const context = {console,URLSearchParams,document:{getElementById:(id)=>mounted ? get(id) : null,dispatchEvent:(event)=>events.push(event.type),createElement:(tag)=>new Element(tag),createTextNode:(text)=>({textContent:text})},
    Event:class { constructor(type) { this.type=type; } },
    window:{h3,QuasarSpatial,mapboxgl, ResizeObserver:class {
      constructor(callback) { resizeCallback=callback; }
      observe(element) { observed=element; }
    }},h3,QuasarSpatial,mapboxgl,
    fetch:async (url) => {
      if (url.startsWith("/api/parcels?")) {
        const offset=Number(new URLSearchParams(url.split("?")[1]).get("offset"));
        if (parcelFailure) return {ok:false,json:async()=>({error:"GIS unavailable"})};
        return {ok:true,json:async()=>({type:"FeatureCollection",status:"ready",features:[{type:"Feature",id:offset+1,geometry:{type:"Polygon",coordinates:[[[-86.49,30.55],[-86.489,30.55],[-86.489,30.551],[-86.49,30.55]]]},properties:{parcel_id:offset+1,folio:`folio-${offset+1}`,risk_score:null}}],source_total:101,checked_count:offset ? 101 : 100,excluded_count:0,next_offset:offset ? null : 100,retrieved_at:"2026-10-17T12:00:00Z",county_boundary_retrieved_at:"2026-10-17T10:00:00Z"})};
      }
      if (scenarioFailure && url.includes("scenario=bad")) return {ok:false,json:async()=>({error:"bad scenario"})};
      const body = url==="/api/county" ? {county_fips:"12091",type:"FeatureCollection",features:[{type:"Feature",geometry:{type:"Polygon",coordinates:[[[-86.6,30.4],[-86.4,30.4],[-86.4,30.6],[-86.6,30.6],[-86.6,30.4]]]}}]} : url==="/api/config" ? {map:{configured,public_token:"pk.test",style:"mapbox://styles/mapbox/satellite-streets-v12"}} :
        url==="/api/scenarios" ? {scenarios:[{id:"baseline",label:"Exercise hour 0"},...(mixed ? [{id:"weathernext",label:"WeatherNext 3 + fictional inputs"}] : [])]} :
        url==="/api/weather/status" ? {status:"not_configured",message:"import not connected"} :
        url==="/api/official-alerts" ? {message:"Not connected; not an all-clear"} : data;
      return {ok:true,json:async()=>body};
    }};
  await vm.runInNewContext(fs.readFileSync("quasar/static/app.js","utf8"),context);
  return {get,map,data,events,
    mount:async()=>{mounted=true; await context.window.Quasar.start();},
    start:()=>context.window.Quasar.start(),
    resize:()=>resizeCallback(),
    get resizeCount(){return resizeCount;},
    get observed(){return observed;},
  };
}

test("without a Mapbox token the table, details and synthetic notification controls still work", async () => {
  const {get,map} = await boot();
  assert.equal(map,undefined);
  assert.equal(get("sites").children.length,1);
  assert.equal(get("detail-heading").textContent,"Fictional site");
  assert.match(get("map-status").textContent,/MAPBOX_PUBLIC_TOKEN/);
  assert.ok(get("detail").children.some((child)=>child.tag==="button"));
});

test("Mapbox receives current sites and H3 polygons even when map loads after API data", async () => {
  const {map,get} = await boot({configured:true});
  map.handlers["load:"]();
  assert.equal(map.sources.sites.data.features.length,1);
  assert.equal(map.sources.hotspots.data.features[0].geometry.type,"Polygon");
  assert.equal(map.layers["site-points"].type,"circle");
  get("hex-toggle").checked=false;
  get("hex-toggle").onchange();
  assert.equal(map.layers["hotspot-fill"].visibility,"none");
});

test("mixed WeatherNext mode stays labeled and cannot expose synthetic notification controls", async () => {
  const {get} = await boot({mixed:true});
  assert.equal(get("mode-badge").textContent,"MIXED DEMO");
  assert.equal(get("detail").children.some((child)=>child.tag==="button"),false);
  assert.match(get("weather-status").textContent,/0.1 degree/);
});

test("failed scenario fetch restores selector to the displayed scenario", async () => {
  const {get} = await boot({scenarioFailure:true});
  get("scenario").value="bad";
  await get("scenario").onchange();
  assert.equal(get("scenario").value,"baseline");
  assert.match(get("error").textContent,/bad scenario/);
});


test("React shell can mount before starting the controller, and repeated starts do not duplicate sites", async () => {
  const app = await boot({mounted:false});
  assert.deepEqual(app.events,["quasar:ready"]);
  assert.equal(app.get("sites").children.length,0);
  await app.mount();
  assert.equal(app.get("sites").children.length,1);
  assert.equal(app.get("detail-heading").textContent,"Fictional site");
  await app.start();
  assert.equal(app.get("scenario").children.length,1);
  assert.equal(app.get("sites").children.length,1);
});

test("changing the shell content width resizes Mapbox without replacing its sources", async () => {
  const app = await boot({configured:true});
  app.map.handlers["load:"]();
  assert.equal(app.observed,app.get("map"));
  app.resize();
  assert.equal(app.resizeCount,1);
  assert.equal(app.map.sources.sites.data.features.length,1);
});


test("the map uses the configured satellite style, direct gestures and visible demo attribution", async () => {
  const {map} = await boot({configured:true});
  assert.equal(map.options.style,"mapbox://styles/mapbox/satellite-streets-v12");
  assert.equal(map.options.cooperativeGestures,false);
  const attribution=map.controls.find(control=>control.options?.customAttribution);
  assert.equal(attribution.options.compact,false);
  assert.match(attribution.options.customAttribution,/DEMO.*Fictional sites.*synthetic site inputs/);
});


test("WeatherNext opens as rainfall with units, timing, labels and a neutral browsing grid", async () => {
  const {map,get} = await boot({configured:true,mixed:true});
  map.handlers["load:"]();
  assert.equal(get("scenario").value,"weathernext");
  assert.equal(get("map-layer").value,"rainfall");
  assert.match(get("map-data-title").textContent,/WeatherNext 3.*mm \/ 6h/);
  assert.match(get("map-data-source").textContent,/initialized 2026-10-17T12:00:00Z.*imported 2026-10-17T12:30:00Z.*0.1 degree/);
  assert.match(get("window").textContent,/Forecast window/);
  assert.equal(map.sources.sites.data.features[0].properties.rainfall_label,"15.0 mm");
  assert.equal(map.layers["rainfall-labels"].visibility,"visible");
  assert.equal(map.layers["hotspot-fill"].visibility,"visible");
  assert.equal(map.layers["hotspot-fill"].paint["fill-color"],"#b9c9cd");
  assert.equal(get("rainfall-legend").hidden,false);
  get("map-layer").value="exposure";get("map-layer").onchange();
  assert.equal(map.layers["rainfall-labels"].visibility,"none");
  assert.equal(map.layers["hotspot-fill"].visibility,"visible");
  assert.equal(get("exposure-legend").hidden,false);
});

test("stale and missing rainfall remain unavailable; zero rain and missing terrain stay separate", async () => {
  for (const args of [{forecastStatus:"stale",rainfall:22},{rainfall:null}]) {
    const {map,get}=await boot({configured:true,mixed:true,...args});map.handlers["load:"]();
    assert.equal(map.sources.sites.data.features[0].properties.rainfall_mm,null);
    assert.equal(map.sources.sites.data.features[0].properties.rainfall_label,"Unavailable");
    assert.match(get("map-data-values").textContent,/Rainfall unavailable at all/);
  }
  const {map,get}=await boot({configured:true,mixed:true,rainfall:0,riskScore:null});map.handlers["load:"]();
  assert.equal(map.sources.sites.data.features[0].properties.rainfall_label,"0.0 mm");
  assert.equal(get("sites").children[0].children[1].textContent,"Unknown");
  assert.equal(get("sites").children[0].children[3].textContent,"0.0");
  assert.match(get("map-data-values").textContent,/1\/1 sampled sites/);
});

test("map inspection opens on site selection and can close without leaving the map", async () => {
  const {get}=await boot();
  get("map-site").value="demo-001";get("map-site").onchange();
  assert.equal(get("map-inspect-toggle")["aria-expanded"],"true");
  get("map-inspect-toggle").onclick();
  assert.equal(get("map-inspect-toggle")["aria-expanded"],"false");
});

test("coarse cells drill down, R7 loads every parcel page, and property panel returns to the cell", async()=>{
  const {map,get}=await boot({configured:true});map.handlers['load:']();
  assert.ok(map.sources.hotspots.data.features.length>1);
  const cell=h3.latLngToCell(30.55,-86.485,7);
  const click=resolution=>map.handlers['click:hotspot-fill']({point:{},features:[{properties:{h3_index:resolution===7?cell:h3.cellToParent(cell,resolution),resolution}}]});
  click(6);assert.equal(map.lastFlight.zoom,11.25);
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

test("county rainfall retains native polygons and never paints stale values as zero", async () => {
  for (const status of ["ready","stale"]) {
    const {map,get} = await boot({configured:true,mixed:true,countyWeather:true,forecastStatus:status,rainfall:0});
    map.handlers["load:"]();
    assert.equal(map.sources["native-rainfall"].data.features[0].id,"native-test-cell");
    assert.equal(map.sources["native-rainfall"].data.features[0].properties.rainfall_mm,status==="ready" ? 0 : null);
    assert.match(get("map-data-values").textContent,/native county cells available/);
    assert.match(get("map-data-source").textContent,/0.1 degree.*parcel scores remain unknown/);
    get("map-layer").value="exposure";get("map-layer").onchange();
    assert.equal(map.layers["native-rainfall-fill"].visibility,"none");
  }
});
