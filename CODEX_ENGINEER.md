# CODEX ENGINEER — local workflow

The Codex Engineer is intentionally outside Darwin's live research/capital loop. It is a software-engineering worker, not a trading agent.

## Interactive use

From the project root:

```powershell
codex
```

Codex will discover `AGENTS.md`. Use `/permissions` to review its sandbox and `/model` if you want to change model/reasoning.

## Reproducible non-interactive use

The included `Run Codex Engineer.cmd` invokes Codex with `workspace-write`, not unrestricted host access. It asks Codex to read:

- `AGENTS.md`
- `CODEX_HANDOFF.md`
- `OPENAI_BRAIN_ARCHITECTURE.md`
- `FACTORY_ARCHITECTURE.md`
- `data/codex-engineer-task.json` if the local API was reachable

It does **not** commit, push, deploy, enable Hyperliquid execution, or grant exchange credentials.

## Darwin task pack

When SwarmTrade is running, `POST /api/engineer/task` freezes current research evidence into SQLite. `Run Codex Engineer.cmd` also tries to export the returned task pack to `data/codex-engineer-task.json` before launching Codex.

This makes the engineering prompt evidence-aware without making Codex part of JUDGE/CERBERUS/HERMES.
