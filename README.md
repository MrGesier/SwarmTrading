# Swarm Trade by Mister Gésier — V0.3

A local, read-only market intent terminal with a Pyrenean mountain / market-line identity built from the V0.2 Product Spec. Python/FastAPI computes the shared state; React/TypeScript displays it. No exchange keys, account access, or live order execution.

> **Project goal:** build an explainable, multi-scale market-intent engine that combines order-book microstructure, strategy swarms, entropy, liquidity geometry and horizon-aware forecasting. The current build is research/paper-analysis software only; it does not place live orders.

## Roadmap / design docs

- [`docs/V0.2_PRODUCT_SPEC.md`](docs/V0.2_PRODUCT_SPEC.md) — terminal, Crowd Shadow, trigger surfaces, liquidity landscape and replay architecture.
- [`docs/V0.3_MULTISCALE_ALPHA.md`](docs/V0.3_MULTISCALE_ALPHA.md) — true multi-horizon state, consensus term structure, propagation front, trade odds and future data sweeps.
- [`AGENTS.md`](AGENTS.md) — implementation rules and priorities for Codex/AI coding agents.


## Start

On Windows, double-click **Start SwarmTrade.cmd**. Requires Python 3.12+ and Node.js 20.19+ (or 22.12+). The launcher installs missing dependencies, starts hidden local servers, and opens **http://localhost:3000**. The backend API is **http://127.0.0.1:8000/docs**. Logs live in `data/`.

Alternatively, run these in separate terminals from this project:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run dev
```

For manual setup: `python -m venv .venv`, then `.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt`, and `npm ci` in `frontend/`.

## Use

- **Simulation** starts immediately with deterministic synthetic market events. It is always visibly labeled. These prices are not current market prices.
- Choose **Binance live** for public spot depth, trades, and book-ticker streams. BTCUSDT, ETHUSDT, and SOLUSDT are supported. Live mode never silently falls back to simulation.
- Select a **1s, 5s, 30s, 1 minute, or 3 minute horizon** to scope the consensus, swarm bars, and strategy table. Intent, entropy, trigger density and effective count now use the selected horizon’s own feature and signal histories.
- **Market cockpit** shows independently selectable 1s–3m OHLCV candles built from received trades, received-window VWAP, a midpoint and trigger overlay, recorded resting-liquidity heatmap, book metrics, swarm, entropy, and explanatory signal transitions.
- **Intent lab** reevaluates the same genomes for changes to price, volatility, and flow. It includes a phase plane, consensus by horizon, and liquidity along trigger paths.
- **Swarm lab** filters strategies by family and horizon. Click a genome for its actual parameters, signal, and decorrelated weight.
- **Replay lab → Capture session** freezes up to the latest 300 derived frames from the current session. Play, pause, change speed, or seek with the slider/candles. Every panel uses the selected historical state. Reloading a capture replaces the replay window.
- The header download button exports the current stream's state as JSON (not the replay cursor) and flushes its event recorder.

## Engine and data

`backend/engine.py` contains the exchange-independent order book and engine. `backend/main.py` contains the Binance adapter, seeded simulator, Parquet recorder and API. `backend/replay.py` rebuilds states from raw events with the same engine.

Binance depth initialization opens and buffers the stream before the REST snapshot, discards already-covered events, requires an update bridging `lastUpdateId + 1`, checks every following sequence, and resnapshots after gaps, crossed books, queue overflow, or reconnect. The book is not healthy until bridged. Data more than three seconds old triggers RISK_OFF. Frontend disconnects also visibly suppress intent.

The public adapter follows Binance's [Spot WebSocket streams documentation](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams). Exchange connectivity depends on network and regional access.

Raw snapshot, depth, trade, quote, and engine-clock events are recorded under `data/<mode>-<symbol>-<session>/` as Zstandard-compressed Parquet parts. Each part stores receive time and the original event payload. Recording happens for simulation as well as live data. Buffered events flush at batch thresholds, export, and graceful shutdown; abrupt process termination can lose the current unflushed batch. Recordings are retained until manually removed; monitor available disk space during extended runs.

Replay a persisted recording:

```powershell
cd backend
..\.venv\Scripts\python.exe replay.py ../data/RECORDING-DIRECTORY --output ../data/replayed.jsonl
```

The browser's replay uses captured state frames; the CLI reconstructs states from raw events, using recorded calculation-clock events. This preserves live calculation timing and avoids future candle mutation. Persistent archive selection in the browser is not implemented in V0.2.

## Model definitions and limits

- 320 explicit genomes: 8 families × 5 horizons × 8 threshold/gain variants. Families: momentum, mean reversion, breakout, trend, order flow, microprice, book pressure, volatility.
- Effective N is `(trace(C)²) / sum(C²)` for the rolling signal correlation matrix; equivalent to the eigenvalue participation ratio. Constant series are excluded. Inverse squared-correlation exposure assigns weights normalized to effective N. Weights refresh every five calculation ticks over 120 samples. Highly redundant genomes often produce effective counts around 2–5, rather than an invented 37.4.
- Swarm entropy is normalized entropy of weighted short/neutral/long support. Market entropy is the equal-weight mean of price-sign, aggressor-volume and depth-distribution entropy. Other entropy measures in later sections of the spec are not implemented.
- Signals are transparent tanh-based feature functions with neutral thresholds. Intent combines consensus (70%), flow (15%), and weighted book imbalance (15%), then applies thresholds with a three-update dwell. Health overrides the dwell immediately. These are **uncalibrated heuristics**, not learned probabilities, proven alpha, or investment recommendations.
- The price perturbation engine changes return-based inputs; it holds the book and microprice feature fixed. Volatility and flow can be perturbed separately. Trigger density sums effective weight for sign changes, including neutral transitions. It is sensitivity analysis, not a prediction of future strategy orders.
- Depth metrics and heatmaps use the top 40 levels per side. Path resistance outside that observed region is a lower bound. Heatmaps show resting liquidity, not cancellation, spoofing, or replenishment classifications.
- Features use receive-time clocks to match replay information availability. No claim of synchronized cross-venue exchange clocks or calibrated lead/lag behavior.
- Candles begin when the stream starts; no historical candles are mixed into a live session. Volatility is the standard deviation of recent sampled log returns in basis points per calculation interval, not annualized volatility.
- Live observation and recording continue for each selected symbol/mode for the backend's lifetime. Derived state memory is bounded at 1,200 frames per session. Stop the backend to stop recording.

The spec's V0.3–V0.5 and later modules remain future work: paper execution and realized cost accounting, calibrated scenario probabilities, historical analog search, learned weights/meta-models, strategy evolution, multi-input trigger surfaces beyond price × volatility, multi-venue/futures feeds, funding/OI, and authenticated execution. No placeholders pretend to implement these.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q
cd frontend
npm run build
```

