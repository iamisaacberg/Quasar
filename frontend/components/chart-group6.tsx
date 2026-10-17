"use client";

import { Bar, BarChart, Pie, PieChart, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/utils";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
// Registry source: @shadcnblocks/chart-group6 (Donut and Bar Chart Pair).
// Card/grid geometry is retained inside the existing app shell. The legend may
// wrap on narrow screens. Data, labels, units and accessible values are Quasar's.
interface ChartGroup6Props {
  className?: string;
  bands: { name: string; value: number; fill: string }[];
  rainfall: { name: string; value: number | null }[];
  rainfallDescription: string;
}

const barConfig = {
  value: { label: "Rainfall (mm / 6h)", color: "var(--primary)" },
} satisfies ChartConfig;

const ChartGroup6 = ({ className, bands: pieData, rainfall: barData, rainfallDescription }: ChartGroup6Props) => {
  const total = pieData.reduce((sum, item) => sum + item.value, 0);
  // Slice colors are supplied by fill; labels need no generated CSS variables.
  const pieConfig = Object.fromEntries(pieData.map(item => [item.name, { label: item.name }])) satisfies ChartConfig;
  const rainfallLabel = `Six-hour rainfall in millimeters. ${barData.map(item => `${item.name}: ${item.value === null ? "Unknown" : item.value}`).join("; ")}. Exact values are in the site table.`;

  return (
    <section aria-label="Selected window charts" className={cn("grid gap-4 md:grid-cols-2", className)}>
        <Card>
          <CardHeader>
            <CardTitle role="heading" aria-level={2}>Relative score distribution</CardTitle>
            <CardDescription>Fictional sites by score band. Lower relative does not mean safe.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-8">
              <div className="relative size-40" role="img" aria-label={`Sites by relative score band. ${pieData.map(item => `${item.name}: ${item.value}`).join("; ")}. Exact values follow.`}>
                <ChartContainer config={pieConfig} className="size-full">
                  <PieChart>
                    <ChartTooltip
                      content={<ChartTooltipContent nameKey="name" hideLabel />}
                      cursor={false}
                    />
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={70}
                      paddingAngle={2}
                      dataKey="value"
                      nameKey="name"
                      isAnimationActive={false}
                      strokeWidth={0}
                    />
                  </PieChart>
                </ChartContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-2xl font-bold">
                    {total.toLocaleString()}
                  </span>
                  <span className="text-xs text-muted-foreground">Total</span>
                </div>
              </div>
              <div className="flex-1 space-y-3">
                {pieData.map((item) => (
                  <div
                    key={item.name}
                    className="flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="size-3 rounded-full"
                        style={{ backgroundColor: item.fill }}
                      />
                      <span className="text-sm">{item.name}</span>
                    </div>
                    <span className="text-sm font-medium">
                      {item.value.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <details className="mt-4 text-sm">
              <summary className="cursor-pointer text-muted-foreground">View band counts</summary>
              <Table>
                <TableHeader><TableRow><TableHead scope="col">Band</TableHead><TableHead scope="col">Sites</TableHead></TableRow></TableHeader>
                <TableBody>{pieData.map(item => <TableRow key={item.name}><TableCell>{item.name}</TableCell><TableCell>{item.value}</TableCell></TableRow>)}</TableBody>
              </Table>
            </details>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle role="heading" aria-level={2}>Rainfall by fictional site</CardTitle>
            <CardDescription>{rainfallDescription} Unknown values have no bar.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={barConfig} className="h-48 w-full" role="img" aria-label={rainfallLabel}>
              <BarChart
                data={barData.map(item => ({ ...item, name: item.name.replace("Missing terrain", "No terrain") }))}
                layout="vertical"
                margin={{ top: 0, right: 10, left: 0, bottom: 0 }}
              >
                <XAxis
                  type="number"
                  domain={[0, (max: number) => Math.max(1, max)]}
                  axisLine={false}
                  tickLine={false}
                  fontSize={12}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  axisLine={false}
                  tickLine={false}
                  fontSize={12}
                  width={70}
                />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar
                  dataKey="value"
                  isAnimationActive={false}
                  fill="var(--color-value)"
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
    </section>
  );
};

export { ChartGroup6 };
