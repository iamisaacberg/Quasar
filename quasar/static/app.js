"use strict";
const $ = (id) => document.getElementById(id);
const colors = { unknown: "#9ca3af" };
const names = { rainfall_6h_mm: "Rainfall, six hours (mm)", elevation_m: "Terrain elevation (m)", fema_zone: "Illustrative FEMA zone", waterway_distance_m: "Waterway distance (m)", gauge_margin_m: "Margin below flood stage (m)", susceptibility_rainfall_interaction: "Susceptibility-rainfall interaction" };
let map, mapLoaded = false, current, mapData = {}, requestId = 0, started = false;
let county, selectedCell, selectedParcel, parcelData, parcelRequest = 0;
const countyGrids = new Map(), rainfallGrids = new Map(), sourceKeys=new Map(), sourceStates=new Map();
let gridScheduled=false, gridEpoch=0;
function stateExpression(expression,field) {
  if(!Array.isArray(expression))return expression;
  if(expression[0]==="get" && expression[1]===field && map?.setFeatureState)return ["feature-state",field];
  return expression.map(value=>stateExpression(value,field));
}
function paintSource(name,collection,key,values) {
  const source=map.getSource(name);
  if(!map.setFeatureState){source.setData(collection);return;}
  if(sourceKeys.get(name)!==key){
    map.removeFeatureState?.({source:name});
    source.setData(collection);sourceKeys.set(name,key);sourceStates.set(name,new Map());
    window.QuasarPerformance?.record("map-update",{source:name,kind:"geometry",features:collection.features.length});
  }
  const previous=sourceStates.get(name);
  for(const feature of collection.features){
    const state=values(feature),signature=JSON.stringify(state);
    if(previous.get(feature.id)===signature)continue;
    map.setFeatureState({source:name,id:feature.id},state);previous.set(feature.id,signature);
  }
}
function clearSource(name){
  sourceKeys.delete(name);sourceStates.delete(name);
  map.removeFeatureState?.({source:name});map.getSource(name).setData(emptyCollection());
}
function opacity(field,value){return stateExpression(["case",["==",["get",field],null],0,value],field);}

let exposureData = null, exposureRequest = 0, exposureHydrationRunning = false, exposureExpiryTimer;
const exposureResponses = new Map(), parcelAssessments = new Map();
const exposureLoads = new Map();
const assessmentSeen=new Set(),assessmentSizes=new Map();
let assessmentBytes=0;
function clearAssessments(){parcelAssessments.clear();assessmentSeen.clear();assessmentSizes.clear();assessmentBytes=0;}
function rememberAssessment(id,record){
  assessmentSeen.add(id);
  assessmentBytes-=assessmentSizes.get(id)||0;
  parcelAssessments.delete(id);parcelAssessments.set(id,record);
  const bytes=JSON.stringify(record).length*2;assessmentSizes.set(id,bytes);assessmentBytes+=bytes;
  while(assessmentBytes>10*1024*1024 && parcelAssessments.size>1){
    const oldest=[...parcelAssessments.keys()].find(value=>value!==selectedParcel);
    assessmentBytes-=assessmentSizes.get(oldest)||0;assessmentSizes.delete(oldest);parcelAssessments.delete(oldest);
  }
  let total=assessmentBytes+[...exposureFrames.values()].reduce((sum,value)=>sum+value.bytes,0);
  while(total>EXPOSURE_CACHE_BYTES && exposureFrames.size){const oldest=exposureFrames.keys().next().value;total-=exposureFrames.get(oldest).bytes;exposureFrames.delete(oldest);}
}

const playbackExposure = new Map(), exposureFrames=new Map();
const EXPOSURE_CACHE_BYTES=20*1024*1024;
function exposureFrameKey(data=current){return data?.scenario.valid_from ? `${$("exposure-model").value || "v2"}:${data.mode}:${data.scenario.valid_from}:${data.scenario.valid_to}` : null;}
function saveExposureFrame(){
  const key=exposureFrameKey();
  if(!key || exposureData?.status!=="ready")return;
  const entry={data:exposureData,responses:new Map([...exposureResponses].filter(([,v])=>v.status==="ready")),parcels:new Map(parcelAssessments)};
  entry.bytes=JSON.stringify([...entry.responses]).length*2+JSON.stringify([...entry.parcels]).length*2;
  exposureFrames.delete(key);exposureFrames.set(key,entry);
  const entries=[...exposureFrames.values()];
  for(const stale of entries.slice(0,-3)){stale.parcels.clear();stale.bytes=JSON.stringify([...stale.responses]).length*2;}
  let bytes=[...exposureFrames.values()].reduce((sum,value)=>sum+value.bytes,0);
  while(bytes>EXPOSURE_CACHE_BYTES){const oldest=exposureFrames.keys().next().value;bytes-=exposureFrames.get(oldest).bytes;exposureFrames.delete(oldest);}
}
function restoreExposureFrame(){
  const entry=exposureFrames.get(exposureFrameKey());
  if(!entry)return;
  if(parcelEntry && entry.data.inventory_id!==parcelEntry.inventory_id){exposureFrames.clear();return;}
  if(current.mode==="county_forecast"){
    const expiry=Math.min(Date.parse(entry.data.valid_to),Date.parse(entry.data.computed_at)+7200000,Date.parse(entry.data.forecast_provenance?.expires_at)||Infinity);
    if(expiry<=Date.now()){exposureFrames.delete(exposureFrameKey());return;}
  }
  exposureData=entry.data;for(const [key,value]of entry.responses)exposureResponses.set(key,value);
  for(const [key,value]of entry.parcels)rememberAssessment(key,value);
}

let parcelExposureLoad;
const parcelCache = window.QuasarParcelCache.create({indexedDB:window.indexedDB});
let selectedResolution = 7, parcelEntry, cellContext, parcelContext, contextRequest = 0;
let contextLoading = false;
let contextMessage = "", parcelListPage = 0, parcelSearch = "", lastParcelPaint = 0;
let parcelPaintTimer;
const contextCache = new Map();
const emptyCollection = () => ({type:"FeatureCollection", features:[]});
let countyFramed = false;
let playback, forecastTimeline, forecastIndex, mapToken, searchController, searchMarker;
let forecastExpiryTimer;
let trendTimeline,trendPeaks=[];
let assessmentFlightCount=0;
const assessmentQueue=[];
function assessmentApi(url,priority=false){
  return new Promise((resolve,reject)=>{
    const run=()=>{assessmentFlightCount++;api(url).then(resolve,reject).finally(()=>{assessmentFlightCount--;assessmentQueue.shift()?.();});};
    if(assessmentFlightCount<3)run();else if(priority)assessmentQueue.unshift(run);else assessmentQueue.push(run);
  });
}


