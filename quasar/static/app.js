"use strict";
const $ = (id) => document.getElementById(id);
const colors = { unknown: "#9ca3af" };
const names = { rainfall_6h_mm: "Rainfall, six hours (mm)", elevation_m: "Terrain elevation (m)", fema_zone: "Illustrative FEMA zone", waterway_distance_m: "Waterway distance (m)", gauge_margin_m: "Margin below flood stage (m)" };
let map, mapLoaded = false, selectedId, current, mapData, requestId = 0, started = false, replayController, previousScenario = "baseline";
let county, selectedCell, selectedParcel, parcelData, parcelRequest = 0;
const countyGrids = new Map();
let exposureData = null, exposureRequest = 0, exposureHydrationRunning = false, exposureExpiryTimer;
const exposureResponses = new Map(), parcelAssessments = new Map();
const parcelCache = window.QuasarParcelCache.create({indexedDB:window.indexedDB});
let selectedResolution = 7, parcelEntry, cellContext, parcelContext, contextRequest = 0;
let contextMessage = "", parcelListPage = 0, parcelSearch = "", lastParcelPaint = 0;
let parcelPaintTimer;
const contextCache = new Map();
const emptyCollection = () => ({type:"FeatureCollection", features:[]});
let countyFramed = false;
let playback, forecastTimeline, forecastIndex = 0, mapToken, searchController, searchMarker;
let forecastExpiryTimer;
const replaySelected = () => $("scenario").value === "isaias-2026";
const bandLabel = (band) => band.replaceAll("_", " ");

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function choose(id, refresh = true) {
  if (refresh) closeSelection();
  if (refresh) $("map-sidebar").removeAttribute?.("data-dismissed");
  if (refresh) $("map-inspect-toggle").setAttribute("aria-expanded", "true");
  if (refresh && playback) $("map-tools").open = false;
  if (refresh && playback) $("map-source-info").open = false;
  $("map-site").value = id;
  if (refresh && replayController && replaySelected()) { selectedId = id; void loadScenario(); return; }
  const feature = current.features.find((item) => item.id === id);
  if (!feature) return;
  selectedId = id;
  const property = feature.properties, risk = property.risk;
  $("detail-heading").textContent = property.label;
  const detail = $("detail");
  detail.replaceChildren(element("p", risk.score === null ? "Unknown" : `${risk.score} / 100`, "score"),
    element("p", `${QuasarSpatial.exposureBand(risk.score).label} · unvalidated relative estimate`, "detail-note"));
  for (const factor of risk.factors) {
    const row = element("div", undefined, "factor");
    const line = element("p");
    line.append(element("span", `${names[factor.name]}: ${factor.value}`), element("span", `+${factor.contribution.toFixed(1)}`));
    const track = element("div", undefined, "track"), fill = element("div", undefined, "fill");
    fill.style.width = `${factor.contribution / (factor.weight * 100) * 100}%`;
    track.append(fill); row.append(line, track); detail.append(row);
  }
  if (risk.missing.length) detail.append(element("p", `Missing inputs: ${risk.missing.map((key) => names[key]).join(", ")}. No score is assigned.`, "detail-note"));
  detail.append(element("p", "Factors show points contributed to the score. Weights and thresholds are illustrative.", "detail-note"));
  if (property.forecast) {
    detail.append(element("p", `WeatherNext 3: ${property.forecast.status}; ${property.forecast.available_hours}/6 hourly rainfall inputs. Rainfall: ${property.forecast.rainfall_6h_mm ?? "unavailable"} mm / 6h. Native forecast grid: ${property.forecast.native_resolution || current.forecast?.native_resolution}. Other risk inputs are fictional.`, "detail-note"));
  }
  if (property.risk.factor_provenance) detail.append(element("p", "Rainfall: historical forecast where available, with any selected synthetic addition. Terrain, FEMA, waterway distance and gauge margin: fictional exercise inputs.", "detail-note"));
  if (mapData) {
    const point = mapData.points.features.find((f) => f.id === id);
    detail.append(element("p", `H3 index: ${point.properties.h3_index} (resolution 7)`, "detail-note"));
  }
  if (risk.band === "elevated" && current.mode === "synthetic_demo") {
    const label = element("label", undefined, "consent"), consent = element("input");
    consent.type = "checkbox";
    label.append(consent, document.createTextNode(" Opt in to a simulated notification for this exercise site."));
    const button = element("button", "Preview simulated email"), result = element("p");
    result.id = "notification-result"; result.setAttribute("role", "status");
    button.onclick = async () => {
      if (!consent.checked) { result.textContent = "Select opt-in to preview a simulated notification."; return; }
      button.disabled = true;
      try {
        const data = await api("/api/notifications/preview", { method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({property_ids:[id], scenario:current.scenario.id, channel:"email", opt_in:true}) });
        result.textContent = `${data.messages[0]?.text || "No elevated-score preview for this scenario."}\nSent: ${data.sent_count}`;
      } catch (error) { result.textContent = error.message; }
      finally { button.disabled = false; }
    };
    detail.append(label, button, result);
  }
}

function render(data) {
  const changedScenario = current?.scenario.id !== data.scenario.id;
  ++exposureRequest;
  window.clearTimeout?.(exposureExpiryTimer);
  exposureData = null; exposureHydrationRunning = false;
  exposureResponses.clear(); parcelAssessments.clear();
  current = data;
  // Keep cached geometry and the inspection panel; invalidate only hourly indices.
  if (parcelEntry && mapLoaded) publishParcels(parcelEntry,true);
  replayController?.activate(data.scenario.id === "isaias-2026");
  $("replay-toggle").setAttribute("aria-pressed", String(data.scenario.id === "isaias-2026"));
  $("replay-toggle").textContent = data.scenario.id === "isaias-2026" ? "Exit Isaias simulation" : "Isaias simulation";
  if (data.scenario.id !== "isaias-2026") previousScenario = data.scenario.id;
  if (changedScenario) $("map-layer").value = data.mode === "synthetic_demo" ? "exposure" : "rainfall";
  $("mode-badge").textContent = data.mode === "what_if_exercise" ? "WHAT-IF EXERCISE" : data.mode === "historical_mixed_demo" ? "ARCHIVE · MIXED DEMO" : data.mode === "mixed_forecast_demo" ? "MIXED DEMO" : "SYNTHETIC DEMO";
  $("data-notice").textContent = data.notice;
  if ($("map-demo-notice")) $("map-demo-notice").textContent = data.notice;
  if (window.h3 && window.QuasarSpatial) mapData = QuasarSpatial.aggregate(data, h3, 7);
  $("site-count").textContent = data.features.length;
  $("elevated-count").textContent = data.features.filter((f) => f.properties.risk.band === "elevated").length;
  $("unknown-count").textContent = data.features.filter((f) => f.properties.risk.band === "unknown").length;
  const time = (value) => new Date(value).toLocaleString("en-US", {timeZone:"America/Chicago", month:"short", day:"numeric", hour:"numeric", timeZoneName:"short"});
  $("window").textContent = `${data.scenario.id === "isaias-2026" ? "Archive forecast window" : data.forecast ? "Forecast window" : "Exercise clock"}: ${time(data.scenario.valid_from)} – ${time(data.scenario.valid_to)}`;
  $("sites").replaceChildren();
  $("map-site").replaceChildren();
  for (const feature of data.features) {
    const siteOption = element("option", feature.properties.label); siteOption.value = feature.id; $("map-site").append(siteOption);
    const p = feature.properties, row = element("tr"), button = element("button", "Inspect");
    button.setAttribute("aria-label", `Inspect ${p.label}`);
    button.onclick = () => choose(p.id);
    const action = element("td"); action.append(button);
    row.append(element("td", p.label), element("td", p.risk.score ?? "Unknown"), element("td", QuasarSpatial.exposureBand(p.risk.score).label), element("td", rainfallValue(feature) === null ? "Unavailable" : rainfallValue(feature).toFixed(1)), action);
    $("sites").append(row);
  }
  showMapSummary();
  updateMap();
  if (data.forecast) showWeatherStatus(data.forecast);
  choose(selectedId || data.features[0]?.id, false);
  if (selectedCell) { if (selectedParcel === null) renderCellPanel(); else renderInspectionInputs(); }
  if (playback) {
    clearTimeout(forecastExpiryTimer);
    if (data.scenario.id === "isaias-2026") playback.configure("archive", Array.from({length:25}, (_,i)=>window.QuasarReplay.hour(i)), replayController.state.index, true, "Archive reconstruction · fictional site inputs");
    else if (data.scenario.id === "weathernext" && forecastTimeline) playback.configure("forecast", forecastTimeline.frames.map(f=>f.at), forecastIndex,
      !["stale","invalid","unavailable","not_configured"].includes(forecastTimeline.status),
      forecastTimeline.status === "stale" ? "Imported forecast is stale. Refresh requires an explicit import." : "Following six-hour rainfall · mm / 6h");
    else playback.configure("none", [], 0, false, "Playback unavailable for static exercise windows.");
    const expiry=Date.parse(forecastTimeline?.expires_at);
    if(data.scenario.id==="weathernext" && forecastTimeline.status!=="stale" && expiry>Date.now()) {
      forecastExpiryTimer=setTimeout(()=>{if(current?.scenario.id==="weathernext")void loadScenario();},expiry-Date.now()+1000);
    }
  }
}

