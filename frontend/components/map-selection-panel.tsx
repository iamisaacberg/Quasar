import { ArrowLeft, X } from "lucide-react";

// Adapted from TrialSmiles LeadCellScorePanel / LeadHouseScorePanel: badge,
// identity, score meter, three summary stats, section stack and close/back flow.
export function MapSelectionPanel() {
  return (
    <aside id="map-selection-panel" className="quasar-score-panel" hidden aria-label="Selected cell or parcel">
      <div className="selection-top-row"><span id="selection-badge" className="selection-badge">R7 cell</span><button id="selection-close" type="button" aria-label="Close cell and parcel details"><X size={16} /></button></div>
      <button id="selection-back" className="selection-back" type="button" hidden><ArrowLeft size={14} />Back to cell</button>
      <div className="selection-identity"><h2 id="selection-title">Selected cell</h2><p id="selection-code" /><p id="selection-subtitle" /></div>
      <div className="selection-meter"><strong id="selection-score">Unscored</strong><span>Experimental relative exposure</span><p>This index is not flood probability or depth. Green does not establish safety.</p></div>
      <div className="selection-stats"><div><strong id="selection-stat-one">—</strong><span id="selection-stat-one-label">Parcels shown</span></div><div><strong id="selection-stat-two">—</strong><span id="selection-stat-two-label">Exercise sites</span></div><div><strong id="selection-stat-three">—</strong><span id="selection-stat-three-label">Scored parcels</span></div></div>
      <div className="selection-actions"><button id="cell-zoom" type="button" hidden>Zoom in</button><button id="parcel-refresh" type="button" hidden>Refresh parcels</button><button id="parcel-clear" type="button">Clear parcel cache</button></div>
      <div className="selection-section-stack">
        <section><h3>Experimental exposure assessment</h3><div id="selection-exposure" aria-live="polite" /></section>
        <section><h3 id="selection-section-title">Parcels in this cell</h3><p id="parcel-status" role="status" aria-live="polite" /><label id="parcel-search-label" hidden>Find loaded parcel<input id="parcel-search" type="search" placeholder="County GIS ID" /></label><div id="selection-content" /><div id="parcel-pagination" hidden><button id="parcel-previous" type="button">Previous</button><span id="parcel-page" role="status" /><button id="parcel-next" type="button">Next</button></div><button id="parcel-retry" type="button" hidden>Retry parcel loading</button></section>
        <section><h3>Flood data availability</h3><p id="context-status" role="status" aria-live="polite" /><dl id="selection-inputs" className="selection-factors" /><p className="selection-note">Real parcel boundaries are separate from fictional exercise sites. Missing inputs remain unknown. H3 does not increase forecast resolution.</p></section>
        <section><h3>Source &amp; coverage</h3><p id="parcel-provenance" className="selection-note" /><p id="context-provenance" className="selection-note" /><a href="https://okgis.myokaloosa.com/arcgis/rest/services/Land-Ownership/Parcels/MapServer/0" target="_blank" rel="noreferrer">Okaloosa parcel source ↗</a><p className="selection-note">Project estimates supplement official NWS/local guidance. They are not flood depths, probabilities or a guarantee of safety.</p></section>
      </div>
    </aside>
  );
}
