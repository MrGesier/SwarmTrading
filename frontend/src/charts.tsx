import { useEffect, useRef, useState, useId } from "react";
import type { State, History } from "./types";
import { aggregateCandles } from "./chart-math";
import {
  useChartWindow,
  WindowControls,
  useAxis,
  AxisControls,
  usePlotWidth,
} from "./chart-controls";
export const fmt = (n: number, d = 2) =>
  n.toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
export const signed = (n: number, d = 2) => (n >= 0 ? "+" : "") + fmt(n, d);
export const clock = (n: number) =>
  new Date(n * 1000).toLocaleTimeString("en-GB", { hour12: false });
const GREEN = "#59ddb2",
  RED = "#ed7d8b";

export function Spark({
  values,
  color = GREEN,
  height = 48,
  label = "Historique des mesures",
}: {
  values: number[];
  color?: string;
  height?: number;
  label?: string;
}) {
  const clean = values.filter(Number.isFinite);
  const lo = clean.length ? Math.min(...clean) : 0,
    hi = clean.length ? Math.max(...clean) : 1,
    range = hi - lo || 1;
  const points = clean
    .map(
      (v, i) =>
        `${(i / Math.max(values.length - 1, 1)) * 300},${height - 4 - (hi === lo ? 0.5 : (v - lo) / range) * (height - 8)}`,
    )
    .join(" ");
  return (
    <>
      {" "}
      <svg
        className="spark"
        viewBox={`0 0 300 ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={label}
      >
        <polyline
          fill="none"
          stroke={color}
          strokeWidth="1.8"
          points={points}
        />
      </svg>
      <details className="mini-history">
        <summary>Explorer la courbe</summary>
        <LineChart label={label} values={values} />
      </details>
    </>
  );
}

// Shared plot navigation keeps display intervals independent from strategy horizons.
export function PriceChart({
  state,
  vwap,
  onSeek,
}: {
  state: State;
  vwap: boolean;
  onSeek?: (time: number) => void;
}) {
  const [interval, setInterval] = useState(5),
    [scale, setScale] = useState("price"),
    [zonesOn, setZonesOn] = useState(true);
  const [hover, setHover] = useState<number | null>(null);
  const view = useChartWindow(state.candles.map((c) => c.time));
  const candles = aggregateCandles(state.candles, interval).filter(
    (c) => c.time + interval > view.from && c.time <= view.to,
  );
  const [origin] = useState(state.candles[0]?.open || state.features.mid || 1),
    mid = state.features.mid;
  const transform = (v: number) =>
    scale === "log"
      ? Math.log(Math.max(v, 1e-12))
      : scale === "percent"
        ? (v / origin - 1) * 100
        : v;
  const inverse = (v: number) => (scale === "log" ? Math.exp(v) : v);
  const axis = useAxis(
    candles.flatMap((c) => [transform(c.low), transform(c.high)]),
  );
  const { ref, width: W } = usePlotWidth(),
    H = 330,
    L = 12,
    R = 82,
    T = 24,
    B = 70,
    P = W - L - R;
  const [lo, hi] = axis.domain,
    y = (v: number) => T + ((hi - transform(v)) / (hi - lo)) * (H - T - B);
  const x = (time: number) => L + ((time - view.from) / view.width) * P;
  const clip = useId(),
    candleWidth = Math.max(
      1,
      Math.min(18, ((P * interval) / view.width) * 0.7),
    );
  const zones = [1, -1].flatMap((sign) =>
    state.triggers
      .filter((t) => t.bp * sign > 0)
      .sort((a, b) => b.density - a.density)
      .slice(0, 1),
  );
  const maxVolume = Math.max(1, ...candles.map((c) => c.volume));
  let sumPV = 0,
    sumV = 0;
  const vw = aggregateCandles(state.candles, interval)
    .map((c) => {
      sumPV += ((c.high + c.low + c.close) / 3) * c.volume;
      sumV += c.volume;
      return { time: c.time, value: sumV ? sumPV / sumV : c.close };
    })
    .filter((c) => c.time + interval > view.from && c.time <= view.to);
  const selected = hover === null ? candles.at(-1) : candles[hover];
  const drag = useRef<{ x: number; end: number } | null>(null);
  const plotRef = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const plot = plotRef.current;
    if (!plot) return;
    const wheel = (e: WheelEvent) => {
      if (e.ctrlKey) {
        e.preventDefault();
        view.zoom(e.deltaY > 0 ? 1.3 : 0.7);
      }
    };
    plot.addEventListener("wheel", wheel, { passive: false });
    return () => plot.removeEventListener("wheel", wheel);
  }, [view.seconds, view.first, view.last]);
  return (
    <div className="interactive-chart" ref={ref}>
      <WindowControls view={view} />
      <div className="plot-toolbar">
        <label>
          Bougie
          <select
            aria-label="Durée des bougies"
            value={interval}
            onChange={(e) => {
              setInterval(Number(e.target.value));
              axis.reset();
            }}
          >
            {[5, 15, 30, 60, 300].map((v) => (
              <option key={v} value={v}>
                {v < 60 ? `${v} s` : `${v / 60} min`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Unité / échelle
          <select
            aria-label="Échelle du prix"
            value={scale}
            onChange={(e) => {
              setScale(e.target.value);
              axis.reset();
            }}
          >
            <option value="price">Prix · linéaire</option>
            <option value="percent">Variation · %</option>
            <option value="log">Prix · logarithmique</option>
          </select>
        </label>
        <button aria-pressed={zonesOn} onClick={() => setZonesOn(!zonesOn)}>
          Zones de déclenchement
        </button>
      </div>
      <AxisControls axis={axis} />
      <div className="plot-readout">
        {selected
          ? `${clock(selected.time)} · O ${fmt(selected.open)} · H ${fmt(selected.high)} · B ${fmt(selected.low)} · C ${fmt(selected.close)} · Vol ${fmt(selected.volume, 3)}`
          : "En attente de bougies observées"}
      </div>
      <svg
        ref={plotRef}
        className="controlled-plot"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Prix, bougies ${interval} secondes, échelle ${scale}`}
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          drag.current = { x: e.clientX, end: view.to };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          if (drag.current) {
            view.setEnd(
              Math.max(
                view.first + view.width,
                Math.min(
                  view.last,
                  drag.current.end -
                    ((e.clientX - drag.current.x) / P) * view.width,
                ),
              ),
            );
          } else {
            const time =
              view.from + ((e.clientX - rect.left - L) / P) * view.width;
            setHover(
              candles.length
                ? candles.reduce(
                    (best, c, i) =>
                      Math.abs(c.time - time) <
                      Math.abs(candles[best].time - time)
                        ? i
                        : best,
                    0,
                  )
                : null,
            );
          }
        }}
        onPointerUp={(e) => {
          const moved = drag.current
            ? Math.abs(e.clientX - drag.current.x) > 4
            : false;
          drag.current = null;
          if (!moved && selected) onSeek?.(selected.time);
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id={clip}>
            <rect x={L} y={T} width={P} height={H - T - B} />
          </clipPath>
        </defs>
        {[0, 1, 2, 3, 4].map((i) => {
          const value = hi - ((hi - lo) * i) / 4,
            yy = T + ((H - T - B) * i) / 4;
          return (
            <g key={i}>
              <line x1={L} x2={W - R} y1={yy} y2={yy} className="plot-grid" />
              <text x={W - R + 8} y={yy + 4}>
                {fmt(
                  inverse(value),
                  scale === "percent" ? 3 : mid < 1000 ? 3 : 1,
                )}
                {scale === "percent" ? "%" : ""}
              </text>
            </g>
          );
        })}
        <g clipPath={`url(#${clip})`}>
          {zonesOn &&
            view.end === null &&
            zones.map((z) => (
              <g key={z.bp}>
                <line
                  x1={L}
                  x2={W - R}
                  y1={y(z.price)}
                  y2={y(z.price)}
                  stroke={z.bp > 0 ? GREEN : RED}
                  strokeDasharray="6 4"
                />
                <text
                  x={L + 6}
                  y={y(z.price) - 5}
                  style={{ fill: z.bp > 0 ? GREEN : RED }}
                >
                  {z.bp > 0 ? "Seuil hausse" : "Seuil baisse"} · {fmt(z.price)}
                </text>
              </g>
            ))}
          {candles.map((c) => (
            <g key={c.time}>
              <line
                x1={x(c.time)}
                x2={x(c.time)}
                y1={y(c.high)}
                y2={y(c.low)}
                stroke={c.close >= c.open ? GREEN : RED}
              />
              <rect
                x={x(c.time) - candleWidth / 2}
                y={y(Math.max(c.open, c.close))}
                width={candleWidth}
                height={Math.max(1, Math.abs(y(c.open) - y(c.close)))}
                fill={c.close >= c.open ? GREEN : RED}
              />
            </g>
          ))}
          {vwap && (
            <polyline
              points={vw.map((c) => `${x(c.time)},${y(c.value)}`).join(" ")}
              fill="none"
              stroke="#e3b77e"
              strokeWidth={1.5}
            />
          )}
          {hover !== null && selected && (
            <line
              x1={x(selected.time)}
              x2={x(selected.time)}
              y1={T}
              y2={H - B}
              stroke="#ddd0bc"
              strokeDasharray="2 3"
            />
          )}
        </g>
        {view.end === null && y(mid) >= T && y(mid) <= H - B && (
          <g>
            <line
              x1={L}
              x2={W - R}
              y1={y(mid)}
              y2={y(mid)}
              stroke="#e3b77e"
              strokeDasharray="2 4"
            />
            <text x={W - R + 8} y={y(mid) - 5} style={{ fill: "#f3c58e" }}>
              {fmt(
                scale === "percent" ? transform(mid) : mid,
                scale === "percent" ? 3 : 2,
              )}
              {scale === "percent" ? "%" : ""}
            </text>
          </g>
        )}
        {candles.map((c) => (
          <rect
            key={c.time}
            x={Math.max(L, x(c.time) - candleWidth / 2)}
            y={H - 30 - (c.volume / maxVolume) * 28}
            width={candleWidth}
            height={(c.volume / maxVolume) * 28}
            fill={c.close >= c.open ? GREEN : RED}
            opacity={0.4}
          />
        ))}
        {[0, 1, 2, 3].map((i) => (
          <text
            key={i}
            x={L + (P * i) / 3}
            y={H - 8}
            textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}
          >
            {clock(view.from + (view.width * i) / 3)}
          </text>
        ))}
      </svg>
      <p className="plot-note">
        Glisser pour naviguer · Ctrl + molette pour zoomer ·{" "}
        {state.candles.length} bougies source de 5 s disponibles. Agrégation
        réelle OHLCV ; première et dernière bougies potentiellement partielles.{" "}
        {vwap ? "VWAP ancré au début de l’historique disponible. " : ""}
        {view.end !== null
          ? "Vue figée : zones actuelles masquées."
          : "Les zones décrivent les seuils actuels, pas des ordres exécutés."}
        {scale === "percent"
          ? ` Base fixe 0 % : ${fmt(origin)} USD à l’ouverture du graphique.`
          : ""}
        {zonesOn &&
        view.end === null &&
        zones.some((z) => y(z.price) < T || y(z.price) > H - B)
          ? " Certains seuils sont hors échelle : réduire le zoom vertical pour les voir."
          : ""}
      </p>
    </div>
  );
}