function rainfallValue(feature) {
  const forecast = feature.properties.forecast;
  const value = forecast ? forecast.rainfall_6h_mm : current?.scenario.rainfall_6h_mm;
  if (forecast && forecast.status !== "ready") return null;
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function showMapSummary() {
  if (!current) return;
  const rain = $("map-layer").value === "rainfall";
  const synthetic = current.mode === "synthetic_demo";
  $("map-data-title").textContent = rain ? `${synthetic ? "Synthetic" : "WeatherNext 3"} rainfall · mm / 6h` : "Experimental relative exposure · index / 100";
  if ($("map-display-label")) $("map-display-label").textContent = $("map-data-title").textContent;
  const values = current.features.map(rainfallValue).filter(v => v !== null);
  $("map-data-values").textContent = values.length ? `${Math.min(...values).toFixed(1)}–${Math.max(...values).toFixed(1)} mm / 6h · ${values.length}/${current.features.length} sampled sites with rainfall · ${current.features.length-values.length} unavailable` : `Rainfall unavailable at all ${current.features.length} sampled sites. Missing or stale inputs remain unknown.`;
  const forecast = current.forecast || current.features.find(f => f.properties.forecast)?.properties.forecast;
  $("map-data-source").textContent = synthetic ? "Fictional rainfall and site inputs. This is a fixed exercise clock." :
    `${forecast?.status || "unavailable"} · initialized ${forecast?.init_time || "unavailable"} · imported ${forecast?.retrieved_at || "unavailable"} · native grid ${forecast?.native_resolution || "0.1 degree"} · ensemble mean. Fictional sites and other score inputs.${current.mode === "what_if_exercise" ? " Includes selected synthetic rainfall addition." : ""}`;
  if (rain && current.weather_cells) {
    const cells = current.weather_cells;
    const available = cells.features.filter(f => f.properties.status === "ready" && typeof f.properties.rainfall_6h_mm === "number");
    const totals = available.map(f => f.properties.rainfall_6h_mm);
    $("map-data-values").textContent = `${totals.length ? `${Math.min(...totals).toFixed(1)}–${Math.max(...totals).toFixed(1)} mm / 6h` : "Rainfall unavailable"} · ${available.length}/${cells.features.length} native county cells available`;
    $("map-data-source").textContent = `WeatherNext 3 · native 0.1 degree ensemble mean · initialized ${forecast?.init_time || "unavailable"} · imported ${cells.retrieved_at}. Native cells intersect Okaloosa and may extend past it. Forecast rainfall only; parcel scores remain unknown.${current.mode === "what_if_exercise" ? " Includes selected synthetic rainfall addition." : ""}`;
  }
  $("exposure-legend").hidden = rain;
  $("rainfall-legend").hidden = !rain;
  $("hex-toggle").disabled = false;
  $("map-layer-note").textContent = rain ? "Labels show rainfall at fictional sites. The neutral county grid is for parcel browsing, not rainfall coverage. H3 does not sharpen the native 0.1 degree forecast." : `Cells show parcel P90; hatching marks incomplete scoring coverage. ${exposureData?.status === "ready" ? `Server aggregation: ${exposureData.aggregation_architecture}.` : exposureData?.message || "Parcel assessments unavailable."} Exercise sites remain fictional. Green does not establish safety.`;
}

function mapColors(field = "risk_score") {
  return QuasarSpatial.exposureExpression(field);
}

function exposureParameters(resolution = 7) {
  if (!current || ["synthetic_demo", "what_if_exercise"].includes(current.mode)) return null;
  return {from:current.scenario.valid_from, to:current.scenario.valid_to, resolution:String(resolution),
    mode:current.mode === "historical_mixed_demo" ? "replay" : "current"};
}

function selectedExposureSummary() {
  const params=exposureParameters(selectedResolution);
  const response=params && exposureResponses.get(new URLSearchParams(params).toString());
  return response?.status === "ready" ? response.cells[selectedCell] : null;
}

function renderExposureInspection() {
  if(!selectedCell) return;
  const content=$("selection-exposure");
  if(selectedParcel===null) {
    const summary=selectedExposureSummary();
    panelStats([[summary?.p90_score == null ? "Unknown" : summary.p90_score.toFixed(1),"Parcel index · P90"],
      [summary ? `${summary.scored_count}/${summary.parcel_count}` : "Unknown","Scoring coverage"],
      [summary ? String(summary.elevated_count) : "Unknown","Indices ≥65"]]);
    content.replaceChildren(element("p",summary ? `${QuasarSpatial.exposureBand(summary.p90_score).label} · ${(summary.coverage*100).toFixed(1)}% scored${summary.incomplete ? " · Incomplete coverage" : ""}` : "Insufficient data · scoring coverage unknown","detail-note"));
    void refreshExposure(selectedResolution);
  } else {
    const assessment=exposureData?.status === "ready" && exposureData.inventory_id===parcelEntry?.inventory_id ? parcelAssessments.get(selectedParcel) : null;
    const score=QuasarSpatial.validScore(assessment?.score) ? assessment.score : null;
    panelStats([[score===null ? "Unknown" : score.toFixed(1),"Exposure index / 100"],
      [QuasarSpatial.exposureBand(score).label,"Relative exposure"],
      [exposureData?.status === "ready" ? exposureData.method_version : "Unavailable","Method"]]);
    $("selection-badge").textContent=score===null ? "County parcel · unscored" : "County parcel · experimental index";
    content.replaceChildren(...(assessment?.factors || []).map(factor=>element("p",
      `${names[factor.name] || factor.name}: ${factor.value ?? "Unknown"} · +${factor.contribution.toFixed(1)} index points`,"detail-note")));
    if(score===null) content.append(element("p",`Insufficient data: ${assessment?.missing?.join(", ") || exposureData?.message || "No matching parcel assessment"}.`,"detail-note"));
  }
  $("selection-score").textContent=$("selection-stat-one").textContent === "Unknown" ? "Unscored" : $("selection-stat-one").textContent+" / 100";
  content.append(element("p","Experimental relative exposure, not flood probability or depth. Green does not establish safety.","detail-note"));
}

function invalidateExposure(data) {
  ++exposureRequest;
  parcelAssessments.clear(); exposureHydrationRunning=false;
  exposureData=data;
  for(const key of exposureResponses.keys()) exposureResponses.set(key,data);
}

function scheduleExposureExpiry() {
  window.clearTimeout?.(exposureExpiryTimer);
  if(exposureData?.status!=="ready" || exposureParameters()?.mode!=="current") return;
  const expires=Math.min(Date.parse(exposureData.valid_to),Date.parse(exposureData.computed_at)+2*3600000);
  if(!Number.isFinite(expires)) return;
  const request=exposureRequest;
  exposureExpiryTimer=window.setTimeout?.(()=>{
    if(request!==exposureRequest)return;
    invalidateExposure({status:"stale",cells:{},message:"Parcel exposure results are stale; scores remain unknown."});
    if(parcelEntry)publishParcels(parcelEntry,true);
    updateCountyGrid();showMapSummary();
    if(selectedCell)renderExposureInspection();
    void refreshExposure(QuasarSpatial.resolutionForZoom(map.getZoom()),true);
  },Math.max(0,expires-Date.now()+1));
}

async function refreshExposure(resolution, force=false) {
  const params=exposureParameters(resolution);
  if(!params) return;
  const key=new URLSearchParams(params).toString();
  if(force) exposureResponses.delete(key);
  if(exposureResponses.has(key)) return;
  const request=exposureRequest;
  exposureResponses.set(key,{status:"loading",cells:{}});
  try {
    const data=await api(`/api/exposure?${key}`);
    if(request!==exposureRequest) return;
    if(data.status==="ready" && (!data.cells || data.aggregation!=="parcel_p90_linear")) throw new Error("Invalid exposure summary");
    if(data.status==="ready" && exposureData?.status==="ready"
        && (data.run_id!==exposureData.run_id || data.inventory_id!==exposureData.inventory_id)) {
      ++exposureRequest;
      parcelAssessments.clear(); exposureHydrationRunning=false; exposureResponses.clear();
    }
    if(data.status!=="ready") invalidateExposure(data);
    exposureResponses.set(key,data);
    exposureData=data;
  } catch(error) {
    if(request!==exposureRequest) return;
    invalidateExposure({status:"unavailable",cells:{},message:`Parcel exposure unavailable: ${error.message}`});
    exposureResponses.set(key,exposureData);
  }
  scheduleExposureExpiry();
  updateCountyGrid(); showMapSummary();
  if(selectedCell) renderExposureInspection();
  if(parcelEntry) publishParcels(parcelEntry,true);
}

async function hydrateParcelExposure() {
  const params=exposureParameters(), run=exposureData;
  if(exposureHydrationRunning || !params || run?.status!=="ready" || !parcelEntry
      || run.inventory_id!==parcelEntry.inventory_id || selectedResolution!==7) return;
  const ids=parcelEntry.features.map(feature=>feature.id).filter(id=>!parcelAssessments.has(id));
  if(!ids.length) return;
  const request=exposureRequest, cell=selectedCell;
  exposureHydrationRunning=true;
  try {
    for(let offset=0;offset<ids.length;offset+=100) {
      if(request!==exposureRequest || selectedCell!==cell) return;
      const batch=ids.slice(offset,offset+100);
      const page=await api(`/api/exposure?${new URLSearchParams({...params,parcel_ids:batch.join(","),run_id:run.run_id})}`);
      if(request!==exposureRequest || selectedCell!==cell) return;
      if(page.status!=="ready" || page.run_id!==run.run_id || page.inventory_id!==parcelEntry?.inventory_id) throw new Error("Parcel exposure run or inventory changed");
      for(const id of batch) parcelAssessments.set(id,page.parcels?.[id] || {score:null,factors:[],missing:["assessment_unavailable"]});
    }
    if(parcelEntry) publishParcels(parcelEntry,true);
  } catch(error) {
    if(request!==exposureRequest) return;
    parcelAssessments.clear();
    exposureData={status:"unavailable",cells:{},message:`Parcel exposure unavailable: ${error.message}`};
    for(const key of exposureResponses.keys()) exposureResponses.set(key,exposureData);
    if(parcelEntry) publishParcels(parcelEntry,true);
    updateCountyGrid(); showMapSummary();
  } finally {
    if(request===exposureRequest) {
      exposureHydrationRunning=false;
      void hydrateParcelExposure();
    }
  }
}

function updateMap() {
  if (!mapLoaded || !mapData) return;
  map.getSource("sites").setData({...mapData.points, features:mapData.points.features.map(feature => {
    const value = rainfallValue(feature);
    return {...feature, properties:{...feature.properties, rainfall_mm:value, rainfall_label:value === null ? "Unavailable" : `${value.toFixed(1)} mm`}};
  })});
  const rain = $("map-layer").value === "rainfall";
  const nativeSource = map.getSource("native-rainfall");
  if (nativeSource) {
    const cells = current.weather_cells || emptyCollection();
    nativeSource.setData({...cells, features:cells.features.map(f => ({...f,
      properties:{...f.properties, rainfall_mm:f.properties.rainfall_6h_mm}}))});
    map.setLayoutProperty("native-rainfall-fill", "visibility", rain ? "visible" : "none");
    map.setLayoutProperty("native-rainfall-outline", "visibility", rain ? "visible" : "none");
  }
  map.setPaintProperty("site-points", "circle-color", rain ? ["case", ["==", ["get", "rainfall_mm"], null], colors.unknown,
    ["step", ["get", "rainfall_mm"], "#b9e2f8", 25, "#509dce", 75, "#3156a6"]] : mapColors());
  map.setLayoutProperty("rainfall-labels", "visibility", rain ? "visible" : "none");
  toggleHex();
  updateCountyGrid();
  const layers = replayController?.layers() || {};
  for (const id of ["network", "route", "baseline", "destinations"]) {
    const source = map.getSource(`replay-${id}`);
    if (source) source.setData(layers[id] || {type:"FeatureCollection", features:[]});
  }
}

function updateCountyGrid() {
  if (!mapLoaded || !mapData) return;
  const resolution = QuasarSpatial.resolutionForZoom(map.getZoom());
  let grid = emptyCollection();
  if (county) {
    if (!countyGrids.has(resolution)) countyGrids.set(resolution, QuasarSpatial.countyCells(county.features[0].geometry, h3, resolution));
    const params = exposureParameters(resolution);
    const cached = params && exposureResponses.get(new URLSearchParams(params).toString());
    grid = QuasarSpatial.exposureCoverage(countyGrids.get(resolution), cached?.status === "ready" ? cached.cells : {});
    void refreshExposure(resolution);
  }
  map.getSource("hotspots").setData(grid);
  const rain = $("map-layer").value === "rainfall";
  map.setPaintProperty("hotspot-fill", "fill-color", rain ? "#b9c9cd" : mapColors("exposure_score"));
  map.setPaintProperty("hotspot-fill", "fill-opacity", rain ? 0.07 : 0.28);
  map.setPaintProperty("hotspot-outline", "line-color", "#c4d5d7");
  for (const layer of ["parcel-fill", "selected-parcel-fill"]) map.setPaintProperty(layer,"fill-color",rain ? colors.unknown : mapColors("exposure_score"));
  map.setLayoutProperty("parcel-hatch","visibility",rain ? "none" : "visible");
  map.setLayoutProperty("hotspot-hatch","visibility",!rain && $("hex-toggle").checked ? "visible" : "none");
  $("grid-resolution").textContent = `H3 · RES ${resolution}`;
  if (county) $("grid-status").textContent = `${grid.features.length.toLocaleString()} cells · R${resolution} · click to inspect`;
}

function frameCounty() {
  if (!mapLoaded || !county || countyFramed) return;
  countyFramed = true;
  const geometry = county.features[0].geometry;
  const points = (geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates]).flat(2);
  const bounds = [0,1].map(axis => [Math.min(...points.map(p=>p[axis])),Math.max(...points.map(p=>p[axis]))]);
  map.fitBounds([[bounds[0][0],bounds[1][0]],[bounds[0][1],bounds[1][1]]], {padding:35,duration:0});
}