Tests cover sequence bridging, stale updates, deletes, gap recovery, crossed books, effective-count redundancy, entropy limits, raw replay equality, immutable historical candles, immediate RISK_OFF, three-minute warm-up, selected-horizon surface consistency, and partial-depth cost calculations.

Both servers bind to loopback. The app is intended for a trusted single-user local workstation; do not expose these development servers publicly. A production service needs authentication, retention policies, operational monitoring, and validated model research.


## Mister Gésier upgrade

- **New identity:** `frontend/public/mister-gesier-logo.png`, a Pyrenean ridge combined with a price line and candlesticks. The icon and favicon share the same asset; the visible name is “Swarm Trade by Mister Gésier”.
- **French tooltips:** question-mark buttons explain the main metrics, panels, horizon selection, book physics, and advanced analyses. Available on hover, keyboard focus, and touch; Escape dismisses them.
- **Five horizons:** 1s / 5s / 30s / 60s / 180s. Each requires the corresponding observed history span before its genomes leave neutral. Simulation seeds 200 seconds of synthetic history; live mode waits for real observations. A reconnect resets the engine’s history and warm-up rather than bridging unknown data gaps. The selected consensus sparkline now uses that horizon’s actual historical consensus.
- **Trigger surface:** 54 counterfactual states, 9 price offsets from −24 to +24 bp and 6 volatility multipliers from 0.5× to 2×. Uses selected-horizon weights and the same strategy functions. Recomputed every two seconds in Intent Lab.
- **Consensus fragility:** minimal contrary price shift, searched in 1 bp steps up to 50 bp, that changes the selected consensus sign. Neutral baselines (absolute consensus < 0.05) and out-of-range inversions are distinguished.
- **Execution-cost preview:** walks the visible bid and ask levels for a configurable notional and fee assumption. Shows VWAP, spread/depth cost and fill fraction. Midpoint is taken from the same book used for the walk. This is a snapshot estimate, not paper execution; it excludes latency and adverse selection. No orders are submitted.
- **Visible-liquidity metrics:** top-five concentration within the top forty levels and largest adjacent price gap above/below the market.

The surface and fragility are local model sensitivities. They do not provide calibrated probabilities. Flow, OFI, book pressure and entropy now have separate time windows per horizon. Horizons still share the same market observations; statistical independence is not claimed.

## V0.3 delivered

- Separate candle interval, prediction horizon and optional slower context.
- Local horizon memory, effective population, entropy and trigger sensitivity.
- Consensus term structure and horizon/time propagation heatmap.
- Direction and short entry alignment shown separately, with stale-data risk override.
- Offline cost-adjusted triple-barrier labels and purged chronological calibration evaluation in `backend/forecasting.py`. Probabilities remain unavailable in the live app.

Desktop installation: run `powershell -ExecutionPolicy Bypass -File install-desktop.ps1`. Then use **SwarmTrading - Mister Gesier** to start and **Arreter SwarmTrading** to flush recordings and stop. The installed build needs no terminal commands. Do not move its folder after creating shortcuts.

See `docs/VALIDATION_V0.3.md` for validation scope and research limits.