export function LineChart({
  values,
  times,
  label,
  color = GREEN,
  unit = "",
  epochs = false,
  zero = false,
}: {
  values: (number | null)[];
  times?: number[];
  label: string;
  color?: string;
  unit?: string;
  epochs?: boolean;
  zero?: boolean;
}) {
  const points = values.map((v, i) => ({ v, t: times?.[i] ?? i }));
  const view = useChartWindow(
      points.map((p) => p.t),
      0,
    ),
    visible = points.filter((p) => p.t >= view.from && p.t <= view.to);
  const axis = useAxis(
    visible.flatMap((p) => (p.v !== null && Number.isFinite(p.v) ? [p.v] : [])),
    zero,
  );
  const { ref, width: W } = usePlotWidth(),
    H = 190,
    L = 62,
    R = 14,
    T = 15,
    B = 32,
    clip = useId();
  const [lo, hi] = axis.domain,
    x = (t: number) => L + ((t - view.from) / view.width) * (W - L - R),
    y = (v: number) => T + ((hi - v) / (hi - lo)) * (H - T - B);
  const [hover, setHover] = useState<number | null>(null);
  let path = "",
    pen = false;
  for (const p of visible) {
    if (p.v === null || !Number.isFinite(p.v)) {
      pen = false;
      continue;
    }
    path += `${pen ? "L" : "M"}${x(p.t)},${y(p.v)} `;
    pen = true;
  }
  const point = hover === null ? visible.at(-1) : visible[hover];
  return (
    <section
      className="interactive-chart line-chart"
      ref={ref}
      aria-label={label}
    >
      <h4>{label}</h4>
      <WindowControls
        view={view}
        epochs={epochs || !times}
        indexLabel={epochs ? "cycles" : "mesures"}
      />
      <details className="axis-options">
        <summary>Échelle et zoom vertical</summary>
        <AxisControls axis={axis} />
      </details>
      <div className="plot-readout">
        {point
          ? `${times && !epochs ? new Date(point.t * 1000).toLocaleString("fr-FR") : epochs ? "Cycle " + point.t : "Mesure " + (point.t + 1)} · ${point.v == null ? "indisponible" : fmt(point.v, 3)} ${unit}`
          : "Collecte des premières mesures…"}
      </div>
      <svg
        className="controlled-plot"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={label}
        onPointerLeave={() => setHover(null)}
        onPointerMove={(e) => {
          const t =
            view.from +
            ((e.clientX - e.currentTarget.getBoundingClientRect().left - L) /
              (W - L - R)) *
              view.width;
          setHover(
            visible.length
              ? visible.reduce(
                  (b, p, i) =>
                    Math.abs(p.t - t) < Math.abs(visible[b].t - t) ? i : b,
                  0,
                )
              : null,
          );
        }}
      >
        <defs>
          <clipPath id={clip}>
            <rect x={L} y={T} width={W - L - R} height={H - T - B} />
          </clipPath>
        </defs>
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <line
              x1={L}
              x2={W - R}
              y1={T + ((H - T - B) * i) / 3}
              y2={T + ((H - T - B) * i) / 3}
              className="plot-grid"
            />
            <text x={L - 8} y={T + ((H - T - B) * i) / 3 + 4} textAnchor="end">
              {fmt(hi - ((hi - lo) * i) / 3, 2)}
            </text>
          </g>
        ))}
        <g clipPath={`url(#${clip})`}>
          {lo < 0 && hi > 0 && (
            <line
              x1={L}
              x2={W - R}
              y1={y(0)}
              y2={y(0)}
              stroke="#957c60"
              strokeDasharray="4 4"
            />
          )}
          <path d={path} stroke={color} strokeWidth={2} fill="none" />
          {visible
            .filter((p) => p.v != null && Number.isFinite(p.v))
            .map((p) => (
              <circle
                key={p.t}
                cx={x(p.t)}
                cy={y(p.v!)}
                r={visible.length < 3 ? 3 : 1.5}
                fill={color}
              />
            ))}
          {point?.v != null && (
            <circle cx={x(point.t)} cy={y(point.v)} r={4} fill={color} />
          )}
        </g>
        {[0, 1, 2].map((i) => (
          <text
            key={i}
            x={L + ((W - L - R) * i) / 2}
            y={H - 8}
            textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
          >
            {times && !epochs
              ? clock(view.from + (view.width * i) / 2)
              : Math.round(view.from + (view.width * i) / 2) +
                (epochs ? "" : "")}
          </text>
        ))}
      </svg>
      <p className="plot-note">
        {times && !epochs
          ? "Horodatages réels · historique disponible uniquement."
          : epochs
            ? "Axe horizontal : cycles, pas une durée de trading."
            : "Axe horizontal : mesures disponibles, pas des secondes."}{" "}
        {unit && `Unité : ${unit}.`} Les données absentes restent des
        interruptions de courbe.
      </p>
    </section>
  );
}