function closeSelection() {
  const restoreFocus=$("map-selection-panel").getAttribute("aria-modal")==="true";
  ++parcelRequest; ++contextRequest;
  window.clearTimeout?.(parcelPaintTimer); parcelPaintTimer=undefined;
  selectedCell = selectedParcel = parcelData = parcelEntry = cellContext = parcelContext = null;
  contextMessage = "";
  $("map-selection-panel").hidden = true;
  if(restoreFocus)$("map-overview").focus();
  if (mapLoaded) {
    for (const id of ["parcels","selected-cell","selected-parcel"]) map.getSource(id).setData(emptyCollection());
  }
}

function panelStats(values) {
  for (const [index, [value, label]] of values.entries()) {
    const key = ["one", "two", "three"][index];
    $(`selection-stat-${key}`).textContent = value;
    $(`selection-stat-${key}-label`).textContent = label;
  }
}

function inputRows(rows) {
  $("selection-inputs").replaceChildren(...rows.map(([label,value])=>{
    const row=element("div"); row.append(element("dt",label),element("dd",value)); return row;
  }));
}

function renderInspectionInputs() {
  const context=selectedParcel === null ? cellContext : parcelContext;
  const rows=selectedParcel === null ? window.QuasarInspection.forecastRows(context,current) : window.QuasarInspection.parcelRows(context,current);
  if(selectedParcel === null) rows.unshift(
    ["Distinct indexed parcels",cellContext?.parcel_count?.toLocaleString() ?? "Unknown"],
    ["Complete terrain summaries",cellContext?.terrain_complete_count?.toLocaleString() ?? "Unknown"],
    ["Complete / partial FEMA coverage",`${cellContext?.fema_complete_count?.toLocaleString() ?? "Unknown"} / ${cellContext?.fema_partial_count?.toLocaleString() ?? "Unknown"}`]);
  inputRows(rows);
  $("context-status").textContent=contextMessage;
  $("context-provenance").textContent=window.QuasarInspection.provenance(context);
  renderExposureInspection();
}

