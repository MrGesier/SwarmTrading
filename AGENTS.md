# AGENTS.md — SwarmTrading implementation contract

## Mission

Build an explainable multi-scale market-intent research terminal. Preserve the strong V0.2 UX while progressively replacing shared/instantaneous heuristics with horizon-specific market states and empirically calibrated forecasts.

## Non-negotiable principles

1. **Chart interval != prediction horizon != context horizon.** Never conflate them in APIs or UI state.
2. **No fake independence.** Strategy counts must be decorrelated; report raw N and effective N separately.
3. **No fake probabilities.** Values labelled probability/confidence must be calibrated out-of-sample. Heuristic scores must be labelled as scores.
4. **No look-ahead.** Live and replay paths must use only information available at that timestamp.
5. **No silent data degradation.** Stale or inconsistent books force RISK_OFF/LOW_CONFIDENCE.
6. **Direction and execution are separate decisions.** A 3m LONG thesis can coexist with a poor 5s entry state.
7. **Contradiction is signal.** Do not average away disagreements across horizons/families/venues.
8. **Costs matter.** Any claimed alpha must survive spread, fees, slippage and adverse-selection assumptions.
9. **Research first.** Keep authenticated order execution out of scope until paper/replay validation is convincing.
10. **Preserve explainability.** Every material state transition must expose the dominant contributing evidence and invalidation conditions.

## Current stack

- Backend: Python + FastAPI + asyncio
- Frontend: React + TypeScript
- Live public data: Binance spot depth/trades/book ticker
- Storage: Parquet event capture
- Modes: deterministic simulation, live read-only, replay

## V0.3 implementation order

1. Add `HorizonState` and horizon-specific feature histories.
2. Rebuild flow/OFI/book/entropy features per horizon.
3. Split display interval from forecast horizon in frontend and API.
4. Compute local swarm entropy / local effective N per horizon.
5. Add consensus term structure `C(h,t)`.
6. Add horizon x time propagation heatmap and propagation-front state.
7. Replace global selected intent with horizon-specific LONG/SHORT/NO-TRADE output contract.
8. Add direction-vs-entry state machine.
9. Add triple-barrier research labels and chronological calibration pipeline.
10. Only then add derivatives / cross-venue / options / news context.

## Validation before merging model changes

- backend tests pass
- frontend build passes
- chronological walk-forward test or documented reason why not yet applicable
- no future-data leakage in replay
- ablation for newly claimed predictive features
- explicit label when a feature is heuristic or uncalibrated

## Read first

- `README.md`
- `docs/V0.2_PRODUCT_SPEC.md`
- `docs/V0.3_MULTISCALE_ALPHA.md`
