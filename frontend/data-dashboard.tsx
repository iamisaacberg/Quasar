import { useEffect, useState } from "react";
import { ArrowDownToLine, ArrowUpRight, Database, RefreshCw } from "lucide-react";
import type { Report, Scenario } from "./reports";
import "./data-dashboard.css";

type SourceStatus = {
  status: string; message?: string; source_table?: string; init_time?: string;
  retrieved_at?: string; valid_from?: string; valid_to?: string;
  native_resolution?: string; statistic?: string;
};
const bands = ["lower_relative", "moderate", "elevated", "unknown"];
const labels: Record<string, string> = {
  lower_relative: "Lower relative", moderate: "Moderate", elevated: "Elevated", unknown: "Unknown",
  rainfall_6h_mm: "Rainfall", elevation_m: "Terrain elevation", fema_zone: "FEMA zone",
  waterway_distance_m: "Waterway distance", gauge_margin_m: "Gauge margin",
  ready: "Ready", incomplete: "Incomplete", stale: "Stale", invalid: "Invalid",
  not_configured: "Not configured", not_connected: "Not connected", unavailable: "Unavailable", checking: "Checking…", synthetic: "Fictional",
};
const colors: Record<string, string> = { lower_relative: "#347e73", moderate: "#a87812", elevated: "#b64d36", unknown: "#747c89" };
const inputs = ["rainfall_6h_mm", "elevation_m", "fema_zone", "waterway_distance_m", "gauge_margin_m"];
const number = (value: number | null) => value === null ? "Unknown" : value.toLocaleString("en-US", { maximumFractionDigits: 2 });
const time = (value: string) => new Date(value).toLocaleString("en-US", { timeZone: "America/New_York", dateStyle: "medium", timeStyle: "short" }) + " Miami time";

async function get<T,>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function Bars({ title, rows, max }: { title: string; rows: { id: string; label: string; value: number | null; color: string }[]; max: number }) {
  return <div className="data-bars" role="img" aria-label={`${title}. ${rows.map(row => `${row.label}: ${number(row.value)}`).join("; ")}. Exact values are also in the table below.`}>
    {rows.map(row => <div className="data-bar-row" key={row.id} aria-hidden="true">
      <span>{row.label}</span><div className="data-bar-track">{row.value !== null && <span style={{ width: `${row.value / Math.max(max, 1) * 100}%`, background: row.color }} />}</div><strong>{number(row.value)}</strong>
    </div>)}
    <div className="data-axis" aria-hidden="true"><span>0</span><span>{number(max)}</span></div>
  </div>;
}

function SourceCard({ title, source }: { title: string; source: SourceStatus }) {
  return <article className="data-source"><div className="data-card-heading"><h3>{title}</h3><span className="data-status" data-status={source.status}>{labels[source.status] || source.status}</span></div>
    {source.message && <p>{source.message}</p>}
    {source.source_table && <p className="data-source-id">{source.source_table}</p>}
    <dl>
      {source.init_time && <><dt>Initialized</dt><dd>{time(source.init_time)}</dd></>}
      {source.retrieved_at && <><dt>Imported</dt><dd>{time(source.retrieved_at)}</dd></>}
      {source.valid_from && <><dt>Valid from</dt><dd>{time(source.valid_from)}</dd></>}
      {source.valid_to && <><dt>Valid to</dt><dd>{time(source.valid_to)}</dd></>}
      {source.native_resolution && <><dt>Native grid</dt><dd>{source.native_resolution} · {source.statistic?.replaceAll("_", " ")}</dd></>}
    </dl>
  </article>;
}