async function loadInspection(kind,identifier) {
  const request=++contextRequest, inventory=parcelEntry?.inventory_id;
  const key=JSON.stringify([kind,identifier,inventory]);
  contextMessage="Loading prepared reference inputs…"; renderInspectionInputs();
  try {
    const context=contextCache.get(key) || await api(`/api/${kind === "parcel" ? "parcels" : "cells"}/${identifier}/${kind === "parcel" ? "context" : "summary"}${inventory ? `?${new URLSearchParams({inventory_id:inventory})}` : ""}`);
    if(context.status!=="ready" || context.county_fips!=="12091" || context.risk_score!==null
        || (kind==="parcel" ? context.parcel_id!==identifier : context.cell_id!==identifier)
        || (parcelEntry?.inventory_id && context.inventory_id!==parcelEntry.inventory_id)) throw new Error("Prepared context is invalid or describes a different inventory");
    if(request!==contextRequest) return;
    contextCache.set(key,context);
    if(contextCache.size>100) contextCache.delete(contextCache.keys().next().value);
    if(kind==="parcel") parcelContext=context; else cellContext=context;
    contextMessage="Reference inputs only · no parcel score calculated";
    if(selectedParcel===null) renderCellPanel(); else {
      panelStats([["Unknown","Exposure"],[context.forecast_overlaps?.length ? "Prepared" : "Unknown","Forecast overlap"],[context.inputs?.terrain?.status || "Unknown","Terrain"]]);
      renderInspectionInputs();
    }
  } catch(error) {
    if(request!==contextRequest) return;
    if(selectedParcel!==null) panelStats([["Unknown","Exposure"],["Unknown","Forecast overlap"],["Unknown","Terrain"]]);
    contextMessage=`Reference inputs unavailable: ${error.message}`; renderInspectionInputs();
  }
}

function renderParcelList() {
  const features=(parcelData?.features || []).filter(f=>String(f.id).includes(parcelSearch));
  const pages=Math.max(1,Math.ceil(features.length/50)); parcelListPage=Math.min(parcelListPage,pages-1);
  $("selection-content").replaceChildren(...features.slice(parcelListPage*50,(parcelListPage+1)*50).map(feature=>{
    const button=element("button",undefined,"selection-parcel-row"); button.type="button";
    const score=feature.properties.exposure_score;
    button.style.borderLeft=`4px solid ${QuasarSpatial.exposureColor(score)}`;
    button.append(element("strong",`Parcel ${feature.id}`),element("span",`${score == null ? "Unknown" : score.toFixed(1)+" / 100"} · ${QuasarSpatial.exposureBand(score).label} →`));
    button.onclick=()=>inspectParcel(feature); return button;
  }));
  $("parcel-page").textContent=`${features.length ? parcelListPage*50+1 : 0}–${Math.min((parcelListPage+1)*50,features.length)} of ${features.length.toLocaleString()} loaded matches`;
  $("parcel-previous").disabled=parcelListPage===0;
  $("parcel-next").disabled=parcelListPage>=pages-1;
}

function renderCellPanel() {
  if (!selectedCell) return;
  $("map-selection-panel").hidden = false;
  $("selection-back").hidden = true;
  $("selection-badge").textContent = `R${selectedResolution} cell · Okaloosa`;
  $("selection-title").textContent = "Cell overview";
  $("selection-code").textContent = selectedCell;
  $("selection-subtitle").textContent = "Indexed parcel coverage and native forecast context";
  $("selection-section-title").textContent = selectedResolution===7 ? "Parcels in this cell" : "Cell coverage";
  $("cell-zoom").hidden=selectedResolution===7;
  $("parcel-refresh").hidden=selectedResolution!==7;
  $("parcel-search-label").hidden=$("parcel-pagination").hidden=selectedResolution!==7;
  const sites=current.features.filter(f=>h3.latLngToCell(f.geometry.coordinates[1],f.geometry.coordinates[0],selectedResolution)===selectedCell);
  const scored=sites.filter(f=>f.properties.risk.score!==null);
  panelStats([[cellContext?.parcel_count?.toLocaleString() ?? (parcelData ? `${parcelData.features.length.toLocaleString()} loaded` : "Unknown"),"Parcels"],
    [String(sites.length),"Fictional sites"],[scored.length ? String(Math.max(...scored.map(f=>f.properties.risk.score))) : "Unknown","Max demo score"]]);
  if(selectedResolution===7) renderParcelList();
  else $("selection-content").replaceChildren(element("p","Zoom in to browse parcel outlines. Counts describe indexed parcels, not homes; adjacent cells can share parcels.","selection-note"));
  renderInspectionInputs();
}

