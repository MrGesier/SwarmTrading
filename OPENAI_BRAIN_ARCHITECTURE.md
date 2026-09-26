# SwarmTrade Darwin V0.11 — OpenAI Brain architecture

## Design rule

**Models reason. Deterministic code measures, selects numerically, gates risk and executes.**

The purpose of V0.11 is not to put a model into every component. It is to put expensive reasoning only where it can add value while preserving hard, inspectable boundaries around market accounting and capital.

## Runtime map

| Component | Default runtime | Default model | Authority |
|---|---|---|---|
| ATLAS | OpenAI Responses API | `gpt-5.6-sol` | research attention only |
| CURIE | OpenAI Responses API | `gpt-5.6-sol` | falsifiable experiment proposal |
| EVOLVE | OpenAI Responses API | `gpt-5.6-terra` | bounded mutation-factor refinement |
| FORGE | deterministic Python | `deterministic-paper-engine` | authoritative paper fills/PnL/fees |
| JUDGE | deterministic Python + OpenAI critic | `gpt-5.6-terra` for critique | deterministic KEEP/KILL/SCALE is authoritative |
| MNEMOSYNE | OpenAI Responses API | `gpt-5.6-luna` | evidence compression / memory |
| CERBERUS | deterministic Python | `deterministic-risk-gate` | hard execution permission boundary |
| HERMES | deterministic Python | `deterministic-executor` | exact translation of approved intent |
| CODEX ENGINEER | outside trading loop | `gpt-6-astra` scaffold | code-only, no capital |

## OpenAI integration

Research brains use the OpenAI Responses API with JSON Schema constrained outputs. Configure:

```env
OPENAI_API_KEY=...
DARWIN_BRAIN_ATLAS=openai
DARWIN_MODEL_ATLAS=gpt-5.6-sol
DARWIN_REASONING_ATLAS=high
```

Each agent can independently switch between:

- `openai` — direct OpenAI Responses API
- `gateway` — Vercel AI Gateway compatibility path
- `deterministic` — local code only

The runtime is visible in `/api/brains/state` and in the Factory.

## Failure semantics

If an OpenAI key/provider is missing or a model call fails:

1. the request returns a deterministic, typed fallback;
2. the failure is logged in `agent_runs`;
3. deterministic accounting/risk remains operational;
4. no missing model can unlock execution.

## Prompt/version audit

Every recorded model call stores:

- agent ID
- model
- runtime/provider
- reasoning effort
- prompt version
- latency
- input/output token counts
- estimated model cost
- success/failure
- structured output payload

This makes model behavior auditable across epochs.

## Codex Engineer boundary

`CODEX ENGINEER` is deliberately drawn above the Factory, not in the trading pipeline.

V0.11 provides a task-pack generator through:

```text
GET  /api/engineer/state
POST /api/engineer/task
```

A task pack contains current research evidence, recent experiments, validation commands and immutable safety invariants. V0.11 never auto-applies code changes and never gives the engineer access to exchange private keys.

The task pack can be handed directly to local Codex CLI through `Run Codex Engineer.cmd`. V0.11 also keeps the OpenAI Agents API as a future cloud-engineering transport, but remote sessions are not auto-started from the trading service.

## Capital boundary

The only external order path remains:

```text
approved target
    ↓
CERBERUS hard deterministic checks
    ↓
HERMES deterministic adapter
    ↓
Hyperliquid SDK
```

An LLM output is not an execution permission.