export function DataDashboard({ active }: { active: boolean }) {
  const [scenario, setScenario] = useState("baseline");
  const [choices, setChoices] = useState<Scenario[]>([]);
  const [loaded, setLoaded] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [weather, setWeather] = useState<SourceStatus>({ status: "checking" });
  const [official, setOfficial] = useState<SourceStatus>({ status: "checking" });
  const [choiceError, setChoiceError] = useState("");
  const [search, setSearch] = useState("");
  const [band, setBand] = useState("all");

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setWeather({ status: "checking" }); setOfficial({ status: "checking" }); setChoiceError("");
    // Source failures are independent: they never remove available exercise data.
    void get<{ scenarios: Scenario[] }>("/api/scenarios", controller.signal).then(data => {
      if (!controller.signal.aborted) setChoices(data.scenarios.filter(item => ["baseline", "heavy-rain", "peak", "weathernext"].includes(item.id)));
    }).catch(() => { if (!controller.signal.aborted) { setChoices([]); setChoiceError("Additional time windows unavailable. Recheck data to retry."); } });
    void get<SourceStatus>("/api/weather/status", controller.signal).then(data => {
      if (!controller.signal.aborted) setWeather(data);
    }).catch(() => { if (!controller.signal.aborted) setWeather({ status: "unavailable", message: "Could not check the imported forecast. No live connection is implied." }); });
    void get<SourceStatus>("/api/official-alerts", controller.signal).then(data => {
      if (!controller.signal.aborted) setOfficial(data);
    }).catch(() => { if (!controller.signal.aborted) setOfficial({ status: "unavailable", message: "Official feed status unavailable. This is not an all-clear." }); });
    return () => controller.abort();
  }, [active, revision]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true); setLoaded(null); setError("");
    void get<Report>(`/api/reports?scenario=${encodeURIComponent(scenario)}`, controller.signal).then(data => {
      if (!controller.signal.aborted) setLoaded(data);
    }).catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active, scenario, revision]);

  // Never display a previous window under a new selection while its request starts.
  const data = !loading && loaded?.scenario?.id === scenario ? loaded : null;
  const summary = data?.summary;
  const rows = data?.rows || [];
  const filtered = rows.filter(row => (band === "all" || row.band === band) && `${row.label} ${row.property_id}`.toLowerCase().includes(search.trim().toLowerCase()));
  const rainfallMax = Math.max(1, ...rows.flatMap(row => row.rainfall_6h_mm === null ? [] : [row.rainfall_6h_mm]));
  const selectedWeather = data?.forecast || weather;

  return <section className="data-page" id="data" hidden={!active} aria-labelledby="data-heading">
    <header className="data-page-heading"><div><p className="data-eyebrow"><Database aria-hidden="true" />MIAMI-DADE · FIPS 12086</p><h1 id="data-heading">Data</h1><p>The inputs, patterns, and gaps behind this exercise.</p></div><a className="data-link" href="#reports">Reports &amp; exports <ArrowUpRight aria-hidden="true" /></a></header>
    <div className="data-toolbar"><label>Time window<select value={scenario} onChange={event => setScenario(event.target.value)}>
      <option value="baseline">Exercise hour 0</option>{choices.filter(item => item.id !== "baseline").map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      {scenario !== "baseline" && !choices.some(item => item.id === scenario) && <option value={scenario}>{scenario} · availability unknown</option>}
    </select></label><button type="button" onClick={() => setRevision(value => value + 1)}><RefreshCw aria-hidden="true" />Recheck data</button><span>Reads local data; no cloud import.</span></div>
    {choiceError && <p role="status" className="data-muted">{choiceError}</p>}
    {loading && <p role="status" className="data-empty">Loading selected window…</p>}
    {error && <p role="alert" className="data-error">Data unavailable: {error}. Recheck data or choose another time window. No substitute values are shown.</p>}
    {data && summary && <>
      <aside className="data-notice"><span className="data-mode">{data.mode === "mixed_forecast_demo" ? "MIXED DEMO" : "SYNTHETIC DEMO"}</span><p>{data.notice} The score is an illustrative heuristic, not trained AI. These fictional sites do not represent countywide coverage.</p></aside>
      <div className="data-window"><p><strong>{data.scenario!.label}</strong><br />{time(data.scenario!.valid_from)} – {time(data.scenario!.valid_to)}</p><p>Summary generated {time(data.generated_at)}<br />This does not refresh the underlying forecast.</p></div>
      <section className="data-metrics" aria-label="Selected window summary">
        <article><p>Fictional sites</p><strong>{summary.site_count}</strong><span>{summary.scored_count} scored · {summary.unknown_count} unknown</span></article>
        <article><p>Mean relative score</p><strong>{number(summary.mean_score)}{summary.mean_score !== null && <small> / 100</small>}</strong><span>Excludes unknown scores</span></article>
        <article><p>Elevated scores</p><strong>{summary.bands.elevated || 0}</strong><span>Illustrative score ≥ 65</span></article>
        <article><p>Insufficient data</p><strong>{summary.unknown_count}</strong><span>Missing or stale inputs stay unscored</span></article>
      </section>
      <div className="data-chart-grid">
        <section className="data-card"><h2>Relative score distribution</h2><p>Site counts in the selected window. Lower relative does not mean safe.</p>
          <Bars title="Sites by relative score band" max={summary.site_count} rows={bands.map(key => ({ id: key, label: labels[key], value: summary.bands[key] || 0, color: colors[key] }))} />
          <details><summary>View band counts</summary><table><caption>Sites by relative score band</caption><thead><tr><th scope="col">Band</th><th scope="col">Sites</th></tr></thead><tbody>{bands.map(key => <tr key={key}><th scope="row">{labels[key]}</th><td>{summary.bands[key] || 0}</td></tr>)}</tbody></table></details>
        </section>
        <section className="data-card"><h2>Rainfall by fictional site</h2><p>Millimeters per six-hour window · {data.forecast ? "Imported ensemble mean" : "Synthetic rainfall"}. Unknown values have no bar.</p>
          <Bars title="Six-hour rainfall in millimeters" max={rainfallMax} rows={rows.map(row => ({ id: row.property_id, label: row.label.replace(" exercise site", ""), value: row.rainfall_6h_mm, color: "#347e73" }))} />
          <p className="data-muted">{data.forecast ? `Native forecast grid: ${data.forecast.native_resolution}. Site assignment does not increase forecast resolution.` : "The same invented rainfall total is applied to every site in each exercise window."} Exact values appear in the site table.</p>
        </section>
        <section className="data-card data-coverage"><h2>Required input coverage</h2><p>Available inputs among {summary.site_count} fictional sites. Availability does not establish source quality or validation.</p>
          <table><caption className="sr-only">Required input availability by factor</caption><thead><tr><th scope="col">Input</th><th scope="col">Available</th><th scope="col">Missing / stale</th><th scope="col">Origin</th></tr></thead><tbody>{inputs.map(key => {
            const missing = rows.filter(row => row.missing.includes(key)).length;
            const available = rows.length - missing;
            return <tr key={key}><th scope="row">{labels[key]}</th><td><div className="data-coverage-value"><meter min={0} max={Math.max(rows.length, 1)} value={available} aria-label={`${labels[key]} available sites`} />{available}/{rows.length}</div></td><td>{missing}</td><td>{key === "rainfall_6h_mm" && data.forecast ? "Imported forecast" : "Fictional"}</td></tr>;
          })}</tbody></table><p className="data-muted">One missing required input prevents scoring. H3 groups occupied sites for display; it does not improve rainfall or terrain resolution.</p>
        </section>
      </div>
      <section className="data-card data-explorer"><div className="data-card-heading"><div><h2>Explore the site data</h2><p>Scores and rainfall from the shared application pipeline.</p></div><a className="data-link" download href={`/api/exports?scenario=${encodeURIComponent(scenario)}&format=csv`}><ArrowDownToLine aria-hidden="true" />Download window CSV</a></div>
        <div className="data-filters"><label>Find a fictional site<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Site name or ID" /></label><label>Score band<select value={band} onChange={event => setBand(event.target.value)}><option value="all">All bands</option>{bands.map(key => <option key={key} value={key}>{labels[key]}</option>)}</select></label><p role="status">{filtered.length} of {rows.length} sites</p></div>
        <div className="data-table-wrap"><table><caption>Selected window · fictional site values</caption><thead><tr><th scope="col">Fictional site</th><th scope="col">Score / 100</th><th scope="col">Band</th><th scope="col">Rainfall (mm / 6h)</th><th scope="col">Input gaps</th><th scope="col">Rainfall status</th></tr></thead><tbody>{filtered.map(row => <tr key={row.property_id}><th scope="row">{row.label}<small>{row.property_id}</small></th><td>{number(row.score)}</td><td><span className="data-band" style={{ color: colors[row.band] }}>{labels[row.band]}</span></td><td>{number(row.rainfall_6h_mm)}</td><td>{row.missing.map(key => labels[key] || key).join(", ") || "None"}</td><td>{data.forecast ? <>{labels[row.forecast_status] || row.forecast_status}{row.available_hours !== null && <small>{row.available_hours}/6 hourly inputs</small>}</> : "Synthetic"}</td></tr>)}</tbody></table></div>
        {!filtered.length && <p className="data-empty">No sites match these filters.</p>}
        <p className="data-muted">Filters affect this table only. Charts, summary, and CSV include the entire selected window. Blank numeric cells in the CSV mean unknown or not applicable, never zero.</p>
      </section>
    </>}
    <section className="data-source-section" aria-labelledby="data-sources-heading"><h2 id="data-sources-heading">Source readiness</h2><p>Access, an imported file, and a fresh forecast are separate states.</p><div className="data-source-grid">
      <SourceCard title="WeatherNext 3 snapshot" source={selectedWeather} />
      <SourceCard title="Official NWS alerts" source={official} />
      <SourceCard title="Site, terrain, FEMA & gauge inputs" source={{ status: "synthetic", message: "The scoring catalog uses fictional site attributes and gauge margins. No real parcel inventory, terrain sampling, FEMA join, or observed gauge feed is connected to these scores." }} />
    </div><p className="data-muted">Rechecking reads the configured local snapshot. It does not query BigQuery. Stale or incomplete rainfall remains unknown. Official feed failures never mean no active alerts.</p></section>
    <footer className="data-footer">{data && <p>{data.provenance}</p>}<p>Unvalidated estimates supplement official guidance. Follow <a href="https://www.weather.gov/mfl/" target="_blank" rel="noopener noreferrer">NWS Miami and local emergency guidance</a>. No notifications are sent.</p></footer>
  </section>;
}