function inspectParcel(feature) {
  selectedParcel=feature.id; parcelContext=null;
  $("selection-back").hidden=false; $("cell-zoom").hidden=true;
  $("parcel-search-label").hidden=$("parcel-pagination").hidden=true;
  $("selection-badge").textContent="County parcel · unscored";
  $("selection-title").textContent="Parcel details";
  $("selection-code").textContent=`Parcel ${feature.id}`;
  $("selection-subtitle").textContent="Okaloosa County · FIPS 12091";
  panelStats([["Unknown","Exposure"],["Loading","Forecast overlap"],["Loading","Terrain"]]);
  $("selection-section-title").textContent="Property record";
  const records=element("dl",undefined,"selection-factors");
  for(const [label,value] of [["County GIS ID",String(feature.id)],["Geometry","County-validated polygon"],["H3 selection",selectedCell]]) {
    const row=element("div"); row.append(element("dt",label),element("dd",value)); records.append(row);
  }
  $("selection-content").replaceChildren(records);
  map.getSource("selected-parcel").setData({type:"FeatureCollection",features:[feature]});
  const polygons=feature.geometry.type==="MultiPolygon"?feature.geometry.coordinates:[feature.geometry.coordinates];
  const points=polygons.flat(2), bounds=[0,1].map(axis=>[Math.min(...points.map(p=>p[axis])),Math.max(...points.map(p=>p[axis]))]);
  map.fitBounds([[bounds[0][0],bounds[1][0]],[bounds[0][1],bounds[1][1]]],{padding:{top:60,bottom:60,left:40,right:Math.min(370,map.getCanvas().clientWidth/2)},maxZoom:18,duration:650});
  void loadInspection("parcel",feature.id);
}

async function inspectCell(cell,resolution=7) {
  closeSelection(); selectedCell=cell; selectedResolution=resolution;
  parcelListPage=0; parcelSearch=""; $("parcel-search").value="";
  $("map-inspect-toggle").setAttribute("aria-expanded","false");
  $("map-sidebar").setAttribute("data-dismissed", "true");
  if (playback) $("map-source-info").open = false;
  map.getSource("selected-cell").setData({type:"FeatureCollection",features:[{type:"Feature",geometry:{type:"Polygon",coordinates:[h3.cellToBoundary(cell,true)]}}]});
  $("parcel-status").textContent=resolution===7?"Restoring parcel inventory…":"Parcel outlines load at resolution 7.";
  $("parcel-provenance").textContent=""; $("parcel-retry").hidden=true;
  renderCellPanel();
  void loadInspection("cell",cell);
  if(resolution===7) {
    const [lat,lon]=h3.cellToLatLng(cell); map.flyTo({center:[lon,lat],zoom:Math.max(13.5,map.getZoom()),duration:650});
    await loadParcels();
  }
}

function publishParcels(entry,force=false) {
  if(cellContext && cellContext.inventory_id!==entry.inventory_id) {
    cellContext=null; contextMessage="Reference inputs do not match the cached parcel inventory; current coverage is unknown.";
  }
  parcelEntry=entry;
  parcelData={type:"FeatureCollection",features:entry.features.map(feature=>QuasarSpatial.exposureFeature(feature,
    exposureData?.status === "ready" && exposureData.inventory_id === entry.inventory_id ? parcelAssessments.get(feature.id) : null))};
  const selected=parcelData.features.find(feature=>feature.id===selectedParcel);
  if(selected) map.getSource("selected-parcel").setData({type:"FeatureCollection",features:[selected]});
  if(selectedParcel!==null) renderExposureInspection();
  void hydrateParcelExposure();
  if(force || Date.now()-lastParcelPaint>=100) {
    window.clearTimeout?.(parcelPaintTimer); parcelPaintTimer=undefined;
    map.getSource("parcels").setData(parcelData); lastParcelPaint=Date.now();
    if(selectedParcel===null) renderCellPanel();
  } else if(!parcelPaintTimer && window.setTimeout) {
    const cell=selectedCell;
    parcelPaintTimer=window.setTimeout(()=>{
      parcelPaintTimer=undefined;
      if(selectedCell===cell && parcelEntry) publishParcels(parcelEntry,true);
    },Math.max(0,100-(Date.now()-lastParcelPaint)));
  }
  $("parcel-status").textContent=entry.complete
    ? `${entry.features.length.toLocaleString()} county-validated parcels shown. All ${entry.source_total.toLocaleString()} source matches checked.${entry.excluded_count ? ` ${entry.excluded_count} excluded by county validation.` : ""}`
    : `Partial inventory: ${entry.features.length.toLocaleString()} parcels shown · ${entry.checked_count || 0} / ${entry.source_total ?? "unknown"} source matches checked…`;
  $("parcel-provenance").textContent=`${entry.source_url} · source snapshot ${entry.retrieved_at} · ${entry.crs}. ${entry.processing || "County-validated geometry"}. Cached ${new Date(entry.savedAt || Date.now()).toISOString()}.`;
}

async function loadParcels(force=false) {
  const cell=selectedCell, request=++parcelRequest, token=parcelCache.token;
  if(!cell || selectedResolution!==7) return;
  if(force) {
    await refreshExposure(selectedResolution,true);
    if(request!==parcelRequest) return;
  }
  $("parcel-retry").hidden=true;
  const cached=await parcelCache.get(cell);
  if(request!==parcelRequest) return;
  if(cached) {
    publishParcels(cached,true);
    $("parcel-status").textContent+=" Checking source version…";
  }
  const checked=await parcelCache.check(()=>api("/api/parcels/manifest"),force);
  let entry=await parcelCache.get(cell,checked.error ? undefined : checked.manifest);
  if(request!==parcelRequest) return;
  if(entry) publishParcels(entry,true);
  if(checked.error) {
    $("parcel-status").textContent=entry ? `Source unavailable; cached inventory from ${new Date(entry.savedAt).toISOString()}. ${entry.complete ? "Previously complete" : "Partial"}; current coverage unverified.` : `Parcel coverage unavailable: ${checked.error.message}`;
    $("parcel-retry").hidden=false; return;
  }
  const manifest=checked.manifest;
  if(entry?.complete) {
    if(parcelCache.diskFailed) $("parcel-status").textContent+=" Browser storage unavailable; cache is limited to this session.";
    return;
  }
  try {
    entry=await parcelCache.single(cell,manifest,async()=>{
      let loaded=entry || {features:[],next_offset:0,excluded_count:0,complete:false};
      const features=new Map(loaded.features.map(f=>[f.id,f]));
      do {
        const offset=loaded.next_offset || 0;
        const query=new URLSearchParams({cell,ring:JSON.stringify(h3.cellToBoundary(cell,true)),offset:String(offset)});
        if(loaded.inventory_id || manifest.inventory_id) query.set("inventory_id",loaded.inventory_id || manifest.inventory_id);
        const page=await api(`/api/parcels?${query}`);
        if(page.status!=="ready" || page.county_fips!=="12091" || !Array.isArray(page.features)
          || typeof page.inventory_id!=="string" || (loaded.inventory_id && page.inventory_id!==loaded.inventory_id)
          || (manifest.inventory_id && page.inventory_id!==manifest.inventory_id)
          || page.dataset_version!==manifest.dataset_version || !Number.isInteger(page.source_total)
          || !Number.isInteger(page.checked_count) || !Number.isInteger(page.excluded_count)
          || page.source_total<offset || page.excluded_count<0 || page.checked_count<offset || page.checked_count>page.source_total
          || page.checked_count!==(page.next_offset ?? page.source_total)
          || (Number.isInteger(loaded.source_total) && page.source_total!==loaded.source_total)
          || (page.next_offset!==null && (!Number.isInteger(page.next_offset) || page.next_offset<=offset))) throw new Error("Parcel page has an invalid or changed inventory; refresh this cell");
        for(const feature of page.features) {
          if(!Number.isSafeInteger(feature.id) || feature.properties?.county_fips!=="12091" || feature.properties.risk_score!==null
             || feature.properties.risk_band!=="unknown" || feature.properties.parcel_id!==feature.id
             || !["Polygon","MultiPolygon"].includes(feature.geometry?.type)) throw new Error("Invalid parcel geometry page");
          features.set(feature.id,feature);
        }
        loaded={...page,features:[...features.values()],excluded_count:loaded.excluded_count+page.excluded_count,complete:page.next_offset===null};
        const saved=await parcelCache.put(cell,manifest,loaded,token);
        loaded=saved || loaded;
        if(selectedCell===cell && token===parcelCache.token) publishParcels(loaded,loaded.complete);
        // Finish the current page for the cache; do not download the rest of an abandoned cell.
        if(selectedCell!==cell || token!==parcelCache.token) break;
      } while(!loaded.complete);
      return loaded;
    });
    if(request!==parcelRequest) return;
    publishParcels(entry,true);
    if(parcelCache.diskFailed) $("parcel-status").textContent+=" Browser storage unavailable; cache is limited to this session.";
  } catch(error) {
    if(request!==parcelRequest) return;
    if(parcelEntry) publishParcels(parcelEntry,true);
    $("parcel-status").textContent=parcelEntry?.manifest && parcelEntry.manifest.dataset_version!==manifest.dataset_version
      ? `Source unavailable; cached inventory from ${new Date(parcelEntry.savedAt).toISOString()}. Replacement inventory could not load: ${error.message}`
      : `Parcel coverage unavailable or incomplete: ${error.message}. ${parcelData?.features.length || 0} parcels shown; this is a partial inventory.`;
    $("parcel-retry").hidden=false;
  }
}

