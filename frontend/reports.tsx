import { useEffect, useState } from "react";
import "./reports.css";

type Factor = { name: string; value: string | number; weight: number; contribution: number };
export type Scenario = { id: string; label: string; valid_from: string; valid_to: string };
type Summary = { site_count: number; scored_count: number; unknown_count: number; mean_score: number | null; bands: Record<string, number> };
type Row = {
  property_id: string; label: string; scenario: string; score: number | null; band: string;
  rainfall_6h_mm: number | null; missing: string[]; factors: Factor[]; forecast_status: string;
  data_status: string; model_version: string; available_hours: number | null;
};
export type Report = {
  county_fips: string; mode: string; generated_at: string; notice: string; provenance: string;
  scenario?: Scenario; summary?: Summary; scenarios?: { scenario: Scenario; summary: Summary }[];
  rows: Row[]; forecast: null | { status: string; source_table: string; init_time: string;
    retrieved_at: string; native_resolution: string; statistic: string };
};
type Preset = "overview" | "compare" | "site";
const bands = ["lower_relative", "moderate", "elevated", "unknown"];
const labels: Record<string, string> = {
  lower_relative: "Lower relative", moderate: "Moderate", elevated: "Elevated", unknown: "Unknown",
  rainfall_6h_mm: "Six-hour rainfall (mm)", elevation_m: "Terrain elevation (m)",
  fema_zone: "Illustrative FEMA zone", waterway_distance_m: "Waterway distance (m)",
  gauge_margin_m: "Margin below flood stage (m)",
};
const colors: Record<string, string> = { lower_relative: "#347e73", moderate: "#a87812", elevated: "#b64d36", unknown: "#6b7280" };
const number = (value: number | null) => value === null ? "Unknown" : value.toLocaleString("en-US", { maximumFractionDigits: 3 });
const time = (value: string) => new Date(value).toLocaleString("en-US", { timeZone: "America/New_York", dateStyle: "medium", timeStyle: "short" }) + " Miami time";

async function get<T,>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not load report");
  return data;
}

function BarChart({ title, rows, max }: { title: string; rows: { key: string; label: string; value: number | null; color: string }[]; max: number }) {
  const height = rows.length * 38 + 30;
  return <svg className="report-chart" viewBox={`0 0 760 ${height}`} role="img" aria-label={title}>
    <title>{`${title}. Values are also provided in the following table.`}</title>
    {rows.map((row, index) => <g key={row.key} transform={`translate(0, ${index * 38 + 14})`}>
      <text x="0" y="14" fontSize="12" fill="currentColor">{row.label}</text>
      {row.value !== null && <rect x="270" y="0" width={row.value / max * 400} height="20" rx="3" fill={row.color} />}
      <text x="690" y="14" fontSize="12" fill="currentColor">{number(row.value)}</text>
    </g>)}
    <text x="270" y={height - 4} fontSize="10" fill="currentColor">0</text>
    <text x="650" y={height - 4} fontSize="10" fill="currentColor">{max}</text>
  </svg>;
}

function BandSummary({ summary, label }: { summary: Summary; label: string }) {
  return <section className="report-block"><h3>{label} · site counts</h3>
    <BarChart title={`${label}: sites by relative score band`} max={Math.max(summary.site_count, 1)}
      rows={bands.map(band => ({ key: band, label: labels[band], value: summary.bands[band] || 0, color: colors[band] }))} />
    <table><caption>Sites by relative score band</caption><thead><tr><th scope="col">Band</th><th scope="col">Sites</th></tr></thead>
      <tbody>{bands.map(band => <tr key={band}><th scope="row">{labels[band]}</th><td>{summary.bands[band] || 0}</td></tr>)}</tbody></table>
    <p>{summary.site_count} fictional sites · {summary.scored_count} scored · {summary.unknown_count} unknown. Mean of scored sites: {number(summary.mean_score)} / 100.</p>
  </section>;
}

function ScoreTable({ rows }: { rows: Row[] }) {
  return <div className="report-table-wrap"><table><caption>Relative scores and input completeness</caption>
    <thead><tr><th scope="col">Fictional site</th><th scope="col">Score / 100</th><th scope="col">Band</th><th scope="col">Rainfall (mm / 6h)</th><th scope="col">Missing inputs / forecast status</th></tr></thead>
    <tbody>{rows.map(row => <tr key={`${row.property_id}:${row.scenario}`}><th scope="row">{row.label}</th><td>{number(row.score)}</td><td>{labels[row.band]}</td><td>{number(row.rainfall_6h_mm)}</td><td>{row.missing.map(key => labels[key] || key).join(", ") || "No missing inputs"} · {row.forecast_status.replaceAll("_", " ")}</td></tr>)}</tbody>
  </table></div>;
}

