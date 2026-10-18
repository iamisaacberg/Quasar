import { ArrowLeft, X } from "lucide-react";

export function MapSelectionPanel() {
  return (
    <aside id="map-selection-panel" className="quasar-score-panel" hidden aria-label="Selected cell or parcel">
      <div className="selection-top-row"><span id="selection-badge" className="selection-badge">R7 cell</span><button id="selection-close" type="button" aria-label="Close cell and parcel details"><X size={16} /></button></div>
      <button id="selection-back" className="selection-back" type="button" hidden><ArrowLeft size={14} />Back to cell</button>
      <div className="selection-identity"><h2 id="selection-title">Selected cell</h2><p id="selection-code" /><p id="selection-subtitle" /></div>
      <p id="selection-window" className="selection-window" />
      <div id="selection-rainfall-meter" className="selection-meter"><strong id="selection-rainfall">Loading…</strong><span>Archived forecast rainfall · mm / 6h</span><p id="selection-rainfall-note">Reading native rainfall overlaps…</p></div>
      <div id="selection-exposure-meter" className="selection-meter" hidden><strong id="selection-score">Unscored</strong><span id="selection-band">Experimental relative exposure</span><p id="selection-assessment" /></div>
      <div className="selection-stats"><div><strong id="selection-stat-one">—</strong><span id="selection-stat-one-label">Parcels shown</span></div><div><strong id="selection-stat-two">—</strong><span id="selection-stat-two-label">Terrain complete</span></div><div><strong id="selection-stat-three">—</strong><span id="selection-stat-three-label">Scored parcels</span></div></div>
      <ul id="selection-insights" className="selection-insights" aria-label="Key insights" />
      <p className="selection-note selection-guidance">Experimental index, not flood probability or depth. Green does not establish safety. Follow official NWS/local guidance.</p>
      <button id="cell-zoom" className="selection-zoom" type="button" hidden>Zoom in to browse parcels</button>
      <div className="selection-section-stack">
        <p id="context-status" role="status" aria-live="polite" /><button id="context-retry" type="button" hidden>Retry reference inputs</button>
        <p id="parcel-status" role="status" aria-live="polite" /><button id="parcel-retry" type="button" hidden>Retry parcel loading</button>
        <details id="selection-records"><summary id="selection-section-title">Browse parcels</summary><label id="parcel-search-label" hidden>Find loaded parcel<input id="parcel-search" type="search" placeholder="County GIS ID" /></label><div id="selection-content" /><div id="parcel-pagination" hidden><button id="parcel-previous" type="button">Previous</button><span id="parcel-page" role="status" /><button id="parcel-next" type="button">Next</button></div></details>
        <details id="selection-exposure-section" hidden><summary>How the index was calculated</summary><div id="selection-exposure" /></details>
        <details><summary>Reference inputs &amp; forecast sources</summary><dl id="selection-inputs" className="selection-factors" /><p className="selection-note">Prepared reference inputs describe real county parcels. Missing inputs remain unknown. H3 does not increase forecast resolution.</p></details>
        <details><summary>Source &amp; coverage details</summary><p id="parcel-provenance" className="selection-note" /><p id="context-provenance" className="selection-note" /><a href="https://okgis.myokaloosa.com/arcgis/rest/services/Land-Ownership/Parcels/MapServer/0" target="_blank" rel="noreferrer">Okaloosa parcel source ↗</a><div className="selection-actions"><button id="parcel-refresh" type="button" hidden>Refresh parcels</button><button id="parcel-clear" type="button">Clear parcel cache</button></div></details>
      </div>
    </aside>
  );
}
