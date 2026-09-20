# Darwin Evolution Observatory — V0.11

The Observatory answers one question: **is Darwin measurably improving in paper research over time?**

It deliberately does not claim that higher paper metrics predict future live profitability. The history is an audit trail of what the research system measured.

## Persisted epoch metrics

Every completed epoch already stores its evaluations in SQLite. V0.11 turns that history into an explicit evolution series containing:

- champion id, family and generation;
- champion fitness and paper return;
- alpha versus the same-window market benchmark;
- fee-stress return;
- evidence weight and trade z-score;
- max drawdown;
- population / eligible / killed / created counts;
- a transparent **Research Quality Index**.

## Research Quality Index

The 0–100 index is only a compact visualization. Its components are returned separately and remain authoritative:

- 25% paper alpha versus benchmark;
- 25% evidence weight;
- 20% fee-stress survival;
- 15% drawdown control;
- 15% multiple-testing evidence.

Zero alpha or zero fee-stress return maps to a neutral midpoint, not a success. The index is never used to place an order and is not a live-return forecast.

## Trend state

The latest three epochs are compared with the earliest three available epochs:

- `IMPROVING` when Research Quality is +4 points or more;
- `REGRESSING` when it is -4 points or worse;
- `FLAT` between those thresholds;
- `WAITING` before six epochs exist; early/latest windows must not overlap;
- `WAITING` before the first completed epoch.

Confidence is `LOW` under 5 epochs, `MEDIUM` from 5–11, and `HIGH` from 12 epochs onward.

## Lineage and gene evolution

The Observatory also exposes:

- maximum generation reached;
- total and active genomes per generation;
- champion epochs by strategy family;
- mutation counts by Genome V2 gene;
- active median/min/max for each gene.

This makes it possible to see not only whether the score moved, but **what Darwin kept changing to get there**.

## API

```text
GET /api/darwin/evolution?symbol=BTCUSDT&mode=simulation&limit=120
```

The same object is embedded in `/api/factory/state` for the animated Factory UI.