export function Liquidity({ history }: { history: History[] }) {
  const view = useChartWindow(history.map((h) => h.time)),
    [spread, setSpread] = useState(10),
    [locked, setLocked] = useState<number | null>(null);
  const frames = history.filter(
      (h) => h.time >= view.from && h.time <= view.to,
    ),
    canvasRef = useRef<HTMLCanvasElement>(null);
  const center = locked ?? frames.at(-1)?.mid ?? 1,
    lo = center * (1 - spread / 10000),
    hi = center * (1 + spread / 10000);
  const [detail, setDetail] = useState(
    "Survoler pour inspecter le prix et la quantité visible.",
  );
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const W = canvas.clientWidth,
        H = 240,
        dpr = window.devicePixelRatio || 1;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.scale(dpr, dpr);
      ctx.fillStyle = "#111820";
      ctx.fillRect(0, 0, W, H);
      const P = W - 84,
        Q = H - 30,
        rows = 40;
      const grids = frames.map((f) => {
        const bins = Array(rows).fill(0);
        for (const [p, q] of f.levels) {
          const j = Math.floor(((hi - p) / (hi - lo)) * rows);
          if (j >= 0 && j < rows) bins[j] += q;
        }
        return bins;
      });
      const max = Math.max(0.001, ...grids.flat());
      grids.forEach((col, i) => {
        const xx = ((frames[i].time - view.from) / view.width) * P;
        const next =
          i + 1 < frames.length
            ? ((frames[i + 1].time - view.from) / view.width) * P
            : P;
        const cw = Math.min(Math.max(1, next - xx), (P * 3) / view.width);
        col.forEach((v, j) => {
          const t = Math.sqrt(v / max);
          ctx.fillStyle = `rgba(224,171,105,${0.04 + t * 0.85})`;
          ctx.fillRect(xx, (j * Q) / rows, cw, Q / rows);
        });
      });
      ctx.strokeStyle = "#d8ede1";
      ctx.beginPath();
      frames.forEach((f, i) => {
        const xx = ((f.time - view.from) / view.width) * P,
          yy = ((hi - f.mid) / (hi - lo)) * Q;
        if (i === 0 || f.time - frames[i - 1].time > 3) ctx.moveTo(xx, yy);
        else ctx.lineTo(xx, yy);
      });
      ctx.save();
      ctx.rect(0, 0, P, Q);
      ctx.clip();
      ctx.stroke();
      ctx.restore();
      ctx.font = "11px monospace";
      ctx.fillStyle = "#b8b1a7";
      for (let i = 0; i < 5; i++)
        ctx.fillText(
          fmt(hi - ((hi - lo) * i) / 4, 2),
          P + 8,
          Math.max(12, (i * Q) / 4),
        );
      for (let i = 0; i < 3; i++)
        ctx.fillText(
          clock(view.from + (view.width * i) / 2),
          (i * (P - 65)) / 2,
          H - 8,
        );
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [history, view.from, view.to, lo, hi]);
  return (
    <div className="interactive-chart">
      <WindowControls view={view} />
      <div className="plot-toolbar">
        <label>
          Étendue de prix
          <select
            aria-label="Étendue de prix de la liquidité"
            value={spread}
            onChange={(e) => setSpread(Number(e.target.value))}
          >
            {[2, 5, 10, 30, 100].map((v) => (
              <option key={v} value={v}>
                ±{v} bp
              </option>
            ))}
          </select>
        </label>
        <button
          aria-pressed={locked !== null}
          onClick={() => setLocked(locked === null ? center : null)}
        >
          {locked === null ? "Verrouiller le centre" : "Centrer sur le prix"}
        </button>
      </div>
      <div className="plot-readout">{detail}</div>
      <canvas
        ref={canvasRef}
        className="liquidity controlled-heatmap"
        role="img"
        aria-label="Liquidité observée par prix et heure"
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect(),
            t =
              view.from +
              ((e.clientX - rect.left) / (rect.width - 84)) * view.width,
            p = hi - ((e.clientY - rect.top) / 210) * (hi - lo);
          const frame = frames.reduce<History | undefined>(
            (best, f) =>
              !best || Math.abs(f.time - t) < Math.abs(best.time - t)
                ? f
                : best,
            undefined,
          );
          const step = (hi - lo) / 40,
            quantity = frame?.levels
              .filter(
                ([price]) =>
                  Math.floor((hi - price) / step) ===
                  Math.floor((hi - p) / step),
              )
              .reduce((sum, [, q]) => sum + q, 0);
          setDetail(
            frame
              ? `${clock(frame.time)} · prix ≈ ${fmt(p)} · quantité ${fmt(quantity ?? 0, 4)}`
              : "Aucune observation",
          );
        }}
      />
      <p className="plot-note">
        Couleur : profondeur relative dans la vue. Les espaces sans observation
        ne sont pas interpolés. Prix en USD, quantité en actif de base.
      </p>
    </div>
  );
}

