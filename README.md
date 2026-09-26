# Lancement courant : Hyperliquid paper

Double-cliquer **Darwin - Hyperliquid Paper** sur le bureau, ou `Demarrer-Darwin-Paper.cmd`. Données actuelles Hyperliquid, ordres simulés localement, aucun wallet requis. Voir [HYPERLIQUID_PAPER.md](HYPERLIQUID_PAPER.md) pour la boucle, les limites et le futur réel.

> Local V1 hardening: see [V1_VALIDATION.md](V1_VALIDATION.md) for Windows launch, executed checks, provider status and remaining work. Current target branch: `darwin-v0.11-factory-evolution`; do not merge PR #1.

# Swarm Trade by Mister Gésier — V0.11 Evolution Observatory + Factory Crew

A local market-intent and strategy-evolution terminal with a Pyrenean mountain / market-line identity. Python/FastAPI computes the shared state and Darwin paper experiments; React/TypeScript displays them. Authenticated execution is isolated behind a disabled-by-default Hyperliquid adapter.

## Start

From a local checkout, double-click **Start SwarmTrade.cmd**. Requires Python 3.11+ (3.12 recommended) and Node.js 22+ with npm for the frontend build. The launcher installs runtime dependencies, rebuilds missing/stale frontend assets and opens **http://127.0.0.1:8000/factory**. A single process serves the API, UI and WebSockets. Simulation is the offline default; the launcher sets `HYPERLIQUID_ENABLED=false`.

Use **Stop SwarmTrade.cmd** for a graceful stop. **Check SwarmTrade.cmd** provides diagnostics; **Repair SwarmTrade.cmd** reinstalls dependencies/rebuilds without deleting research databases. Logs: `data/launcher.log`, `data/backend.log`, `data/backend-error.log`.

PowerShell equivalents from the repository:

```powershell
.\start.ps1
.\stop.ps1
.\start.ps1 -Repair
```

## Configuration

No `.env` is required for deterministic paper research. `.env.example` is the versioned template; `.env` is private and ignored by Git. To configure providers, copy the template **only if `.env` does not already exist**, then edit it locally. Never overwrite an existing file containing credentials.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Restart Darwin after changing environment settings. Existing process environment variables take precedence over `.env`.

- `DARWIN_AUTOSTART_MODE=live`: current public Hyperliquid market data with paper execution. Synthetic sessions are not exposed by the application.
- `DARWIN_AUTO_EPOCH_ENABLED=true`, `DARWIN_EPOCH_SECONDS=86400`: automatic daily selection, subject to evidence gates; the initial schedule survives restart.
- `DARWIN_PAPER_FEE_BPS=3.5`: modeled fee per fill, not a verified Hyperliquid account tier. Changing accounting settings with an existing checkpoint is rejected; keep original settings or use a separate data directory.
- `DARWIN_LLM_ENABLED=true`: allows configured research providers; without a key the deterministic fallback remains usable. Set `false` to disable provider calls explicitly.
- `DARWIN_LLM_MAX_OUTPUT_TOKENS=4096`, `DARWIN_LLM_DAILY_BUDGET_USD=1`: bounded output and estimated 24-hour reservations **per symbol/mode database**, excluding OpenBot. Not a global billing cap.
- `HYPERLIQUID_ENABLED=false`: keep execution disabled. The Windows launcher enforces this value.

## Read PnL and recursive progress

In **Factory**, the **PnL paper net de frais** panel shows mean independent-account net PnL in USD/bp, deducted fees, fixed G0 and descendants. These are not portfolio returns. The minute-sampled curves restart at each epoch; recorded epoch comparisons remain below. An explicit warning identifies mismatched G0/control windows.

The **Research cycle** panel shows the countdown, minimum observation/trade requirements, last completed cycle and generation. Research automatically measures, selects, mutates one bounded gene, evaluates descendants on the next window and repeats. Repeated proposals trigger bounded exploration; stagnation queues an engineering task. Automatic execution/adoption of code changes is **not implemented**.

**Evolution Observatory** contains the frozen G0/descendant comparisons. A comparison remains WAITING until a full common window exists. Fees, visible-book VWAP and partial fills are modeled; funding, queue/latency effects and endogenous market impact are not. No live readiness or durable profitability is claimed. See [AUTONOMY_AND_LIVE.md](AUTONOMY_AND_LIVE.md).

Run three accelerated synthetic cycles in isolated temporary databases:

