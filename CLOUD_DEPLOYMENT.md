# SwarmTrade Darwin V0.11 — Cloud deployment

## Target

One always-on Railway service runs:

- Hyperliquid mainnet **public data** websocket
- SwarmTrade signal engine
- 320+ isolated paper accounts
- Darwin experiment loop
- OpenAI research brains + deterministic capital authorities
- CODEX ENGINEER task boundary (disabled for auto-apply)
- FastAPI API + React dashboard
- SQLite memory under `/data`

## OpenAI authentication

Direct OpenAI research brains use `OPENAI_API_KEY`. Optional Vercel AI Gateway compatibility remains available through `AI_GATEWAY_API_KEY`/`VERCEL_OIDC_TOKEN` if an agent runtime is explicitly set to `gateway`.

Without a configured model provider, research agents fall back to typed safe behavior; FORGE/CERBERUS/HERMES remain deterministic regardless.

## No trading secret required

For paper mode keep:

```text
HYPERLIQUID_ENABLED=false
```

Do not add a Hyperliquid private key to the paper deployment.

## Persistence

Mount a persistent Railway Volume at `/data`. The Docker image sets `DARWIN_DATA_DIR=/data`.

## Useful endpoints

- `/` dashboard
- `/api/health` process health
- `/api/runtime` cloud configuration summary
- `/api/state?symbol=BTCUSDT&mode=live` current Hyperliquid-derived state
- `/api/darwin/state?symbol=BTCUSDT&mode=live` paper population + memory
- `/api/agents/state?symbol=BTCUSDT&mode=live` agent identity/model/status
- `/ws?symbol=BTCUSDT&mode=live` live UI websocket

## Deployment safety

The container defaults to public market data + paper-only. `CERBERUS` and `HERMES` are deterministic capital-authority components and remain locked by default. Live trading requires a separate, explicit execution configuration and should not share the research service credentials.

## V0.6 research endpoints

- `/api/darwin/research?symbol=BTCUSDT&mode=live` — evidence quality, market regime/benchmark, family cells, experiments and LLM usage
- `/api/darwin/strategy/{strategy_id}?symbol=BTCUSDT&mode=live` — lineage and frozen epoch history

For V0.6 durable paper research, keep `DARWIN_MULTIPLE_TESTING_GUARD=true`, `DARWIN_REQUIRE_POSITIVE_FEE_STRESS=true`, and a persistent `/data` volume.
