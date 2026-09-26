# SwarmTrade Darwin V0.11 — Agents and authority

The human-facing Factory uses role-specific characters, while V0.11 separates **reasoning brains** from **authority code**.

| Color | Agent | Brain | Function | Capital authority |
|---|---|---|---|---|
| Purple | ATLAS | GPT-5.6 Sol | chooses research attention and diverse experiment parents | none |
| Blue | CURIE | GPT-5.6 Sol | creates one falsifiable controlled hypothesis | none |
| Green | EVOLVE | GPT-5.6 Terra | refines bounded mutation factors | none |
| Cyan | FORGE | deterministic Python | authoritative paper fills, fees, PnL and positions | paper only |
| Yellow | JUDGE | deterministic stats + GPT-5.6 Terra critic | KEEP/KILL/SCALE + independent overfit critique | none |
| Pink | MNEMOSYNE | GPT-5.6 Luna | evidence-backed memory compression | none |
| Red | CERBERUS | deterministic Python | hard execution gate | gatekeeper |
| Orange | HERMES | deterministic Python | submit already-approved intent | guarded execution |

Above the factory sits **CODEX ENGINEER**. It is an engineering role, not a trading role. It receives task packs and can later be connected to the OpenAI Agents API / Codex harness, but V0.11 never auto-applies code changes.

## Research loop

```text
ATLAS → CURIE → EVOLVE → FORGE → JUDGE → MNEMOSYNE ↺
```

Only ATLAS/CURIE/EVOLVE/MNEMOSYNE are model-first. JUDGE is hybrid. FORGE is deliberately model-free for measurement.

## Capital path

```text
CERBERUS → HERMES → Hyperliquid
```

Both components are deterministic. Mainnet is still locked by environment gates and is disabled by default.

## Brain endpoint

`GET /api/brains/state` exposes the policy, configured runtimes/models, last results, 24-hour usage/cost and CODEX ENGINEER status.
