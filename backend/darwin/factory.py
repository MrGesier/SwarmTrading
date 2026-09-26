"""Human-readable event layer for the animated Darwin Factory UI."""
from __future__ import annotations

import time
from typing import Any


AGENT_COPY = {
    "atlas": ("ATLAS", "Atlas Owl · conductor", "🦉"),
    "curie": ("CURIE", "Curie Frog · scientist", "🐸"),
    "evolve": ("EVOLVE", "Evolve Chameleon · smith", "🦎"),
    "forge": ("FORGE", "Forge Bot · operator", "🤖"),
    "judge": ("JUDGE", "Judge Lion · arbiter", "🦁"),
    "mnemosyne": ("MNEMOSYNE", "Memory Octopus · archivist", "🐙"),
    "cerberus": ("CERBERUS", "Cerberus Hound · guardian", "🐺"),
    "hermes": ("HERMES", "Hermes Bird · courier", "🐦"),
    "codex": ("CODEX", "Codex Raccoon · engineer", "🦝"),
}


def event_label(event: dict[str, Any]) -> str:
    t = event.get("type", "event")
    p = event.get("payload", {}) or {}
    sid = event.get("strategy_id") or p.get("strategy_id") or p.get("parent_id")
    labels = {
        "agent_started": "started thinking",
        "agent_finished": "finished its task",
        "hypothesis_created": "created a hypothesis",
        "mutation_created": "forged challengers",
        "judge_decision": f"decided {p.get('decision', '')}".strip(),
        "strategy_killed": "sent a strategy to the pit",
        "champion_promoted": "crowned a new champion",
        "lesson_saved": "archived a lesson",
        "epoch_started": "started a Darwin epoch",
        "epoch_completed": "completed a Darwin epoch",
        "epoch_deferred": "deferred the epoch for more evidence",
        "experiment_resolved": "resolved an experiment",
        "paper_activity": "processed paper activity",
        "risk_gate_blocked": "blocked external execution",
        "engineer_task_prepared": "prepared an engineering task",
    }
    base = labels.get(t, t.replace("_", " "))
    return f"{base}{f' · {sid}' if sid else ''}"


def decorate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        agent_id = e.get("agent_id")
        name, persona, icon = AGENT_COPY.get(agent_id, (str(agent_id or "SYSTEM").upper(), "Factory", "⚙️"))
        out.append({**e, "agent_name": name, "persona": persona, "icon": icon, "label": event_label(e)})
    return out


def factory_state(supervisor: Any, agent_state: dict[str, Any], execution_state: dict[str, Any], market_state: dict[str, Any] | None) -> dict[str, Any]:
    state = supervisor.state()
    research = supervisor.research_state()
    champion_id = (state.get("champion") or {}).get("id")
    leader = next((r for r in state.get("leaderboard", []) if r.get("strategy_id") == champion_id), None)
    return {
        "ts": time.time(),
        "symbol": supervisor.symbol,
        "mode": supervisor.mode,
        "market": {
            "health": (market_state or {}).get("health", {}).get("status", "WAITING"),
            "price": (market_state or {}).get("mid") or (market_state or {}).get("price"),
            "regime": (research.get("market") or {}).get("regime", "WAITING"),
            "benchmark_return_bps": (research.get("benchmark") or {}).get("market_return_bps", 0.0),
        },
        "pnl": supervisor.pnl_state(),
        "pnl_history": supervisor.store.pnl_history(),
        "cycle": state.get("cycle", {}),
        "population": state.get("population", 0),
        "historical_population": state.get("historical_population", 0),
        "status_counts": state.get("status_counts", {}),
        "champion": {"id": champion_id, "metrics": leader} if champion_id else None,
        "agents": agent_state.get("agents", []),
        "experiments": state.get("experiments", [])[:10],
        "leaderboard": state.get("leaderboard", [])[:12],
        "lessons": state.get("lessons", [])[:8],
        "execution": execution_state,
        "engineer": state.get("engineer", {}),
        "brain_policy": {
            "research_models": ["ATLAS", "CURIE", "EVOLVE", "JUDGE", "MNEMOSYNE"],
            "deterministic_authority": ["FORGE", "CERBERUS", "HERMES"],
            "principle": "Models reason; code measures and gates capital.",
        },
        "research": {
            "agent_runs": research.get("agent_runs", []),
            "eligible": (research.get("evidence") or {}).get("eligible", 0),
            "multiple_test_pass": (research.get("evidence") or {}).get("multiple_test_pass", 0),
            "family_cells": research.get("family_cells", [])[:8],
            "llm_usage_24h": research.get("llm_usage_24h", {}),
            "genome": research.get("genome", {}),
        },
        "evolution": supervisor.evolution_state(120),
    }
