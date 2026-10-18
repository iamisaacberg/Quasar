import { useEffect, useState } from "react";
import { useReplaySelection } from "./lib/replay-selection";
import "./reports.css";

type Row = { native_cell_id: string; rainfall_6h_mm: number | null; available_hours: number; status: string; valid_from: string; valid_to: string };
type Report = { source: string; status: string; message?: string; notice?: string; rows: Row[]; selected_index: number; init_time?: string; retrieved_at?: string; source_table?: string; windows: { at: string; valid_to: string }[] };
const time = (value?: string) => value ? new Date(value).toLocaleString("en-US", { timeZone: "America/Chicago", dateStyle: "medium", timeStyle: "short" }) + " Central" : "Unavailable";

export function Reports({ active }: { active: boolean }) {
  const [frame, selectFrame] = useReplaySelection();
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setError("");
    void fetch(`/api/reports?source=archive&frame=${frame}`, { signal: controller.signal, cache: "no-store" })
      .then(async response => { const body = await response.json(); if (!response.ok) throw new Error(body.error || "Source unavailable"); if (body.source !== "archive") throw new Error("Unexpected forecast source"); return body as Report; })
      .then(body => { if (!controller.signal.aborted) setData(body); })
      .catch((reason: Error) => { if (!controller.signal.aborted) { setData(null); setError(reason.message); } });
    return () => controller.abort();
  }, [active, frame, revision]);
  const current = data?.source === "archive" && data.selected_index === frame && !error ? data : null;
  const exportUrl = current && `/api/exports?source=archive&frame=${current.selected_index}`;
  return <section className="reports-page" id="reports" hidden={!active} aria-labelledby="reports-heading">
    <header><p className="report-eyebrow">ISAIAS · OCTOBER 9, 2026 · OKALOOSA</p><h1 id="reports-heading">Reports &amp; exports</h1><p>The selected Isaias forecast window, with source dates and cell availability.</p></header>
    <div className="report-controls">
      {!!data?.windows?.length && <label>Replay hour<select value={frame} onChange={event => selectFrame(Number(event.target.value))}>{data.windows.map((window, index) => <option key={window.at} value={index}>{time(window.at)}</option>)}</select></label>}
      <button type="button" onClick={() => setRevision(value => value + 1)}>Recheck source</button>
      <button type="button" disabled={!current?.rows.length} onClick={() => window.print()}>Print / Save as PDF</button>
    </div>
    {error && <p role="alert">Archive unavailable: {error}. Recheck the source to try again.</p>}
    {!current && !error && active && <p role="status">Loading the selected Isaias hour…</p>}
    {current && <article className="report-document">
      <h2>Isaias · archived forecast rainfall</h2>
      <p role="status">{current.status.replaceAll("_", " ")} · {current.rows.length} native cells</p><p>{current.message || current.notice}</p>
      {!!current.rows.length && <p><strong>Six-hour forecast window</strong><br />{time(current.rows[0].valid_from)} – {time(current.rows[0].valid_to)}</p>}
      <p>Initialized: {time(current.init_time)} · Imported: {time(current.retrieved_at)}</p><p className="report-source-id">{current.source_table}</p>
      <p>Forecast reconstruction, not observed rainfall. Initialization timing does not establish when a forecast was published. Rainfall is not parcel flood risk, depth or probability. Follow official NWS/local guidance.</p>
      {current.rows.length > 0 && <>
        <div className="report-downloads">{(["csv", "geojson", "zip"] as const).map(format => <a key={format} href={`${exportUrl}&format=${format}`}>Download {format.toUpperCase()}</a>)}</div>
        <div className="report-table-wrap"><table><caption>Native forecast cells · mm / 6h · grid 0.1 degree · ensemble mean</caption><thead><tr><th>Native cell</th><th>Valid from (UTC)</th><th>Valid to (UTC)</th><th>Rainfall · mm / 6h</th><th>Available hours</th><th>Status</th></tr></thead><tbody>{current.rows.map((row, index) => <tr key={row.native_cell_id}><th scope="row">Cell {index + 1}<small className="report-cell-id">{row.native_cell_id}</small></th><td>{row.valid_from}</td><td>{row.valid_to}</td><td>{row.rainfall_6h_mm === null ? "Unknown" : row.rainfall_6h_mm.toFixed(2)}</td><td>{row.available_hours}/6</td><td>{row.status}</td></tr>)}</tbody></table></div>
      </>}
    </article>}
  </section>;
}