function setupMap(settings) {
  mapToken = settings.configured ? settings.public_token : null;
  if (!settings.configured) {
    $("map-status").textContent = "Add MAPBOX_PUBLIC_TOKEN to your local .env and restart the app to enable the map. The site list remains available.";
    $("map").replaceChildren(element("p", "Mapbox token not configured", "map-fallback"));
    return;
  }
  if (!window.mapboxgl || !window.h3 || !window.QuasarSpatial) {
    $("map-status").textContent = "Map libraries unavailable. Check your network; the site list remains available.";
    return;
  }
  try {
    $("map").replaceChildren();
    map = new mapboxgl.Map({container:"map", accessToken:settings.public_token, style:settings.style,
      center:[-86.57,30.65], zoom:9, cooperativeGestures:false, attributionControl:false});
    map.addControl(new mapboxgl.NavigationControl(), "bottom-left");
    map.addControl(new mapboxgl.AttributionControl({compact:false, customAttribution:
      "DEMO · Fictional sites / synthetic site inputs · Unvalidated estimates. Follow official NWS/local guidance."}), "bottom-right");
    // The shell animates its sidebar width without a window resize event. Observe
    // the visible viewport so Mapbox also gets a resize after its flex layout settles.
    if (window.ResizeObserver) {
      new window.ResizeObserver(() => map.resize()).observe($("map").parentElement);
    }
    map.on("error", () => { $("map-status").textContent = "Mapbox could not load a resource. Check your token, URL restrictions and network. The site list remains available."; });
    map.on("load", () => {
      const empty = {type:"FeatureCollection", features:[]};
      const hatch = new Uint8Array(8*8*4);
      for (let y=0;y<8;y++) for (let x=0;x<8;x++) {
        const offset = (y*8+x)*4;
        hatch.set([55,65,81,(x+y)%8<2 ? 150 : 0],offset);
      }
      map.addImage("exposure-hatch", {width:8,height:8,data:hatch});
      map.addSource("native-rainfall", {type:"geojson", data:empty});
      map.addLayer({id:"native-rainfall-fill",type:"fill",source:"native-rainfall",paint:{
        "fill-color":["case",["==",["get","rainfall_mm"],null],"#a1a9ad",["step",["get","rainfall_mm"],"#b9e2f8",25,"#509dce",75,"#3156a6"]],"fill-opacity":0.35}});
      map.addLayer({id:"native-rainfall-outline",type:"line",source:"native-rainfall",paint:{"line-color":"#6d99bc","line-width":0.6}});
      map.addSource("hotspots", {type:"geojson", data:empty});
      map.addLayer({id:"hotspot-fill", type:"fill", source:"hotspots", paint:{"fill-color":mapColors("exposure_score"), "fill-opacity":0.28}});
      map.addLayer({id:"hotspot-hatch", type:"fill", source:"hotspots", filter:["==",["get","exposure_incomplete"],true], paint:{"fill-pattern":"exposure-hatch","fill-opacity":0.45}});
      map.addLayer({id:"hotspot-outline", type:"line", source:"hotspots", paint:{"line-color":"#9ca3af", "line-width":1}});
      map.addSource("county-boundary", {type:"geojson", data:county || empty});
      map.addLayer({id:"county-boundary", type:"line", source:"county-boundary", paint:{"line-color":"#ecf4ef","line-width":2,"line-dasharray":[3,2]}});
      map.addSource("selected-cell", {type:"geojson", data:empty});
      map.addLayer({id:"selected-cell-outline", type:"line", source:"selected-cell", paint:{"line-color":"#ffffff","line-width":3}});
      map.addSource("parcels", {type:"geojson", data:empty});
      map.addLayer({id:"parcel-fill", type:"fill", source:"parcels", paint:{"fill-color":mapColors("exposure_score"),"fill-opacity":0.45}});
      map.addLayer({id:"parcel-hatch", type:"fill", source:"parcels", filter:["==",["get","exposure_incomplete"],true], paint:{"fill-pattern":"exposure-hatch","fill-opacity":0.65}});
      map.addLayer({id:"parcel-outline", type:"line", source:"parcels", paint:{"line-color":"#6b7280","line-width":1.1}});
      map.addSource("selected-parcel", {type:"geojson", data:empty});
      map.addLayer({id:"selected-parcel-fill", type:"fill", source:"selected-parcel", paint:{"fill-color":mapColors("exposure_score"),"fill-opacity":0.3}});
      map.addLayer({id:"selected-parcel-outline", type:"line", source:"selected-parcel", paint:{"line-color":"#ffffff","line-width":3}});
      map.addSource("sites", {type:"geojson", data:empty});
      map.addLayer({id:"site-points", type:"circle", source:"sites", paint:{"circle-radius":8,
        "circle-color":mapColors(), "circle-stroke-color":"#ffffff", "circle-stroke-width":1}});
      map.addLayer({id:"rainfall-labels",type:"symbol",source:"sites",layout:{"text-field":["get","rainfall_label"],"text-size":12,"text-offset":[0,1.5],"text-anchor":"top","text-allow-overlap":true,visibility:"none"},paint:{"text-color":"#102c43","text-halo-color":"#ffffff","text-halo-width":2}});
      map.on("click", "site-points", (event) => {
        const id = event.features[0].properties.property_id;
        choose(id);
        const point = current.features.find((f) => f.id === id);
        new mapboxgl.Popup().setLngLat(point.geometry.coordinates)
          .setDOMContent(element("div", `${point.properties.label}: ${$("map-layer").value === "rainfall" ? (rainfallValue(point) === null ? "Rainfall unavailable" : `${rainfallValue(point).toFixed(1)} mm / 6h`) : `${point.properties.risk.score ?? "Unknown"} / 100 (demo)`}`)).addTo(map);
      });
      map.on("click", "hotspot-fill", (event) => {
        if (map.queryRenderedFeatures(event.point, {layers:["site-points", "parcel-fill"]}).length) return;
        const p = event.features[0].properties;
        if (selectedCell !== p.h3_index) void inspectCell(p.h3_index,Number(p.resolution));
      });
      map.on("click", "parcel-fill", (event) => {
        if (map.queryRenderedFeatures(event.point, {layers:["site-points"]}).length) return;
        const feature = parcelData?.features.find(f=>f.id === event.features[0].properties.parcel_id);
        if (feature) inspectParcel(feature);
      });
      for (const layer of ["site-points", "hotspot-fill", "parcel-fill"]) {
        map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
      }
      for (const id of ["network", "route", "baseline", "destinations"]) map.addSource(`replay-${id}`, {type:"geojson", data:empty});
      map.addLayer({id:"replay-network",type:"line",source:"replay-network",filter:["==",["get","kind"],"road"],paint:{"line-color":["match",["get","state"],"closed","#d97835","unknown","#a4a8bb","#9bb8af"],"line-width":2,"line-opacity":0.6}});
      map.addLayer({id:"replay-network-access",type:"line",source:"replay-network",filter:["==",["get","kind"],"simulated_access"],paint:{"line-color":"#a4a8bb","line-width":2,"line-dasharray":[1,2]}});
      map.addLayer({id:"replay-baseline",type:"line",source:"replay-baseline",paint:{"line-color":"#6b7280","line-width":4,"line-dasharray":[2,2]}});
      map.addLayer({id:"replay-route",type:"line",source:"replay-route",filter:["==",["get","kind"],"road"],paint:{"line-color":"#168c7d","line-width":5}});
      map.addLayer({id:"replay-connectors",type:"line",source:"replay-route",filter:["==",["get","kind"],"simulated_access"],paint:{"line-color":"#168c7d","line-width":4,"line-dasharray":[1,2]}});
      map.addLayer({id:"replay-destinations",type:"circle",source:"replay-destinations",paint:{"circle-radius":9,"circle-color":["case",["get","available"],"#168c7d","#a4a8bb"],"circle-stroke-color":"#ffffff","circle-stroke-width":2}});
      mapLoaded = true; frameCounty(); updateMap(); toggleHex();
    });
    map.on("zoomend", () => {
      updateCountyGrid();
    });
    $("hex-toggle").onchange = toggleHex;
  } catch {
    $("map-status").textContent = "Mapbox could not initialize on this browser. The site list remains available.";
  }
}

