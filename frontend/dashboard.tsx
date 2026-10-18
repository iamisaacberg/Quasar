import { memo, useEffect, useState } from "react";
import { Reports } from "./reports";
import { MapSelectionPanel } from "./components/map-selection-panel";
import { DataDashboard } from "./data-dashboard";
import { ArrowUpRight, CircleHelp, CloudRain, Layers3, MapPin, Radar, TriangleAlert, Waves, Search, X, SlidersHorizontal, Plus, Minus, ChevronLeft, ChevronRight, Info } from "lucide-react";

declare global {
  interface Window { Quasar?: { start: () => Promise<void> }; }
}

export const QuasarDashboard = memo(function QuasarDashboard() {
  const [isReportsView, setIsReportsView] = useState(window.location.hash === "#reports");
  const [isDataView, setIsDataView] = useState(window.location.hash === "#data");
  useEffect(() => {
    // Mapbox may have initialized while a separate view hid its container.
    if (!isReportsView && !isDataView) window.dispatchEvent(new Event("resize"));
  }, [isReportsView, isDataView]);
  useEffect(() => {
    const update = () => {
      setIsReportsView(window.location.hash === "#reports");
      setIsDataView(window.location.hash === "#data");
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  const [isMapView, setIsMapView] = useState(!window.location.hash || ["#map-overview", "#isaias-replay"].includes(window.location.hash));
  useEffect(() => {
    const update = () => setIsMapView(!window.location.hash || ["#map-overview", "#isaias-replay"].includes(window.location.hash));
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  useEffect(() => {
    const start = () => { void window.Quasar?.start(); };
    if (window.Quasar) start();
    else document.addEventListener("quasar:ready", start, { once: true });
    return () => document.removeEventListener("quasar:ready", start);
  }, []);
  return (
    <div className={`workspace-view${isMapView ? " is-map-view" : ""}${isReportsView ? " is-reports-view" : ""}${isDataView ? " is-data-view" : ""}`}>
      <Reports active={isReportsView} />
      <DataDashboard active={isDataView} />
      <header className="workspace-header">
        <div className="breadcrumb"><span>Okaloosa County</span><span aria-hidden="true">/</span><strong>Map overview</strong></div>
      </header>
      <div className="dashboard">
        <section className="page-heading">
          <div><p className="eyebrow"><Radar aria-hidden="true" />EXPOSURE WORKSPACE</p><h1>A clearer view of changing conditions.</h1><p>Explore county parcels, forecast rainfall, and available flood data.</p></div>
          <div className="county-tag"><MapPin aria-hidden="true" /><span>Okaloosa, FL<small>County FIPS 12091</small></span></div>
        </section>
        <aside className="notice"><TriangleAlert aria-hidden="true" /><p id="data-notice">Flood data availability and experimental parcel summaries are not flood depths, probabilities, or official warnings.</p></aside>
        <p id="error" role="alert" hidden />
        <div className="map-workspace">
          <section className="map-card" id="map-overview" tabIndex={-1} aria-label="Okaloosa county map">
            <div className="panel-header"><div><h2 id="map-heading"><MapPin aria-hidden="true" />County map</h2><p>County grid · parcel browsing · forecast cells</p></div><span id="grid-resolution" className="subtle-tag">H3 · RES 6</span></div>
            <div className="map-viewport">
              <div id="map"><p className="map-fallback">Map loading. Use Tools to browse county parcels.</p></div>
              <div className="map-search map-float" role="search">
                <div className="map-search-input"><Search aria-hidden="true" /><input id="map-search" type="text" disabled placeholder="Search Okaloosa addresses and places…" aria-label="Search Okaloosa County" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="map-search-results" aria-describedby="map-search-status" autoComplete="off" /><button id="map-search-clear" type="button" disabled aria-label="Clear search"><X aria-hidden="true" /></button></div>
                <ul id="map-search-results" role="listbox" aria-label="County search results" hidden />
                <p id="map-search-status" role="status">Search requires a configured map and an available county boundary.</p>
              </div>
              <div className="map-state map-float"><span className="demo-badge" id="mode-badge">SYNTHETIC DEMO</span><span id="map-display-label">Loading map data…</span></div>
              <p id="map-status" className="map-message map-float" role="status" />
              <div className="map-tool-dock map-float">
                <div className="map-zoom"><button id="map-zoom-in" type="button" aria-label="Zoom in"><Plus /></button><button id="map-zoom-out" type="button" aria-label="Zoom out"><Minus /></button></div>
                <details id="map-tools"><summary aria-label="Map tools"><SlidersHorizontal aria-hidden="true" /><span>Tools</span></summary><div className="map-tools-panel"><h2>Map tools</h2>
                  <section className="exercise-toolbar" aria-label="Map toolbar">
                    <label htmlFor="scenario"><CloudRain aria-hidden="true" /><span>Data source</span><select id="scenario" disabled aria-label="Map data source and time window" /></label>
                    <label htmlFor="map-layer"><Layers3 aria-hidden="true" /><span>Display</span><select id="map-layer" defaultValue="exposure"><option value="rainfall">Rainfall · mm / 6h</option><option value="exposure">Relative exposure · /100</option></select></label>
                    <button id="replay-toggle" type="button" disabled aria-pressed="false" aria-controls="map-sidebar"><Radar aria-hidden="true" /><span>Isaias simulation</span></button>
                  </section>
                  <div className="map-controls"><label className="hex-control"><input type="checkbox" id="hex-toggle" defaultChecked /><Layers3 aria-hidden="true" />County H3 grid</label><span id="grid-status" className="subtle-tag">Loading county boundary…</span></div>
                </div></details>
              </div>
              <section className="map-playback map-float" aria-label="Forecast and archive playback">
                <p id="playback-clock">Select a forecast or archive</p>
                <div className="playback-main"><button id="replay-prev" type="button" disabled aria-label="Previous hour"><ChevronLeft /></button><button id="replay-play" type="button" disabled aria-label="Play forecast or archive" aria-pressed="false">▶</button><button id="replay-next" type="button" disabled aria-label="Next hour"><ChevronRight /></button><input id="replay-hour" type="range" min="0" max="0" step="1" defaultValue="0" disabled aria-label="Forecast or archive hour" /></div>
                <p id="playback-status" role="status">Playback unavailable for static exercise windows.</p>
              </section>
              <details className="map-legend map-float" id="map-legend" open><summary><Layers3 aria-hidden="true" />Legend</summary><div className="map-legend-content">
                <div id="exposure-legend" className="legend exposure-legend" aria-label="Experimental relative exposure">
                <strong>Experimental relative exposure</strong>
                <div className="exposure-gradient" aria-hidden="true" />
                <span><i className="dot lower_relative" />0–34 · Lower relative exposure</span>
                <span><i className="dot moderate" />35–64 · Moderate relative exposure</span>
                <span><i className="dot elevated" />65–84 · Elevated relative exposure</span>
                <span><i className="dot highest" />85–100 · Highest relative exposure</span>
                <span><i className="dot unknown" />Unknown · Insufficient data</span>
                <span>Hatched · Incomplete scoring coverage</span>
                <strong>Green does not establish safety.</strong>
              </div>
                <div id="rainfall-legend" className="legend" hidden aria-label="Rainfall legend"><span><i className="dot rain-light" />0–25</span><span><i className="dot rain-medium" />25–75</span><span><i className="dot rain-heavy" />75+ mm / 6h</span><span><i className="dot unknown" />Unavailable</span></div>
                <p>Rainfall: mm / 6h · Exposure: score / 100</p>
                <details className="map-info" id="map-source-info"><summary><Info aria-hidden="true" />Source &amp; interpretation</summary>
                  <div className="map-data-summary" aria-live="polite"><strong id="map-data-title">Loading map data…</strong><p id="window">Loading data window…</p><p id="map-data-values" /><p id="map-data-source" /></div>
                  <p id="map-layer-note" className="detail-note">County cells support parcel browsing and do not increase forecast resolution.</p>
                  <p id="map-demo-notice">Unvalidated demonstration. Follow official NWS/local guidance.</p>
                </details>
              </div></details>
              <button id="map-sheet-backdrop" className="map-sheet-backdrop" type="button" aria-label="Close map details" tabIndex={-1} hidden />
              <MapSelectionPanel />
              <aside id="map-sidebar" className="map-sidebar" aria-label="Map inspection and simulation">
                <div className="map-sidebar-header"><strong>Map details</strong><button id="map-sidebar-close" type="button" aria-label="Close map inspection"><X /></button></div>
                <section id="isaias-replay" className="replay-panel" hidden aria-labelledby="replay-heading">
                  <div className="panel-header"><div><p className="eyebrow">HISTORICAL CONTEXT · FICTIONAL INPUTS</p><h2 id="replay-heading">Isaias simulation · 2026</h2><p>Oct 9 archive reconstruction and simulated routes with a fixed illustrative input.</p></div><strong id="replay-clock" /></div>
                  <div className="replay-options">
                    <label>Scenario mode<select id="replay-mode" defaultValue="archive"><option value="archive">Archive reconstruction</option><option value="what_if">What-if exercise</option></select></label>
                    <label>Rainfall preset<select id="replay-preset" defaultValue="archived"><option value="archived">Archived rainfall</option><option value="plus-5">Archived +5 mm/hour · synthetic</option><option value="plus-10">Archived +10 mm/hour · synthetic</option></select></label>
                  </div>
                  <button id="replay-reset" type="button">Reset simulation</button>
                  <p id="replay-loading" role="status" /><p id="replay-source-status" className="detail-note" />
                  <details><summary>NHC storm context</summary><p id="advisory-context" className="advisory-text" /><a id="advisory-link" href="https://www.nhc.noaa.gov/archive/2026/ISAIAS.shtml" target="_blank" rel="noopener noreferrer">Open original NHC advisory</a></details>
                </section>
                <section id="replay-results" className="replay-results" hidden aria-label="Hourly exposure and evacuation exercise">
                  <section className="replay-panel"><h2 id="timeline-heading">Illustrative exposure for the next six hours</h2><p id="timeline-change" role="status" /><svg id="risk-chart" viewBox="0 0 650 150" role="img" aria-label="Hourly relative score; missing data appears as gaps" /><p className="detail-note">Oct 9, midnight Central – Oct 10, midnight Central · Missing data creates gaps. Scores are unvalidated relative estimates.</p><details><summary>Hourly values and source status</summary><div className="table-wrap"><table><thead><tr><th>Central time</th><th>Score / 100</th><th>Hourly change</th><th>Rainfall status</th></tr></thead><tbody id="timeline-rows" /></table></div></details></section>
                  <section className="replay-panel"><h2>Resident evacuation route exercise</h2><p id="route-summary" role="status" /><p id="route-comparison" className="detail-note" /><p id="route-notice" className="detail-note" /><p className="detail-note">Map: gray dashed = unrestricted comparison; teal = chosen exercise route; orange = closed; gray = unknown; dashed connectors = simulated access.</p>
                    <div className="road-overrides"><label>Exercise segment<select id="road-select" /></label><label>Override state<select id="road-state" defaultValue="closed"><option value="closed">Closed</option><option value="unknown">Unknown</option><option value="open">Assumed open</option></select></label><button id="road-apply" type="button">Apply override</button></div>
                    <div id="destination-controls" className="destination-controls" /><p id="routing-overrides" className="detail-note" />
                  </section>
                </section>
              </aside>
            </div>
          </section>
        </div>
        <section className="source-grid" id="data-sources" aria-label="Forecast and official source status">
          <section className="source-card" aria-labelledby="forecast-heading"><CloudRain aria-hidden="true" /><div><h2 id="forecast-heading">WeatherNext 3</h2><p id="weather-status" role="status">Checking imported forecast status…</p></div></section>
          <section className="source-card" aria-labelledby="official-heading"><Radar aria-hidden="true" /><div><h2 id="official-heading">Official NWS alerts</h2><p id="official-status">Official feed is not connected. This is not an all-clear.</p><a href="https://www.weather.gov/mob/" target="_blank" rel="noopener noreferrer">Open NWS Mobile/Pensacola <ArrowUpRight aria-hidden="true" /></a></div></section>
        </section>
        <details className="exercise-guide" id="exercise-guide"><summary><CircleHelp aria-hidden="true" />How to read this map</summary><p>Forecast rainfall cells preserve their source units, timestamps, and missing-data states. Parcel scores remain unavailable unless matching verified assessments are configured. H3 is for browsing and does not increase forecast resolution.</p><p>Map colors and experimental summaries do not represent flood depth or probability. Follow official NWS and local guidance for real decisions.</p></details>
        <footer className="dashboard-footer"><span><Waves aria-hidden="true" />Quasar · IBM Z Datathon</span><p>Okaloosa only · Parcel scores remain unknown without verified assessments · No notifications are sent</p></footer>
      </div>
    </div>
  );
});