export function Reports({ active }: { active: boolean }) {
  const [preset, setPreset] = useState<Preset>("overview");
  const [scenario, setScenario] = useState("baseline");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [site, setSite] = useState("demo-001");
  const [loadedData, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const selection = preset === "compare" ? "compare" : scenario;
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true); setData(null); setError("");
    void Promise.all([
      get<Report>(`/api/reports?scenario=${encodeURIComponent(selection)}`, controller.signal),
      get<{ scenarios: Scenario[] }>("/api/scenarios", controller.signal),
    ]).then(([result, choices]) => {
      if (controller.signal.aborted) return;
      setData(result);
      // Reports support the three exercise windows and the explicit WeatherNext mode.
      setScenarios(choices.scenarios.filter(item => ["baseline", "heavy-rain", "peak", "weathernext"].includes(item.id)));
      if (!result.rows.some(row => row.property_id === site)) setSite(result.rows[0]?.property_id || "");
    }).catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active, selection]);
  const data = loadedData && (selection === "compare" ? !!loadedData.scenarios : loadedData.scenario?.id === selection) ? loadedData : null;
  const selected = data?.rows.find(row => row.property_id === site);
  const windows = data?.scenarios || (data?.scenario && data.summary ? [{ scenario: data.scenario, summary: data.summary }] : []);
  const title = preset === "compare" ? "Compare exercise windows" : preset === "site" ? "Explain a site" : "Scenario overview";
  const exportUrl = `/api/exports?scenario=${encodeURIComponent(selection)}`;
  return <section className="reports-page" id="reports" hidden={!active} aria-labelledby="reports-heading">
    <header><p className="report-eyebrow">MIAMI-DADE · FIPS 12086</p><h1 id="reports-heading">Reports &amp; exports</h1><p>Read a report, print a summary, or explore the same data in Power BI or Tableau.</p></header>
    <div className="report-controls">
      <label>Report<select value={preset} onChange={event => setPreset(event.target.value as Preset)}><option value="overview">Scenario overview</option><option value="compare">Compare exercise windows</option><option value="site">Explain a site</option></select></label>
      {preset !== "compare" && <label>Time window<select value={scenario} onChange={event => setScenario(event.target.value)}><option value="baseline">Exercise hour 0</option>{scenarios.filter(item => item.id !== "baseline").map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>}
      {preset === "site" && data && <label>Fictional site<select value={site} onChange={event => setSite(event.target.value)}>{data.rows.map(row => <option key={row.property_id} value={row.property_id}>{row.label}</option>)}</select></label>}
      <button type="button" disabled={!data || loading} onClick={() => window.print()}>Print / Save as PDF</button>
    </div>
    {loading && <p role="status">Loading report…</p>}
    {error && <p role="alert" className="report-error">Report unavailable: {error}. No substitute data is shown. Choose another time window or reopen Reports to retry.</p>}
    {data && !loading && <>
      <article className="report-document" aria-label={title}>
        <header><span className="report-mode">{data.mode === "mixed_forecast_demo" ? "MIXED DEMO" : "SYNTHETIC DEMO"}</span><h2>{title}</h2>
          {preset === "site" && selected && <p>{selected.label}</p>}
          <p>Generated {time(data.generated_at)}</p>
          {windows.map(window => <p key={window.scenario.id}>{window.scenario.label}: {time(window.scenario.valid_from)} – {time(window.scenario.valid_to)}</p>)}
        </header>
        <aside className="report-notice">{data.notice} These scores are an illustrative heuristic, not trained AI. Lower relative does not mean safe. These fictional points do not represent countywide coverage.</aside>
        {preset === "overview" && data.summary && <>
          <BandSummary summary={data.summary} label={data.scenario!.label} />
          <section className="report-block"><h3>Ranked fictional sites · relative score / 100</h3>
            <BarChart title="Ranked relative site scores; unknown sites have no bar" max={100} rows={data.rows.map(row => ({ key: row.property_id, label: row.label, value: row.score, color: colors[row.band] }))} />
            <ScoreTable rows={data.rows} />
          </section>
        </>}
        {preset === "compare" && <>
          <section className="report-block"><h3>How scores change through the exercise</h3><p>Three synthetic six-hour windows, not a historical storm or observed weather. Unknown scores have no bar.</p>
            <div className="report-table-wrap"><table><caption>Site scores / 100 across exercise windows</caption><thead><tr><th scope="col">Fictional site</th>{windows.map(item => <th key={item.scenario.id} scope="col">{item.scenario.label}</th>)}</tr></thead>
              <tbody>{data.rows.filter(row => row.scenario === "baseline").map(row => <tr key={row.property_id}><th scope="row">{row.label}</th>{windows.map(item => <td key={item.scenario.id}>{number(data.rows.find(value => value.property_id === row.property_id && value.scenario === item.scenario.id)?.score ?? null)}</td>)}</tr>)}</tbody></table></div>
          </section>
          {windows.map(item => <section className="report-block" key={item.scenario.id}>
            <h3>{item.scenario.label} · relative site scores / 100</h3>
            <BarChart title={`${item.scenario.label}: relative site scores`} max={100} rows={data.rows.filter(row => row.scenario === item.scenario.id).map(row => ({ key: row.property_id, label: row.label, value: row.score, color: colors[row.band] }))} />
            <BandSummary summary={item.summary} label={item.scenario.label} />
          </section>)}
        </>}
        {preset === "site" && selected && <section className="report-block"><h3>{selected.label} · {number(selected.score)}{selected.score !== null ? " / 100" : ""} · {labels[selected.band]}</h3>
          <ScoreTable rows={[selected]} />
          {selected.factors.length > 0 ? <>
            <BarChart title="Factor contributions in relative score points" max={100} rows={selected.factors.map(factor => ({ key: factor.name, label: labels[factor.name], value: factor.contribution, color: "#347e73" }))} />
            <table><caption>Factors behind the illustrative score</caption><thead><tr><th scope="col">Input</th><th scope="col">Value</th><th scope="col">Weight</th><th scope="col">Score points</th></tr></thead><tbody>{selected.factors.map(factor => <tr key={factor.name}><th scope="row">{labels[factor.name]}</th><td>{factor.value}</td><td>{factor.weight * 100}%</td><td>{number(factor.contribution)}</td></tr>)}</tbody></table>
            <p>Illustrative weights and thresholds. Rounded contributions may differ slightly from the rounded total.</p>
          </> : <p>No factor contributions are assigned while required inputs are missing or stale. An unknown score is not a low score.</p>}
          <p>Model: {selected.model_version} · Input status: {selected.data_status.replaceAll("_", " ")}{selected.available_hours !== null && ` · Hourly rainfall coverage: ${selected.available_hours}/6`}.</p>
        </section>}
        <footer className="report-sources"><h3>Sources and limitations</h3><p>{data.provenance}</p>
          {data.forecast && <><p>Forecast status: {data.forecast.status}. Source: {data.forecast.source_table}.</p><p>Initialized {time(data.forecast.init_time)} · Imported {time(data.forecast.retrieved_at)}.</p><p>Native resolution: {data.forecast.native_resolution} · {data.forecast.statistic}. Rainfall is mm per six-hour window; native hourly means are summed once. Other site, terrain, FEMA and gauge inputs remain fictional. Stale or incomplete rainfall stays unknown.</p></>}
          <p>Official NWS alerts are not connected. This is not an all-clear. Follow <a href="https://www.weather.gov/mfl/" target="_blank" rel="noopener noreferrer">NWS Miami and local emergency guidance</a>. No notifications are sent.</p>
          <p className="report-map-link"><a href="#map-overview" onClick={() => {
            const control = document.getElementById("scenario") as HTMLSelectElement | null;
            if (control && !control.disabled) { control.value = preset === "compare" ? "baseline" : scenario; control.dispatchEvent(new Event("change", { bubbles: true })); }
          }}>Open interactive Quasar map</a><span className="report-print-map"> · Interactive map: {window.location.origin}/#map-overview</span></p>
        </footer>
      </article>
      <section className="report-downloads" aria-label="Download report data"><h2>Use the same data in your analysis</h2><p>Downloads include all sites for the selected window, or all 18 site/window rows for comparison. The site selector changes the explanation only.</p>
        <div><a download href={`${exportUrl}&format=csv`}>Download CSV</a><a download href={`${exportUrl}&format=geojson`}>Download GeoJSON</a><a download href={`${exportUrl}&format=zip`}>Download BI bundle</a></div>
        <p>The BI bundle adds factor rows, metadata and import instructions. Refresh manually by replacing the bundle together. Blank numeric cells mean unknown or not applicable; keep status fields and do not replace blanks with zero.</p>
        <p>Power BI: compare scenarios and completeness. Tableau: map fictional sites and unknowns. Relate factor data using both site and scenario; joining factors can repeat site counts.</p>
      </section>
    </>}
  </section>;
}