function toggleHex() {
  if (!mapLoaded) return;
  for (const id of ["hotspot-fill", "hotspot-outline"]) map.setLayoutProperty(id, "visibility", $("hex-toggle").checked ? "visible" : "none");
  map.setLayoutProperty("hotspot-hatch", "visibility", $("hex-toggle").checked && $("map-layer").value !== "rainfall" ? "visible" : "none");
}

function showWeatherStatus(data) {
  if (data.message) { $("weather-status").textContent = data.message; return; }
  $("weather-status").textContent = `${data.status.toUpperCase()} · initialized ${data.init_time} · imported ${data.retrieved_at} · ${data.native_resolution} ensemble mean. Stale or incomplete rainfall is not scored.`;
}

async function loadScenario(options = {}) {
  const thisRequest = ++requestId;
  const isReplay = replaySelected() && replayController;
  if (!isReplay) replayController?.pause();
  const site = selectedId || "demo-001";
  const params = isReplay ? replayController.parameters() : {};
  const query = new URLSearchParams({scenario:$("scenario").value,...params});
  try {
    if (isReplay) {
      const [data, timeline, routes] = await Promise.all([
        api(`/api/properties?${query}`),
        api(`/api/timeline?${new URLSearchParams({site,...params})}`),
        api("/api/routes", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(replayController.routing(site))}),
      ]);
      if (thisRequest !== requestId) return false;
      if ([data.replay.at,timeline.at,routes.at].some(at=>at!==params.at)) throw new Error("Replay timestamps do not match");
      selectedId = site;
      replayController.render(timeline,routes);
      render(data);
    } else {
      let data;
      if (playback && $("scenario").value === "weathernext") {
        const timeline = await api("/api/weather/timeline");
        if (thisRequest !== requestId) return false;
        if (!timeline.frames?.length) throw new Error(timeline.message || "Forecast playback unavailable");
        const index = Math.min(options.forecastIndex ?? (current?.scenario.id === "weathernext" ? forecastIndex : timeline.default_index), timeline.frames.length-1);
        forecastTimeline = timeline; forecastIndex = index;
        data = timeline.frames[index].collection;
      } else data = await api(`/api/properties?${query}`);
      if (thisRequest !== requestId) return false;
      render(data);
    }
    $("error").hidden = true;
    return true;
  } catch (error) {
    if (thisRequest !== requestId) return false;
    if (isReplay) {
      replayController.fail();
      if (current?.replay?.at) replayController.state.index = Math.round((Date.parse(current.replay.at)-Date.parse(window.QuasarReplay.hour(0)))/3600000);
    }
    if (current) $("scenario").value = current.scenario.id;
    $("error").textContent = `Could not load exercise data: ${error.message}`;
    $("error").hidden = false;
    playback?.pause();
    return false;
  }
}

