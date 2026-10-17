import { memo, useEffect, useState } from "react";
import { Reports } from "./reports";
import { ArrowUpRight, CircleHelp, CloudRain, Layers3, MapPin, Radar, TriangleAlert, Waves } from "lucide-react";

declare global {
  interface Window { Quasar?: { start: () => Promise<void> }; }
}

export const QuasarDashboard = memo(function QuasarDashboard() {
  const [isReportsView, setIsReportsView] = useState(window.location.hash === "#reports");
  useEffect(() => {
    // Mapbox may have initialized while the Reports view hid its container.
    if (!isReportsView) window.dispatchEvent(new Event("resize"));
  }, [isReportsView]);
  useEffect(() => {
    const update = () => setIsReportsView(window.location.hash === "#reports");
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
    <div className={`workspace-view${isReportsView ? " is-reports-view" : ""}`}>
      <Reports active={isReportsView} />
      <header className="workspace-header">
        <div className="breadcrumb"><span>Miami-Dade County</span><span aria-hidden="true">/</span><strong>Map overview</strong></div>
        <span className="demo-badge" id="mode-badge">SYNTHETIC DEMO</span>
      </header>
      <div className="dashboard">
        <section className="page-heading" id="map-overview" tabIndex={-1}>
          <div><p className="eyebrow"><Radar aria-hidden="true" />EXPOSURE WORKSPACE</p><h1>A clearer view of changing conditions.</h1><p>Explore Miami-Dade exercise sites, rainfall scenarios, and the factors behind each score.</p></div>
          <div className="county-tag"><MapPin aria-hidden="true" /><span>Miami-Dade, FL<small>County FIPS 12086</small></span></div>
        </section>
        <aside className="notice"><TriangleAlert aria-hidden="true" /><p id="data-notice">Unvalidated demonstration estimates. These are not flood depths, probabilities, or official warnings. All sites and attributes are synthetic.</p></aside>
        <section className="exercise-toolbar" aria-label="Exercise controls">
          <label htmlFor="scenario"><CloudRain aria-hidden="true" /><span>Time window</span><select id="scenario" disabled aria-label="Exercise time window" /></label>
          <p id="window">Loading exercise clock…</p>
        </section>
        <p id="error" role="alert" hidden />
        <section className="stats" aria-label="Scenario summary">
          <div><div className="stat-label">Exercise sites<MapPin aria-hidden="true" /></div><strong id="site-count">—</strong><p>Fictional locations in the county</p></div>
          <div><div className="stat-label">Elevated relative score<TriangleAlert aria-hidden="true" /></div><strong id="elevated-count">—</strong><p>Illustrative score of 65 or above</p></div>
          <div><div className="stat-label">Insufficient data<CircleHelp aria-hidden="true" /></div><strong id="unknown-count">—</strong><p>Unknown inputs remain unscored</p></div>
        </section>
        <div className="map-workspace">
          <section className="map-card" aria-labelledby="map-heading">
            <div className="panel-header"><div><h2 id="map-heading"><MapPin aria-hidden="true" />County map</h2><p>Fictional sites · relative exposure</p></div><span className="subtle-tag">H3 · RES 7</span></div>
            <div id="map"><p className="map-fallback">Map loading. Exercise sites remain available below.</p></div>
            <div className="map-controls"><label className="hex-control"><input type="checkbox" id="hex-toggle" defaultChecked /><Layers3 aria-hidden="true" />H3 hotspot summaries</label><span className="subtle-tag">6-hour rainfall</span></div>
            <div className="map-caption"><p id="map-status" role="status" />
              <div className="legend" aria-label="Relative exposure legend"><span><i className="dot elevated" />Elevated</span><span><i className="dot moderate" />Moderate</span><span><i className="dot lower_relative" />Lower relative</span><span><i className="dot unknown" />Unknown</span></div>
              <p className="detail-note">Hexagons summarize exercise sites. They are not flood extents, county boundaries, or higher-resolution forecasts.</p>
            </div>
          </section>
          <section className="details" id="site-details" aria-labelledby="detail-heading"><div className="detail-title"><p className="eyebrow">SITE EXPLAINER</p><Waves aria-hidden="true" /></div><h2 id="detail-heading">Choose an exercise site</h2><div id="detail" aria-live="polite">Select a map point or inspect a site below.</div></section>
        </div>
        <section className="sites" id="exercise-sites" aria-labelledby="sites-heading"><div className="panel-header"><div><h2 id="sites-heading">Prioritized exercise sites</h2><p>Fictional points, not a parcel inventory. Lower relative scores do not mean safe conditions.</p></div><span className="subtle-tag">MIAMI-DADE</span></div><div className="table-wrap"><table><thead><tr><th scope="col">Exercise site</th><th scope="col">Relative score / 100</th><th scope="col">Band</th><th scope="col"><span className="sr-only">Details</span></th></tr></thead><tbody id="sites" /></table></div></section>
        <section className="source-grid" id="data-sources" aria-label="Forecast and official source status">
          <section className="source-card" aria-labelledby="forecast-heading"><CloudRain aria-hidden="true" /><div><h2 id="forecast-heading">WeatherNext 3</h2><p id="weather-status" role="status">Checking imported forecast status…</p></div></section>
          <section className="source-card" aria-labelledby="official-heading"><Radar aria-hidden="true" /><div><h2 id="official-heading">Official NWS alerts</h2><p id="official-status">Official feed is not connected. This is not an all-clear.</p><a href="https://www.weather.gov/mfl/" target="_blank" rel="noopener noreferrer">Open NWS Miami <ArrowUpRight aria-hidden="true" /></a></div></section>
        </section>
        <details className="exercise-guide" id="exercise-guide"><summary><CircleHelp aria-hidden="true" />How to read this exercise</summary><p>Choose a time window, then inspect a site on the map or in the table. The explainer shows how each input contributes to an illustrative relative score. Unknown sites are missing required data and receive no score. Synthetic exercise dates are a fictional clock, not current weather.</p><p>WeatherNext mode uses imported forecast rainfall with fictional site inputs and is labeled MIXED DEMO. H3 cells summarize occupied sites; they do not represent flood depth or probability. Follow official NWS and local guidance for real decisions.</p></details>
        <footer className="dashboard-footer"><span><Waves aria-hidden="true" />Quasar · IBM Z Datathon</span><p>Miami-Dade only · Synthetic exercise, not a historical storm replay · No notifications are sent</p></footer>
      </div>
    </div>
  );
});
