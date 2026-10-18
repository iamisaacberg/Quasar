import type { ReactNode } from "react";
import { Activity, CircleHelp, Database, TriangleAlert } from "lucide-react";


// Extracted from @shadcnblocks/dashboard2: keep the KPI strip and table layout.
export function DashboardStats({ parcelCount, cellCount, availableCount, meanRainfall }: {
  parcelCount: number | null; cellCount: number | null; availableCount: number | null; meanRainfall: number | null;
}) {
  const value = (input: number | null) => input === null ? "Unknown" : input.toLocaleString("en-US", { maximumFractionDigits: 2 });
  const stats = [
    { title: "Indexed parcels", value: value(parcelCount), icon: Database, context: "County-validated geometry", helper: "Parcel flood scores remain unknown" },
    { title: "Native forecast cells", value: value(cellCount), icon: Activity, context: "Intersecting Okaloosa County", helper: "Original forecast resolution" },
    { title: "Mean cell rainfall", value: value(meanRainfall), icon: TriangleAlert, context: "Millimeters per six hours", helper: "Unweighted; excludes unavailable cells" },
    { title: "Available rainfall", value: value(availableCount), icon: CircleHelp, context: "Complete, fresh native cells", helper: "Missing or stale rainfall stays unknown" },
  ];
  return <section aria-label="Selected window summary" className="grid grid-cols-2 gap-3 rounded-xl border bg-card p-4 sm:gap-4 sm:p-5 lg:grid-cols-4 lg:gap-6 lg:p-6">
    {stats.map((stat, index) => <div key={stat.title} className="flex items-start">
      <div className="flex-1 space-y-1 sm:space-y-2 lg:space-y-3">
        <div className="flex items-center gap-1.5 text-muted-foreground sm:gap-2">
          <stat.icon className="size-3.5 sm:size-4" aria-hidden="true" />
          <span className="truncate text-[10px] font-medium sm:text-xs lg:text-sm">{stat.title}</span>
        </div>
        <p className="hidden text-[10px] text-muted-foreground/70 sm:block sm:text-xs">{stat.context}</p>
        <p className="text-xl leading-tight font-semibold tracking-tight sm:text-2xl lg:text-[28px]">{stat.value}</p>
        <div className="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[10px] sm:text-xs">
          <span className="text-muted-foreground">{stat.helper}</span>
        </div>
      </div>
      {index < stats.length - 1 && <div className="mx-4 hidden h-full w-px bg-border lg:block xl:mx-6" />}
    </div>)}
  </section>;
}

export function DashboardTable({ title, count, controls, children, footer, id }: {
  title: string; count?: string; controls?: ReactNode; children: ReactNode; footer: ReactNode; id?: string;
}) {
  return <section id={id} aria-label={title} className="min-w-0 rounded-xl border bg-card">
    <div className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:gap-4 sm:px-6 sm:py-3.5">
      <div className="flex flex-1 items-center gap-2 sm:gap-2.5">
        <h2 className="text-sm font-medium sm:text-base">{title}</h2>
        {count && <span role="status" className="ml-1 inline-flex items-center rounded-md bg-muted px-2 py-1 text-[10px] font-medium text-muted-foreground ring-1 ring-border ring-inset sm:text-xs">{count}</span>}
      </div>
      {controls && <div className="flex flex-wrap items-center gap-2">{controls}</div>}
    </div>
    <div className="overflow-x-auto px-3 pb-3 sm:px-6 sm:pb-4">{children}</div>
    <div className="border-t px-3 py-3 text-xs text-muted-foreground sm:px-6">{footer}</div>
  </section>;
}
