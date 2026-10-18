"use strict";
const $ = (id) => document.getElementById(id);
const colors = { unknown: "#9ca3af" };
const names = { rainfall_6h_mm: "Rainfall, six hours (mm)", elevation_m: "Terrain elevation (m)", fema_zone: "Illustrative FEMA zone", waterway_distance_m: "Waterway distance (m)", gauge_margin_m: "Margin below flood stage (m)" };
let map, mapLoaded = false, current, mapData = {}, requestId = 0, started = false;
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

function render(data) {
  ++exposureRequest;
  window.clearTimeout?.(exposureExpiryTimer);
  exposureData = null; exposureHydrationRunning = false;
  exposureResponses.clear(); parcelAssessments.clear();
  current = data;
  if (parcelEntry && mapLoaded) publishParcels(parcelEntry,true);
  $("mode-badge").textContent = ["invalid","unavailable","not_configured"].includes(data.forecast?.status) ? "ARCHIVE UNAVAILABLE" : data.forecast?.status === "loading" ? "LOADING ISAIAS" : "ISAIAS · ARCHIVED FORECAST";
  $("data-notice").textContent = data.notice;
  $("map-demo-notice").textContent = data.notice;
  showMapSummary(); updateMap(); renderArchiveTrend();
  if (selectedCell) { if (selectedParcel === null) renderCellPanel(); else renderInspectionInputs(); }
  const archive = data.mode === "county_archive";
  const status = data.forecast?.status || "unavailable";
  const enabled = !["stale","invalid","unavailable","not_configured"].includes(status);
  playback?.configure(archive ? "archive" : "forecast", (forecastTimeline?.frames || []).map(f=>f.at), forecastIndex, enabled,
    status === "stale" ? "Current forecast is stale. An explicit import is required to refresh it." :
    forecastTimeline?.message || (status === "loading" ? "Loading Isaias archive…" : status === "incomplete" ? "Some cells lack six complete hours. Gaps remain unknown." : "Following six-hour rainfall · forecast reconstruction"));
  $("forecast-retry").disabled = status === "loading";
  window.clearTimeout?.(forecastExpiryTimer);
  const expiry = Date.parse(forecastTimeline?.expires_at);
  if (!archive && enabled && expiry > Date.now()) forecastExpiryTimer = window.setTimeout?.(()=>{
    // Clear expired values before waiting for a potentially slow or failed refresh.
    if (current?.mode !== "county_forecast") return;
    forecastTimeline = {...forecastTimeline,status:"stale"};
    const cells = current.weather_cells;
    render({...current,forecast:{...current.forecast,status:"stale"},weather_cells:cells && {...cells,
      features:cells.features.map(f=>({...f,properties:{...f.properties,status:"stale",rainfall_6h_mm:null}}))}});
    void loadScenario({forecastIndex});
  },expiry-Date.now()+1);
}

function showMapSummary() {
  if (!current) return;
  const rain = $("map-layer").value === "rainfall";
  const forecast = current.forecast || {}, cells = current.weather_cells;
  const available = (cells?.features || []).filter(f=>f.properties.status === "ready" && typeof f.properties.rainfall_6h_mm === "number");
  const values = available.map(f=>f.properties.rainfall_6h_mm);
  $("map-data-title").textContent = rain ? "WeatherNext 3 rainfall · mm / 6h" : "Experimental relative exposure · index / 100";
  $("map-display-label").textContent = !rain ? (exposureData?.status === "ready" ? "Experimental parcel exposure · /100" : "Parcel assessments unavailable") : values.length ? `${Math.min(...values).toFixed(1)}–${Math.max(...values).toFixed(1)} mm / 6h · ${available.length}/${cells.features.length} cells` : "Rainfall unavailable";
  $("map-data-values").textContent = values.length ? `${Math.min(...values).toFixed(1)}–${Math.max(...values).toFixed(1)} mm / 6h · ${available.length}/${cells.features.length} native cells available` : `Rainfall unavailable · ${forecast.status || "not configured"}. Missing and stale values remain unknown.`;
  $("window").textContent = current.scenario.valid_from ? `${current.mode === "county_archive" ? "Archived forecast" : "Forecast window"}: ${formatForecastTime(current.scenario.valid_from)} – ${formatForecastTime(current.scenario.valid_to)}` : "No imported forecast window available";
  $("map-data-source").textContent = `${forecast.status || "unavailable"} · initialized ${forecast.init_time || "unavailable"} · imported ${forecast.retrieved_at || "unavailable"} · native ${forecast.native_resolution || "0.1 degree"} ensemble mean. ${forecast.source_table || "Source unavailable"}. Forecast rain is not observed rain or parcel flood risk.`;
  $("exposure-legend").hidden = rain; $("rainfall-legend").hidden = !rain;
  $("map-layer-note").textContent = rain ? "Native rainfall cells retain their source resolution. Transparent cells have unavailable rainfall. H3 outlines support parcel browsing and do not sharpen forecasts." : `${exposureData?.message || "Parcel assessments are unavailable unless matching results are configured."} Transparent interiors indicate unknown scores. Incomplete coverage is reported in details. Green does not establish safety.`;
  showWeatherStatus(forecast);
}

