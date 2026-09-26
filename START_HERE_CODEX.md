> Local V1 hardening: see [V1_VALIDATION.md](V1_VALIDATION.md) for Windows launch, executed checks, provider status and remaining work. Current target branch: `darwin-v0.11-factory-evolution`; do not merge PR #1.

# START HERE — Codex

You are taking over **SwarmTrade Darwin V0.11**.

Read, in order:

1. `AGENTS.md` — non-negotiable authority/safety contract.
2. `GENOME_V2.md` — new bounded strategy genome semantics.
3. `CODEX_HANDOFF.md` — build, test and branch workflow.
4. `OPENBOT_BRIDGE.md` — CopilotKit/OpenBot integration.
5. `DARWIN_ARCHITECTURE.md` and `FACTORY_ARCHITECTURE.md` — system behavior/UI.

## First mission

1. Make Windows boot/build fully reliable.
2. Run backend tests and frontend build.
3. Verify `/api/health` reports `0.11.0`.
4. Validate Genome V2 persistence and Factory rendering.
5. Optionally install `backend/requirements-openbot.txt` and validate all four AG-UI coworkers.
6. Validate the read-only `/api/openbot/context/{agent_id}` bridge. Do not expose execution/risk writes.
7. Push your work to branch `darwin-v0.11-openbot-codex`; do not force-push `main`.

## Commands

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-runtime.txt
.\.venv\Scripts\python.exe -m pytest backend -q
cd frontend
npm ci
npm run build
cd ..
```

Optional OpenBot bridge:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-openbot.txt
```

The system must remain paper-only by default.

## V0.11 evolution checks

Also verify:

```bash
curl http://127.0.0.1:8000/api/darwin/evolution?symbol=BTCUSDT\&mode=simulation
```

The object must expose `definition`, `trend`, `history`, `lineage`, and `gene_evolution`. Preserve the safety invariant that this telemetry is not used by CERBERUS or HERMES.
