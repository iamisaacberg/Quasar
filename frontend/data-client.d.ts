interface Window {
  QuasarGeometryClient?: {create(worker: Worker): NonNullable<Window["QuasarGeometry"]>};
  QuasarGeometry?: {coverage(geometry: unknown, resolution: number, weather: unknown): Promise<{grid: unknown; rainfall: unknown}>};
  QuasarData?: {
    get<T>(url: string, options?: {signal?: AbortSignal; force?: boolean; ttl?: number}): Promise<T>;
    invalidate(prefix?: string): void;
  };
}
