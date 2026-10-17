import { useEffect, useState } from "react";
import { ArrowDownToLine, ArrowUpRight, Info, RefreshCw, Search } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ChartGroup6 } from "@/components/chart-group6";
import { DashboardStats, DashboardTable } from "@/components/dashboard2-data";
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
const time = (value: string) => new Date(value).toLocaleString("en-US", { timeZone: "America/Chicago", dateStyle: "medium", timeStyle: "short" }) + " Central time";

async function get<T,>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function SourceCard({ title, source }: { title: string; source: SourceStatus }) {
  return <Card>
    <CardHeader>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <CardTitle role="heading" aria-level={3}>{title}</CardTitle>
        <Badge variant={source.status === "invalid" || source.status === "unavailable" ? "destructive" : "secondary"} data-status={source.status}>{labels[source.status] || source.status}</Badge>
      </div>
      {source.message && <CardDescription>{source.message}</CardDescription>}
    </CardHeader>
    {(source.source_table || source.init_time || source.retrieved_at || source.valid_from || source.valid_to || source.native_resolution) && <CardContent>
      {source.source_table && <p className="break-all text-xs text-muted-foreground">{source.source_table}</p>}
      <dl className="mt-3 grid gap-3 text-xs">
        {source.init_time && <div><dt className="text-muted-foreground">Initialized</dt><dd>{time(source.init_time)}</dd></div>}
        {source.retrieved_at && <div><dt className="text-muted-foreground">Imported</dt><dd>{time(source.retrieved_at)}</dd></div>}
        {source.valid_from && <div><dt className="text-muted-foreground">Valid from</dt><dd>{time(source.valid_from)}</dd></div>}
        {source.valid_to && <div><dt className="text-muted-foreground">Valid to</dt><dd>{time(source.valid_to)}</dd></div>}
        {source.native_resolution && <div><dt className="text-muted-foreground">Native grid</dt><dd>{source.native_resolution} · {source.statistic?.replaceAll("_", " ")}</dd></div>}
      </dl>
    </CardContent>}
  </Card>;
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
  const selectedWeather = data?.forecast || weather;

  // Dashboard 2 supplies the content layout, KPI strip and table panels;
  // Chart Group 6 supplies the donut/bar pair. No duplicate navigation shell.
  return <section className="data-page w-full flex-1 space-y-4 overflow-auto bg-background p-3 sm:space-y-6 sm:p-4 md:p-6" id="data" hidden={!active} aria-labelledby="data-heading" aria-busy={loading}>
    <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">Okaloosa County · FIPS 12091</p>
        <h1 id="data-heading" className="text-2xl font-semibold tracking-tight">Data</h1>
        <p className="text-sm text-muted-foreground">The inputs, patterns, and gaps behind this exercise.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <Select value={scenario} onValueChange={setScenario}>
          <SelectTrigger aria-label="Time window" className="h-8 w-[220px] text-xs sm:h-9 sm:text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="baseline">Exercise hour 0</SelectItem>{choices.filter(item => item.id !== "baseline").map(item => <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>)}
            {scenario !== "baseline" && !choices.some(item => item.id === scenario) && <SelectItem value={scenario}>{scenario} · availability unknown</SelectItem>}
          </SelectContent>
        </Select>
        <Button type="button" variant="outline" size="sm" className="h-8 gap-2 sm:h-9" onClick={() => setRevision(value => value + 1)}><RefreshCw className="size-4" aria-hidden="true" />Recheck data</Button>
        <Button variant="outline" size="sm" className="h-8 gap-2 sm:h-9" asChild><a href="#reports">Reports &amp; exports <ArrowUpRight className="size-4" aria-hidden="true" /></a></Button>
      </div>
    </header>
    {choiceError && <p role="status" className="text-sm text-muted-foreground">{choiceError}</p>}
    {loading && <div role="status" className="space-y-4"><span className="sr-only">Loading selected window…</span><Skeleton className="h-36 w-full rounded-xl" /><div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-72 rounded-xl" /><Skeleton className="h-72 rounded-xl" /></div></div>}
    {error && <Alert variant="destructive"><Info aria-hidden="true" /><AlertTitle>Data unavailable</AlertTitle><AlertDescription>{error}. Recheck data or choose another time window. No substitute values are shown.</AlertDescription></Alert>}
    {data && summary && <>
      <Alert role="note"><Info aria-hidden="true" /><AlertTitle>{data.mode === "mixed_forecast_demo" ? "MIXED DEMO" : "SYNTHETIC DEMO"}</AlertTitle><AlertDescription>{data.notice} The score is an illustrative heuristic, not trained AI. These fictional sites do not represent countywide coverage.</AlertDescription></Alert>
      <div className="flex flex-col gap-3 text-xs text-muted-foreground sm:flex-row sm:items-start sm:justify-between">
        <p><strong className="font-medium text-foreground">{data.scenario!.label}</strong><br />{time(data.scenario!.valid_from)} – {time(data.scenario!.valid_to)}</p>
        <p>Summary generated {time(data.generated_at)}<br />This does not refresh the underlying forecast.</p>
      </div>
      <DashboardStats summary={summary} />
      <ChartGroup6
        bands={bands.map(key => ({ name: labels[key], value: summary.bands[key] || 0, fill: colors[key] }))}
        rainfall={rows.map(row => ({ name: row.label.replace(" exercise site", ""), value: row.rainfall_6h_mm }))}
        rainfallDescription={`Millimeters per six-hour window · ${data.forecast ? "Imported ensemble mean" : "Synthetic rainfall"}.`}
      />
      <p className="text-xs text-muted-foreground">{data.forecast ? `Native forecast grid: ${data.forecast.native_resolution}. Site assignment does not increase forecast resolution.` : "The same invented rainfall total is applied to every site in each exercise window."} Exact rainfall values appear in the site table.</p>
      <DashboardTable title="Required input coverage" footer="One missing required input prevents scoring. Availability does not establish source quality or validation. H3 groups occupied sites for display; it does not improve rainfall or terrain resolution.">
        <Table>
          <TableCaption className="sr-only">Required input availability by factor</TableCaption>
          <TableHeader><TableRow className="bg-muted/50 hover:bg-muted/50"><TableHead scope="col">Input</TableHead><TableHead scope="col">Available</TableHead><TableHead scope="col">Missing / stale</TableHead><TableHead scope="col">Origin</TableHead></TableRow></TableHeader>
          <TableBody>{inputs.map(key => {
            const missing = rows.filter(row => row.missing.includes(key)).length;
            const available = rows.length - missing;
            return <TableRow key={key}><TableCell className="font-medium">{labels[key]}</TableCell><TableCell><div className="flex items-center gap-3"><meter min={0} max={Math.max(rows.length, 1)} value={available} aria-label={`${labels[key]} available sites`} className="h-2 w-20 accent-primary" />{available}/{rows.length}</div></TableCell><TableCell>{missing}</TableCell><TableCell>{key === "rainfall_6h_mm" && data.forecast ? "Imported forecast" : "Fictional"}</TableCell></TableRow>;
          })}</TableBody>
        </Table>
      </DashboardTable>
      <DashboardTable id="data-explorer" title="Explore the site data" count={`${filtered.length} of ${rows.length} sites`} controls={<>
        <div className="relative flex-1 sm:flex-none">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground sm:size-5" aria-hidden="true" />
          <Input type="search" aria-label="Find a fictional site" autoComplete="off" value={search} onChange={event => setSearch(event.target.value)} placeholder="Site name or ID" className="h-8 w-full pl-9 text-sm sm:h-9 sm:w-[160px] sm:pl-10 lg:w-[200px]" />
        </div>
        <Select value={band} onValueChange={setBand}>
          <SelectTrigger className="h-8 w-[120px] text-xs sm:h-9 sm:w-[140px] sm:text-sm" aria-label="Score band"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="all">All bands</SelectItem>{bands.map(key => <SelectItem key={key} value={key}>{labels[key]}</SelectItem>)}</SelectContent>
        </Select>
        <Button variant="outline" size="sm" className="h-8 gap-1.5 sm:h-9 sm:gap-2" asChild><a download href={`/api/exports?scenario=${encodeURIComponent(scenario)}&format=csv`}><ArrowDownToLine className="size-4" aria-hidden="true" />Download window CSV</a></Button>
      </>} footer="Filters affect this table only. Charts, summary, and CSV include the entire selected window. Blank numeric cells in the CSV mean unknown or not applicable, never zero.">
        <Table>
          <TableCaption>Selected window · fictional site values from the shared application pipeline</TableCaption>
          <TableHeader><TableRow className="bg-muted/50 hover:bg-muted/50"><TableHead scope="col">Fictional site</TableHead><TableHead scope="col">Score / 100</TableHead><TableHead scope="col">Band</TableHead><TableHead scope="col">Rainfall (mm / 6h)</TableHead><TableHead scope="col">Input gaps</TableHead><TableHead scope="col">Rainfall status</TableHead></TableRow></TableHeader>
          <TableBody>{filtered.map(row => <TableRow key={row.property_id}>
            <TableCell className="text-xs font-medium sm:text-sm">{row.label}<span className="block text-xs font-normal text-muted-foreground">{row.property_id}</span></TableCell>
            <TableCell className="tabular-nums">{number(row.score)}</TableCell><TableCell><Badge variant="outline" style={{ color: colors[row.band] }}>{labels[row.band]}</Badge></TableCell>
            <TableCell className="tabular-nums">{number(row.rainfall_6h_mm)}</TableCell><TableCell>{row.missing.map(key => labels[key] || key).join(", ") || "None"}</TableCell>
            <TableCell>{data.forecast ? <>{labels[row.forecast_status] || row.forecast_status}{row.available_hours !== null && <span className="block text-xs text-muted-foreground">{row.available_hours}/6 hourly inputs</span>}</> : "Synthetic"}</TableCell>
          </TableRow>)}{!filtered.length && <TableRow><TableCell colSpan={6} className="h-24 text-center text-sm text-muted-foreground">No sites match these filters.</TableCell></TableRow>}</TableBody>
        </Table>
      </DashboardTable>
    </>}
    <section className="space-y-4" aria-labelledby="data-sources-heading">
      <div className="space-y-1"><h2 id="data-sources-heading" className="text-base font-medium">Source readiness</h2><p className="text-sm text-muted-foreground">Access, an imported file, and a fresh forecast are separate states.</p></div>
      <div className="grid gap-4 lg:grid-cols-3">
        <SourceCard title="WeatherNext 3 snapshot" source={selectedWeather} />
        <SourceCard title="Official NWS alerts" source={official} />
        <SourceCard title="Site, terrain, FEMA & gauge inputs" source={{ status: "synthetic", message: "The scoring catalog uses fictional site attributes and gauge margins. No real parcel inventory, terrain sampling, FEMA join, or observed gauge feed is connected to these scores." }} />
      </div>
      <p className="text-xs text-muted-foreground">Rechecking reads the configured local snapshot. It does not query BigQuery. Stale or incomplete rainfall remains unknown. Official feed failures never mean no active alerts.</p>
    </section>
    <footer className="space-y-2 border-t pt-4 text-xs text-muted-foreground">{data && <p>{data.provenance}</p>}<p>Unvalidated estimates supplement official guidance. Follow <a className="underline underline-offset-4" href="https://www.weather.gov/mob/" target="_blank" rel="noopener noreferrer">NWS Mobile/Pensacola and local emergency guidance</a>. No notifications are sent.</p></footer>
  </section>;
}
