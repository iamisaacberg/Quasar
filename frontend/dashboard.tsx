import { memo, useEffect, useState } from "react";
import { Reports } from "./reports";
import { MapSelectionPanel } from "./components/map-selection-panel";
import { DataDashboard } from "./data-dashboard";
import { ArrowUpRight, CloudRain, Layers3, MapPin, Radar, TriangleAlert, Waves, Search, X, SlidersHorizontal, Plus, Minus, ChevronLeft, ChevronRight, Info } from "lucide-react";

declare global {
  interface Window { Quasar?: { start: () => Promise<void>; frame?: () => number }; }
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
  const [isMapView, setIsMapView] = useState(!window.location.hash || ["#map-overview", "#isaias-replay", "#site-details"].includes(window.location.hash));
  useEffect(() => {
    const update = () => setIsMapView(!window.location.hash || ["#map-overview", "#isaias-replay", "#site-details"].includes(window.location.hash));
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
          <div><p className="eyebrow"><Radar aria-hidden="true" />ISAIAS REPLAY</p><h1>Isaias, one forecast hour at a time.</h1><p>October 9, 2026 · Okaloosa County · Archived WeatherNext 3 rainfall.</p></div>
          <div className="county-tag"><MapPin aria-hidden="true" /><span>Okaloosa, FL<small>County FIPS 12091</small></span></div>
        </section>
        <aside className="notice"><TriangleAlert aria-hidden="true" /><p id="data-notice">Imported county source data. Missing inputs remain unknown. Forecast rainfall is not flood depth, probability or an official warning.</p></aside>
        <p id="error" role="alert" hidden />
        <div className="map-workspace">
          <section className="map-card" id="map-overview" tabIndex={-1} aria-label="Okaloosa county map">
            <div className="panel-header"><div><h2 id="map-heading"><MapPin aria-hidden="true" />County map</h2><p>County grid · parcel browsing · native forecast rainfall</p></div><span id="grid-resolution" className="subtle-tag">H3 · RES 6</span></div>
            <div className="map-viewport">
              <div id="map"><p className="map-fallback">Map loading. County source tables remain available in Data.</p></div>
              <div className="map-search map-float" role="search">
                <div className="map-search-input"><Search aria-hidden="true" /><input id="map-search" type="text" disabled placeholder="Search Okaloosa addresses and places…" aria-label="Search Okaloosa County" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="map-search-results" aria-describedby="map-search-status" autoComplete="off" /><button id="map-search-clear" type="button" disabled aria-label="Clear search"><X aria-hidden="true" /></button></div>
                <ul id="map-search-results" role="listbox" aria-label="County search results" hidden />
                <p id="map-search-status" role="status">Search requires a configured map and an available county boundary.</p>
              </div>
              <div className="map-state map-float"><span className="demo-badge" id="mode-badge">ISAIAS · ARCHIVED FORECAST</span><span id="map-display-label">Loading map data…</span></div>
              <p id="map-status" className="map-message map-float" role="status" />
              <div className="map-tool-dock map-float">
                <div className="map-zoom"><button id="map-zoom-in" type="button" aria-label="Zoom in"><Plus /></button><button id="map-zoom-out" type="button" aria-label="Zoom out"><Minus /></button></div>
                <details id="map-tools"><summary aria-label="Map tools"><SlidersHorizontal aria-hidden="true" /><span>Tools</span></summary><div className="map-tools-panel"><h2>Map tools</h2>
                  <section className="exercise-toolbar" aria-label="Map toolbar">
                    <p className="detail-note">Isaias archive · October 9, 2026<br />Each hour shows the following six forecast hours.</p>
                    <label htmlFor="map-layer"><Layers3 aria-hidden="true" /><span>Display</span><select id="map-layer" defaultValue="rainfall"><option value="rainfall">Rainfall · mm / 6h</option><option value="exposure">Relative exposure · /100</option></select></label>
                  </section>
                  <div className="map-controls"><label className="hex-control"><input type="checkbox" id="hex-toggle" defaultChecked /><Layers3 aria-hidden="true" />County H3 grid</label><span id="grid-status" className="subtle-tag">Loading county boundary…</span></div>
                </div></details>
              </div>
              <section className="map-playback map-float" aria-label="Isaias archive playback">
                <div className="archive-playback-heading"><strong id="archive-trend-label">Isaias · October 9, 2026</strong><button id="forecast-retry" type="button">Recheck source</button></div>
                <div id="archive-trend" className="archive-trend" role="group" aria-label="Hourly maximum forecast rainfall; select an hour" />
                <p id="archive-trend-range" />
                <p id="playback-clock">Loading Isaias archive…</p>
                <div className="playback-main"><button id="replay-prev" type="button" disabled aria-label="Previous hour"><ChevronLeft /></button><button id="replay-play" type="button" disabled aria-label="Play Isaias timeline" aria-pressed="false">▶</button><button id="replay-next" type="button" disabled aria-label="Next hour"><ChevronRight /></button><input id="replay-hour" type="range" min="0" max="0" step="1" defaultValue="0" disabled aria-label="Isaias replay hour" /></div>
                <p id="playback-status" role="status">Loading archived forecast rainfall.</p>
              </section>
              <details className="map-legend map-float" id="map-legend" open><summary><Layers3 aria-hidden="true" />Legend</summary><div className="map-legend-content">
                <div id="exposure-legend" className="legend exposure-legend" aria-label="Experimental relative exposure">
                <strong>Experimental relative exposure</strong>
                <div className="exposure-gradient" aria-hidden="true" />
                <span><i className="dot lower_relative" />0–34 · Lower relative exposure</span>
                <span><i className="dot moderate" />35–64 · Moderate relative exposure</span>
                <span><i className="dot elevated" />65–84 · Elevated relative exposure</span>
                <span><i className="dot highest" />85–100 · Highest relative exposure</span>
                <span>Transparent · Unknown or unavailable assessment</span>
                <strong>Green does not establish safety.</strong>
              </div>
                <div id="rainfall-legend" className="legend" hidden aria-label="Rainfall legend"><span><i className="dot rain-light" />0</span><span><i className="dot rain-low" />5</span><span><i className="dot rain-medium" />25</span><span><i className="dot rain-heavy" />75+ mm / 6h</span><span>Transparent · Unavailable</span></div>
                <p>Rainfall: mm / 6h · Exposure: score / 100</p>
                <details className="map-info" id="map-source-info"><summary><Info aria-hidden="true" />Source &amp; interpretation</summary>
                  <div className="map-data-summary" aria-live="polite"><strong id="map-data-title">Loading map data…</strong><p id="window">Loading source window…</p><p id="map-data-values" /><p id="map-data-source" /></div>
                  <p id="map-layer-note" className="detail-note">H3 outlines support parcel browsing. Native rainfall cells retain their original resolution.</p>
                  <p id="map-demo-notice">Forecasts supplement official NWS/local guidance.</p>
                </details>
              </div></details>
              <button id="map-sheet-backdrop" className="map-sheet-backdrop" type="button" aria-label="Close map details" tabIndex={-1} hidden />
              <MapSelectionPanel />
            </div>
          </section>
        </div>
        <section className="source-grid" id="data-sources" aria-label="Forecast and official source status">
          <section className="source-card" aria-labelledby="forecast-heading"><CloudRain aria-hidden="true" /><div><h2 id="forecast-heading">WeatherNext 3</h2><p id="weather-status" role="status">Checking imported forecast status…</p></div></section>
          <section className="source-card" aria-labelledby="official-heading"><Radar aria-hidden="true" /><div><h2 id="official-heading">Official NWS alerts</h2><p id="official-status">Official feed is not connected. This is not an all-clear.</p><a href="https://www.weather.gov/mob/" target="_blank" rel="noopener noreferrer">Open NWS Mobile/Pensacola <ArrowUpRight aria-hidden="true" /></a></div></section>
        </section>
        <footer className="dashboard-footer"><span><Waves aria-hidden="true" />Quasar · IBM Z Datathon</span><p>Okaloosa only · Source dates and coverage retained · Follow official guidance</p></footer>
      </div>
    </div>
  );
});
