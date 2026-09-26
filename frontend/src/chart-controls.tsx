import { useEffect, useRef, useState } from "react";
import { windowRange, extent } from "./chart-math";

export function useChartWindow(times: number[], initial = 300) {
  const [seconds, setSeconds] = useState(initial),
    [end, setEnd] = useState<number | null>(null);
  const first = times[0] ?? 0,
    last = times.at(-1) ?? first;
  const range = windowRange(first, last, seconds, end);
  return {
    ...range,
    seconds,
    end,
    first,
    last,
    setSeconds,
    setEnd,
  };
}
export type ChartWindow = ReturnType<typeof useChartWindow>;
export function WindowControls({
  view,
  epochs = false,
  indexLabel = "cycles",
}: {
  view: ChartWindow;
  epochs?: boolean;
  indexLabel?: string;
}) {
  return (
    <div
      className="plot-toolbar"
      role="group"
      aria-label="Période du graphique"
    >
      <label>
        {epochs ? `Fenêtre · ${indexLabel}` : "Période"}
        <select
          aria-label={
            epochs ? `Nombre de ${indexLabel} affichés` : "Période affichée"
          }
          value={
            [0, 10, 30, 60, 300, 900, 3600, 86400].includes(view.seconds)
              ? view.seconds
              : -1
          }
          onChange={(e) => {
            view.setSeconds(Number(e.target.value));
            view.setEnd(null);
          }}
        >
          {(epochs ? [10, 30, 60] : [60, 300, 900]).map((v) => (
            <option key={v} value={v}>
              {epochs
                ? `${v} ${indexLabel}`
                : v < 3600
                  ? `${v / 60} min`
                  : v < 86400
                    ? `${v / 3600} h`
                    : "24 h"}
            </option>
          ))}
          <option value={0}>Tout disponible</option>
        </select>
      </label>
    </div>
  );
}
export function useAxis(values: number[], zero = false) {
  return { domain: extent(values, zero) };
}

export function usePlotWidth() {
  const ref = useRef<HTMLDivElement>(null),
    [width, setWidth] = useState(650);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(() =>
      setWidth(Math.max(280, node.clientWidth)),
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}
