import { memo, useEffect, useState } from "react";
import { Reports } from "./reports";
import { MapSelectionPanel } from "./components/map-selection-panel";
import { DataDashboard } from "./data-dashboard";
import { ArrowUpRight, CircleHelp, CloudRain, Layers3, MapPin, Radar, TriangleAlert, Waves } from "lucide-react";

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
          <div><p className="eyebrow"><Radar aria-hidden="true" />EXPOSURE WORKSPACE</p><h1>A clearer view of changing conditions.</h1><p>Explore Okaloosa exercise sites, rainfall scenarios, and the factors behind each score.</p></div>
          <div className="county-tag"><MapPin aria-hidden="true" /><span>Okaloosa, FL<small>County FIPS 12091</small></span></div>
        </section>
        <aside className="notice"><TriangleAlert aria-hidden="true" /><p id="data-notice">Unvalidated demonstration estimates. These are not flood depths, probabilities, or official warnings. All sites and attributes are synthetic.</p></aside>
        <section className="exercise-toolbar" aria-label="Map toolbar">
          <label htmlFor="scenario"><CloudRain aria-hidden="true" /><span>Data source</span><select id="scenario" disabled aria-label="Map data source and time window" /></label>
          <label htmlFor="map-layer"><Layers3 aria-hidden="true" /><span>Display</span><select id="map-layer" defaultValue="exposure"><option value="rainfall">Rainfall · mm / 6h</option><option value="exposure">Relative exposure · /100</option></select></label>
          <button id="replay-toggle" type="button" disabled aria-pressed="false" aria-controls="map-sidebar"><Radar aria-hidden="true" /><span>Isaias simulation</span></button>
          <button id="map-inspect-toggle" type="button" aria-expanded="false" aria-controls="map-sidebar"><MapPin aria-hidden="true" />Inspect sites</button>
          <span className="demo-badge" id="mode-badge">SYNTHETIC DEMO</span>
        </section>
        <p id="error" role="alert" hidden />
        <section className="stats" aria-label="Scenario summary">
          <div><div className="stat-label">Exercise sites<MapPin aria-hidden="true" /></div><strong id="site-count">—</strong><p>Fictional locations in the county</p></div>
          <div><div className="stat-label">Elevated relative score<TriangleAlert aria-hidden="true" /></div><strong id="elevated-count">—</strong><p>Illustrative score of 65 or above</p></div>
          <div><div className="stat-label">Insufficient data<CircleHelp aria-hidden="true" /></div><strong id="unknown-count">—</strong><p>Unknown inputs remain unscored</p></div>
        </section>
        <div className="map-workspace">
          <section className="map-card" id="map-overview" tabIndex={-1} aria-label="Okaloosa exercise map">
            <div className="panel-header"><div><h2 id="map-heading"><MapPin aria-hidden="true" />County map</h2><p>County grid · parcel browsing · fictional exercise sites</p></div><span id="grid-resolution" className="subtle-tag">H3 · RES 6</span></div>
            <div className="map-data-summary" aria-live="polite"><strong id="map-data-title">Loading map data…</strong><p id="window">Loading exercise clock…</p><p id="map-data-values" /><p id="map-data-source" /></div>
            <div className="map-viewport"><div id="map"><p className="map-fallback">Map loading. Exercise sites remain available below.</p></div><MapSelectionPanel /></div>
            <div className="map-controls"><label className="hex-control"><input type="checkbox" id="hex-toggle" defaultChecked /><Layers3 aria-hidden="true" />County H3 grid</label><span id="grid-status" className="subtle-tag">Loading county boundary…</span></div>
            <div className="map-caption"><p id="map-status" role="status" />
              <div id="exposure-legend" className="legend" aria-label="Relative exposure legend"><span><i className="dot elevated" />Elevated</span><span><i className="dot moderate" />Moderate</span><span><i className="dot lower_relative" />Lower relative</span><span><i className="dot unknown" />Unknown</span></div>
              <div id="rainfall-legend" className="legend" hidden aria-label="Rainfall legend"><span><i className="dot rain-light" />0–25</span><span><i className="dot rain-medium" />25–75</span><span><i className="dot rain-heavy" />75+ mm / 6h</span><span><i className="dot unknown" />Unavailable</span></div>
              <p id="map-layer-note" className="detail-note">Hexagons summarize exercise sites. They are not flood extents, county boundaries, or higher-resolution forecasts.</p>
            </div>
          </section>
          <aside id="map-sidebar" className="map-sidebar" aria-label="Map inspection and simulation">
            <section id="isaias-replay" className="replay-panel" hidden aria-labelledby="replay-heading">
              <div className="panel-header"><div><p className="eyebrow">HISTORICAL CONTEXT · FICTIONAL SITE INPUTS</p><h2 id="replay-heading">Isaias simulation · 2026</h2><p>Oct 9 archive reconstruction and simulated routes. Select a site on the map to update the trend.</p></div><strong id="replay-clock" /></div>
              <div className="replay-options">
                <label>Scenario mode<select id="replay-mode" defaultValue="archive"><option value="archive">Archive reconstruction</option><option value="what_if">What-if exercise</option></select></label>
                <label>Rainfall preset<select id="replay-preset" defaultValue="archived"><option value="archived">Archived rainfall</option><option value="plus-5">Archived +5 mm/hour · synthetic</option><option value="plus-10">Archived +10 mm/hour · synthetic</option></select></label>
              </div>
              <div className="playback-controls"><button id="replay-prev" type="button">Previous hour</button><button id="replay-play" type="button">Play</button><button id="replay-next" type="button">Next hour</button><button id="replay-reset" type="button">Reset</button></div>
              <label className="hour-scrubber">Replay hour<input id="replay-hour" type="range" min="0" max="24" step="1" defaultValue="0" aria-label="Isaias replay hour" /></label>
              <p id="replay-loading" role="status" /><p id="replay-source-status" className="detail-note" />
              <details><summary>NHC storm context</summary><p id="advisory-context" className="advisory-text" /><a id="advisory-link" href="https://www.nhc.noaa.gov/archive/2026/ISAIAS.shtml" target="_blank" rel="noopener noreferrer">Open original NHC advisory</a></details>
            </section>
            <section className="details" id="site-details" aria-labelledby="detail-heading"><label className="site-selector">Exercise site<select id="map-site" aria-label="Inspect an exercise site" /></label><div className="detail-title"><p className="eyebrow">SITE EXPLAINER</p><Waves aria-hidden="true" /></div><h2 id="detail-heading">Choose an exercise site</h2><div id="detail" aria-live="polite">Select a map point or inspect a site below.</div></section>
            <section id="replay-results" className="replay-results" hidden aria-label="Hourly exposure and evacuation exercise">
              <section className="replay-panel"><h2 id="timeline-heading">Illustrative exposure for the next six hours</h2><p id="timeline-change" role="status" /><svg id="risk-chart" viewBox="0 0 650 150" role="img" aria-label="Hourly relative score; missing data appears as gaps" /><p className="detail-note">Oct 9, midnight Central – Oct 10, midnight Central · Missing data creates gaps. Scores are unvalidated relative estimates.</p><details><summary>Hourly values and source status</summary><div className="table-wrap"><table><thead><tr><th>Central time</th><th>Score / 100</th><th>Hourly change</th><th>Rainfall status</th></tr></thead><tbody id="timeline-rows" /></table></div></details></section>
              <section className="replay-panel"><h2>Resident evacuation route exercise</h2><p id="route-summary" role="status" /><p id="route-comparison" className="detail-note" /><p id="route-notice" className="detail-note" /><p className="detail-note">Map: gray dashed = unrestricted comparison; teal = chosen exercise route; orange = closed; gray = unknown; dashed connectors = simulated access.</p>
                <div className="road-overrides"><label>Exercise segment<select id="road-select" /></label><label>Override state<select id="road-state" defaultValue="closed"><option value="closed">Closed</option><option value="unknown">Unknown</option><option value="open">Assumed open</option></select></label><button id="road-apply" type="button">Apply override</button></div>
                <div id="destination-controls" className="destination-controls" /><p id="routing-overrides" className="detail-note" />
              </section>
            </section>
          </aside>
        </div>
        <section className="sites" id="exercise-sites" aria-labelledby="sites-heading"><div className="panel-header"><div><h2 id="sites-heading">Prioritized exercise sites</h2><p>Fictional points, not a parcel inventory. Lower relative scores do not mean safe conditions.</p></div><span className="subtle-tag">OKALOOSA</span></div><div className="table-wrap"><table><thead><tr><th scope="col">Exercise site</th><th scope="col">Relative score / 100</th><th scope="col">Band</th><th scope="col">Rainfall · mm / 6h</th><th scope="col"><span className="sr-only">Details</span></th></tr></thead><tbody id="sites" /></table></div></section>
        <section className="source-grid" id="data-sources" aria-label="Forecast and official source status">
          <section className="source-card" aria-labelledby="forecast-heading"><CloudRain aria-hidden="true" /><div><h2 id="forecast-heading">WeatherNext 3</h2><p id="weather-status" role="status">Checking imported forecast status…</p></div></section>
          <section className="source-card" aria-labelledby="official-heading"><Radar aria-hidden="true" /><div><h2 id="official-heading">Official NWS alerts</h2><p id="official-status">Official feed is not connected. This is not an all-clear.</p><a href="https://www.weather.gov/mob/" target="_blank" rel="noopener noreferrer">Open NWS Mobile/Pensacola <ArrowUpRight aria-hidden="true" /></a></div></section>
        </section>
        <details className="exercise-guide" id="exercise-guide"><summary><CircleHelp aria-hidden="true" />How to read this exercise</summary><p>Choose a time window, then inspect a site on the map or in the table. The explainer shows how each input contributes to an illustrative relative score. Unknown sites are missing required data and receive no score. Synthetic exercise dates are a fictional clock, not current weather.</p><p>WeatherNext mode uses imported forecast rainfall with fictional site inputs and is labeled MIXED DEMO. H3 cells summarize occupied sites; they do not represent flood depth or probability. Follow official NWS and local guidance for real decisions.</p></details>
        <footer className="dashboard-footer"><span><Waves aria-hidden="true" />Quasar · IBM Z Datathon</span><p>Okaloosa only · Fictional sites and unvalidated scores · No notifications are sent</p></footer>
      </div>
    </div>
  );
});