```powershell
.\.venv\Scripts\python.exe backend\replay_research.py --output replay-report.json --epochs 3
```

This verifies research mechanics, not trading performance. See [V1_VALIDATION.md](V1_VALIDATION.md) for validation history and limitations.

## Use

- **Simulation** starts immediately with deterministic synthetic market events. It is always visibly labeled. These prices are not current market prices.
- Choose **Live** for Hyperliquid public perp `l2Book`, trades and asset-context streams. BTCUSDT, ETHUSDT, and SOLUSDT map to BTC, ETH and SOL perps. Live mode is still paper execution unless the separate Hyperliquid execution gate is explicitly enabled.
- Select a **1s, 5s, 30s, 1 minute, or 3 minute horizon** to scope the consensus, swarm bars, and strategy table. Market intent, entropy, trigger density, and effective count use the full population and are global metrics.
- **Marché** shows 5-second OHLCV candles built from received trades, received-window VWAP, a midpoint and trigger overlay, recorded resting-liquidity heatmap, book metrics, swarm, entropy, and explanatory signal transitions.
- **Intent lab** reevaluates the same genomes for changes to price, volatility, and flow. It includes a phase plane, consensus by horizon, and liquidity along trigger paths.
- **Swarm lab** filters strategies by family and horizon. Click a genome for its actual parameters, signal, and decorrelated weight.
- **Replay lab → Capture session** freezes up to the latest 300 derived frames from the current session. Play, pause, change speed, or seek with the slider/candles. Every panel uses the selected historical state. Reloading a capture replaces the replay window.
- The header download button exports the current stream's state as JSON (not the replay cursor) and flushes its event recorder.

## Engine and data

`backend/engine.py` contains the exchange-independent order book and engine. `backend/marketdata/hyperliquid.py` contains the default cloud market-data adapter; `backend/main.py` hosts the seeded simulator, optional legacy Binance adapter, Parquet recorder and API. `backend/replay.py` rebuilds states from raw events with the same engine.

Binance depth initialization opens and buffers the stream before the REST snapshot, discards already-covered events, requires an update bridging `lastUpdateId + 1`, checks every following sequence, and resnapshots after gaps, crossed books, queue overflow, or reconnect. The book is not healthy until bridged. Data more than three seconds old triggers RISK_OFF. Frontend disconnects also visibly suppress intent.

The public adapter follows Binance's [Spot WebSocket streams documentation](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams). Exchange connectivity depends on network and regional access.

Raw snapshot, depth, trade, quote, and engine-clock events are recorded under `data/<mode>-<symbol>-<session>/` as Zstandard-compressed Parquet parts. Each part stores receive time and the original event payload. The application records current Hyperliquid data; synthetic generators remain only in offline tests. Buffered events flush at batch thresholds, export, and graceful shutdown; abrupt process termination can lose the current unflushed batch. Raw recording is configurable with `DARWIN_RECORD_RAW`; each session keeps at most `DARWIN_RECORD_MAX_PARTS` part files (240 by default) to prevent unbounded disk growth. Set the cap to `0` only if you intentionally want unlimited parts.

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

Still future work: calibrated scenario probabilities, historical analog search, multi-input trigger surfaces, robust account reconciliation and explicitly governed champion-to-execution promotion. V0.11 adds a persistent Evolution Observatory and role-specific Factory crew on top of V0.10 Genome V2, while preserving the OpenAI-Brain / deterministic-capital architecture.

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
- **Execution-cost preview:** walks the visible bid and ask levels for a configurable notional and fee assumption. Shows VWAP, spread/depth cost and fill fraction. Midpoint is taken from the same book used for the walk. This remains a snapshot estimate for the cockpit; Darwin has a separate paper-execution loop. It excludes latency and adverse selection. No real orders are submitted by this preview.
- **Visible-liquidity metrics:** top-five concentration within the top forty levels and largest adjacent price gap above/below the market.

The surface and fragility are local model sensitivities. They do not provide calibrated probabilities. Short-horizon flow and book features remain shared context across horizons; the horizon-specific return and its normalization differ. The five horizons are not five fully independent forecasting models.

## V0.4 — Darwin agentic evolution loop

SwarmTrade now contains a **paper-first strategy evolution engine**. The original 320 transparent genomes are the generation-0 population. Every active genome receives the same market state and trades an isolated paper account using visible order-book levels plus a configurable fee assumption. This gives Darwin comparable PnL, return, turnover, drawdown, closed-trade count and win-rate evidence instead of asking an LLM which strategy “looks best”.