async function api(url, options) {
  if(window.QuasarData) return window.QuasarData.get(url,options);
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
  saveExposureFrame();
  ++exposureRequest;
  if(mapLoaded && map.setFeatureState){for(const feature of countyGrids.get(QuasarSpatial.resolutionForZoom(map.getZoom()))?.features || [])map.setFeatureState({source:"hotspots",id:feature.id},{rainfall_mm:null,exposure_score:null});sourceStates.delete("hotspots");sourceStates.set("hotspots",new Map());}
  window.clearTimeout?.(exposureExpiryTimer);
  exposureData = null; exposureHydrationRunning = false;
  exposureResponses.clear(); clearAssessments();
  current = data;
  restoreExposureFrame();
  scheduleExposureExpiry();
  if (parcelEntry && mapLoaded) publishParcels(parcelEntry,true);
  $("mode-badge").textContent = ["invalid","unavailable","not_configured"].includes(data.forecast?.status) ? "ARCHIVE UNAVAILABLE" : data.forecast?.status === "loading" ? "LOADING ISAIAS" : "ISAIAS · ARCHIVED FORECAST";
  $("data-notice").textContent = data.notice;
  $("map-demo-notice").textContent = data.notice;
  showMapSummary(); updateMap(); renderArchiveTrend();
  if (selectedCell) { if (selectedParcel === null) renderCellPanel(); else renderInspectionInputs(); }
  const archive = data.mode === "county_archive";
  const status = data.forecast?.status || "unavailable";
  const enabled = !["stale","invalid","unavailable","not_configured"].includes(status);
  playback?.configure(archive ? "archive" : "forecast", (forecastTimeline?.frames || []).map(f=>f.at), forecastIndex ?? 0, enabled,
    status === "stale" ? "Current forecast is stale. An explicit import is required to refresh it." :
    forecastTimeline?.message || (status === "loading" ? "Loading Isaias archive…" : status === "incomplete" ? "Some cells lack six complete hours. Gaps remain unknown." : "Following six-hour rainfall · forecast reconstruction"),
    forecastTimeline?.default_index ?? 0);
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
  $("map-layer-note").textContent = rain ? "Hex color shows the maximum rainfall among overlapping native forecast cells. Missing overlaps stay transparent. The H3 display does not increase forecast resolution." : `${exposureData?.message || "Parcel assessments are unavailable unless matching results are configured."} Transparent interiors indicate unknown scores. Incomplete coverage is reported in details. Green does not establish safety.`;
  showWeatherStatus(forecast);
}

