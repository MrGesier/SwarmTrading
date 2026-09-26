# SwarmTrade Darwin — Agent Engineering Contract (V0.11)

This repository is an evolutionary **paper-trading research system**. Treat the following boundaries as hard requirements.

## Architecture

- ATLAS: research supervisor. OpenAI advisory reasoning only.
- CURIE: research scientist. OpenAI advisory reasoning only.
- EVOLVE: bounded strategy mutation designer. OpenAI advisory reasoning only.
- FORGE: deterministic paper accounting/fills/PnL. Do not replace authoritative calculations with model output.
- JUDGE: deterministic numerical RETEST/KEEP/KILL/SCALE authority. LLM critique is commentary only.
- MNEMOSYNE: research-memory summarization. Source evidence remains the database.
- CERBERUS: deterministic risk gate. Model output may never bypass it.
- HERMES: deterministic exchange adapter. Disabled by default.
- CODEX ENGINEER: software engineer outside the trading/capital path.

## Hard safety invariants

1. Never enable `HYPERLIQUID_ENABLED` or mainnet execution as part of an engineering task.
2. Never weaken CERBERUS hard limits, stale-feed blocks, or execution acknowledgements without explicit human instruction.
3. Never expose, log, copy, print, commit, or move private keys/API secrets.
4. Never use LLM prose as authoritative PnL, fills, drawdown, fees, benchmark, or JUDGE selection data.
5. Never let a research model directly submit an exchange order.
6. Do not auto-merge, auto-deploy, or auto-apply Codex-generated changes from inside Darwin.
7. Preserve paper-only defaults and statistical guardrails unless the user explicitly asks to change them.

## Required validation after code changes

Backend:

```bash
python -m pytest backend/test_darwin.py backend/test_engine.py backend/test_analysis.py -q
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

Smoke endpoints when the app is running:

- `/api/health`
- `/api/brains/state`
- `/api/darwin/research`
- `/api/factory/state`
- `/api/engineer/state`

## Preferred workflow

- Make bounded, reviewable changes.
- Add or update tests for behavioral changes.
- Preserve lineage and experiment reproducibility.
- Prefer explicit schemas/config over hidden prompt-only behavior.
- Keep research, capital authority, and software engineering as separate planes.
- If a requested change would cross a capital/execution boundary, stop and surface that fact rather than silently doing it.

## OpenBot bridge (V0.11)

`CopilotKit/OpenBot` is an optional coworker/orchestration plane. It is not an execution authority.

- AG-UI coworkers: ATLAS, CURIE, EVOLVE, MNEMOSYNE only.
- Keep FORGE/JUDGE/CERBERUS/HERMES authoritative behavior inside Darwin.
- OpenBot actions must remain advisory/read-only with respect to capital.
- Do not expose exchange credentials, order submission or risk-limit mutation as OpenBot tools.
- `OPENBOT_AGENT_TOKEN` is a secret and must never be committed or printed.
- See `OPENBOT_BRIDGE.md` and `openbot/swarmtrade-tenant/`.


## Genome V2 invariant (V0.11)

- `backend/darwin/genome.py` owns gene semantics and hard bounds.
- CURIE changes one permitted gene per experiment.
- EVOLVE may alter factors, never gene semantics/bounds.
- FORGE remains authoritative for paper positions and accounting.
- New genes must be paper-tested and persisted before any consideration of external execution.

## Evolution Observatory invariant (V0.11)

- `/api/darwin/evolution` is descriptive research telemetry, never an execution signal.
- Do not feed `research_quality_index`, `trend`, or `confidence` into HERMES/CERBERUS order approval.
- Preserve the individual components (alpha, evidence, fee stress, drawdown, multiple-testing evidence) even if the visualization changes.
- If the Research Quality formula changes, version/document the formula so historical comparisons are not silently reinterpreted.
- `IMPROVING` means improving paper-research metrics only; UI copy must not call it a prediction of future profit.
