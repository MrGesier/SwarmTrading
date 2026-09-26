# Visual and interaction audit — 2026-09-26

Scope: rendered market, diagnostics and Factory charts; trading calculations remain unchanged.

| View | Previous problem | Implemented behavior |
| --- | --- | --- |
| Price / trigger zones | Hardcoded last 100 five-second bars; auto axes jumped; no navigation; fixed bar widths | Full available candle buffer, real OHLCV aggregation (5/15/30/60/300 seconds), time window, pan, horizontal zoom, vertical zoom, locked axis, linear/log/percentage, OHLCV inspection |
| Trigger overlays | Current hypothetical levels looked like historical entries; empty sides could crash the chart | Optional current overlays, hidden in historical view, safe empty sides, out-of-range notice; explicitly not executed entries |
| Liquidity | Last 100 snapshots evenly spaced; no controls; fine labels | Observed timestamps, gaps visible, time navigation, price extent in bp, center lock, inspect time/price/quantity, consistent palette |
| Trigger density | Tiny labels and clipped rows, hardcoded extent | Scrollable readable rows, ±5/10/20/30 bp extent, price/bp units, density scale. Snapshot, not time series |
| Entropy and metric histories | Decorative curves without values or axes | Full entropy chart; metric thumbnails expand to an inspectable chart. Measurement-index axis used when timestamps are not supplied; never called seconds |
| Factory paper PnL | Auto-normalized thumbnails without time/scale | Timestamped plots, hover readout, zero reference, zoom/lock, unavailable data remain gaps; current epoch only, not a cumulative invested portfolio |
| Factory evolution | Nulls coerced to zero; no cycle axis | Missing values retained, explicit cycle axis and window, vertical controls |
| Phase plane | Slope silently clamped, no period selection | Observed period, selectable slope range, clipped rather than falsified values, point details |
| Trigger surface | Dense matrix difficult to read | Adjustable matrix size with horizontal scroll, readable cells, explicit snapshot semantics |
| Family votes / consensus / normalized gauges | Can be mistaken for performance or time charts | Keep meaningful fixed fraction/[-1,1]/[0,1] domains and existing explanatory help; no artificial timeframe or logarithm for signed fractions |
| Multi-horizon component | Fixed last 90 samples | Shared period controls (component is not currently mounted by main routing) |

## Interaction conventions

- Period = visible historical window; candle duration = OHLCV grouping; strategy horizon = unchanged engine analysis. They are independent.
- Window controls offer 1/5/15 minutes, 1/24 hours and all **available** observations. They cannot fetch nonexistent history. Engine currently retains at most 180 five-second candles and sends 180 market snapshots; replay has its own smaller capture.
- Pan freezes the visible time endpoint; follow resumes incoming observations. If the engine evicts old observations, the accessible window clamps to retained history.
- Lock axis fixes vertical bounds; zoom operates around their center. Percentage reference is fixed at chart opening. Log is offered only for the positive price series, not PnL.
- Price VWAP uses the entire retained source buffer, not the selected zoom window; it is not a session/exchange VWAP. Source-buffer eviction changes its anchor.
- First/last aggregated candles may be partial. Missing candles are not synthesized. Charts do not modify risk, PnL, fees, strategy horizon or orders.
- Historical database-backed PnL remains descriptive: changing active cohorts and different G0 windows are still disclosed in Factory.

## Validation

Node tests cover OHLCV buckets/order/volume/immutability, missing data, viewport clamps and pause, constant/negative axes and vertical zoom. Build includes TypeScript checking. Required backend checks ensure presentation changes leave the engine contract intact. Browser checks exercise period/interval/unit selection, keyboard axis locking, Factory data and narrow/wide layout.

## Remaining data limitations

Long-duration selections do not add a historical candle download service. Real executed trade markers cannot be inferred from trigger levels. Cohort means are not portfolio equity. A historical funding-adjusted invested portfolio and exchange-level execution markers require separate underlying data work, not graphical interpolation.
