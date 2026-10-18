import { useEffect, useState } from "react";

// One selected archive hour across the map, source tables and downloads.
export function useReplaySelection() {
  const [index, setIndex] = useState(() => window.Quasar?.frame?.() ?? 0);
  useEffect(() => {
    const update = (event: Event) => setIndex((event as CustomEvent<{ index: number }>).detail.index);
    window.addEventListener("quasar:frame", update);
    return () => window.removeEventListener("quasar:frame", update);
  }, []);
  const select = (next: number) => {
    if (!Number.isInteger(next) || next < 0 || next > 24) return;
    setIndex(next);
    window.dispatchEvent(new CustomEvent("quasar:seek", { detail: { index: next } }));
  };
  return [index, select] as const;
}
