import { useEffect, useRef } from "react";
import type { State, History } from "./types";
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
}: {
  values: number[];
  color?: string;
  height?: number;
}) {
  const lo = Math.min(...values),
    hi = Math.max(...values),
    range = hi - lo || 1;
  const points = values
    .map(
      (v, i) =>
        `${(i / Math.max(values.length - 1, 1)) * 300},${height - 4 - ((v - lo) / range) * (height - 8)}`,
    )
    .join(" ");
  return (
    <svg
      className="spark"
      viewBox={`0 0 300 ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Historical trend"
    >
      <polyline fill="none" stroke={color} strokeWidth="1.8" points={points} />
    </svg>
  );
}

export function PriceChart({
  state,
  vwap,
  onSeek,
}: {
  state: State;
  vwap: boolean;
  onSeek?: (time: number) => void;
}) {
  const candles = state.candles.slice(-100),
    W = 1000,
    H = 320,
    L = 12,
    R = 83,
    T = 18,
    B = 32;
  const all = candles.flatMap((c) => [c.high, c.low]);
  const mid = state.features.mid;
  const lo = Math.min(...all, mid * 0.999) - mid * 0.0003,
    hi = Math.max(...all, mid * 1.001) + mid * 0.0003;
  const y = (p: number) => T + ((hi - p) / (hi - lo)) * (H - T - B - 40),
    x = (i: number) =>
      L + ((i + 0.5) / Math.max(candles.length, 1)) * (W - L - R);
  const maxV = Math.max(...candles.map((c) => c.volume), 1);
  let sumPV = 0,
    sumV = 0;
  const vw = candles
    .map((c, i) => {
      sumPV += ((c.high + c.low + c.close) / 3) * c.volume;
      sumV += c.volume;
      return `${x(i)},${y(sumPV / Math.max(sumV, 1e-9))}`;
    })
    .join(" ");
  const zones = [
    state.triggers
      .filter((t) => t.bp > 0)
      .reduce((a, b) => (a.density > b.density ? a : b)),
    state.triggers
      .filter((t) => t.bp < 0)
      .reduce((a, b) => (a.density > b.density ? a : b)),
  ];
  return (
    <svg
      className="price-chart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Candlesticks at selected display interval, volume and strategy trigger zones"
    >
      {[0, 1, 2, 3, 4].map((i) => {
        let p = hi - ((hi - lo) * i) / 4;
        return (
          <g key={i}>
            <line
              x1={L}
              x2={W - R}
              y1={y(p)}
              y2={y(p)}
              stroke="#1c2934"
              strokeDasharray="3 5"
            />
            <text x={W - R + 10} y={y(p) + 4}>
              {fmt(p, mid < 1000 ? 2 : 1)}
            </text>
          </g>
        );
      })}
      {zones.map(
        (z) =>
          y(z.price) > T &&
          y(z.price) < H - B - 40 && (
            <g key={z.bp}>
              <rect
                x={L}
                y={y(z.price) - 8}
                width={W - L - R}
                height={16}
                fill={z.bp > 0 ? GREEN : RED}
                opacity=".07"
              />
              <line
                x1={L}
                x2={W - R}
                y1={y(z.price)}
                y2={y(z.price)}
                stroke={z.bp > 0 ? GREEN : RED}
                opacity=".4"
                strokeDasharray="4 4"
              />
              <text
                x={L + 10}
                y={y(z.price) - 13}
                fill={z.bp > 0 ? GREEN : RED}
              >
                {z.bp > 0 ? "LONG" : "SHORT"} TRIGGER · {fmt(z.density, 1)} EFF.
              </text>
            </g>
          ),
      )}
      {candles.map((c, i) => {
        const color = c.close >= c.open ? GREEN : RED;
        return (
          <g
            key={c.time}
            onClick={() => onSeek?.(c.time)}
            style={{ cursor: onSeek ? "crosshair" : "default" }}
          >
            <title>
              {clock(c.time)} · O {fmt(c.open)} H {fmt(c.high)} L {fmt(c.low)} C{" "}
              {fmt(c.close)}
            </title>
            <rect
              x={x(i) - 4}
              y={T}
              width={8}
              height={H - T - B}
              fill="transparent"
            />
            <line
              x1={x(i)}
              x2={x(i)}
              y1={y(c.high)}
              y2={y(c.low)}
              stroke={color}
            />
            <rect
              x={x(i) - Math.max(1, 350 / candles.length)}
              y={y(Math.max(c.open, c.close))}
              width={Math.max(2, 700 / candles.length)}
              height={Math.max(1, Math.abs(y(c.open) - y(c.close)))}
              fill={color}
            />
            <rect
              x={x(i) - 3}
              y={H - B - (c.volume / maxV) * 28}
              width={6}
              height={(c.volume / maxV) * 28}
              fill={color}
              opacity=".3"
            />
            {i % Math.max(1, Math.floor(candles.length / 6)) === 0 && (
              <text x={x(i)} y={H - 8} textAnchor="middle">
                {clock(c.time).slice(0, 5)}
              </text>
            )}
          </g>
        );
      })}
      {vwap && (
        <polyline points={vw} stroke="#d7b575" strokeWidth="1.4" fill="none" />
      )}
      <line
        x1={L}
        x2={W - R}
        y1={y(mid)}
        y2={y(mid)}
        stroke={GREEN}
        strokeDasharray="3 4"
        opacity=".7"
      />
      <rect
        x={W - R + 3}
        y={y(mid) - 11}
        width={80}
        height={22}
        rx={3}
        fill={GREEN}
      />
      <text
        x={W - R + 43}
        y={y(mid) + 4}
        textAnchor="middle"
        style={{ fill: "#081610", fontWeight: 700 }}
      >
        {fmt(mid, mid < 1000 ? 2 : 1)}
      </text>
    </svg>
  );
}

export function Liquidity({ history }: { history: History[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !history.length) return;
    const draw = () => {
      const width = canvas.clientWidth,
        height = canvas.clientHeight,
        dpr = window.devicePixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.scale(dpr, dpr);
      const frames = history.slice(-100),
        lo = Math.min(...frames.map((f) => f.mid)) * 0.999,
        hi = Math.max(...frames.map((f) => f.mid)) * 1.001;
      const cols = frames.length,
        rows = 42,
        plot = width - 75,
        cw = plot / cols,
        rh = (height - 24) / rows;
      const grid = frames.map((f) => {
        const bins = Array(rows).fill(0);
        for (const [p, q] of f.levels) {
          const j = Math.floor(((hi - p) / (hi - lo)) * rows);
          if (j >= 0 && j < rows) bins[j] += q;
        }
        return bins;
      });
      const max = Math.max(...grid.flat(), 0.001);
      ctx.fillStyle = "#0a141c";
      ctx.fillRect(0, 0, width, height);
      grid.forEach((col, i) =>
        col.forEach((v, j) => {
          const t = Math.sqrt(v / max);
          ctx.fillStyle = `rgba(${Math.round(14 + t * 40)},${Math.round(36 + t * 170)},${Math.round(60 + t * 110)},${0.18 + t * 0.8})`;
          ctx.fillRect(i * cw, j * rh, cw + 0.2, rh - 0.6);
        }),
      );
      ctx.beginPath();
      frames.forEach((f, i) => {
        const xx = (i + 0.5) * cw,
          yy = ((hi - f.mid) / (hi - lo)) * (height - 24);
        if (i === 0) ctx.moveTo(xx, yy);
        else ctx.lineTo(xx, yy);
      });
      ctx.strokeStyle = "#d1eee3";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.font = "11px monospace";
      ctx.fillStyle = "#718493";
      for (let i = 0; i < 5; i++) {
        const yy = (i / 4) * (height - 34) + 10;
        ctx.fillText(
          fmt(hi - ((hi - lo) * i) / 4, hi < 1000 ? 2 : 0),
          plot + 10,
          yy,
        );
      }
      for (let i = 0; i < 4; i++) {
        const f = frames[Math.floor((i * (frames.length - 1)) / 3)];
        ctx.fillText(clock(f.time), (i * (plot - 55)) / 3, height - 5);
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [history]);
  return (
    <canvas
      ref={ref}
      className="liquidity"
      role="img"
      aria-label="Recorded resting liquidity by time and price, with midpoint overlay"
    />
  );
}

export function Phase({ history }: { history: History[] }) {
  const h = history.slice(-70);
  return (
    <svg
      viewBox="0 0 350 220"
      className="phase"
      role="img"
      aria-label="Market entropy phase plane"
    >
      <line x1="35" x2="335" y1="115" y2="115" stroke="#2a3945" />
      <line x1="185" x2="185" y1="15" y2="205" stroke="#2a3945" />
      <text x="42" y="30">
        CHAOS BUILDING
      </text>
      <text x="215" y="30">
        DISORDER
      </text>
      <text x="42" y="195">
        ORDERED
      </text>
      <text x="204" y="195">
        STRUCTURE FORMING
      </text>
      <polyline
        points={h
          .map(
            (p) =>
              `${35 + p.market_entropy * 300},${115 - Math.max(-0.1, Math.min(0.1, p.slope)) * 800}`,
          )
          .join(" ")}
        stroke="#59ddb2"
        strokeWidth="1.7"
        fill="none"
      />
      {h.length > 0 && (
        <circle
          cx={35 + h.at(-1)!.market_entropy * 300}
          cy={115 - Math.max(-0.1, Math.min(0.1, h.at(-1)!.slope)) * 800}
          r="5"
          fill="#59ddb2"
        />
      )}
      <text x="160" y="218">
        MARKET ENTROPY →
      </text>
    </svg>
  );
}
