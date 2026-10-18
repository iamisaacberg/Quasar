import * as h3 from "h3-js";
import polygonClipping from "polygon-clipping";
import "../quasar/static/spatial.js";

type Collection = {features: {id: string; properties: Record<string, unknown>}[]};
type Spatial = {
  configureGeometry(value: typeof polygonClipping): void;
  countyCells(geometry: unknown, index: typeof h3, resolution: number): Collection;
  rainfallCoverage(grid: Collection, weather: unknown): Collection;
};
const scope = globalThis as unknown as {
  QuasarSpatial: Spatial;
  onmessage: (event: MessageEvent) => void;
  postMessage: (value: unknown) => void;
};
scope.QuasarSpatial.configureGeometry(polygonClipping);
let boundary: unknown;
const grids = new Map<number, Collection>();
scope.onmessage = ({data}) => {
  if (data.type === "boundary") {boundary = data.geometry; grids.clear(); return;}
  const start = performance.now();
  try {
    const first = !grids.has(data.resolution);
    if (first) grids.set(data.resolution, scope.QuasarSpatial.countyCells(boundary, h3, data.resolution));
    const grid = grids.get(data.resolution)!;
    const result = scope.QuasarSpatial.rainfallCoverage(grid, data.weather);
    scope.postMessage({id: data.id, resolution: data.resolution, grid: first ? grid : undefined,
      rainfall: result.features.map(feature => ({id: feature.id, properties: feature.properties})),
      duration_ms: performance.now() - start});
  } catch {
    scope.postMessage({id: data.id, error: "County geometry preparation failed; coverage remains unknown."});
  }
};