function formatForecastTime(value) {
  return value ? new Date(value).toLocaleString("en-US", {timeZone:"America/Chicago",month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"}) : "Unavailable";
}

function renderArchiveTrend() {
  const frames=forecastTimeline?.frames || [];
  if(trendTimeline===forecastTimeline){
    Array.from($("archive-trend").children).forEach((button,index)=>button.setAttribute("aria-pressed",String(index===forecastIndex)));
    $("archive-peak").textContent=trendPeaks[forecastIndex]?.peak?.toFixed(1) ?? "—";
    return;
  }
  trendTimeline=forecastTimeline;
  const peaks=frames.map(frame=>{
    const features=frame.collection.weather_cells.features;
    const values=features.filter(f=>f.properties.status==="ready" && Number.isFinite(f.properties.rainfall_6h_mm)).map(f=>f.properties.rainfall_6h_mm);
    return {peak:values.length ? Math.max(...values) : null, available:values.length, total:features.length};
  });
  trendPeaks=peaks;
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
  $("archive-trend-label").textContent="ISAIAS / OCTOBER 9, 2026";
  $("archive-peak").textContent=peaks[forecastIndex]?.peak?.toFixed(1) ?? "—";
  $("archive-trend-range").textContent=frames.length ? "Oct 9, midnight → Oct 10, midnight · Central" : "Archive unavailable. Recheck the source or inspect Data.";
}

function selectForecastFrame(index) {
  if(!Number.isInteger(index) || !forecastTimeline?.frames?.[index]) return false;
  forecastIndex=index;
  render(forecastTimeline.frames[index].collection);
  window.dispatchEvent?.(new CustomEvent("quasar:frame",{detail:{index}}));
  return true;
}

async function selectPlaybackFrame(index) {
  if (!selectForecastFrame(index)) return false;
  const frame = current;
  if (!mapLoaded || $("map-layer").value !== "exposure") return true;
  // Keep this hour selected until its summaries and visible parcel scores finish.
  // The playback clock must not invalidate slower source responses.
  const resolutions = new Set([QuasarSpatial.resolutionForZoom(map.getZoom())]);
  if (selectedCell) resolutions.add(selectedResolution);
  await Promise.all([...resolutions].map(resolution => refreshExposure(resolution)));
  if (current !== frame) return false;
  if (exposureData?.status !== "ready") throw new Error(exposureData?.message || "Exposure scores unavailable.");
  await loadParcelExposure(true);
  void hydrateParcelExposure();
  if (current !== frame) return false;
  if (exposureData?.status !== "ready") throw new Error(exposureData?.message || "Parcel scores unavailable.");
  return true;
}

function preparePlaybackFrame(index) {
  if(playback?.playing===false || document.hidden || window.location && !["#map-overview","#isaias-replay", ""].includes(window.location.hash))return;
  const frame=forecastTimeline?.frames?.[index]?.collection;
  if(!mapLoaded || $("map-layer").value!=="exposure" || frame?.mode!=="county_archive") return;
  const resolutions=new Set([QuasarSpatial.resolutionForZoom(map.getZoom())]);
  if(selectedCell) resolutions.add(selectedResolution);
  for(const resolution of resolutions) {
    const key=new URLSearchParams({from:frame.scenario.valid_from,to:frame.scenario.valid_to,
      resolution:String(resolution),mode:"replay",model:$("exposure-model").value || "v2"}).toString();
    if(playbackExposure.has(key)) continue;
    // Buffer one hour of summaries only; never publish future scores or prefetch
    // parcel inventories. Failed reads are retried when that hour is selected.
    const pending=api(`/api/exposure?${key}`).then(data=>data.status==="ready" ? data : null,()=>null);
    playbackExposure.set(key,pending);
    if(playbackExposure.size>4) playbackExposure.delete(playbackExposure.keys().next().value);
  }
}

function mapColors(field = "risk_score") {
  return stateExpression(QuasarSpatial.exposureExpression(field),field);
}

function exposureParameters(resolution = 7) {
  if (!current?.scenario.valid_from || !["county_forecast", "county_archive"].includes(current.mode)) return null;
  return {from:current.scenario.valid_from, to:current.scenario.valid_to, resolution:String(resolution),
    mode:current.mode === "county_archive" ? "replay" : "current", model:$("exposure-model").value || "v2"};
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
  let assessmentNote;
  if(selectedParcel===null) {
    const summary=selectedExposureSummary(); score=summary?.p90_score ?? null;
    assessmentNote=summary ? `Upper-end parcel index (90th percentile). ${summary.scored_count.toLocaleString()}/${summary.parcel_count.toLocaleString()} parcels assessed${summary.incomplete ? "; coverage is incomplete" : ""}.` : "No matching parcel assessment is available for this hour.";
    content.replaceChildren(element("p",summary ? `${summary.scored_count}/${summary.parcel_count} parcels scored · ${(summary.coverage*100).toFixed(1)}% coverage · P90 ${score ?? "Unknown"}${summary.incomplete ? " · Incomplete coverage" : ""}` : "No matching parcel assessment is available. Prepared reference inputs are shown below.","detail-note"));
    if($("map-layer").value === "exposure") void refreshExposure(selectedResolution);
  } else {
    const assessment=exposureData?.status === "ready" && exposureData.inventory_id===parcelEntry?.inventory_id ? parcelAssessments.get(selectedParcel) : null;
    const missingNotes=assessment?.missing?.map(reason=>reason==="excluded_zero_fema_overlap" ? "Excluded from this model: no FEMA hazard-area overlap" : reason==="verified_positive_fema_overlap_required" ? "Verified FEMA hazard-area overlap is unavailable" : reason).join(", ");
    score=QuasarSpatial.validScore(assessment?.score) ? assessment.score : null;
    $("selection-badge").textContent="County parcel · experimental";
    assessmentNote=score===null ? `Assessment unavailable: ${missingNotes || exposureData?.message || "No matching result for this hour"}.` : assessment?.model_details ? "Combines mapped susceptibility with forecast rainfall. Not validated against observed flooding." : "Relative index from the supplied assessment. See calculation details below.";
    content.replaceChildren(...(assessment?.factors || []).map(factor=>element("p", `${names[factor.name] || factor.name}: ${factor.value ?? "Unknown"} · +${factor.contribution.toFixed(1)} index points`,"detail-note")));
    if(score===null) content.append(element("p",`Assessment unavailable: ${missingNotes || exposureData?.message || "No matching parcel assessment"}. Prepared reference inputs are shown below.`,"detail-note"));
    const model = assessment?.model_details;
    if (model && score !== null) {
      content.append(element("p", `Model: ${exposureData?.model_metadata?.model_version || exposureData?.method_version || "Unavailable"}`, "detail-note"));
      content.append(element("p", `Learned mapped susceptibility: ${model.susceptibility.toFixed(3)} · FEMA mapping proxy, not observed flood skill.`, "detail-note"));
      content.append(element("p", `Actual FEMA mapped fraction: ${typeof model.fema_mapped_area_fraction === "number" ? model.fema_mapped_area_fraction.toFixed(3) : "Unknown or incomplete reference"} · Estimated fraction: ${model.susceptibility.toFixed(3)}.`, "detail-note"));
      content.append(element("p", `Forecast rainfall: ${model.rainfall_6h_mm.toFixed(1)} mm / 6h · Rainfall stress: ${model.rainfall_stress.toFixed(3)} (experimental rule).`, "detail-note"));
      content.append(element("p", "Index = 100 × estimated mapped fraction × rainfall / (rainfall + 50). The 50 mm constant is uncalibrated; surge and drainage are not modeled.", "detail-note"));
      const evidence = exposureData?.model_metadata;
      if (evidence?.evaluation_protocol) {
        content.append(element("p", `Evaluation: ${evidence.evaluation_protocol} · Geographic cross-validation on existing research data; original test excluded.`, "detail-note"));
        const summary = evidence.evaluation_summary;
        if (evidence.inference_population === "positive_fema_overlap") content.append(element("p", "Model scope: properties with verified FEMA hazard-area overlap only. Properties with zero or unknown overlap are excluded and unscored.", "detail-note"));
        if (summary) content.append(element("p", `Mapped-fraction errors: mean subgroup MAE ${summary.macro_subgroup_mae.toFixed(3)} · Fully mapped MAE ${summary.fully_mapped_mae.toFixed(3)} · RMSE ${summary.parcel_rmse.toFixed(3)} · Supported ${(100 * summary.coverage).toFixed(1)}%. These measure mapping agreement.`, "detail-note"));
        content.append(element("p", `Model SHA-256: ${evidence.model_sha256} · Dataset: ${evidence.training_dataset_id} · Evaluation SHA-256: ${evidence.evaluation_sha256}`, "detail-note"));
      }
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
  $("selection-band").textContent=score===null ? "Experimental relative exposure unavailable" : QuasarSpatial.exposureBand(score).label;
  $("selection-assessment").textContent=assessmentNote;
  renderSelectionInsights();
}

function renderSelectionInsights() {
  const insights=[];
  const rain=$("map-layer").value === "rainfall";
  if(selectedParcel!==null) {
    const overview=window.QuasarInspection.parcelOverview(parcelContext);
    panelStats(overview.stats);
    if(!rain) {
      const rainfall=window.QuasarInspection.rainfallSummary(parcelContext,current);
      insights.push(rainfall.value==="Unavailable" ? "Forecast rainfall is unavailable for this parcel." : `Archived forecast rain: ${rainfall.value} mm over six hours. ${rainfall.detail}`);
    }
    insights.push(...overview.insights);
  } else {
    const summary=selectedExposureSummary();
    panelStats([[summary?.parcel_count?.toLocaleString() ?? cellContext?.parcel_count?.toLocaleString() ?? (parcelData ? `${parcelData.features.length.toLocaleString()} loaded` : "Unknown"),"Parcels"],
      [summary?.elevated_count?.toLocaleString() ?? "Unknown","Elevated parcels"],
      [summary && Number.isFinite(summary.coverage) ? `${(summary.coverage*100).toFixed(0)}%` : "Unknown","Assessed"]]);
    if(summary) {
      insights.push(`${summary.elevated_count.toLocaleString()} of ${summary.parcel_count.toLocaleString()} parcels have an elevated experimental index (65+).`);
      if(summary.incomplete) {
        const unknown=summary.parcel_count-summary.scored_count;
        insights.push(`${unknown.toLocaleString()} ${unknown===1 ? "parcel is" : "parcels are"} unassessed. Missing results do not mean low exposure.`);
      }
    } else insights.push("Parcel exposure is unavailable for this hour; rainfall alone cannot establish parcel flood risk.");
    if(cellContext) insights.push(`Terrain inputs complete for ${cellContext.terrain_complete_count?.toLocaleString() ?? "an unknown number of"} parcels; FEMA coverage complete for ${cellContext.fema_complete_count?.toLocaleString() ?? "an unknown number of"}.`);
  }
  $("selection-insights").replaceChildren(...insights.map(text=>element("li",text)));
}

function invalidateExposure(data) {
  exposureFrames.clear();
  window.QuasarData?.invalidate("/api/exposure");
  ++exposureRequest;
  clearAssessments(); exposureHydrationRunning=false;
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

function refreshExposure(resolution, force=false) {
  const params=exposureParameters(resolution);
  if(!params) return Promise.resolve();
  const key=new URLSearchParams(params).toString(), request=exposureRequest;
  const pending=exposureLoads.get(key);
  if(pending?.request===request) return pending.promise;
  const promise=loadExposure(resolution,force).finally(()=>{
    if(exposureLoads.get(key)?.promise===promise) exposureLoads.delete(key);
  });
  exposureLoads.set(key,{request,promise});
  return promise;
}

async function loadExposure(resolution, force=false) {
  const params=exposureParameters(resolution);
  if(!params) return;
  const key=new URLSearchParams(params).toString();
  if(force) exposureResponses.delete(key);
  if(exposureResponses.has(key)) return;
  const request=exposureRequest;
  exposureResponses.set(key,{status:"loading",cells:{}});
  try {
    const buffered=playbackExposure.get(key);
    playbackExposure.delete(key);
    const data=(buffered && await buffered) || await api(`/api/exposure?${key}`,{force});
    if(request!==exposureRequest) return;
    if(data.status==="ready" && data.model_choice!==params.model) throw new Error("The source did not return the selected model version");
    if(data.status==="ready" && (!data.cells || data.aggregation!=="parcel_p90_linear")) throw new Error("Invalid exposure summary");
    if(data.status==="ready" && exposureData?.status==="ready"
        && (data.run_id!==exposureData.run_id || data.inventory_id!==exposureData.inventory_id)) {
      ++exposureRequest;
      clearAssessments(); exposureHydrationRunning=false; exposureResponses.clear(); exposureFrames.clear();
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

function hydrateParcelExposure() {
  const request=exposureRequest;
  if(parcelExposureLoad?.request===request) return parcelExposureLoad.promise;
  const promise=loadParcelExposure().finally(()=>{
    if(parcelExposureLoad?.promise===promise) parcelExposureLoad=null;
  });
  parcelExposureLoad={request,promise};
  return promise;
}

async function loadParcelExposure(selectedOnly=false) {
  const params=exposureParameters(),run=exposureData;
  if($("map-layer").value!=="exposure" || (!selectedOnly && exposureHydrationRunning) || !params || run?.status!=="ready" || !parcelEntry
      || run.inventory_id!==parcelEntry.inventory_id || selectedResolution!==7)return;
  const bounds=map.getBounds?.();
  const visible=feature=>{
    if(!bounds)return false;
    const coordinates=feature.geometry.type==="Polygon" ? feature.geometry.coordinates : feature.geometry.coordinates.flat();
    return coordinates.some(ring=>ring.some(point=>bounds.contains(point)));
  };
  const ids=parcelEntry.features.filter(feature=>(!selectedOnly || feature.id===selectedParcel) && (selectedOnly ? !parcelAssessments.has(feature.id) : !assessmentSeen.has(feature.id)))
    .map(feature=>({id:feature.id,priority:feature.id===selectedParcel?2:visible(feature)?1:0}))
    .sort((a,b)=>b.priority-a.priority).map(feature=>feature.id);
  if(!ids.length)return;
  const request=exposureRequest,cell=selectedCell;
  if(!selectedOnly)exposureHydrationRunning=true;
  let offset=0,failed=false;
  async function worker(){
    while(offset<ids.length && !failed){
      if(request!==exposureRequest || selectedCell!==cell)return;
      const batch=ids.slice(offset,offset+=100);
      const page=await assessmentApi(`/api/exposure?${new URLSearchParams({...params,parcel_ids:batch.join(","),run_id:run.run_id})}`,selectedOnly);
      if(request!==exposureRequest || selectedCell!==cell)return;
      if(page.status!=="ready" || page.model_choice!==params.model || page.run_id!==run.run_id || page.inventory_id!==parcelEntry?.inventory_id){failed=true;throw new Error("Parcel exposure model, run or inventory changed");}
      for(const id of batch)rememberAssessment(id,page.parcels?.[id] || {score:null,factors:[],missing:["assessment_unavailable"]});
      if(parcelEntry)publishParcels(parcelEntry,false);
    }
  }
  try {
    await Promise.all(Array.from({length:selectedOnly?1:Math.min(3,Math.ceil(ids.length/100))},worker));
    if(request===exposureRequest && selectedCell===cell && parcelEntry)publishParcels(parcelEntry,true);
  } catch(error){
    failed=true;
    if(request!==exposureRequest)return;
    invalidateExposure({status:"unavailable",cells:{},message:`Parcel exposure unavailable: ${error.message}`});
    if(parcelEntry)publishParcels(parcelEntry,true);
    updateCountyGrid();showMapSummary();
  } finally {
    if(!selectedOnly && request===exposureRequest){
      exposureHydrationRunning=false;
      // New geometry may have arrived while the original batches were running.
      if(exposureData?.status==="ready" && parcelEntry?.features.some(feature=>!assessmentSeen.has(feature.id)))await loadParcelExposure();
    }
  }
}

function updateMap() {
  if (!mapLoaded || !mapData) return;
  toggleHex();
  updateCountyGrid();
}

function updateCountyGrid() {
  if(gridScheduled)return;
  if(window.requestAnimationFrame){gridScheduled=true;window.requestAnimationFrame(()=>{gridScheduled=false;void drawCountyGrid();});}
  else void drawCountyGrid();
}

async function prepareGrid(resolution) {
  const weather=current?.weather_cells;
  const cached=rainfallGrids.get(resolution);
  if(cached?.weather===weather)return cached.grid;
  let base,grid;
  if(window.QuasarGeometry){
    const result=await window.QuasarGeometry.coverage(county.features[0].geometry,resolution,weather);
    base=result.grid;
    grid={...base,features:base.features.map((feature,index)=>({...feature,properties:result.rainfall[index].properties}))};
  } else {
    if(!countyGrids.has(resolution))countyGrids.set(resolution,QuasarSpatial.countyCells(county.features[0].geometry,h3,resolution));
    base=countyGrids.get(resolution);grid=QuasarSpatial.rainfallCoverage(base,weather);
  }
  countyGrids.set(resolution,base);
  if(current?.weather_cells===weather)rainfallGrids.set(resolution,{weather,grid});
  return grid;
}

async function drawCountyGrid() {
  if(!mapLoaded || !mapData || !county)return;
  const resolution=QuasarSpatial.resolutionForZoom(map.getZoom()),frame=current,epoch=++gridEpoch;
  let rainfallGrid;
  try {
    if(window.QuasarGeometry)rainfallGrid=await prepareGrid(resolution);
    else {
      if(!countyGrids.has(resolution))countyGrids.set(resolution,QuasarSpatial.countyCells(county.features[0].geometry,h3,resolution));
      rainfallGrid=QuasarSpatial.rainfallCoverage(countyGrids.get(resolution),current?.weather_cells);
      rainfallGrids.set(resolution,{weather:current?.weather_cells,grid:rainfallGrid});
    }
  } catch(error){
    if(epoch===gridEpoch){$("grid-status").textContent=error.message;$("map-status").textContent=error.message;}
    return;
  }
  if(epoch!==gridEpoch || current!==frame)return;
  const params=exposureParameters(resolution),cached=params && exposureResponses.get(new URLSearchParams(params).toString());
  const grid=QuasarSpatial.exposureCoverage(rainfallGrid,cached?.status==="ready"?cached.cells:{});
  paintSource("hotspots",grid,countyGrids.get(resolution),feature=>({rainfall_mm:feature.properties.rainfall_mm,exposure_score:feature.properties.exposure_score}));
  if($("map-layer").value==="exposure")void refreshExposure(resolution);
  const rain=$("map-layer").value==="rainfall";
  map.setPaintProperty("hotspot-fill","fill-color",rain ? stateExpression(QuasarSpatial.rainfallExpression(),"rainfall_mm") : mapColors("exposure_score"));
  map.setPaintProperty("hotspot-fill","fill-opacity",rain ? opacity("rainfall_mm",0.5) : opacity("exposure_score",0.28));
  for(const layer of ["parcel-fill","selected-parcel-fill"])map.setPaintProperty(layer,"fill-opacity",rain ? 0 : opacity("exposure_score",0.45));
  $("grid-resolution").textContent=`H3 · RES ${resolution}`;
  $("grid-status").textContent=`${grid.features.length.toLocaleString()} cells · R${resolution} · click to inspect`;
  if(selectedCell && selectedResolution===resolution)renderInspectionInputs();
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
  for(const name of ["parcels","selected-cell","selected-parcel"]){sourceKeys.delete(name);sourceStates.delete(name);}
  const restoreFocus=$("map-selection-panel").getAttribute("aria-modal")==="true";
  ++parcelRequest; ++contextRequest;
  window.clearTimeout?.(parcelPaintTimer); parcelPaintTimer=undefined;
  selectedCell = selectedParcel = parcelData = parcelEntry = cellContext = parcelContext = null;
  contextLoading=false; contextMessage = "";
  $("map-selection-panel").hidden = true;
  if(restoreFocus)$("map-overview").focus();
  if (mapLoaded) {
    for (const id of ["parcels","selected-cell","selected-parcel"]) clearSource(id);
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

function weatherContextForCell() {
  if(!selectedCell || !county)return null;
  const cached=rainfallGrids.get(selectedResolution);
  if(cached?.weather===current?.weather_cells)return cached.grid.features.find(f=>f.id===selectedCell)?.properties;
  if(window.QuasarGeometry){
    const cell=selectedCell,weather=current?.weather_cells;
    void prepareGrid(selectedResolution).then(()=>{if(selectedCell===cell && current?.weather_cells===weather)renderInspectionInputs();}).catch(()=>{});
    return null;
  }
  if(!countyGrids.has(selectedResolution))countyGrids.set(selectedResolution,QuasarSpatial.countyCells(county.features[0].geometry,h3,selectedResolution));
  return QuasarSpatial.rainfallCoverage(countyGrids.get(selectedResolution),current?.weather_cells).features.find(f=>f.id===selectedCell)?.properties;
}

function renderInspectionInputs() {
  const prepared=selectedParcel === null ? cellContext : parcelContext;
  const weather=selectedParcel===null ? weatherContextForCell() : null;
  const context=selectedParcel === null ? {...prepared,forecast_overlaps:weather?.forecast_overlaps || [],forecast_coverage_complete:weather?.forecast_coverage_complete} : prepared;
  const rain=$("map-layer").value === "rainfall";
  const summary=selectedParcel===null
    ? window.QuasarInspection.rainfallSummary(context,current)
    : window.QuasarInspection.parcelRainfallSummary(context,current);
  if (selectedParcel===null && !context.forecast_overlaps.length) {
    summary.value=current?.forecast?.status==="loading" ? "Loading…" : "No rainfall data";
    summary.detail="No native forecast geometry covers this selection in the loaded archive.";
  } else if (!context) {
    summary.value=contextLoading ? "Loading…" : "Not linked";
    summary.detail=contextLoading ? "Loading this selection’s prepared weather overlaps…" : "Parcel reference inputs did not load. Retry below, or inspect the parent H3 cell for forecast rainfall.";
  }
  $("selection-rainfall").textContent=summary.value;
  $("selection-rainfall-note").textContent=summary.detail + (selectedParcel===null ? " Hex color uses the maximum; H3 does not increase forecast resolution." : "");
  $("selection-window").textContent=current?.scenario?.valid_from ? `${formatForecastTime(current.scenario.valid_from)} → ${formatForecastTime(current.scenario.valid_to)}` : "Forecast window unavailable";
  $("selection-rainfall-meter").hidden=!rain;
  $("selection-exposure-meter").hidden=rain;
  $("selection-exposure-section").hidden=rain;
  const rows=selectedParcel === null ? window.QuasarInspection.forecastRows(context,current) : window.QuasarInspection.parcelRows(context,current);
  if(selectedParcel === null) rows.unshift(
    ["Distinct indexed parcels",cellContext?.parcel_count?.toLocaleString() ?? "Unknown"],
    ["Complete terrain summaries",cellContext?.terrain_complete_count?.toLocaleString() ?? "Unknown"],
    ["Complete / partial FEMA coverage",`${cellContext?.fema_complete_count?.toLocaleString() ?? "Unknown"} / ${cellContext?.fema_partial_count?.toLocaleString() ?? "Unknown"}`]);
  inputRows(rows);
  $("context-status").textContent=contextMessage;
  $("context-status").hidden=Boolean(prepared) && !contextLoading;
  $("context-retry").hidden=Boolean(prepared) || contextLoading;
  $("context-provenance").textContent=window.QuasarInspection.provenance(prepared);
  renderExposureInspection();
}

async function loadInspection(kind,identifier,force=false) {
  const request=++contextRequest, inventory=parcelEntry?.inventory_id;
  const key=JSON.stringify([kind,identifier,inventory]);
  if(force) {
    contextCache.delete(key);
    if(kind==="parcel") parcelContext=null; else cellContext=null;
  }
  contextLoading=true; contextMessage="Loading prepared reference inputs…";
  if(selectedParcel===null) renderCellPanel(); else renderInspectionInputs();
  try {
    const context=(!force && contextCache.get(key)) || await api(`/api/${kind === "parcel" ? "parcels" : "cells"}/${identifier}/${kind === "parcel" ? "context" : "summary"}${inventory ? `?${new URLSearchParams({inventory_id:inventory})}` : ""}`);
    if(context.status!=="ready" || context.county_fips!=="12091" || context.risk_score!==null
        || (kind==="parcel" ? context.parcel_id!==identifier : context.cell_id!==identifier)
        || (parcelEntry?.inventory_id && context.inventory_id!==parcelEntry.inventory_id)) throw new Error("Prepared context is invalid or describes a different inventory");
    if(request!==contextRequest) return;
    contextLoading=false;
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
    contextLoading=false;
    contextMessage=`Reference inputs unavailable: ${error.message}`;
    if(selectedParcel===null) renderCellPanel(); else renderInspectionInputs();
  }
}

function renderParcelList() {
  const features=(parcelData?.features || []).filter(f=>String(f.id).includes(parcelSearch));
  const pages=Math.max(1,Math.ceil(features.length/50)); parcelListPage=Math.min(parcelListPage,pages-1);
  $("selection-content").replaceChildren(...features.slice(parcelListPage*50,(parcelListPage+1)*50).map(feature=>{
    const button=element("button",undefined,"selection-parcel-row"); button.type="button";
    const score=feature.properties.exposure_score;
    button.style.borderLeft=`4px solid ${QuasarSpatial.exposureColor(score)}`;
    const label=$("map-layer").value === "rainfall" ? "View terrain & rainfall →" : `${score == null ? "Unknown" : score.toFixed(1)+" / 100"} · ${QuasarSpatial.exposureBand(score).label} →`;
    button.append(element("strong",`Parcel ${feature.id}`),element("span",label));
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
  $("selection-subtitle").textContent = "Okaloosa County · archived forecast";
  $("selection-section-title").textContent = "Browse parcels in this cell";
  $("selection-records").hidden=selectedResolution!==7;
  $("cell-zoom").hidden=selectedResolution===7;
  $("parcel-refresh").hidden=selectedResolution!==7;
  $("parcel-search-label").hidden=$("parcel-pagination").hidden=selectedResolution!==7;
  if(selectedResolution===7) renderParcelList();
  else $("selection-content").replaceChildren(element("p","Zoom in to browse parcel outlines. Counts describe indexed parcels, not homes; adjacent cells can share parcels.","selection-note"));
  renderInspectionInputs();
}

function inspectParcel(feature) {
  selectedParcel=feature.id; parcelContext=null;
  void loadParcelExposure(true);
  $("selection-back").hidden=false; $("cell-zoom").hidden=true;
  $("parcel-search-label").hidden=$("parcel-pagination").hidden=true;
  $("selection-badge").textContent="County parcel · unscored";
  $("selection-title").textContent="Parcel details";
  $("selection-code").textContent=`Parcel ${feature.id}`;
  $("selection-subtitle").textContent="Okaloosa County · FIPS 12091";
  panelStats([["Unknown","Exposure"],["Loading","Forecast overlap"],["Loading","Terrain"]]);
  $("selection-section-title").textContent="Property record";
  $("selection-records").hidden=false;
  $("selection-records").open=false;
  const records=element("dl",undefined,"selection-factors");
  for(const [label,value] of [["County GIS ID",String(feature.id)],["Geometry","County-validated polygon"],["H3 selection",selectedCell]]) {
    const row=element("div"); row.append(element("dt",label),element("dd",value)); records.append(row);
  }
  $("selection-content").replaceChildren(records);
  paintSource("selected-parcel",{type:"FeatureCollection",features:[feature]},`${parcelEntry?.inventory_id}:${feature.id}`,item=>({exposure_score:exposureData?.status==="ready" && exposureData.inventory_id===parcelEntry?.inventory_id ? parcelAssessments.get(item.id)?.score ?? null : null}));
  const polygons=feature.geometry.type==="MultiPolygon"?feature.geometry.coordinates:[feature.geometry.coordinates];
  const points=polygons.flat(2), bounds=[0,1].map(axis=>[Math.min(...points.map(p=>p[axis])),Math.max(...points.map(p=>p[axis]))]);
  map.fitBounds([[bounds[0][0],bounds[1][0]],[bounds[0][1],bounds[1][1]]],{padding:{top:60,bottom:60,left:40,right:Math.min(370,map.getCanvas().clientWidth/2)},maxZoom:18,duration:650});
  void loadInspection("parcel",feature.id);
}

async function inspectCell(cell,resolution=7) {
  closeSelection(); selectedCell=cell; selectedResolution=resolution;
  $("selection-records").open=false;
  parcelListPage=0; parcelSearch=""; $("parcel-search").value="";
  if (playback) $("map-source-info").open = false;
  const selectionGeometry=countyGrids.get(resolution)?.features.find(feature=>feature.id===cell)?.geometry || (county && !window.QuasarGeometry && QuasarSpatial.clipGeometry({type:"Polygon",coordinates:[h3.cellToBoundary(cell,true)]},county.features[0].geometry));
  map.getSource("selected-cell").setData({type:"FeatureCollection",features:selectionGeometry ? [{type:"Feature",geometry:selectionGeometry}] : []});
  $("parcel-status").textContent=resolution===7?"Restoring parcel inventory…":"Parcel outlines load at resolution 7.";
  $("parcel-provenance").textContent=""; $("parcel-retry").hidden=true;
  renderCellPanel();
  void loadInspection("cell",cell);
  if(resolution===7) {
    const [lat,lon]=h3.cellToLatLng(cell); map.flyTo({center:[lon,lat],zoom:Math.max(13.5,map.getZoom()),duration:650});
    await loadParcels();
    // A cached inventory can arrive before the manifest and reject the first
    // context response. Retry against the now-verified inventory, not that cache.
    if(selectedCell===cell && selectedParcel===null && !cellContext) await loadInspection("cell",cell);
  }
}

function publishParcels(entry,force=false) {
  const inventoryChanged=parcelEntry && parcelEntry.inventory_id!==entry.inventory_id;
  if(inventoryChanged) {
    ++contextRequest;
    parcelContext=cellContext=null;
    contextLoading=false;
    contextMessage="Parcel inventory changed; reloading reference inputs…";
  }
  if(cellContext && cellContext.inventory_id!==entry.inventory_id) {
    cellContext=null; contextMessage="Reference inputs do not match the cached parcel inventory; current coverage is unknown.";
  }
  parcelEntry=entry;
  parcelData={type:"FeatureCollection",features:map.setFeatureState ? entry.features : entry.features.map(feature=>QuasarSpatial.exposureFeature(feature,
    exposureData?.status === "ready" && exposureData.inventory_id === entry.inventory_id ? parcelAssessments.get(feature.id) : null))};
  const selected=parcelData.features.find(feature=>feature.id===selectedParcel);
  if(selected) paintSource("selected-parcel",{type:"FeatureCollection",features:[selected]},`${entry.inventory_id}:${selected.id}`,feature=>({exposure_score:exposureData?.status==="ready" && exposureData.inventory_id===entry.inventory_id ? parcelAssessments.get(feature.id)?.score ?? null : null}));
  // Do not join a shape retained from the old inventory to replacement inputs.
  if(inventoryChanged && selectedParcel!==null && !selected) {
    selectedParcel=null;
    clearSource("selected-parcel");
    renderCellPanel();
  }
  if(selectedParcel!==null) renderExposureInspection();
  void hydrateParcelExposure();
  if(force || Date.now()-lastParcelPaint>=100) {
    window.clearTimeout?.(parcelPaintTimer); parcelPaintTimer=undefined;
    paintSource("parcels",parcelData,`${entry.inventory_id}:${selectedCell}:${entry.features.length}`,feature=>({exposure_score:exposureData?.status==="ready" && exposureData.inventory_id===entry.inventory_id ? parcelAssessments.get(feature.id)?.score ?? null : null})); lastParcelPaint=Date.now();
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
  if(inventoryChanged) void loadInspection(selectedParcel===null ? "cell" : "parcel",selectedParcel ?? selectedCell,true);
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
      const featureList=[...features.values()];
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
          if(!features.has(feature.id)) featureList.push(feature);
          features.set(feature.id,feature);
        }
        loaded={...page,features:featureList,excluded_count:loaded.excluded_count+page.excluded_count,complete:page.next_offset===null};
        if(selectedCell===cell && token===parcelCache.token) publishParcels(loaded,loaded.complete);
        const saved=await parcelCache.put(cell,manifest,loaded,token,{offset,features:page.features});
        loaded=saved || loaded;
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
      const belowLabels=map.getStyle?.().layers?.find(layer=>layer.type==="symbol")?.id;
      // Satellite imagery competes with rain colors. Keep geography, quiet its texture.
      for(const layer of map.getStyle?.().layers || []) if(layer.type==="raster") {
        map.setPaintProperty(layer.id,"raster-saturation",-1);
        map.setPaintProperty(layer.id,"raster-brightness-max",0.55);
      }
      // Vector tiles retain integer IDs only. Promote the H3 property so tiled
      // hexagons can read the string-keyed rainfall and exposure feature state.
      map.addSource("hotspots", {type:"geojson", data:empty, promoteId:"h3_index"});
      map.addLayer({id:"hotspot-fill", type:"fill", source:"hotspots", paint:{"fill-color":mapColors("exposure_score"), "fill-opacity":opacity("exposure_score",0.28)}},belowLabels);
      map.addLayer({id:"hotspot-outline", type:"line", source:"hotspots", paint:{"line-color":"#9ca3af", "line-opacity":0.45, "line-width":0.65}});
      map.addSource("county-boundary", {type:"geojson", data:county || empty});
      map.addLayer({id:"county-boundary", type:"line", source:"county-boundary", paint:{"line-color":"#ecf4ef","line-width":2,"line-dasharray":[3,2]}});
      map.addSource("selected-cell", {type:"geojson", data:empty});
      map.addLayer({id:"selected-cell-outline", type:"line", source:"selected-cell", paint:{"line-color":"#0d9488","line-width":3}});
      map.addSource("parcels", {type:"geojson", data:empty});
      map.addLayer({id:"parcel-fill", type:"fill", source:"parcels", paint:{"fill-color":mapColors("exposure_score"),"fill-opacity":opacity("exposure_score",0.45)}});
      map.addLayer({id:"parcel-outline", type:"line", source:"parcels", paint:{"line-color":"#ffffff","line-width":0.65}});
      map.addSource("selected-parcel", {type:"geojson", data:empty});
      map.addLayer({id:"selected-parcel-fill", type:"fill", source:"selected-parcel", paint:{"fill-color":mapColors("exposure_score"),"fill-opacity":opacity("exposure_score",0.3)}});
      map.addLayer({id:"selected-parcel-outline", type:"line", source:"selected-parcel", paint:{"line-color":"#ffffff","line-width":3}});
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
  map.setLayoutProperty("hotspot-outline", "visibility", $("hex-toggle").checked ? "visible" : "none");
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
  exposureFrames.clear();
  exposureData=null;
  for(const prefix of ["/api/weather/","/api/data/weather","/api/reports","/api/exposure"])window.QuasarData?.invalidate(prefix);
  playbackExposure.clear();
  const source="archive";
  forecastTimeline=null;
  render(unavailableFrame(source,"loading","Loading the Isaias county archive…"));
  try {
    const timeline=await api(`/api/weather/timeline?source=${source}`);
    if(thisRequest!==requestId)return false;
    if(timeline.county_fips!=="12091" || timeline.source!=="archive")throw new Error("Wrong forecast county or source");
    forecastTimeline=timeline;
    const index=Math.min(options.forecastIndex ?? forecastIndex ?? timeline.default_index ?? 0,Math.max(0,(timeline.frames?.length || 0)-1));
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
    playback = window.QuasarMapUI.createPlayback({get:$, select:(_kind,index)=>selectPlaybackFrame(index),
      prepare:(_kind,index)=>preparePlaybackFrame(index)});
    window.addEventListener("hashchange",()=>{
      if (!["#map-overview", "#isaias-replay", ""].includes(window.location.hash)) {playback.pause();playbackExposure.clear();searchController?.close();}
    });
    document.addEventListener?.("visibilitychange",()=>{if(document.hidden){playback.pause();playbackExposure.clear();}});
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
  $("forecast-retry").onclick=async()=>{
    playback?.pause(); const loaded=await loadScenario();
    if(selectedCell) await loadInspection(selectedParcel===null ? "cell" : "parcel",selectedParcel ?? selectedCell,true);
    return loaded;
  };
  $("context-retry").onclick=()=>loadInspection(selectedParcel===null ? "cell" : "parcel",selectedParcel ?? selectedCell,true);
  window.addEventListener?.("quasar:seek",event=>{playback?.pause();forecastIndex=event.detail.index;selectForecastFrame(forecastIndex);});
  // Archive reads must not wait for Mapbox or the external county service.
  const archiveLoad=loadScenario();
  const configLoad=api("/api/config");
  const countyLoad=api("/api/county").then(data=>({data}),error=>({error}));
  $("selection-close").onclick = closeSelection;
  $("selection-back").onclick = () => {
    selectedParcel = null;
    if (mapLoaded) clearSource("selected-parcel");
    renderCellPanel();
    void loadInspection("cell",selectedCell);
  };
  $("parcel-retry").onclick = () => {
    selectedParcel=null; clearSource("selected-parcel");
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
    clearSource("selected-parcel"); clearSource("parcels");
    renderCellPanel(); await loadParcels(true);
    if(selectedCell===cell) void loadInspection("cell",cell);
  };
  $("parcel-clear").onclick=async()=>{closeSelection();contextCache.clear();await parcelCache.clear();};
  void parcelCache.check(()=>api("/api/parcels/manifest"));
  window.addEventListener?.("keydown", event => { if (event.key === "Escape") closeSelection(); });
  $("map-layer").onchange = () => { playback?.pause(); showMapSummary(); updateMap(); if(selectedCell) { if(selectedParcel===null)renderCellPanel(); else renderInspectionInputs(); } };
  $("exposure-model").value ||= "v2";
  $("exposure-model").onchange = async() => {
    if(!["v1","v2"].includes($("exposure-model").value)) return;
    playback?.pause();
    window.clearTimeout?.(exposureExpiryTimer);
    invalidateExposure({status:"loading",cells:{},message:`Loading ${$("exposure-model").value.toUpperCase()} exposure…`});
    exposureResponses.clear();exposureLoads.clear();playbackExposure.clear();parcelExposureLoad=null;
    $("exposure-model-note").textContent=$("exposure-model").value==="v2"
      ? "V2 assesses properties with verified FEMA hazard-area overlap. Excluded properties stay unscored."
      : "V1 is the original mapping model. Both versions use an experimental rainfall rule; neither predicts verified flooding.";
    if(parcelEntry)publishParcels(parcelEntry,true);
    updateCountyGrid();showMapSummary();
    if(selectedCell)renderExposureInspection();
    if($("map-layer").value==="exposure") await refreshExposure(selectedResolution,true);
  };
  try {
    const config=await configLoad;
    if(config.exposure_scale) QuasarSpatial.configureExposure(config.exposure_scale);
    setupMap(config.map);
  }
  catch { $("map-status").textContent = "Map configuration unavailable; source tables remain available."; }
  if (map) {
    try {
      const result = await countyLoad;
      if(result.error) throw result.error;
      const data = result.data;
      if (data.county_fips !== "12091" || data.features?.length !== 1) throw new Error("County boundary unavailable");
      county = data;
      if (mapLoaded) map.getSource("county-boundary").setData(county);
      frameCounty();
      updateCountyGrid();
    } catch {
      $("grid-status").textContent = "County boundary unavailable · reload to retry";
      $("map-status").textContent = "County boundary unavailable. H3 rainfall cannot be drawn; native forecasts remain available in Data. Reload to retry.";
    }
  }
  if (window.QuasarMapUI) searchController = window.QuasarMapUI.createSearch({get:$,element,token:mapToken,geometry:county?.features[0]?.geometry,
    isCellId:value=>h3.isValidCell(value),select:feature=>{
    searchMarker?.remove();searchMarker=null;
    if(!feature || !map)return;
    if(feature.properties?.h3_index) {
      const cell=feature.properties.h3_index;
      const resolution=h3.getResolution(cell);
      if(resolution<4 || resolution>7) {
        $("map-search-status").textContent="Search supports Okaloosa H3 cells at resolutions 4 through 7.";return;
      }
      const cellGeometry={type:"Polygon",coordinates:[h3.cellToBoundary(cell,true)]};
      if(!county || !QuasarSpatial.clipGeometry(cellGeometry,county.features[0].geometry)) {
        $("map-search-status").textContent="That hex cell does not overlap Okaloosa County.";return;
      }
      const [lat,lon]=h3.cellToLatLng(cell);
      void inspectCell(cell,resolution);
      map.flyTo({center:[lon,lat],zoom:Math.max(map.getZoom(),resolution===7?13.5:QuasarSpatial.childZoom(resolution)),padding:{top:90,bottom:150,left:40,right:40},duration:650});
      return;
    }
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
window.Quasar = { start, frame:()=>forecastIndex ?? 16 };
if ($("map-overview")) start();
else document.dispatchEvent(new Event("quasar:ready"));
