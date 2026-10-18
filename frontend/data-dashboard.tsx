import { useEffect, useState } from "react";
import { ArrowDownToLine, Info, RefreshCw, Search } from "lucide-react";
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
import "./data-dashboard.css";

type SourceStatus = {
  status: string; message?: string; source_table?: string; source_url?: string; init_time?: string;
  retrieved_at?: string; native_resolution?: string; statistic?: string;
};
type Cell = { native_cell_id: string; rainfall_6h_mm: number | null; available_hours: number; status: string };
type Weather = SourceStatus & {
  county_fips: string; generated_at: string; default_index: number; expires_at?: string;
  frames: { at: string; valid_to: string; rows: Cell[] }[];
};
type Parcels = SourceStatus & { county_fips?: string; source_mode?: string; parcel_count?: number | null; crs?: string };
const labels: Record<string, string> = {
  ready: "Ready", incomplete: "Incomplete", stale: "Stale", invalid: "Invalid",
  not_configured: "Not configured", not_connected: "Not connected", unavailable: "Unavailable", checking: "Checking…",
};
const statuses = ["ready", "incomplete", "stale", "unavailable"];
const colors: Record<string, string> = { ready: "#347e73", incomplete: "#a87812", stale: "#b64d36", unavailable: "#747c89" };
const number = (value: number | null) => value === null ? "Unknown" : value.toLocaleString("en-US", { maximumFractionDigits: 2 });
const time = (value: string) => new Date(value).toLocaleString("en-US", { timeZone: "America/Chicago", dateStyle: "medium", timeStyle: "short" }) + " Central time";

