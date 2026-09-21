"""Codex Engineer boundary for Darwin V0.11.

This component is deliberately outside the trading/control loop. It prepares
reproducible engineering task packs for Codex / OpenAI Agents API. It never
receives exchange credentials and cannot change capital/risk state.
"""
from __future__ import annotations

import os
import shutil
import time
from typing import Any


class CodexEngineer:
    def __init__(self):
        self.enabled = os.getenv("CODEX_ENGINEER_ENABLED", "false").lower() in {"1", "true", "yes"}
        self.model = os.getenv("CODEX_ENGINEER_MODEL", "gpt-6-astra")
        self.runtime = "codex-cli"
        self.environment = os.getenv("CODEX_ENGINEER_ENVIRONMENT", "local")
        self.api_key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
        self.auto_apply = False  # hard invariant in V0.11

    def status(self) -> dict[str, Any]:
        return {
            "id": "codex",
            "name": "CODEX ENGINEER",
            "runtime": self.runtime,
            "model": self.model,
            "environment": self.environment,
            "enabled": self.enabled,
            "available": bool(os.getenv("DARWIN_CODEX_BIN") or shutil.which("codex")),
            "authentication": "verified by local demo worker at invocation",
            "auto_apply": self.auto_apply,
            "authority": "CODE_ONLY_NO_CAPITAL",
            "capital_permission": "NONE",
            "detail": "Task packs feed the isolated local demo worker. Codex login is checked at invocation; all successful patches await human review.",
        }

    def task_pack(self, supervisor: Any, *, objective: str | None = None) -> dict[str, Any]:
        research = supervisor.research_state()
        state = supervisor.state()
        evidence = research.get("evidence") or {}
        benchmark = research.get("benchmark") or {}
        experiments = research.get("experiments") or []
        agents = research.get("llm_usage_24h") or {}
        objective = objective or "Improve strategy research quality without weakening statistical or execution safety invariants."
        return {
            "created_at": time.time(),
            "objective": objective,
            "repo": "SwarmTrading",
            "scope": "engineering only",
            "read_only_inputs": {
                "population": state.get("population"),
                "champion_id": (state.get("champion") or {}).get("id"),
                "evidence": evidence,
                "benchmark": benchmark,
                "recent_experiments": experiments[:8],
                "llm_usage_24h": agents,
            },
            "safety_invariants": [
                "Do not change authoritative paper PnL/fill accounting to LLM outputs.",
                "Do not let an LLM override JUDGE deterministic KEEP/KILL/SCALE decisions.",
                "Do not let an LLM override CERBERUS hard checks.",
                "Do not enable Hyperliquid mainnet or change HYPERLIQUID_ENABLED.",
                "Do not read, print, copy or move exchange private keys.",
                "Keep code changes testable and isolated; require tests before merge.",
            ],
            "suggested_focus": [
                "genome V2 / richer bounded genes",
                "walk-forward and unseen-regime validation",
                "market microstructure features native to Hyperliquid",
                "research observability and experiment reproducibility",
                "launcher/build reliability",
            ],
            "validation": [
                "python -m pytest backend/test_darwin.py backend/test_engine.py backend/test_analysis.py -q",
                "cd frontend && npm ci && npm run build",
                "verify /api/health, /api/darwin/research, /api/factory/state",
            ],
        }