async function start() {
  if (started) return;
  started = true;
  if (window.QuasarMapUI) {
    playback = window.QuasarMapUI.createPlayback({get:$, select:(kind,index)=>kind === "archive" ? replayController.seek(index) : loadScenario({forecastIndex:index})});
    window.addEventListener("hashchange",()=>{
      if (!["#map-overview", "#isaias-replay", "#site-details", ""].includes(window.location.hash)) {playback.pause();searchController?.close();}
    });
    $("map-sidebar-close").onclick = () => {
      $("map-inspect-toggle").setAttribute("aria-expanded", "false");
      $("map-sidebar").setAttribute("data-dismissed", "true");
      Promise.resolve().then(()=>$("map-tools").querySelector("summary").focus());
    };
    $("map-zoom-in").onclick=()=>map?.zoomIn();
    $("map-zoom-out").onclick=()=>map?.zoomOut();
    // Mobile details are modal; trap focus and make the covered controls inert.
    const viewport=$("map-overview");
    $("map-source-info").ontoggle=()=>{
      if(!$("map-source-info").open)return;
      closeSelection();$("map-sidebar").setAttribute("data-dismissed","true");
    };
    viewport.addEventListener("pointerdown",event=>{if(!event.target.closest(".map-search"))searchController?.close();});
    function syncSheet() {
      const selection=!$("map-selection-panel").hidden;
      const inspection=$("map-sidebar").getAttribute("data-dismissed")!=="true" &&
        ($("map-inspect-toggle").getAttribute("aria-expanded")==="true" || $("replay-toggle").getAttribute("aria-pressed")==="true");
      const mobile=window.matchMedia("(max-width: 767px)").matches;
      const panel=selection ? $("map-selection-panel") : inspection ? $("map-sidebar") : null;
      for (const node of [$("map-selection-panel"),$("map-sidebar")]) {
        node.inert=Boolean(mobile && panel && node!==panel);
        if(mobile && node===panel){node.setAttribute("role","dialog");node.setAttribute("aria-modal","true");}
        else {node.removeAttribute("role");node.removeAttribute("aria-modal");}
      }
      for(const node of viewport.querySelectorAll(".map-float, #map")) node.inert=Boolean(mobile && panel);
      const hideBackdrop=!(mobile && panel);
      if($("map-sheet-backdrop").hidden!==hideBackdrop)$("map-sheet-backdrop").hidden=hideBackdrop;
      if(mobile && panel && !panel.contains(document.activeElement))panel.querySelector("button, select, input, a")?.focus();
    }
    new MutationObserver(syncSheet).observe(viewport,{subtree:true,attributes:true,attributeFilter:["hidden","aria-expanded","aria-pressed","data-dismissed"]});
    $("map-legend").open=viewport.clientWidth>850;
    window.addEventListener("resize",syncSheet);
    const inspectLink=()=>{
      if(window.location.hash==="#site-details"){
        $("map-sidebar").removeAttribute("data-dismissed");
        $("map-inspect-toggle").setAttribute("aria-expanded","true");
      }
    };
    window.addEventListener("hashchange",inspectLink);
    inspectLink();
    $("map-sheet-backdrop").onclick=()=>{if(!$("map-selection-panel").hidden)closeSelection();else $("map-sidebar-close").click();};
    viewport.addEventListener("keydown",event=>{
      const panel=viewport.querySelector('[aria-modal="true"]');
      if(!panel)return;
      if(event.key==="Escape"){$("map-sheet-backdrop").click();event.preventDefault();}
      if(event.key==="Tab"){
        const nodes=Array.from(panel.querySelectorAll('button, select, input, a[href], [tabindex="0"]')).filter(n=>!n.disabled && n.getClientRects().length);
        const first=nodes[0],last=nodes.at(-1);
        if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}
      }
    });
  }
  $("selection-close").onclick = closeSelection;
  $("selection-back").onclick = () => {
    selectedParcel = null;
    if (mapLoaded) map.getSource("selected-parcel").setData(emptyCollection());
    renderCellPanel();
    void loadInspection("cell",selectedCell);
  };
  $("parcel-retry").onclick = () => {
    selectedParcel=null; map.getSource("selected-parcel").setData(emptyCollection());
    renderCellPanel(); void loadInspection("cell",selectedCell); return loadParcels();
  };
  $("cell-zoom").onclick=()=>{const [lat,lon]=h3.cellToLatLng(selectedCell); map.flyTo({center:[lon,lat],zoom:QuasarSpatial.childZoom(selectedResolution),duration:650});};
  $("parcel-search").oninput=()=>{parcelSearch=$("parcel-search").value.trim();parcelListPage=0;renderParcelList();};
  $("parcel-previous").onclick=()=>{parcelListPage=Math.max(0,parcelListPage-1);renderParcelList();};
  $("parcel-next").onclick=()=>{parcelListPage++;renderParcelList();};
  $("parcel-refresh").onclick=async()=>{
    const cell=selectedCell; ++parcelRequest; ++contextRequest; contextCache.clear();
    await parcelCache.remove(cell);
    if(selectedCell!==cell) return;
    selectedParcel=null; parcelEntry=parcelData=cellContext=parcelContext=null;
    map.getSource("selected-parcel").setData(emptyCollection()); map.getSource("parcels").setData(emptyCollection());
    renderCellPanel(); await loadParcels(true);
    if(selectedCell===cell) void loadInspection("cell",cell);
  };
  $("parcel-clear").onclick=async()=>{closeSelection();contextCache.clear();await parcelCache.clear();};
  void parcelCache.check(()=>api("/api/parcels/manifest"));
  window.addEventListener?.("keydown", event => { if (event.key === "Escape") closeSelection(); });
  $("map-layer").onchange = () => { showMapSummary(); updateMap(); };
  $("map-site").onchange = () => choose($("map-site").value);
  $("map-inspect-toggle").onclick = () => {
    $("map-sidebar").removeAttribute?.("data-dismissed");
    const inspecting = $("map-inspect-toggle").getAttribute("aria-expanded") !== "true";
    if (inspecting) closeSelection();
    $("map-inspect-toggle").setAttribute("aria-expanded", String(inspecting));
    if(playback)$("map-tools").open=false;
    if(playback)$("map-source-info").open=false;
  };
  $("replay-toggle").onclick = () => {
    playback?.pause();
    $("map-sidebar").removeAttribute?.("data-dismissed");
    if(playback)$("map-tools").open=false;
    if(playback)$("map-source-info").open=false;
    $("scenario").value = replaySelected() ? previousScenario : "isaias-2026";
    if (window.location) window.location.hash = "#map-overview";
    return loadScenario();
  };
  if (window.QuasarReplay) {
    replayController = window.QuasarReplay.create({get:$,element,load:loadScenario,controls:!playback,onPause:()=>{if(replaySelected())playback?.pause();}});
    window.addEventListener("hashchange",()=>{
      if (!["#map-overview", "#isaias-replay", "#site-details", ""].includes(window.location.hash)) replayController.pause();
      if (window.location.hash === "#isaias-replay" && $("scenario").children.length) {
        $("scenario").value="isaias-2026";void loadScenario();
      }
    });
    try { replayController.setContext(await api("/api/replay/context")); } catch { /* Explicit unavailable context in the replay. */ }
  }
  try {
    const config=await api("/api/config");
    if(config.exposure_scale) QuasarSpatial.configureExposure(config.exposure_scale);
    setupMap(config.map);
  }
  catch { $("map-status").textContent = "Map configuration unavailable; the site list remains available."; }
  if (map) {
    try {
      const data = await api("/api/county");
      if (data.county_fips !== "12091" || data.features?.length !== 1) throw new Error("County boundary unavailable");
      county = data;
      if (mapLoaded) map.getSource("county-boundary").setData(county);
      frameCounty();
      updateCountyGrid();
    } catch {
      $("grid-status").textContent = "County boundary unavailable · reload to retry";
    }
  }
  if (window.QuasarMapUI) searchController = window.QuasarMapUI.createSearch({get:$,element,token:mapToken,geometry:county?.features[0]?.geometry,select:feature=>{
    searchMarker?.remove();searchMarker=null;
    if(!feature || !map)return;
    closeSelection();
    $("map-inspect-toggle").setAttribute("aria-expanded","false");
    $("map-sidebar").setAttribute("data-dismissed","true");
    const coordinates=feature.geometry.coordinates;
    searchMarker=new mapboxgl.Marker({color:"#166b62"}).setLngLat(coordinates).addTo(map);
    map.flyTo({center:coordinates,zoom:15,padding:{top:90,bottom:150,left:40,right:40},essential:false});
  }});
  try { showWeatherStatus(await api("/api/weather/status")); }
  catch { $("weather-status").textContent = "Forecast status unavailable. No live connection is implied."; }
  try {
    const data = await api("/api/scenarios");
    for (const scenario of data.scenarios) {
      const option = element("option", scenario.label); option.value = scenario.id; $("scenario").append(option);
    }
    $("replay-toggle").disabled = !replayController || !data.scenarios.some(s => s.id === "isaias-2026");
    $("scenario").disabled = false; $("scenario").onchange = () => {playback?.pause();return loadScenario();};
    if (data.scenarios.some(s => s.id === "weathernext")) $("scenario").value = "weathernext";
    if (window.location?.hash === "#isaias-replay") $("scenario").value="isaias-2026";
    await loadScenario();
  } catch (error) {
    $("error").textContent = `Could not initialize the exercise: ${error.message}`; $("error").hidden = false;
  }
  try { $("official-status").textContent = (await api("/api/official-alerts")).message; }
  catch { $("official-status").textContent = "Official feed status unavailable. This is not an all-clear."; }
}
// React mounts the existing map workspace before starting its data controller.
window.Quasar = { start };
if ($("scenario")) start();
else document.dispatchEvent(new Event("quasar:ready"));
