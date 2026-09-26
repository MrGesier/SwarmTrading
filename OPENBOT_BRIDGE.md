# OpenBot Bridge — SwarmTrade Darwin V0.11

Target project: `CopilotKit/OpenBot`.

OpenBot is **not** the trading engine and **not** a financial risk authority. It is the local coworker/orchestration/governance plane for ATLAS, CURIE, EVOLVE and MNEMOSYNE.

## Boundary

```text
OpenBot local
  ├─ ATLAS       advisory / GPT-5.6 Sol
  ├─ CURIE       advisory / GPT-5.6 Sol
  ├─ EVOLVE      advisory / GPT-5.6 Terra
  └─ MNEMOSYNE   advisory / GPT-5.6 Luna
           │ AG-UI
           ▼
SwarmTrade Darwin
  ├─ research evidence / lineage / experiment ledger
  ├─ FORGE        deterministic paper accounting
  ├─ JUDGE        deterministic selection authority
  ├─ CERBERUS     deterministic risk gate
  └─ HERMES       deterministic exchange adapter
```

No OpenBot coworker has capital authority.

## What is already packaged

- `backend/agents/openbot_agui.py`: optional Pydantic-AI/AG-UI harness.
- `backend/requirements-openbot.txt`: optional dependencies.
- `/api/openbot/state`: bridge status.
- `/ag-ui/atlas`
- `/ag-ui/curie`
- `/ag-ui/evolve`
- `/ag-ui/mnemosyne`
- `openbot/swarmtrade-tenant/*`: tenant package ready to copy into an OpenBot checkout.
- `openbot/.env.swarmtrade.example`: local connection template.

The bridge follows the official `CopilotKit/OpenBot` Pydantic AI example: `pydantic-ai-slim[openai,ag-ui]` with `AGUIAdapter.dispatch_request`.

## Local setup target for Codex

1. Keep SwarmTrade on `127.0.0.1:8000`.
2. Install optional bridge deps:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-openbot.txt
```

3. Generate a strong random shared token and set in SwarmTrade:

```dotenv
OPENBOT_AGENT_TOKEN=...
```

4. Clone `CopilotKit/OpenBot` separately.
5. Copy `openbot/swarmtrade-tenant` into the OpenBot checkout as `examples/swarmtrade`.
6. Apply values from `openbot/.env.swarmtrade.example` to OpenBot `.env`.
7. Ensure Docker can resolve `host.docker.internal`; on Linux add the normal host-gateway mapping if needed.
8. Test each coworker connection before enabling handoffs.

## Next Codex tasks

The current AG-UI coworkers have their standing roles but intentionally have **no direct trading tools**. Codex should next expose a small read-only Darwin research tool surface, then grant only those tools to the relevant coworkers.

Recommended read-only capabilities:

- research state / champion / evidence quality
- experiment ledger
- strategy lineage/history
- factory event history
- market regime summary

Do **not** expose:

- Hyperliquid private credentials
- order submission
- CERBERUS configuration writes
- direct PnL mutation
- JUDGE verdict mutation

After read-only tools are stable, configure OpenBot directional handoffs:

```text
ATLAS -> CURIE
ATLAS -> EVOLVE
ATLAS -> MNEMOSYNE
CURIE -> EVOLVE
EVOLVE -> ATLAS
MNEMOSYNE -> ATLAS
```

Keep handoff depth and per-run caps low during paper research.


## V0.11 read-only Darwin context

Each cognitive coworker can read a role-scoped, redacted snapshot through:

```text
GET /api/openbot/context/atlas
GET /api/openbot/context/curie
GET /api/openbot/context/evolve
GET /api/openbot/context/mnemosyne
```

The request must carry the same `x-openbot-agent-token` secret as the AG-UI bridge. Context includes paper research evidence, Genome V2 metadata, experiments and memory appropriate to the role. It never contains Hyperliquid private keys or an execution method.