Open **Recherche et trades** in the sidebar to see the live leaderboard, current champion, selection history, cumulative lessons and Hyperliquid execution status. A Judge epoch can be triggered manually for research; the automatic interval defaults to 24 hours (`DARWIN_EPOCH_SECONDS=86400`). A Judge epoch only runs when at least one strategy has the configured minimum sample and closed-trade evidence. At an accepted epoch Darwin:

1. freezes the common paper window and closes remaining paper positions through the visible book;
2. computes risk-adjusted fitness deterministically;
3. promotes a champion when promotion evidence is sufficient;
4. kills sufficiently bad strategies in the lower tail;
5. mutates gain/threshold around the strongest survivors to create challengers;
6. writes evaluations and structured lessons to a per-market SQLite memory database;
7. resets surviving paper accounts so the next generation is compared over a common window.

The long-term memory is stored under `data/darwin-<mode>-<symbol>.sqlite`. It records strategy lineage, frozen evaluations, selection epochs and evidence-backed lessons. Conversation text is not used as performance memory.

### Hyperliquid boundary

`backend/execution/hyperliquid.py` integrates the official `hyperliquid-python-sdk`. **Execution is disabled by default.** V0.4 does not automatically send a Darwin champion to the exchange. This is intentional: the current live market-data adapter is Binance spot while the intended execution venue is Hyperliquid perps, so promotion to real trading should wait until the Hyperliquid market-data/reconciliation path is added and testnet behaviour is validated.

Copy `.env.example` to `.env` when you are ready to configure the connector. Prefer a dedicated Hyperliquid API wallet. Mainnet requires all of the following: `HYPERLIQUID_ENABLED=true`, `HYPERLIQUID_NETWORK=mainnet`, credentials, and the explicit acknowledgement `HYPERLIQUID_MAINNET_ACK=I_UNDERSTAND_LIVE_TRADING`. Keep `.env` private; it is git-ignored.

Useful Darwin environment variables are documented in `.env.example`. Defaults are intentionally conservative and are research assumptions, not claims about current exchange fees or expected profitability.


### V0.4 human agent map

The **Darwin Lab** now exposes the architecture as named, color-coded agents. This is not cosmetic: the backend publishes the same registry at `/api/agents/state`, including the exact code path and capital permission for every agent.

| Color | Agent | Role | Code | Capital permission |
|---|---|---|---|---|
| `#9B7BFF` | ATLAS | CEO / supervisor | `backend/darwin/supervisor.py` | none |
| `#55C7FF` | CURIE | scientist / experiment hypothesis | `backend/darwin/scientist.py` | none |
| `#43D69E` | EVOLVE | strategist / mutation | `backend/darwin/strategist.py` | none |
| `#38D7E8` | FORGE | paper worker | `backend/darwin/paper.py` | paper only |
| `#F4C95D` | JUDGE | deterministic evaluator | `backend/darwin/judge.py` | none |
| `#EE78C5` | MNEMOSYNE | long-term memory | `backend/darwin/memory.py`, `store.py` | none |
| `#FF6B6B` | CERBERUS | hard risk gate | `backend/execution/hyperliquid.py` | gatekeeper |
| `#FF9F43` | HERMES | Hyperliquid executor | `backend/execution/hyperliquid.py` | testnet or explicitly guarded live |

The research loop is `ATLAS → CURIE → EVOLVE → FORGE → JUDGE → MNEMOSYNE → ATLAS`. The capital path is separate: an approved intent must pass `CERBERUS → HERMES`. CURIE/EVOLVE may later use an LLM to propose hypotheses, but JUDGE, CERBERUS and HERMES remain deterministic boundaries.

---

## V0.5 — Agentic cloud paper lab

V0.5 adds a cloud-ready Darwin runtime. The safe default is **real Hyperliquid mainnet public market data + paper execution only**. No wallet is needed to run research.

### Runtime architecture

