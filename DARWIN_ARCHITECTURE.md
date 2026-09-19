# SwarmTrade Darwin V0.11

## What is implemented

```text
Market state (simulation / Binance spot)
        |
        v
320 generation-0 genomes + descendants
        |
        v
Independent paper accounts
(visible-book fills + fee assumption)
        |
        v
Common experiment window
        |
        v
Deterministic Judge
  RETEST / KEEP / KILL / SCALE
        |
        +------> SQLite experiment memory
        |        lineage + epochs + evaluations + lessons
        v
CURIE Scientist + EVOLVE Strategist
evidence-directed local mutations
        |
        v
Next common experiment window
```

The LLM is deliberately **not** allowed to decide that a strategy made money. Financial metrics and selection gates are deterministic code. CURIE/EVOLVE already expose typed hypothesis/mutation contracts; a future LLM may enrich those proposals, but the Judge remains evidence-based.

## Main modules

- `backend/darwin/signals.py` — evaluates arbitrary descendants with the same transparent signal semantics as the original vectorised engine.
- `backend/darwin/paper.py` — one isolated paper account per genome; visible-book fills, fees, PnL, turnover, drawdown and closed-trade statistics.
- `backend/darwin/scientist.py` — CURIE experiment-plan agent.
- `backend/darwin/strategist.py` — EVOLVE controlled mutation agent.
- `backend/darwin/judge.py` — deterministic evidence thresholds and risk-adjusted fitness.
- `backend/darwin/store.py` — persistent SQLite strategy lineage, frozen evaluations, epochs and lessons.
- `backend/darwin/memory.py` — converts frozen results into compact evidence-backed lessons.
- `backend/darwin/supervisor.py` — CEO loop: observe, judge, kill, promote, mutate, persist, reset.
- `backend/execution/hyperliquid.py` — isolated official-SDK execution adapter; disabled by default.
- `backend/agents/registry.py` — names, colors, roles, code paths and live capital permissions for the human-facing agent map.
- `frontend/src/darwin.tsx` — Darwin Lab dashboard and color-coded agent architecture.

## Why experiment windows reset

A newly-created challenger must not be compared with a strategy that has accumulated PnL for days. At every valid Judge epoch, open paper positions are closed through the visible book, results are frozen, selection happens, and all survivors/children start a new common window. Long-term information lives in SQLite rather than in an ever-growing paper PnL number.

## Hyperliquid deployment path

V0.4 stops before autonomous real execution. The next safe progression is:

1. add Hyperliquid native L2/trades/funding/OI market data;
2. replay and paper trade on that exact venue feed;
3. add position/order reconciliation against Hyperliquid testnet;
4. shadow mode: generate orders but do not submit them;
5. testnet execution with strict max notional and kill switch;
6. champion deployment policy based on multiple out-of-sample epochs;
7. only then consider tightly capped mainnet execution.

This keeps research, capital allocation and exchange permissions as separate boundaries.

## V0.6 robustness layer

The research loop now separates **performance**, **evidence quality**, and **selection bias**. Positive raw fitness is shrunk by an evidence weight based on closed trades and common-window duration. `SCALE` requires both the ordinary promotion minimums and a multiple-testing z guard (`sqrt(2 log M)` for the active population), plus positive return under a configurable 1.5x fee stress by default.

Each epoch also has a common BTC market benchmark. Genome rows expose alpha versus that benchmark for diagnosis, but the benchmark does not silently modify strategy signals. CURIE/EVOLVE experiments are first-class persisted objects (parent, children, hypothesis, factors, status, winner) and can be inspected independently of LLM prose.

Population growth is bounded (`DARWIN_MAX_ACTIVE_STRATEGIES`, `DARWIN_MAX_NEW_PER_EPOCH`), and autonomous epoch triggering can be paused without stopping paper observation. These controls prevent the search process itself from becoming an uncontrolled source of compute cost and multiple-testing noise.


## V0.11 brain and engineering boundary

```text
OpenAI research plane
  ATLAS (Sol) ---- CURIE (Sol) ---- EVOLVE (Terra)
       \              |                /
        \---------- MNEMOSYNE (Luna)-/
                     |
                     v
Deterministic evidence plane
  FORGE paper accounting -> JUDGE numerical selection
                     |
                     v
Deterministic capital plane
  CERBERUS risk gate -> HERMES exchange adapter

Separate engineering plane
  CODEX ENGINEER -> code-only task pack / tests / proposed changes
  (no exchange credentials, no direct capital authority, no auto-apply)
```

This separation is enforced in `backend/agents/policy.py` and `backend/agents/roles.py`, not merely documented in the UI. `AgentBrain` can use the direct OpenAI Responses API for structured research output, while deterministic roles never require an LLM response to calculate PnL, approve risk or execute.