function formatForecastTime(value) {
  return value ? new Date(value).toLocaleString("en-US", {timeZone:"America/Chicago",month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"}) : "Unavailable";
}

function renderArchiveTrend() {
  const frames=forecastTimeline?.frames || [];
  const peaks=frames.map(frame=>{
    const features=frame.collection.weather_cells.features;
    const values=features.filter(f=>f.properties.status==="ready" && Number.isFinite(f.properties.rainfall_6h_mm)).map(f=>f.properties.rainfall_6h_mm);
    return {peak:values.length ? Math.max(...values) : null, available:values.length, total:features.length};
  });
  const max=Math.max(1,...peaks.map(p=>p.peak ?? 0));
  const chart=$("archive-trend"), focused=chart.contains?.(document.activeElement); chart.replaceChildren();
  frames.forEach((frame,index)=>{
    const {peak,available,total}=peaks[index];
    const label=`${formatForecastTime(frame.at)}: ${peak===null ? "rainfall unavailable" : `${peak.toFixed(2)} mm / 6h maximum; ${available}/${total} cells available`}`;
    const button=element("button"); button.type="button"; button.title=label;
    button.setAttribute("aria-label",label); button.setAttribute("aria-pressed",String(index===forecastIndex));
    button.className=peak===null ? "trend-hour is-unknown" : available<total ? "trend-hour is-partial" : "trend-hour";
    const bar=element("span"); bar.style.height=peak===null ? "100%" : `${Math.max(4,peak/max*100)}%`;
    button.append(bar); button.onclick=()=>{playback?.pause();selectForecastFrame(index);};chart.append(button);
  });
  if(focused) chart.children[forecastIndex]?.focus();
  $("archive-trend-label").textContent=frames.length ? "Maximum native-cell rainfall · mm / 6h" : "Isaias · October 9, 2026";
  $("archive-trend-range").textContent=frames.length ? "Oct 9, midnight → Oct 10, midnight · Central" : "Archive unavailable. Recheck the source or inspect Data.";
}

function selectForecastFrame(index) {
  if(!Number.isInteger(index) || !forecastTimeline?.frames?.[index]) return false;
  forecastIndex=index;
  render(forecastTimeline.frames[index].collection);
  window.dispatchEvent?.(new CustomEvent("quasar:frame",{detail:{index}}));
  return true;
}

function mapColors(field = "risk_score") {
  return QuasarSpatial.exposureExpression(field);
}

function exposureParameters(resolution = 7) {
  if (!current?.scenario.valid_from || !["county_forecast", "county_archive"].includes(current.mode)) return null;
  return {from:current.scenario.valid_from, to:current.scenario.valid_to, resolution:String(resolution),
    mode:current.mode === "county_archive" ? "replay" : "current"};
}

function selectedExposureSummary() {
  const params=exposureParameters(selectedResolution);
  const response=params && exposureResponses.get(new URLSearchParams(params).toString());
  return response?.status === "ready" ? response.cells[selectedCell] : null;
}

function renderExposureInspection() {
  if(!selectedCell) return;
  const content=$("selection-exposure");
  let score = null;
  if(selectedParcel===null) {
    const summary=selectedExposureSummary(); score=summary?.p90_score ?? null;
    content.replaceChildren(element("p",summary ? `${summary.scored_count}/${summary.parcel_count} parcels scored · ${(summary.coverage*100).toFixed(1)}% coverage · P90 ${score ?? "Unknown"}${summary.incomplete ? " · Incomplete coverage" : ""}` : "No matching parcel assessment is available. Prepared reference inputs are shown below.","detail-note"));
    void refreshExposure(selectedResolution);
  } else {
    const assessment=exposureData?.status === "ready" && exposureData.inventory_id===parcelEntry?.inventory_id ? parcelAssessments.get(selectedParcel) : null;
    score=QuasarSpatial.validScore(assessment?.score) ? assessment.score : null;
    $("selection-badge").textContent=$("map-layer").value === "rainfall" ? "County parcel · archived inputs" : score===null ? "County parcel · unscored" : "County parcel · experimental index";
    content.replaceChildren(...(assessment?.factors || []).map(factor=>element("p", `${names[factor.name] || factor.name}: ${factor.value ?? "Unknown"} · +${factor.contribution.toFixed(1)} index points`,"detail-note")));
    if(score===null) content.append(element("p",`Assessment unavailable: ${assessment?.missing?.join(", ") || exposureData?.message || "No matching parcel assessment"}. Prepared reference inputs are shown below.`,"detail-note"));
    const model = assessment?.model_details;
    if (model && score !== null) {
      content.append(element("p", `Model: ${exposureData?.model_metadata?.model_version || exposureData?.method_version || "Unavailable"}`, "detail-note"));
      content.append(element("p", `Learned mapped susceptibility: ${model.susceptibility.toFixed(3)} · FEMA mapping proxy, not observed flood skill.`, "detail-note"));
      content.append(element("p", `Forecast rainfall: ${model.rainfall_6h_mm.toFixed(1)} mm / 6h · Rainfall stress: ${model.rainfall_stress.toFixed(3)} (experimental rule).`, "detail-note"));
      content.append(element("p", `Model instability: ${model.model_instability.toFixed(3)} · Ensemble spread, not a confidence interval.`, "detail-note"));
      content.append(element("p", `Raw model baseline: ${model.baseline.toFixed(3)} · Signed tree-path attributions (not physical causes):`, "detail-note"));
      for (const [name, value] of Object.entries(model.attributions)) {
        content.append(element("p", `${name}: ${value >= 0 ? "+" : ""}${value.toFixed(4)} raw susceptibility`, "detail-note"));
      }
      const source = exposureData?.forecast_provenance;
      if (source) content.append(element("p", `Forecast initialized ${source.init_time} · Imported ${source.retrieved_at} · ${source.native_resolution} · ${source.availability_basis}`, "detail-note"));
    }
  }
  $("selection-score").textContent=score===null ? "Unscored" : score.toFixed(1)+" / 100";
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
  const sourceExpiry=exposureData.forecast_provenance?.expires_at;
  const expires=Math.min(Date.parse(exposureData.valid_to),Date.parse(exposureData.computed_at)+2*3600000,
    sourceExpiry ? Date.parse(sourceExpiry) : Infinity);
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
  const rain = $("map-layer").value === "rainfall";
  const nativeSource = map.getSource("native-rainfall");
  if (nativeSource) {
    const cells = current?.weather_cells || emptyCollection();
    nativeSource.setData({...cells, features:cells.features.map(f => ({...f,
      properties:{...f.properties, rainfall_mm:f.properties.rainfall_6h_mm}}))});
    map.setLayoutProperty("native-rainfall-fill", "visibility", rain ? "visible" : "none");
    map.setLayoutProperty("native-rainfall-outline", "visibility", rain ? "visible" : "none");
  }
  toggleHex();
  updateCountyGrid();
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
  map.setPaintProperty("hotspot-fill", "fill-opacity", rain ? 0 : ["case",["==",["get","exposure_score"],null],0,0.28]);
  for (const layer of ["parcel-fill", "selected-parcel-fill"]) map.setPaintProperty(layer,"fill-opacity",rain ? 0 : ["case",["==",["get","exposure_score"],null],0,0.45]);
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
  const rain=$("map-layer").value === "rainfall";
  const summary=window.QuasarInspection.rainfallSummary(context,current);
  $("selection-rainfall").textContent=summary.value;
  $("selection-rainfall-note").textContent=summary.detail;
  $("selection-rainfall-meter").hidden=!rain;
  $("selection-exposure-meter").hidden=rain;
  $("selection-exposure-section").hidden=rain;
  const rows=selectedParcel === null ? window.QuasarInspection.forecastRows(context,current) : window.QuasarInspection.parcelRows(context,current);
  if(selectedParcel === null) rows.unshift(
    ["Distinct indexed parcels",cellContext?.parcel_count?.toLocaleString() ?? "Unknown"],
    ["Complete terrain summaries",cellContext?.terrain_complete_count?.toLocaleString() ?? "Unknown"],
    ["Complete / partial FEMA coverage",`${cellContext?.fema_complete_count?.toLocaleString() ?? "Unknown"} / ${cellContext?.fema_partial_count?.toLocaleString() ?? "Unknown"}`]);
  inputRows(rows);
  if (selectedParcel !== null) {
    const terrain=context?.inputs?.terrain;
    panelStats([[typeof terrain?.mean_m === "number" ? `${terrain.mean_m.toFixed(2)} m` : "Unknown","Mean terrain"],
      [context?.inputs?.fema?.status || "Unknown","FEMA coverage"],
      [context?.forecast_overlaps?.length ? String(context.forecast_overlaps.length) : "Unknown","Native overlaps"]]);
  }
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
  panelStats([[cellContext?.parcel_count?.toLocaleString() ?? (parcelData ? `${parcelData.features.length.toLocaleString()} loaded` : "Unknown"),"Parcels"],
    [cellContext?.terrain_complete_count?.toLocaleString() ?? "Unknown","Terrain complete"],
    [cellContext?.fema_complete_count?.toLocaleString() ?? "Unknown","FEMA complete"]]);
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
    $("map-status").textContent = "Add MAPBOX_PUBLIC_TOKEN to your local .env and restart the app to enable the map. Source tables remain available.";
    $("map").replaceChildren(element("p", "Mapbox token not configured", "map-fallback"));
    return;
  }
  if (!window.mapboxgl || !window.h3 || !window.QuasarSpatial) {
    $("map-status").textContent = "Map libraries unavailable. Check your network; source tables remain available.";
    return;
  }
  try {
    $("map").replaceChildren();
    map = new mapboxgl.Map({container:"map", accessToken:settings.public_token, style:settings.style,
      center:[-86.57,30.65], zoom:9, cooperativeGestures:false, attributionControl:false});
    map.addControl(new mapboxgl.NavigationControl(), "bottom-left");
    map.addControl(new mapboxgl.AttributionControl({compact:false, customAttribution:
      "Okaloosa County source data · Forecast rainfall is not flood depth. Follow official NWS/local guidance."}), "bottom-right");
    // The shell animates its sidebar width without a window resize event. Observe
    // the visible viewport so Mapbox also gets a resize after its flex layout settles.
    if (window.ResizeObserver) {
      new window.ResizeObserver(() => map.resize()).observe($("map").parentElement);
    }
    map.on("error", () => { $("map-status").textContent = "Mapbox could not load a resource. Check your token, URL restrictions and network. Source tables remain available."; });
    map.on("load", () => {
      const empty = {type:"FeatureCollection", features:[]};
      map.addSource("native-rainfall", {type:"geojson", data:empty});
      map.addLayer({id:"native-rainfall-fill",type:"fill",source:"native-rainfall",paint:{
        "fill-color":["case",["==",["get","rainfall_mm"],null],"#a1a9ad",["interpolate",["linear"],["get","rainfall_mm"],0,"#e0edf4",5,"#83c9df",25,"#3093bc",75,"#25439a"]],"fill-opacity":["case",["==",["get","rainfall_mm"],null],0,0.55]}});
      map.addLayer({id:"native-rainfall-outline",type:"line",source:"native-rainfall",paint:{"line-color":"#6d99bc","line-width":0.6}});
      map.addSource("hotspots", {type:"geojson", data:empty});
      map.addLayer({id:"hotspot-fill", type:"fill", source:"hotspots", paint:{"fill-color":mapColors("exposure_score"), "fill-opacity":["case",["==",["get","exposure_score"],null],0,0.28]}});
      map.addLayer({id:"hotspot-outline", type:"line", source:"hotspots", paint:{"line-color":"#9ca3af", "line-width":1}});
      map.addSource("county-boundary", {type:"geojson", data:county || empty});
      map.addLayer({id:"county-boundary", type:"line", source:"county-boundary", paint:{"line-color":"#ecf4ef","line-width":2,"line-dasharray":[3,2]}});
      map.addSource("selected-cell", {type:"geojson", data:empty});
      map.addLayer({id:"selected-cell-outline", type:"line", source:"selected-cell", paint:{"line-color":"#0d9488","line-width":3}});
      map.addSource("parcels", {type:"geojson", data:empty});
      map.addLayer({id:"parcel-fill", type:"fill", source:"parcels", paint:{"fill-color":mapColors("exposure_score"),"fill-opacity":["case",["==",["get","exposure_score"],null],0,0.45]}});
      map.addLayer({id:"parcel-outline", type:"line", source:"parcels", paint:{"line-color":"#667f80","line-width":0.65}});
      map.addSource("selected-parcel", {type:"geojson", data:empty});
      map.addLayer({id:"selected-parcel-fill", type:"fill", source:"selected-parcel", paint:{"fill-color":mapColors("exposure_score"),"fill-opacity":["case",["==",["get","exposure_score"],null],0,0.3]}});
      map.addLayer({id:"selected-parcel-outline", type:"line", source:"selected-parcel", paint:{"line-color":"#0d9488","line-width":3}});
      map.on("click", "hotspot-fill", (event) => {
        if (map.queryRenderedFeatures(event.point, {layers:["parcel-fill"]}).length) return;
        const p = event.features[0].properties;
        if (selectedCell !== p.h3_index) void inspectCell(p.h3_index,Number(p.resolution));
      });
      map.on("click", "parcel-fill", (event) => {
        const feature = parcelData?.features.find(f=>f.id === event.features[0].properties.parcel_id);
        if (feature) inspectParcel(feature);
      });
      for (const layer of ["hotspot-fill", "parcel-fill"]) {
        map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
      }
      mapLoaded = true; frameCounty(); updateMap(); toggleHex();
    });
    map.on("zoomend", () => {
      updateCountyGrid();
    });
    $("hex-toggle").onchange = toggleHex;
  } catch {
    $("map-status").textContent = "Mapbox could not initialize on this browser. Source tables remain available.";
  }
}

function toggleHex() {
  if (!mapLoaded) return;
  for (const id of ["hotspot-fill", "hotspot-outline"]) map.setLayoutProperty(id, "visibility", $("hex-toggle").checked ? "visible" : "none");
}

function showWeatherStatus(data) {
  if (data.message) { $("weather-status").textContent = data.message; return; }
  $("weather-status").textContent = `${(data.status || "unavailable").replaceAll("_"," ")} · initialized ${formatForecastTime(data.init_time)} · imported ${formatForecastTime(data.retrieved_at)} · ${data.native_resolution || "Unknown resolution"} ensemble mean. ${data.reconstruction || "Forecast rainfall, not observed rain."}`;
}

function unavailableFrame(source, status, message) {
  return {mode:source === "archive" ? "county_archive" : "county_forecast",features:[],notice:message,
    scenario:{id:source === "archive" ? "isaias-2026" : "weathernext",valid_from:null,valid_to:null},
    forecast:{status},weather_cells:emptyCollection()};
}

async function loadScenario(options = {}) {
  const thisRequest = ++requestId;
  const source="archive";
  forecastTimeline=null;
  render(unavailableFrame(source,"loading","Loading the Isaias county archive…"));
  try {
    const timeline=await api(`/api/weather/timeline?source=${source}`);
    if(thisRequest!==requestId)return false;
    if(timeline.county_fips!=="12091" || timeline.source!=="archive")throw new Error("Wrong forecast county or source");
    forecastTimeline=timeline;
    const index=Math.min(options.forecastIndex ?? forecastIndex,Math.max(0,(timeline.frames?.length || 0)-1));
    forecastIndex=index;
    if(!selectForecastFrame(index)) render(unavailableFrame(source,timeline.status,timeline.message));
    $("error").hidden=true;return true;
  } catch(error) {
    if(thisRequest!==requestId)return false;
    forecastTimeline={status:"unavailable",frames:[],message:`Forecast source unavailable: ${error.message}`};
    render(unavailableFrame(source,"unavailable",forecastTimeline.message));
    $("error").textContent=forecastTimeline.message;$("error").hidden=false;playback?.pause();return false;
  }
}

async function start() {
  if (started) return;
  started = true;
  if (window.QuasarMapUI) {
    playback = window.QuasarMapUI.createPlayback({get:$, select:(_kind,index)=>selectForecastFrame(index)});
    window.addEventListener("hashchange",()=>{
      if (!["#map-overview", "#isaias-replay", ""].includes(window.location.hash)) {playback.pause();searchController?.close();}
    });
    $("map-zoom-in").onclick=()=>map?.zoomIn();
    $("map-zoom-out").onclick=()=>map?.zoomOut();
    // Mobile details are modal; trap focus and make the covered controls inert.
    const viewport=$("map-overview");
    $("map-source-info").ontoggle=()=>{
      if(!$("map-source-info").open)return;
      closeSelection();
    };
    viewport.addEventListener("pointerdown",event=>{if(!event.target.closest(".map-search"))searchController?.close();});
    function syncSheet() {
      const selection=!$("map-selection-panel").hidden;
      const mobile=window.matchMedia("(max-width: 767px)").matches;
      const panel=selection ? $("map-selection-panel") : null;
      const node=$("map-selection-panel");
      if(mobile && panel){node.setAttribute("role","dialog");node.setAttribute("aria-modal","true");}
      else {node.removeAttribute("role");node.removeAttribute("aria-modal");}
      for(const node of viewport.querySelectorAll(".map-float, #map")) node.inert=Boolean(mobile && panel);
      const hideBackdrop=!(mobile && panel);
      if($("map-sheet-backdrop").hidden!==hideBackdrop)$("map-sheet-backdrop").hidden=hideBackdrop;
      if(mobile && panel && !panel.contains(document.activeElement))panel.querySelector("button, select, input, a")?.focus();
    }
    new MutationObserver(syncSheet).observe(viewport,{subtree:true,attributes:true,attributeFilter:["hidden","aria-expanded","aria-pressed","data-dismissed"]});
    $("map-legend").open=viewport.clientWidth>850;
    window.addEventListener("resize",syncSheet);
    $("map-sheet-backdrop").onclick=closeSelection;
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
  $("forecast-retry").onclick=()=>{playback?.pause();return loadScenario();};
  window.addEventListener?.("quasar:seek",event=>{playback?.pause();forecastIndex=event.detail.index;selectForecastFrame(forecastIndex);});
  // Archive reads must not wait for Mapbox or the external county service.
  const archiveLoad=loadScenario();
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
  $("map-layer").onchange = () => { showMapSummary(); updateMap(); if(selectedCell)renderInspectionInputs(); };
  try {
    const config=await api("/api/config");
    if(config.exposure_scale) QuasarSpatial.configureExposure(config.exposure_scale);
    setupMap(config.map);
  }
  catch { $("map-status").textContent = "Map configuration unavailable; source tables remain available."; }
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
    const coordinates=feature.geometry.coordinates;
    searchMarker=new mapboxgl.Marker({color:"#166b62"}).setLngLat(coordinates).addTo(map);
    map.flyTo({center:coordinates,zoom:15,padding:{top:90,bottom:150,left:40,right:40},essential:false});
  }});
  await archiveLoad;
  try { $("official-status").textContent = (await api("/api/official-alerts")).message; }
  catch { $("official-status").textContent = "Official feed status unavailable. This is not an all-clear."; }
}
// React mounts the existing map workspace before starting its data controller.
window.Quasar = { start, frame:()=>forecastIndex };
if ($("map-overview")) start();
else document.dispatchEvent(new Event("quasar:ready"));
