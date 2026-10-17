/* Shared replay state, accessible controls and chart. No cloud requests. */
(function (root) {
  "use strict";
  const START = Date.parse("2026-10-09T04:00:00Z"), LAST = 24;
  const hour = (index) => new Date(START + Math.max(0, Math.min(LAST, index)) * 3600000).toISOString().replace(".000Z", "Z");
  const localTime = (value) => new Date(value).toLocaleString("en-US", {timeZone:"America/New_York", month:"short", day:"numeric", hour:"numeric", timeZoneName:"short"});
  function segments(points) {
    const paths = []; let current = [];
    for (let i=0; i<points.length; i++) {
      if (points[i].risk.score === null) { if (current.length) paths.push(current); current=[]; }
      else current.push([30 + i / LAST * 600, 130 - points[i].risk.score]);
    }
    if (current.length) paths.push(current);
    return paths;
  }
  function create({get, element, load}) {
    const state = {index:0, mode:"archive", preset:"archived", roads:{}, destinations:{}};
    let timer = null, active = false, layers = {}, context = null, busy = false;
    const pause = () => { if (timer !== null) clearInterval(timer); timer=null; get("replay-play").textContent="Play"; };
    function refresh() { busy=true; get("replay-loading").textContent="Loading selected hour…"; return Promise.resolve(load()); }
    function step(delta) {
      state.index = Math.max(0, Math.min(LAST, state.index+delta));
      get("replay-hour").value=String(state.index);
      if (state.index === LAST) pause();
      return refresh();
    }
    function activate(value) { active=value; get("isaias-replay").hidden=!value; get("replay-results").hidden=!value; if (!value) pause(); }
    function presetChanged() {
      state.preset=get("replay-preset").value;
      if (state.preset!=="archived") { state.mode="what_if"; get("replay-mode").value="what_if"; }
      return refresh();
    }
    get("replay-prev").onclick=()=>{pause();return step(-1);};
    get("replay-next").onclick=()=>{pause();return step(1);};
    get("replay-play").onclick=()=>{
      if (timer!==null) { pause(); return; }
      if (state.index===LAST) state.index=0;
      get("replay-play").textContent="Pause";
      timer=setInterval(()=>{if (!busy) void step(1);},1000);
    };
    get("replay-hour").oninput=()=>{pause(); state.index=Number(get("replay-hour").value); return refresh();};
    get("replay-mode").onchange=()=>{
      state.mode=get("replay-mode").value;
      if (state.mode==="archive") {
        state.preset="archived";state.roads={};state.destinations={};get("replay-preset").value="archived";
      }
      return refresh();
    };
    get("replay-preset").onchange=presetChanged;
    get("replay-reset").onclick=()=>{
      pause();Object.assign(state,{index:0,mode:"archive",preset:"archived",roads:{},destinations:{}});
      get("replay-mode").value="archive";get("replay-preset").value="archived";get("replay-hour").value="0";
      return refresh();
    };
    get("road-apply").onclick=()=>{
      const id=get("road-select").value;if (!id) return;
      if (!(id in state.roads) && Object.keys(state.roads).length>=100) {get("route-summary").textContent="Reset before adding more than 100 overrides.";return;}
      state.roads[id]=get("road-state").value;state.mode="what_if";get("replay-mode").value="what_if";return refresh();
    };
    function drawTimeline(data) {
      get("timeline-heading").textContent=`${data.site} · ${data.label}`;
      const current=data.points[state.index];
      get("timeline-change").textContent=`${current.risk.score ?? "Unknown"} / 100 · hourly change: ${current.change===null ? "unavailable" : `${current.change>0 ? "+" : ""}${current.change} points`}`;
      const svg=get("risk-chart");svg.replaceChildren();
      const ns="http://www.w3.org/2000/svg";
      const shape=(name,attrs)=>{const n=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n;};
      svg.append(shape("line",{x1:30,y1:130,x2:630,y2:130,stroke:"#adb8b3"}));
      for(const value of [0,35,65,100]){
        const label=shape("text",{x:1,y:134-value,"font-size":10,fill:"#677571"});label.textContent=String(value);svg.append(label);
      }
      for(const path of segments(data.points)) {
        svg.append(shape("polyline",{points:path.map(p=>p.join(",")).join(" "),fill:"none",stroke:"#166b62","stroke-width":2}));
        if(path.length===1)svg.append(shape("circle",{cx:path[0][0],cy:path[0][1],r:2,fill:"#166b62"}));
      }
      const x=30+state.index/LAST*600;
      svg.append(shape("line",{x1:x,y1:25,x2:x,y2:135,stroke:"#876219","stroke-dasharray":"4 4"}));
      get("timeline-rows").replaceChildren();
      for(const point of data.points){
        const row=element("tr");row.append(element("td",localTime(point.at)),element("td",point.risk.score??"Unknown"),element("td",point.change??"Unavailable"),element("td",point.forecast.status));get("timeline-rows").append(row);
      }
    }
    function drawRoutes(data) {
      const selected=data.route, baseline=data.unrestricted;
      get("route-summary").textContent=selected ? `${selected.destination_label} · ${(selected.distance_m/1000).toFixed(2)} km · ${selected.duration_minutes} modeled minutes. ${data.destination_changed ? "Destination changed. " : ""}${data.route_changed ? "Route differs from the unrestricted exercise route." : "Unrestricted exercise route remains available."}` : `${data.status.replaceAll("_"," ")}. ${data.message}`;
      get("route-comparison").textContent=baseline ? `Unrestricted: ${baseline.destination_label}, ${baseline.duration_minutes} modeled minutes. ${data.message}` : data.notice;
      get("route-notice").textContent=data.notice;
      const previous=get("road-select").value;
      get("road-select").replaceChildren();
      for(const f of data.network.features){const o=element("option",`${f.properties.label} · ${f.id} · ${f.properties.state}`);o.value=f.id;get("road-select").append(o);}
      if(data.network.features.some(f=>f.id===previous))get("road-select").value=previous;
      get("road-apply").disabled=!data.network.features.length;
      get("destination-controls").replaceChildren();
      for(const d of data.destinations){
        const label=element("label"),input=element("input");input.type="checkbox";input.checked=d.available;
        input.onchange=()=>{state.destinations[d.id]=input.checked;state.mode="what_if";get("replay-mode").value="what_if";return refresh();};
        label.append(input,document.createTextNode(` ${d.label} · exercise availability`));get("destination-controls").append(label);
      }
      get("routing-overrides").textContent=`${Object.keys(state.roads).length} road overrides; ${Object.keys(state.destinations).length} destination overrides. ${data.excluded_roads.length} segments excluded as closed or unknown.`;
      const empty={type:"FeatureCollection",features:[]};
      layers={network:data.network,route:selected?.geometry||empty,baseline:baseline?.geometry||empty,
        destinations:{type:"FeatureCollection",features:data.destinations.map(d=>({type:"Feature",geometry:{type:"Point",coordinates:d.coordinates},properties:{label:d.label,available:d.available}}))}};
    }
    function drawContext(at) {
      const eligible=(context?.advisories||[]).filter(a=>a.issued_at<=at);
      const latest=eligible.at(-1);
      get("advisory-context").textContent=latest ? `NHC advisory ${latest.number} · ${localTime(latest.issued_at)}\n${latest.text.split("\n").filter(l=>l.trim()).slice(0,9).join("\n")}` : "NHC advisory context unavailable at this replay hour.";
      get("advisory-link").href=latest?.source_url||"https://www.nhc.noaa.gov/archive/2026/ISAIAS.shtml";
    }
    return {state,activate,step,pause,
      parameters:()=>({at:hour(state.index),preset:state.preset,mode:state.mode}),
      routing:(site)=>({site,at:hour(state.index),preset:state.preset,mode:state.mode,roads:{...state.roads},destinations:{...state.destinations}}),
      setContext:(data)=>{context=data;},
      fail:()=>{busy=false;pause();get("replay-loading").textContent="Selected hour could not load. Displayed results retain their previous timestamp.";},
      layers:()=>active ? layers : {},
      render:(timeline,routes)=>{
        busy=false;get("replay-loading").textContent="";get("replay-hour").value=String(state.index);
        get("replay-clock").textContent=localTime(timeline.at);get("replay-prev").disabled=state.index===0;get("replay-next").disabled=state.index===LAST;
        get("replay-source-status").textContent=`Historical rainfall: ${timeline.source_status}. ${timeline.reconstruction}. Static site factors and gauges remain fictional. +${state.preset==="plus-5" ? 5 : state.preset==="plus-10" ? 10 : 0} mm/hour synthetic addition; missing hours remain unknown.`;
        drawTimeline(timeline);drawRoutes(routes);drawContext(timeline.at);
      }};
  }
  const exported={hour,segments,create,localTime};
  if(typeof module!=="undefined"&&module.exports)module.exports=exported;
  else root.QuasarReplay=exported;
})(typeof window!=="undefined" ? window : globalThis);
