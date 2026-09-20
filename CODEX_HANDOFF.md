> Local V1 hardening: see [V1_VALIDATION.md](V1_VALIDATION.md) for Windows launch, executed checks, provider status and remaining work. Current target branch: `darwin-v0.11-factory-evolution`; do not merge PR #1.

# Codex handoff — SwarmTrade Darwin V0.11

## Immediate objective

First make the packaged app boot reliably on Windows, then preserve the V0.11 OpenAI-Brain boundaries while improving the product.

## Runtime target

- Python 3.11+
- Node 22 LTS only to build `frontend/dist`
- one FastAPI process on `127.0.0.1:8000`
- `/api/health` version must be `0.11.0`
- public Hyperliquid data may run on mainnet for paper research
- `HYPERLIQUID_ENABLED=false` by default

## Verification

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-runtime.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m pytest backend -q
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Verify:

- `/api/health`
- `/api/brains/state`
- `/api/engineer/state`
- `/api/darwin/research?symbol=BTCUSDT&mode=simulation`
- `/api/factory/state?symbol=BTCUSDT&mode=simulation`
- `/factory`

## V0.11 invariants

### OpenAI research brains

- ATLAS: `gpt-5.6-sol`, high reasoning
- CURIE: `gpt-5.6-sol`, high reasoning
- EVOLVE: `gpt-5.6-terra`, medium reasoning
- JUDGE: deterministic decision + `gpt-5.6-terra` critique only
- MNEMOSYNE: `gpt-5.6-luna`, low reasoning

### Deterministic authority

- FORGE computes fills/PnL/fees; no LLM authority
- CERBERUS hard checks cannot be overridden by a model
- HERMES cannot change side/size/venue
- missing OpenAI provider falls back safely
- no automatic paper-to-mainnet promotion

### Codex Engineer

`backend/agents/codex_engineer.py` is outside the trading loop. It prepares persistent engineering task packs. Do not give it exchange keys, do not auto-apply patches, and do not couple code deployment to strategy promotion.

### Research robustness inherited from V0.6/V0.7

Preserve:

- evidence shrinkage
- multiple-testing guard
- fee stress
- common-window market benchmark
- experiment ledger
- strategy lineage/history
- persistent Factory event bus/playback
- population governor

## Current backend verification

At package creation the targeted Python suite passes **28 tests**.


## Local Codex bridge

`Run Codex Engineer.cmd` uses the official `codex exec` non-interactive workflow with a `workspace-write` sandbox. It reads `AGENTS.md` and the handoff docs, optionally exports `/api/engineer/task` to `data/codex-engineer-task.json`, and never commits/pushes/deploys automatically.

## V0.11 OpenBot integration target

This package includes the first optional bridge for `CopilotKit/OpenBot`.

Validate first:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-openbot.txt
```

Then configure a random `OPENBOT_AGENT_TOKEN` and verify:

- `GET /api/openbot/state`
- `POST /ag-ui/atlas`
- `POST /ag-ui/curie`
- `POST /ag-ui/evolve`
- `POST /ag-ui/mnemosyne`

The OpenBot tenant files are under `openbot/swarmtrade-tenant/`.

Important: the first bridge intentionally exposes standing-role coworkers only. The next engineering step is a **read-only Darwin research tool surface**, not execution tools. Follow `OPENBOT_BRIDGE.md` exactly.

### Git target

Preferred branch name when pushing from the user's local Codex/Git environment:

```text
darwin-v0.11-openbot-codex
```

Do not force-push `main`. Create the branch, run the full test/build suite, then open a PR or merge after review.

## V0.11 Evolution Observatory

The Factory now includes persistent evolution telemetry from `DarwinStore.evolution_history()`. Keep the score explainable and descriptive. Do not optimize directly against the composite Research Quality Index; experiments should continue to be selected/evaluated from their underlying evidence and deterministic Judge rules. See `EVOLUTION_OBSERVATORY.md`.