export function Phase({ history }: { history: History[] }) {
  const view = useChartWindow(history.map((h) => h.time)),
    [range, setRange] = useState(0.1),
    clip = useId();
  const h = history.filter((p) => p.time >= view.from && p.time <= view.to),
    x = (v: number) => 45 + v * 310,
    y = (v: number) => 115 - (v / range) * 85;
  return (
    <div className="interactive-chart">
      <WindowControls view={view} />
      <div className="plot-toolbar">
        <label>
          Étendue verticale
          <select
            aria-label="Échelle de variation de l’entropie"
            value={range}
            onChange={(e) => setRange(Number(e.target.value))}
          >
            {[0.01, 0.05, 0.1, 0.5].map((v) => (
              <option key={v} value={v}>
                ±{v}/s
              </option>
            ))}
          </select>
        </label>
      </div>
      <svg
        viewBox="0 0 400 240"
        className="controlled-plot"
        role="img"
        aria-label="Entropie et variation par seconde"
      >
        <defs>
          <clipPath id={clip}>
            <rect x="45" y="20" width="310" height="190" />
          </clipPath>
        </defs>
        <line x1="45" x2="355" y1="115" y2="115" className="plot-grid" />
        <line x1="200" x2="200" y1="20" y2="210" className="plot-grid" />
        <text x="4" y="30">
          +{range}
        </text>
        <text x="4" y="205">
          −{range}
        </text>
        <g clipPath={`url(#${clip})`}>
          <polyline
            points={h
              .map((p) => `${x(p.market_entropy)},${y(p.slope)}`)
              .join(" ")}
            fill="none"
            stroke={GREEN}
          />
          {h.map((p) => (
            <circle
              key={p.time}
              cx={x(p.market_entropy)}
              cy={y(p.slope)}
              r="2"
              fill={GREEN}
            >
              <title>
                {clock(p.time)} · entropie {fmt(p.market_entropy, 3)} ·
                variation {fmt(p.slope, 4)}/s
              </title>
            </circle>
          ))}
        </g>
        <text x="45" y="233">
          0
        </text>
        <text x="155" y="233">
          Entropie →
        </text>
        <text x="345" y="233">
          1
        </text>
      </svg>
    </div>
  );
}

