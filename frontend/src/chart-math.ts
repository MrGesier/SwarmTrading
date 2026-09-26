import type { Candle } from "./types";

export function aggregateCandles(
  candles: Candle[],
  interval: number,
): Candle[] {
  const result: Candle[] = [];
  for (const c of [...candles].sort((a, b) => a.time - b.time)) {
    if (
      ![c.time, c.open, c.high, c.low, c.close, c.volume].every(Number.isFinite)
    )
      continue;
    const bucket = Math.floor(c.time / interval) * interval,
      last = result.at(-1);
    if (last?.time === bucket) {
      last.high = Math.max(last.high, c.high);
      last.low = Math.min(last.low, c.low);
      last.close = c.close;
      last.volume += c.volume;
    } else result.push({ ...c, time: bucket });
  }
  return result;
}
export function windowRange(
  first: number,
  last: number,
  seconds: number,
  end: number | null,
) {
  const span = Math.max(1, last - first),
    width = seconds === 0 ? span : Math.min(span, Math.max(1, seconds));
  const right =
    end === null ? last : Math.max(first + width, Math.min(last, end));
  return { from: right - width, to: right, width };
}
export function extent(values: number[], zero = false): [number, number] {
  const clean = values.filter(Number.isFinite);
  let lo = clean.length ? Math.min(...clean) : 0,
    hi = clean.length ? Math.max(...clean) : 1;
  if (zero) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  const pad = (hi - lo || Math.max(Math.abs(hi) * 0.001, 1e-6)) * 0.08;
  return [lo - pad, hi + pad];
}
export function axisDomain(
  bounds: [number, number],
  zoom: number,
): [number, number] {
  const center = (bounds[0] + bounds[1]) / 2,
    half = (bounds[1] - bounds[0]) / 2 / zoom;
  return [center - half, center + half];
}