| Agent | LLM | Responsibility | Deterministic boundary |
|---|---|---|---|
| ATLAS | GPT-5.6 Sol | Chooses which evidence-rich parents deserve the next experiment budget | Cannot place orders or rewrite metrics |
| CURIE | GPT-5.6 Sol | Writes one falsifiable controlled experiment | Only `threshold` or `gain` can be tested in V0.5 |
| EVOLVE | GPT-5.6 Luna | Refines local mutation factors | `StrategistAgent` clamps and constructs children |
| FORGE | GPT-5.6 Luna | Audits paper-execution/regime quality | Fills/PnL are calculated by `PaperPopulation` |
| JUDGE | GPT-5.6 Luna | Audits overfit/sample risk | KEEP/KILL/SCALE is frozen by deterministic `judge.py` |
| MNEMOSYNE | GPT-5.6 Luna | Compresses epochs into reusable lessons | Raw epoch evidence stays in SQLite |
| CERBERUS | GPT-5.6 Luna | Reviews an external-order intent | Hard risk checks have final authority |
| HERMES | GPT-5.6 Luna | Explains an already approved execution | Cannot change side, size or venue |

The eight brains live in `backend/agents/roles.py`; the shared structured-output runtime is `backend/agents/llm.py`.

### Hyperliquid data

`backend/marketdata/hyperliquid.py` subscribes to the public `l2Book`, `trades`, and `activeAssetCtx` feeds. `Session` normalizes these events into the existing SwarmTrade engine, so all genomes see the same Hyperliquid perp market stream.

Safe cloud defaults:

```text
DARWIN_AUTOSTART_SYMBOL=BTCUSDT
DARWIN_AUTOSTART_MODE=live
DARWIN_MARKET_SOURCE=hyperliquid
HYPERLIQUID_DATA_NETWORK=mainnet
HYPERLIQUID_ENABLED=false
```

`live` means **live market data**, not live capital. Execution is still paper while `HYPERLIQUID_ENABLED=false`.

### LLM activation

All eight agents use one Vercel AI Gateway key. Add only this secret to the host:

```text
AI_GATEWAY_API_KEY=...
```

Without the key, Darwin continues paper trading with deterministic fallbacks and the UI reports each brain as `WAITING_KEY`. This makes an LLM outage fail safe rather than stop market observation.

### Railway deployment

The repository includes `Dockerfile` and `railway.toml`. The Docker image:

1. builds the Vite dashboard,
2. installs the Python backend,
3. serves UI + API from one FastAPI process,
4. starts the Hyperliquid paper session automatically,
5. stores Darwin SQLite state under `DARWIN_DATA_DIR` (`/data` in Docker).

For durable memory across redeployments, attach a Railway Volume at `/data`.

Health endpoint: `/api/health`.

### Capital boundary

Paper research starts without credentials. Do **not** set `HYPERLIQUID_ENABLED=true` for the research deployment. Hyperliquid wallet credentials are intentionally unnecessary for V0.5 paper operation.


## V0.6 — Research Desk and robustness gates

Darwin V0.6 treats strategy search as a multiple-testing research problem rather than a raw leaderboard. FORGE now records trade expectancy, profit factor, payoff ratio, per-trade dispersion/z-score and entry-regime results. JUDGE keeps both raw fitness and evidence-weighted fitness; positive results are shrunk toward zero until trade count and elapsed-time evidence accumulate. With hundreds of simultaneous genomes, `SCALE` also requires the champion's closed-trade z-score to clear the deterministic `sqrt(2 log M)` selection-bias guard (`M` = active strategies). This is a conservative heuristic guardrail, not a formal p-value.

A second robustness gate recalculates the result under a configurable degraded-fee assumption (`DARWIN_FEE_STRESS_MULTIPLIER`, default 1.5×). A strategy cannot `SCALE` if this stressed result is non-positive when `DARWIN_REQUIRE_POSITIVE_FEE_STRESS=true`. The live Research Cockpit shows evidence-ready counts, the current z threshold, regime, market benchmark, LLM calls/tokens, and the experiment ledger.

Every controlled CURIE/EVOLVE test is persisted in the `experiments` table with parent, children, parameter, factors, hypothesis, confidence, winner and resolved evidence. Clicking a genome in Darwin Lab opens its lineage and frozen epoch history. LLM calls are persisted in `agent_runs`; the dashboard reports 24-hour calls and token usage. Strategy history is therefore inspectable independently from the current conversation.

The population is bounded by `DARWIN_MAX_ACTIVE_STRATEGIES` (default 400) and `DARWIN_MAX_NEW_PER_EPOCH` (default 12). `DARWIN_AUTO_EPOCH_ENABLED=false` pauses autonomous evolution while allowing paper observation to continue. A common-window BTC market benchmark is reset with every epoch and the leaderboard reports `alpha_vs_market_bps`; this benchmark is diagnostic and does not directly alter selection.