function csvDownload(weather: Weather, frame: Weather["frames"][number], rows: Cell[]) {
  const columns = ["county_fips", "native_cell_id", "valid_from", "valid_to", "rainfall_6h_mm", "units", "status", "available_hours", "init_time", "retrieved_at", "native_resolution", "statistic", "source_table"];
  const lines = [columns, ...rows.map(row => ["12091", row.native_cell_id, frame.at, frame.valid_to, row.rainfall_6h_mm, "mm / 6h", row.status, row.available_hours, weather.init_time, weather.retrieved_at, weather.native_resolution, weather.statistic, weather.source_table])];
  return "data:text/csv;charset=utf-8," + encodeURIComponent(lines.map(line => line.map(value => value == null ? "" : `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n"));
}

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
    <CardContent>
      {(source.source_table || source.source_url) && <p className="break-all text-xs text-muted-foreground">{source.source_table || source.source_url}</p>}
      <dl className="mt-3 grid gap-3 text-xs">
        {source.init_time && <div><dt className="text-muted-foreground">Initialized</dt><dd>{time(source.init_time)}</dd></div>}
        {source.retrieved_at && <div><dt className="text-muted-foreground">Retrieved</dt><dd>{time(source.retrieved_at)}</dd></div>}
        {source.native_resolution && <div><dt className="text-muted-foreground">Native grid</dt><dd>{source.native_resolution} · {source.statistic?.replaceAll("_", " ")}</dd></div>}
      </dl>
    </CardContent>
  </Card>;
}

export function DataDashboard({ active }: { active: boolean }) {
  const [selected, setSelected] = useState("");
  const [weather, setWeather] = useState<Weather | null>(null);
  const [parcels, setParcels] = useState<Parcels>({ status: "checking" });
  const [official, setOfficial] = useState<SourceStatus>({ status: "checking" });
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true); setWeather(null); setParcels({ status: "checking" }); setOfficial({ status: "checking" });
    void get<Weather>("/api/data/weather", controller.signal).then(data => {
      if (data.county_fips !== "12091") throw new Error("Wrong forecast county");
      if (!controller.signal.aborted) setWeather(data);
    }).catch(() => {
      if (!controller.signal.aborted) setWeather({ status: "unavailable", county_fips: "12091", generated_at: "", frames: [], default_index: 0, message: "Could not read the county forecast. No substitute values are shown." });
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    void get<Parcels>("/api/parcels/manifest", controller.signal).then(data => {
      if (data.county_fips !== "12091") throw new Error("Wrong parcel county");
      if (!controller.signal.aborted) setParcels(data);
    }).catch(() => { if (!controller.signal.aborted) setParcels({ status: "unavailable", message: "Could not verify the parcel inventory. Counts and inputs remain unknown." }); });
    void get<SourceStatus>("/api/official-alerts", controller.signal).then(data => {
      if (!controller.signal.aborted) setOfficial(data);
    }).catch(() => { if (!controller.signal.aborted) setOfficial({ status: "unavailable", message: "Official feed status unavailable. This is not an all-clear." }); });
    return () => controller.abort();
  }, [active, revision]);

  useEffect(() => {
    if (!active || !weather?.expires_at) return;
    const delay = Date.parse(weather.expires_at) - Date.now();
    if (delay <= 0) return;
    const timer = setTimeout(() => setRevision(value => value + 1), delay);
    return () => clearTimeout(timer);
  }, [active, weather]);

  const expired = !!weather?.expires_at && Date.parse(weather.expires_at) <= Date.now();
  const source = weather ? { ...weather, status: expired ? "stale" : weather.status } : { status: "checking" };
  const frame = weather?.frames.find(item => item.at === selected) || weather?.frames[weather.default_index];
  const rows = (frame?.rows || []).map(row => expired ? { ...row, status: "stale", rainfall_6h_mm: null } : row);
  const available = rows.filter(row => row.status === "ready" && row.rainfall_6h_mm !== null);
  const filtered = rows.filter(row => (status === "all" || row.status === status) && row.native_cell_id.toLowerCase().includes(search.trim().toLowerCase()));
  const parcelCount = parcels.status === "ready" && parcels.source_mode === "indexed" && typeof parcels.parcel_count === "number" ? parcels.parcel_count : null;

  return <section className="data-page w-full flex-1 space-y-4 overflow-auto bg-background p-3 sm:space-y-6 sm:p-4 md:p-6" id="data" hidden={!active} aria-labelledby="data-heading" aria-busy={loading}>
    <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">Okaloosa County · FIPS 12091</p>
        <h1 id="data-heading" className="text-2xl font-semibold tracking-tight">Data</h1>
        <p className="text-sm text-muted-foreground">Imported county forecasts and verified parcel geometry.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {!!weather?.frames.length && <Select value={frame?.at} onValueChange={setSelected}>
          <SelectTrigger aria-label="Forecast window" className="h-8 w-[260px] text-xs sm:h-9 sm:text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>{weather.frames.map(item => <SelectItem key={item.at} value={item.at}>{time(item.at)}</SelectItem>)}</SelectContent>
        </Select>}
        <Button type="button" variant="outline" size="sm" className="h-8 gap-2 sm:h-9" onClick={() => setRevision(value => value + 1)}><RefreshCw className="size-4" aria-hidden="true" />Recheck data</Button>
      </div>
    </header>
    {loading && <div role="status" className="space-y-4"><span className="sr-only">Loading county data…</span><Skeleton className="h-36 w-full rounded-xl" /></div>}
    {!loading && <>
      <Alert role="note"><Info aria-hidden="true" /><AlertTitle>Real source data · parcel risk unknown</AlertTitle><AlertDescription>Native forecast rainfall and county-validated parcel geometry are descriptive inputs. Parcel flood scores, observed gauge conditions and model validation remain unavailable.</AlertDescription></Alert>
      {weather && !frame && <Alert><Info aria-hidden="true" /><AlertTitle>County rainfall unavailable</AlertTitle><AlertDescription>{weather.message} Recheck after a county forecast has been imported.</AlertDescription></Alert>}
      {frame && <div className="flex flex-col gap-3 text-xs text-muted-foreground sm:flex-row sm:items-start sm:justify-between">
        <p><strong className="font-medium text-foreground">Selected forecast window</strong><br />{time(frame.at)} – {time(frame.valid_to)}</p>
        <p>Summary generated {weather?.generated_at && time(weather.generated_at)}<br />Rechecking does not refresh the underlying forecast.</p>
      </div>}
      <DashboardStats parcelCount={parcelCount} cellCount={frame ? rows.length : null} availableCount={frame ? available.length : null} meanRainfall={available.length ? available.reduce((sum, row) => sum + row.rainfall_6h_mm!, 0) / available.length : null} />
      {frame && <>
        <ChartGroup6 bands={statuses.map(key => ({ name: labels[key], value: rows.filter(row => row.status === key).length, fill: colors[key] }))}
          rainfall={rows.map((row, index) => ({ name: `Cell ${index + 1}`, value: row.rainfall_6h_mm }))}
          rainfallDescription="Imported ensemble mean · millimeters per six-hour window." />
        <p className="text-xs text-muted-foreground">Native grid: {weather?.native_resolution}. Cells may extend beyond the county. Mean rainfall is an unweighted cell average, not a county area average. H3 does not increase forecast resolution.</p>
        <DashboardTable id="data-explorer" title="Explore native forecast data" count={`${filtered.length} of ${rows.length} cells`} controls={<>
          <div className="relative flex-1 sm:flex-none"><Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input type="search" aria-label="Find a native forecast cell" autoComplete="off" value={search} onChange={event => setSearch(event.target.value)} placeholder="Native cell ID" className="h-8 w-full pl-9 text-sm sm:h-9 sm:w-[200px]" /></div>
          <Select value={status} onValueChange={setStatus}><SelectTrigger className="h-8 w-[140px] text-xs sm:h-9 sm:text-sm" aria-label="Rainfall status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All statuses</SelectItem>{statuses.map(key => <SelectItem key={key} value={key}>{labels[key]}</SelectItem>)}</SelectContent></Select>
          <Button variant="outline" size="sm" className="h-8 gap-2 sm:h-9" asChild><a download="quasar-native-forecast.csv" href={csvDownload(weather!, frame, rows)}><ArrowDownToLine className="size-4" aria-hidden="true" />Download window CSV</a></Button>
        </>} footer="Filters affect this table only. Charts, summary and CSV include all native cells in the selected window. Blank rainfall in the CSV means unknown, never zero.">
          <Table><TableCaption>Imported native forecast cells · no fictional sites or synthetic rainfall</TableCaption>
            <TableHeader><TableRow className="bg-muted/50 hover:bg-muted/50"><TableHead scope="col">Native cell</TableHead><TableHead scope="col">Rainfall (mm / 6h)</TableHead><TableHead scope="col">Hourly inputs</TableHead><TableHead scope="col">Status</TableHead></TableRow></TableHeader>
            <TableBody>{filtered.map(row => <TableRow key={row.native_cell_id}><TableCell className="text-xs font-medium">Cell {rows.findIndex(item => item.native_cell_id === row.native_cell_id) + 1}<span className="block max-w-64 break-all font-mono text-xs font-normal text-muted-foreground">{row.native_cell_id}</span></TableCell><TableCell className="tabular-nums">{number(row.rainfall_6h_mm)}</TableCell><TableCell>{row.available_hours}/6</TableCell><TableCell><Badge variant="outline">{labels[row.status] || row.status}</Badge></TableCell></TableRow>)}{!filtered.length && <TableRow><TableCell colSpan={4} className="h-24 text-center text-sm text-muted-foreground">No native cells match these filters.</TableCell></TableRow>}</TableBody>
          </Table>
        </DashboardTable>
      </>}
    </>}
    <section className="space-y-4" aria-labelledby="data-sources-heading">
      <div className="space-y-1"><h2 id="data-sources-heading" className="text-base font-medium">Source readiness</h2><p className="text-sm text-muted-foreground">Imported files, source access, and fresh data are separate states.</p></div>
      <div className="grid gap-4 lg:grid-cols-3">
        <SourceCard title="WeatherNext 3 county snapshot" source={source} />
        <SourceCard title="County parcel inventory" source={{ ...parcels, message: parcels.message || (parcels.source_mode === "indexed" ? "County-boundary-validated polygon inventory. Geometry does not establish terrain, FEMA coverage or flood risk." : "Live county GIS browsing is available on the map. A verified countywide count is unavailable.") }} />
        <SourceCard title="Official NWS alerts" source={official} />
      </div>
      <p className="text-xs text-muted-foreground">Rechecking reads configured sources without querying BigQuery. Stale and incomplete rainfall stays unknown. Official feed failures never mean no active alerts.</p>
    </section>
    <footer className="space-y-2 border-t pt-4 text-xs text-muted-foreground"><p>Project estimates supplement <a className="underline underline-offset-4" href="https://www.weather.gov/mob/" target="_blank" rel="noopener noreferrer">NWS Mobile/Pensacola and local emergency guidance</a>. No notifications are sent.</p></footer>
  </section>;
}
