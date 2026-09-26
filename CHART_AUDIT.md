# Chart and integration review — 2026-09-26

## Revised interface

The earlier navigation/axis control panel was too complex. All shared chart controls now expose only a time window (or number of cycles). Price has one candle-duration selector: 5/15/30 seconds, 1/5 minutes. It groups observed OHLCV and displays up to 60 bars within retained history. Axes adjust automatically. Freeze, reset, pan, zoom, axis locking, logarithmic/percentage selectors and matrix zoom have been removed. Metric thumbnails stay compact. Hover and contextual help retain details without permanent explanatory paragraphs.

Liquidity, entropy, phase, Factory PnL and evolution retain their own appropriate time/cycle selector. Trigger density and the trigger surface are current snapshots: a time selector would be misleading. Fixed normalized gauges retain their semantic domains. The owl replaces the flock in the application and favicon; wallet access sits below research navigation.

## Data meaning

Display intervals never change strategy horizons or trading decisions. Source candles are five seconds; at most 180 are retained. Longer grouping cannot create missing history. Partial buckets remain partial. VWAP uses the retained buffer, not an exchange session. Trigger zones are hypothetical sensitivities, not actual entries. Factory PnL is per-strategy/cohort paper performance, not invested portfolio equity; missing observations are not zero returns.

## Strategy attributes reviewed

Eight bounded genes already control entry/exit thresholds, gain, maximum holding, cooldown, stop loss, take profit and confirmation ticks. Order-flow, book-pressure and microprice families use flow, weighted imbalance and microprice; volatility and spread also enter family calculations. These are not all freely mutable weights. Existing paired paper experiments isolate imbalance, flow, microprice and spread filtering.

The next useful experiments are an entry cost/spread ceiling, minimum executable depth and flow/imbalance alignment. Each needs one bounded gene, persisted context and a paired paper comparison before promotion. No new unvalidated gene or live permission is introduced by this interface change.

## Validation scope

Required backend regression checks: 37 passed. Dependency install and production build pass. Runtime health, brains, research, Factory and engineer endpoints respond successfully; health confirms Hyperliquid source and paper-only execution. Browser integration checks cover live market rendering, candle duration independent of strategy horizon, Factory telemetry, wallet navigation and responsive layout. These checks do not establish profitability, wallet signing or exchange order execution. Observed intermittent stale-book warnings remain visible and must not be bypassed.

Observed integration snapshot: Factory exposed 52 active strategies, generation 14 and epoch 45, with 230 closed trades in the current active cohort. Mean net was approximately -3.18 USD against 3.10 USD fees per active strategy. UI rounded these consistently to -3.2 and 3.1 USD. Recursive telemetry recorded a usable LLM response and earlier paced/fallback attempts. This is a working research loop with fee drag, not demonstrated profitable self-improvement. Browser selection of 60-second candles left the strategy horizon at 5 seconds; no chart toolbar buttons remained. Compact layout had no document-level horizontal overflow. Wallet stayed read-only and testnet had no submitted validation order.