## V0.7 — Darwin Factory / Troll Mode

A second Darwin UI is available at `/factory`. It visualizes the real agent loop as an animated troll factory. Events are persisted in SQLite and streamed over `/ws/factory`; the page includes impact inspection, strategy lineage inspection and event playback. See `FACTORY_ARCHITECTURE.md`.


## V0.9 — OpenAI Brain / Codex Engineer

Darwin now separates **reasoning**, **measurement**, **capital authority**, and **software engineering**. ATLAS and CURIE default to `gpt-5.6-sol`; EVOLVE and the optional JUDGE critic default to `gpt-5.6-terra`; MNEMOSYNE defaults to `gpt-5.6-luna`. FORGE, CERBERUS and HERMES are true deterministic components and do not call a model to calculate paper PnL, authorize risk, or submit an order.

The common `AgentBrain` runtime supports direct OpenAI Responses API structured JSON, the previous optional Vercel AI Gateway path, and deterministic brains. Per-agent runtime/model/reasoning can be overridden through environment variables. Every model run stores runtime, provider, model, reasoning effort, prompt version, token usage, latency, result status and an estimated API cost; secrets are never returned by the state endpoints.

A separate **CODEX ENGINEER** sits above the Troll Factory. It can prepare an auditable software-engineering task pack from current Darwin evidence (`POST /api/engineer/task`) but has `CODE_ONLY_NO_CAPITAL` authority, no exchange credentials, and `auto_apply=false`. V0.9 intentionally does not let Codex merge/deploy changes or alter risk/execution automatically.

Useful V0.9 endpoints:

- `GET /api/brains/state?symbol=BTCUSDT&mode=live` — brain policy, runtime/model status, usage/cost and engineer state.
- `GET /api/engineer/state` — CODEX ENGINEER boundary and recent prepared tasks.
- `POST /api/engineer/task` — freeze a code-only task pack from current research evidence.
- `GET /api/factory/state` — Troll Factory state including brain classes and Codex Engineer.

See `OPENAI_BRAIN_ARCHITECTURE.md`, `AGENT_ARCHITECTURE.md`, `FACTORY_ARCHITECTURE.md`, `CODEX_ENGINEER.md` and `CODEX_HANDOFF.md`.

For a local engineering pass, double-click **Run Codex Engineer.cmd** after installing/logging into Codex CLI. The script uses `codex exec --sandbox workspace-write`, exports a current Darwin task pack when the local API is reachable, and explicitly forbids automatic trading/deployment changes. Codex also discovers the root `AGENTS.md` contract automatically.

## V0.9 — OpenBot Bridge

V0.9 adds an optional bridge to `CopilotKit/OpenBot` for the four cognitive coworkers: ATLAS, CURIE, EVOLVE and MNEMOSYNE. OpenBot remains outside the authoritative trading/capital path. See `OPENBOT_BRIDGE.md`.

Install only when using OpenBot:

```bash
pip install -r backend/requirements-openbot.txt
```

Bridge status:

```text
GET /api/openbot/state
```


## V0.10 — Genome V2 + Vibe Factory

V0.10 expands Darwin from threshold/gain tuning into bounded execution-policy research while keeping FORGE deterministic. See `GENOME_V2.md`. CURIE can now test one of eight genes at a time, and the Factory visualizes the resulting hypothesis → mutation → evidence → Judge → memory flow with moving event tokens, Judge stamps, champion bursts, filters and a playback scrubber.

OpenBot coworkers remain advisory-only but can now request redacted research context from `GET /api/openbot/context/{agent_id}` using the configured OpenBot token. The response intentionally excludes exchange credentials and execution methods.

Raw event recording can be disabled or bounded with `DARWIN_RECORD_RAW` and `DARWIN_RECORD_MAX_PARTS`.


## V0.11 — Evolution Observatory + Factory Crew

V0.11 makes Darwin's progress auditable over time instead of showing only the current leaderboard. `GET /api/darwin/evolution` reconstructs an epoch-by-epoch history from SQLite: champion alpha, fitness, fee-stress survival, evidence weight, drawdown, generations, family wins and Genome V2 mutation pressure. The Factory embeds the same object and displays an Evolution Observatory with `IMPROVING / FLAT / REGRESSING` trend states. These are explicitly paper-research metrics, not a prediction of future live profitability.

