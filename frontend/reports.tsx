import { useEffect, useState } from "react";
import "./reports.css";

type Row = { native_cell_id: string; rainfall_6h_mm: number | null; status: string; available_hours: number; valid_from: string; valid_to: string };
type Report = { source: string; status: string; message?: string; notice?: string; rows: Row[]; selected_index: number; init_time?: string; retrieved_at?: string; source_table?: string; expires_at?: string };

function expireReport(data: Report): Report {
  if (!data.expires_at || Date.parse(data.expires_at) > Date.now()) return data;
  return {...data, status: "stale", rows: data.rows.map(row => ({...row, status: "stale", rainfall_6h_mm: null}))};
}

export function Reports({ active }: { active: boolean }) {
  const [source, setSource] = useState("current");
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setData(null); setError("");
    void fetch(`/api/reports?source=${source}`, { signal: controller.signal, cache: "no-store" })
      .then(async response => { const body = await response.json(); if (!response.ok) throw new Error(body.error || "Source unavailable"); return body as Report; })
      .then(body => { if (!controller.signal.aborted) setData(body); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, [active, source]);
  useEffect(() => {
    if (!active || data?.source !== source || !data.expires_at) return;
    const delay = Date.parse(data.expires_at) - Date.now();
    if (delay <= 0) return;
    const timer = window.setTimeout(() => setData(value => value ? expireReport(value) : null), delay + 1);
    return () => window.clearTimeout(timer);
  }, [active, data?.expires_at, data?.source, source]);
  const current = data?.source === source ? expireReport(data) : null;
  const exportUrl = current && `/api/exports?source=${source}&frame=${current.selected_index}`;
  return <section className="reports-page" id="reports" hidden={!active} aria-labelledby="reports-heading">
    <header><p className="report-eyebrow">OKALOOSA · FIPS 12091</p><h1 id="reports-heading">Reports &amp; exports</h1><p>Native county forecast rainfall with source dates and availability.</p></header>
    <div className="report-controls"><label>Source<select value={source} onChange={event => setSource(event.target.value)}><option value="current">Current county forecast</option><option value="archive">October 9 archived forecast</option></select></label><button type="button" disabled={!current?.rows.length} onClick={() => window.print()}>Print / Save as PDF</button></div>
    {error && <p role="alert">Source unavailable: {error}. No substitute values are shown.</p>}
    {!current && !error && active && <p role="status">Reading imported county source…</p>}
    {current && <article className="report-document">
      <h2>{source === "archive" ? "Archived forecast rainfall" : "Current forecast rainfall"}</h2>
      <p role="status">{current.status} · {current.rows.length} native cells</p><p>{current.message || current.notice}</p>
      <p>Initialized: {current.init_time || "Per-cell archive initialization"} · Imported: {current.retrieved_at || "Unavailable"}</p><p>{current.source_table}</p>
      <p>Forecast rainfall is not observed rain, parcel flood risk, depth or probability. Missing values remain unknown. Follow official NWS/local guidance.</p>
      {current.rows.length > 0 && <>
        <div className="report-downloads">{(["csv", "geojson", "zip"] as const).map(format => <a key={format} href={`${exportUrl}&format=${format}`}>Download {format.toUpperCase()}</a>)}</div>
        <div className="table-wrap"><table><caption>Native forecast cells · mm / 6h · grid 0.1 degree · ensemble mean</caption><thead><tr><th>Native cell</th><th>Valid from (UTC)</th><th>Valid to (UTC)</th><th>Rainfall · mm / 6h</th><th>Available hours</th><th>Status</th></tr></thead><tbody>{current.rows.map(row => <tr key={row.native_cell_id}><th scope="row">{row.native_cell_id}</th><td>{row.valid_from}</td><td>{row.valid_to}</td><td>{row.rainfall_6h_mm === null ? "Unknown" : row.rainfall_6h_mm.toFixed(2)}</td><td>{row.available_hours}/6</td><td>{row.status}</td></tr>)}</tbody></table></div>
      </>}
    </article>}
  </section>;
}
