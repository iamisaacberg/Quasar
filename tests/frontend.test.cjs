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
}

async function boot({configured=false, mixed=false, scenarioFailure=false, mounted=true}={}) {
  const ids = new Map();
  const get = (id) => { if (!ids.has(id)) ids.set(id,new Element(id==="scenario" ? "select" : "div")); return ids.get(id); };
  const data = {type:"FeatureCollection", mode:mixed ? "mixed_forecast_demo" : "synthetic_demo", notice:"demo notice",
    scenario:{id:"baseline",valid_from:"2026-10-17T12:00:00Z",valid_to:"2026-10-17T18:00:00Z"},
    forecast:mixed ? {status:"ready",init_time:"2026-10-17T12:00:00Z",retrieved_at:"2026-10-17T12:30:00Z",native_resolution:"0.1 degree"} : null,
    features:[{type:"Feature",id:"demo-001",geometry:{type:"Point",coordinates:[-80.185,25.85]},
      properties:{id:"demo-001",label:"Fictional site",risk:{score:72,band:"elevated",factors:[],missing:[]},
        ...(mixed ? {forecast:{status:"ready",available_hours:6,rainfall_6h_mm:15}} : {})}}]};
  let map, resizeCallback, resizeCount=0, observed;
  const events=[];
  class FakeMap {
    constructor(options) { map=this; this.options=options; this.controls=[]; this.sources={}; this.layers={}; this.handlers={}; }
    resize() { resizeCount++; }
    addControl(control) { this.controls.push(control); }
    on(name,...rest) { this.handlers[`${name}:${rest.length===1 ? "" : rest[0]}`]=rest.at(-1); }
    addSource(id,source) { this.sources[id]={data:source.data,setData(data){this.data=data;}}; }
    getSource(id) { return this.sources[id]; }
    addLayer(layer) { this.layers[layer.id]=layer; }
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
      if (scenarioFailure && url.includes("scenario=bad")) return {ok:false,json:async()=>({error:"bad scenario"})};
      const body = url==="/api/config" ? {map:{configured,public_token:"pk.test",style:"mapbox://styles/mapbox/satellite-streets-v12"}} :
        url==="/api/scenarios" ? {scenarios:[{id:"baseline",label:"Exercise hour 0"}]} :
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
