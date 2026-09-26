import { useEffect, useRef, useState } from "react";
import { windowRange, extent, axisDomain } from "./chart-math";

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
    reset: () => {
      setSeconds(initial);
      setEnd(null);
    },
    zoom: (factor: number) => {
      setSeconds(
        Math.max(
          5,
          Math.min(
            Math.max(5, last - first),
            (seconds || last - first) * factor,
          ),
        ),
      );
    },
    pan: (fraction: number) =>
      setEnd(
        Math.max(
          first + range.width,
          Math.min(last, range.to + fraction * range.width),
        ),
      ),
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
      aria-label="Navigation du graphique"
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
          <option value={-1} disabled>
            Personnalisée
          </option>
          {(epochs ? [10, 30, 60] : [60, 300, 900, 3600, 86400]).map((v) => (
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
      <button
        type="button"
        aria-label="Reculer dans le graphique"
        disabled={view.from <= view.first}
        onClick={() => view.pan(-0.5)}
      >
        ←
      </button>
      <button
        type="button"
        aria-label="Avancer dans le graphique"
        disabled={view.to >= view.last}
        onClick={() => view.pan(0.5)}
      >
        →
      </button>
      <button
        type="button"
        aria-label="Zoom temporel avant"
        onClick={() => view.zoom(0.5)}
      >
        ＋
      </button>
      <button
        type="button"
        aria-label="Zoom temporel arrière"
        onClick={() => view.zoom(2)}
      >
        −
      </button>
      <button
        type="button"
        aria-pressed={view.end === null}
        onClick={() => view.setEnd(view.end === null ? view.to : null)}
      >
        {view.end === null ? "Figer la vue" : "Suivre le flux"}
      </button>
      <button type="button" onClick={view.reset}>
        Réinitialiser
      </button>
      <span className="plot-available">
        Disponible :{" "}
        {epochs
          ? `${Math.round(view.last - view.first) + 1} ${indexLabel}`
          : `${Math.floor((view.last - view.first) / 60)} min ${Math.round((view.last - view.first) % 60)} s`}
      </span>
    </div>
  );
}
export function useAxis(values: number[], zero = false) {
  const [zoom, setZoom] = useState(1),
    [locked, setLocked] = useState<[number, number] | null>(null);
  const base = locked ?? extent(values, zero),
    domain = axisDomain(base, zoom);
  return {
    domain,
    zoom,
    setZoom,
    locked,
    toggle: () => setLocked(locked ? null : base),
    reset: () => {
      setZoom(1);
      setLocked(null);
    },
  };
}
export function AxisControls({ axis }: { axis: ReturnType<typeof useAxis> }) {
  return (
    <div className="plot-toolbar axis-toolbar">
      <label>
        Zoom vertical
        <input
          aria-label="Zoom vertical"
          type="range"
          min="0.5"
          max="5"
          step="0.1"
          value={axis.zoom}
          onChange={(e) => axis.setZoom(Number(e.target.value))}
        />
        <span>{axis.zoom.toFixed(1)}×</span>
      </label>
      <button type="button" aria-pressed={!!axis.locked} onClick={axis.toggle}>
        {axis.locked ? "Échelle verrouillée" : "Verrouiller l’échelle"}
      </button>
      <button type="button" onClick={axis.reset}>
        Échelle auto
      </button>
    </div>
  );
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
