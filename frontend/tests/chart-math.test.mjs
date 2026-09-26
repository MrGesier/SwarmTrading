import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";
const source = await readFile(
  new URL("../src/chart-math.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText;
const { aggregateCandles, windowRange, extent, axisDomain } = await import(
  "data:text/javascript;base64," + Buffer.from(compiled).toString("base64")
);
test("OHLCV aggregation respects UTC buckets, order, volumes and source immutability", () => {
  const input = [
    { time: 10, open: 12, high: 16, low: 10, close: 15, volume: 3 },
    { time: 5, open: 11, high: 13, low: 9, close: 12, volume: 2 },
    { time: 15, open: 15, high: 17, low: 14, close: 16, volume: 4 },
  ];
  const original = JSON.stringify(input);
  assert.deepEqual(aggregateCandles(input, 15), [
    { time: 0, open: 11, high: 16, low: 9, close: 15, volume: 5 },
    { time: 15, open: 15, high: 17, low: 14, close: 16, volume: 4 },
  ]);
  assert.equal(JSON.stringify(input), original);
});
test("No synthetic candles inserted across gaps; invalid inputs skipped", () => {
  const c = { time: 0, open: 1, high: 1, low: 1, close: 1, volume: 1 };
  assert.equal(
    aggregateCandles(
      [c, { ...c, time: 300 }, { ...c, time: 310, close: NaN }],
      5,
    ).length,
    2,
  );
});
test("Window clamps to observed data and a paused end remains stable as new data arrives", () => {
  assert.deepEqual(windowRange(100, 200, 3600, null), {
    from: 100,
    to: 200,
    width: 100,
  });
  assert.deepEqual(windowRange(100, 300, 60, 200), {
    from: 140,
    to: 200,
    width: 60,
  });
  assert.deepEqual(windowRange(100, 400, 60, 200), {
    from: 140,
    to: 200,
    width: 60,
  });
  assert.equal(windowRange(100, 400, 60, 999).to, 400);
  assert.equal(windowRange(100, 400, 60, 0).from, 100);
});
test("Empty/constant/negative data produce finite, non-degenerate axes", () => {
  for (const values of [[], [0, 0], [100, 100], [-30, -20], [NaN, Infinity]]) {
    const [lo, hi] = extent(values);
    assert.ok(Number.isFinite(lo) && Number.isFinite(hi) && lo < hi);
  }
  const [lo, hi] = extent([-30, -20], true);
  assert.ok(lo < 0 && hi > 0);
});
test("Vertical zoom keeps center and reduces span", () => {
  assert.deepEqual(axisDomain([10, 30], 2), [15, 25]);
});