export function TriggerChart({ state }: { state: State }) {
  const [range, setRange] = useState(30),
    [unit, setUnit] = useState("bp"),
    [ceiling, setCeiling] = useState(0);
  const rows = state.triggers
    .filter((t) => Math.abs(t.bp) <= range)
    .slice()
    .reverse();
  const max = ceiling || Math.max(...rows.map((t) => t.density), 1);
  return (
    <div className="interactive-chart">
      <div className="plot-toolbar">
        <label>
          Étendue
          <select
            aria-label="Étendue des seuils"
            value={range}
            onChange={(e) => setRange(Number(e.target.value))}
          >
            {[5, 10, 20, 30].map((v) => (
              <option key={v} value={v}>
                ±{v} bp
              </option>
            ))}
          </select>
        </label>
        <label>
          Axe prix
          <select
            aria-label="Unité des seuils"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
          >
            <option value="bp">Écart · bp</option>
            <option value="price">Prix · USD</option>
          </select>
        </label>
        <label>
          Densité max
          <select
            value={ceiling}
            aria-label="Échelle de densité"
            onChange={(e) => setCeiling(Number(e.target.value))}
          >
            <option value={0}>Auto</option>
            {[1, 5, 10, 25, 50].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="trigger-bars">
        {rows.map((t) => (
          <div
            key={t.bp}
            title={`Prix ${fmt(t.price)} · profondeur opposée ${fmt(t.resistance)}`}
          >
            <span>
              {unit === "bp" ? signed(t.bp, 0) + " bp" : fmt(t.price)}
            </span>
            <div>
              <i
                style={{
                  width: `${Math.min(100, (t.density / max) * 100)}%`,
                  background: t.bp >= 0 ? GREEN : RED,
                }}
              />
            </div>
            <b>
              {fmt(t.density, 1)}
              {t.density > max ? " ↗" : ""}
            </b>
          </div>
        ))}
      </div>
      <p className="plot-note">
        Instantané des seuils actuels · densité en stratégies effectives. Ce
        n’est ni une série temporelle ni un historique d’entrées exécutées.
      </p>
    </div>
  );
}