The visual identities are also role-specific rather than eight identical trolls: Atlas Owl, Curie Frog, Evolve Chameleon, Forge Bot, Judge Lion, Memory Octopus, Cerberus Hound, Hermes Bird and Codex Raccoon. See `EVOLUTION_OBSERVATORY.md` and `V0.11_CHANGELOG.md`.


### Navigation et journal paper

Trois vues principales : **Marché** pour les données et signaux, **Recherche et trades** pour les positions, clôtures et classements, **Factory** pour les cycles, mutations et comparaisons de rendement. Les anciens laboratoires restent dans **Diagnostics avancés**. Le sélecteur d’horizon et les indicateurs de consensus du marché ne sont pas affichés sur Darwin : ils décrivent une autre population.

Le journal conserve les 10 000 dernières clôtures paper par base symbole/mode, y compris entre les cycles et redémarrages ; l’écran affiche les 50 dernières. Chaque ligne expose le résultat net, les frais connus et la raison de sortie. Les prix affichés sont les milieux de carnet de référence, pas les prix exécutés. Les trades antérieurs à cette fonctionnalité ne sont pas reconstruits ; les frais d’une position déjà ouverte avant la mise à jour peuvent être inconnus. La sauvegarde suit les checkpoints (une interruption brutale peut perdre les dernières secondes).

JUDGE et les mutations fonctionnent automatiquement lorsque les conditions du cycle sont remplies. La commande manuelle est facultative. Les tâches d’ingénierie sont préparées automatiquement en cas de stagnation ; l’exécution et l’adoption de code autonome restent à implémenter.


### Réaction autonome aux problèmes de recherche

`DARWIN_AUTO_REPAIR_ENABLED=true` active un diagnostic chaque minute à partir des comptes mesurés. Après au moins 1 800 secondes observées et 20 clôtures par stratégie, des frais dominants chez au moins 25 % des stratégies évaluables, ou une perte supérieure à 100 bp chez au moins 50 %, avancent le prochain cycle à `DARWIN_REPAIR_INTERVAL_SECONDS` depuis le dernier cycle (3 600 s par défaut, minimum 1 800 s). Les contrôles de sélection, frais et limites de population restent inchangés. Le minuteur est reconstruit depuis le dernier cycle sauvegardé et les symptômes depuis les checkpoints.

ATLAS et CURIE reçoivent le symptôme chiffré. Les parents affectés peuvent produire de nouveaux challengers sans réactiver un compte retiré. FORGE observe ces descendants sur les données suivantes ; JUDGE les réévalue au cycle suivant, et les résultats alimentent la mémoire. Factory indique le problème et le déclenchement anticipé. Cela automatise la recherche de mutations bornées ; cela ne réécrit pas encore librement le code et ne prouve pas qu’une mutation a causé une amélioration.

Les agents nécessitent un fournisseur LLM configuré. `enabled=true` signifie autorisé, `available=true` signifie configuration présente ; seul un appel réussi vérifie la connexion. Sans clé, le repli déterministe demeure explicite. Le connecteur OpenBot optionnel utilise également un fournisseur de modèles ; son installation seule ne donne pas accès à OpenAI.


### Démonstration locale de correction de code V3

Voir [DARWIN_DEMO_V3.md](DARWIN_DEMO_V3.md). `Demarrer-Darwin-Demo.cmd` lance la Factory et son worker séparé. La démo produit un vrai diff via Codex CLI (ou un mock explicitement étiqueté), exécute des tests indépendants et laisse la proposition en attente de revue. `Verifier-Darwin-Demo.cmd` expose l’état local. OpenRouter gratuit est préparé avec quota partagé ; aucune intégration de code ou activation du trading réel n’est automatique.


### Fusion contrôlée de la PR V3

`Fusionner-Darwin-PR2.cmd` vérifie la PR #2, ses validations et son commit exact, puis demande de saisir `FUSIONNER <SHA>` avant la demande de fusion. `Fusionner-Darwin-PR2.ps1 -VerifierSeulement` effectue les contrôles sans fusion. Le script utilise GitHub CLI et le helper installé du plugin PR Completion 0.3.0 ; il s’arrête si une dépendance ou une validation manque.

Destination de cette fusion : `darwin-v0.11-factory-evolution`, pas `main`. La PR #1 vers `main` reste une étape distincte avec ses propres validations. Aucun code généré par une expérience isolée n’est intégré par ce script ; aucun déploiement ni trading réel n’est activé.


### Wallet Hyperliquid

Ouvrir **Wallet Hyperliquid** ou `http://127.0.0.1:8000/hyperliquid` : connexion du wallet navigateur ou consultation d’une adresse publique, mainnet/testnet, positions perps principales, balances spot et ordres ouverts. Lecture seule sans signature, sans stockage de clé et sans activation du réel. Voir [HYPERLIQUID_WALLET.md](HYPERLIQUID_WALLET.md).


### Journal de recherche et connexion MetaMask

Factory affiche désormais les questions et aperçus de contexte conservés à chaque appel d’agent, ses réponses, son statut (appel réseau réel, cache, repli ou historique non instrumenté), ainsi que les hypothèses et décisions des expériences. Les questions CURIE portent explicitement sur les frais, la durée des positions, les sorties et la contribution non démontrée des indicateurs. Les lots incluent des métriques compactes des parents et les comparaisons d’indicateurs terminées, sans prétendre constituer une preuve causale. Les anciennes questions ne sont pas reconstruites.

Les nouveaux trades enregistrent le régime et les indicateurs d’entrée, le brut avant frais et les excursions MAE/MFE sur les ticks observés au milieu du carnet. Les anciennes données restent inconnues. Ces attributs sont de la télémétrie : ils n’ajoutent pas de nouveaux gènes ni de preuve de rentabilité. Les noms courts sont des alias d’affichage ; les identifiants et la filiation sont inchangés.

La connexion MetaMask utilise l’extension détectée ou le QR officiel pour mobile. Elle partage uniquement l’adresse permettant de consulter Hyperliquid ; le live reste désactivé. Voir [le parcours wallet](HYPERLIQUID_WALLET.md). Les propositions de code restent soumises à revue dans Autocorrection.


### Recherche regroupée et corrections sur incident

Le laboratoire regroupe les questions dans un seul appel CURIE (au plus 3 plans), uniquement après une évolution quantifiée des observations et au plus une fois toutes les deux heures par marché. La sélection des parents et la mémoire des résultats restent déterministes. La critique LLM de JUDGE est réservée aux descendants prometteurs, au plus une fois par 24 heures. Aucun de ces avis ne remplace les décisions numériques.

Le budget gratuit local est configurable jusqu’à 50 tentatives sur 24 heures glissantes (40 par défaut), dont 4 réservées aux incidents. Les demandes ordinaires sont espacées de 30 minutes et les incidents de 5 minutes, tous marchés/processus confondus. Les échecs comptent ; les succès identiques peuvent être servis du cache. Factory affiche séparément le quota OpenRouter observé, mis en cache une heure, qui utilise le jour UTC et peut être indisponible. Les modèles restent exclusivement gratuits. Le statut d’un lot refusé n’est jamais présenté comme une réponse réelle.

Des comptes shadow gelés avant observation comparent quatre interventions pendant une heure : neutraliser imbalance (Book pressure), flux (Breakout), microprice (Microprice), ou filtrer le spread au-delà de 2 bp (Momentum). Mêmes carnets et frais, aucune promotion automatique. Une comparaison avec trop peu de trades reste insuffisante, y compris une ablation qui supprime toutes les entrées. Un redémarrage recommence une fenêtre commune sans effacer les bilans terminés.

`DARWIN_AUTO_CODE_RESEARCH=true` autorise le worker local à préparer au plus un candidat par jour lorsqu’un incident se répète sur deux cycles et que des observations Hyperliquid ont été enregistrées. Codex propose uniquement une fonction pure de filtrage du signal dans `research_policy.py`, isolée de l’exécution et inactive dans le moteur. Aucun défaut n’est injecté. La validation utilise le dernier segment des observations enregistrées, non transmis au modèle, ainsi que des contrats indépendants, les régressions et le build. Ce replay utilise de vraies observations ; il n’est pas une validation live future. Des échantillons courts restent explicitement insuffisants.

`DARWIN_RESEARCH_CREATE_DRAFT_PR=true` autorise la publication d’une branche candidate et d’une PR brouillon après les tests via Git/gh déjà authentifiés. Les options automatiques de code/publication sont désactivées dans `.env.example` et doivent être activées localement. Aucune fusion, intégration ou activation du live. Un échec de publication reste visible et le candidat est conservé. Factory présente les lots, expériences comparatives, décisions, propositions et bilans des dernières 24 heures.
