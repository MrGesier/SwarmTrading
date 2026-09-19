"""Agent identities and runtime state.

The registry is deliberately metadata-first: the UI can explain who does what,
where the code lives, and whether an agent is allowed to affect capital.
"""
from __future__ import annotations

from typing import Any


AGENT_SPECS: list[dict[str, Any]] = [
    {
        "id": "atlas",
        "name": "ATLAS",
        "color": "#9B7BFF",
        "role": "CEO / Supervisor",
        "function": "Orchestrates the daily/epoch loop, freezes evidence, asks for experiments and applies promotion/retirement decisions.",
        "code_path": "backend/darwin/supervisor.py",
        "inputs": ["market state", "Judge evidence", "memory"],
        "outputs": ["epoch", "champion", "new experiments"],
        "llm_capable": True,
        "brain_class": "RESEARCH",
        "capital_permission": "NONE",
        "order": 1,
    },
    {
        "id": "curie",
        "name": "CURIE",
        "color": "#55C7FF",
        "role": "Scientist / Hypothesis",
        "function": "Explains why a strategy may be working and chooses the next variable worth testing while keeping experiments interpretable.",
        "code_path": "backend/darwin/scientist.py",
        "inputs": ["leaderboard", "drawdown", "turnover", "memory"],
        "outputs": ["experiment plan", "hypothesis", "rationale"],
        "llm_capable": True,
        "brain_class": "RESEARCH",
        "capital_permission": "NONE",
        "order": 2,
    },
    {
        "id": "evolve",
        "name": "EVOLVE",
        "color": "#43D69E",
        "role": "Strategist / Mutation",
        "function": "Turns CURIE's experiment plan into versioned child genomes. It changes controlled parameters, never sends orders.",
        "code_path": "backend/darwin/strategist.py",
        "inputs": ["parent genome", "experiment plan"],
        "outputs": ["challenger genomes", "lineage"],
        "llm_capable": True,
        "brain_class": "RESEARCH",
        "capital_permission": "NONE",
        "order": 3,
    },
    {
        "id": "forge",
        "name": "FORGE",
        "color": "#38D7E8",
        "role": "Worker / Paper Executor",
        "function": "Executes every genome on the same market stream inside isolated paper accounts and measures fills, fees and positions.",
        "code_path": "backend/darwin/paper.py",
        "inputs": ["genome", "order book", "market features"],
        "outputs": ["paper fills", "PnL", "trades", "fees"],
        "llm_capable": False,
        "brain_class": "DETERMINISTIC",
        "capital_permission": "PAPER_ONLY",
        "order": 4,
    },
    {
        "id": "judge",
        "name": "JUDGE",
        "color": "#F4C95D",
        "role": "Evaluator / Selection",
        "function": "Computes deterministic risk-adjusted fitness and assigns RETEST, KEEP, KILL or SCALE from frozen evidence.",
        "code_path": "backend/darwin/judge.py",
        "inputs": ["PnL", "drawdown", "turnover", "sample size"],
        "outputs": ["fitness", "decision", "champion candidate"],
        "llm_capable": True,
        "brain_class": "HYBRID",
        "capital_permission": "NONE",
        "order": 5,
    },
    {
        "id": "mnemosyne",
        "name": "MNEMOSYNE",
        "color": "#EE78C5",
        "role": "Memory / Experience",
        "function": "Stores lineage, epochs and evidence-backed lessons so later experiments know what succeeded, failed and under which conditions.",
        "code_path": "backend/darwin/memory.py + backend/darwin/store.py",
        "inputs": ["Judge results", "champion", "lineage"],
        "outputs": ["lessons", "historical evidence"],
        "llm_capable": True,
        "brain_class": "RESEARCH",
        "capital_permission": "NONE",
        "order": 6,
    },
    {
        "id": "cerberus",
        "name": "CERBERUS",
        "color": "#FF6B6B",
        "role": "Risk Gate",
        "function": "Hard permission boundary before any external order: health, venue, network, notional cap and kill-switch checks live here.",
        "code_path": "backend/execution/hyperliquid.py",
        "inputs": ["approved intent", "limits", "exchange state"],
        "outputs": ["ALLOW", "BLOCK", "reason"],
        "llm_capable": False,
        "brain_class": "DETERMINISTIC",
        "capital_permission": "GATEKEEPER",
        "order": 7,
    },
    {
        "id": "hermes",
        "name": "HERMES",
        "color": "#FF9F43",
        "role": "Hyperliquid Execution",
        "function": "Translates an explicitly approved target into a Hyperliquid order through the guarded official-SDK adapter.",
        "code_path": "backend/execution/hyperliquid.py",
        "inputs": ["CERBERUS approval", "side", "size", "reference price"],
        "outputs": ["exchange order", "fill / error"],
        "llm_capable": False,
        "brain_class": "DETERMINISTIC",
        "capital_permission": "TESTNET_OR_GUARDED_LIVE",
        "order": 8,
    },
]


def agent_runtime_state(*, darwin_state: dict[str, Any], execution_state: dict[str, Any], market_state: dict[str, Any] | None, darwin_error: str = "", llm_states: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Decorate static agent identities with live, explainable statuses."""
    leaders = darwin_state.get("leaderboard", [])
    lessons = darwin_state.get("lessons", [])
    champion = darwin_state.get("champion")
    min_sample = float(darwin_state.get("judge_config", {}).get("min_sample_seconds", 300))
    min_trades = int(darwin_state.get("judge_config", {}).get("min_closed_trades", 5))
    evidence_ready = any(
        float(r.get("sample_seconds", 0)) >= min_sample and int(r.get("closed_trades", 0)) >= min_trades
        for r in leaders
    )
    health = (market_state or {}).get("health", {}).get("status", "WAITING")
    population = int(darwin_state.get("population", 0))
    challengers = int(darwin_state.get("status_counts", {}).get("CHALLENGER", 0))

    statuses = {
        "atlas": ("ERROR" if darwin_error else "RUNNING", "Orchestrating current population" if not darwin_error else darwin_error),
        "curie": ("READY" if evidence_ready else "WAITING", "Evidence available for a new hypothesis" if evidence_ready else "Waiting for minimum sample/trades"),
        "evolve": ("ACTIVE" if challengers else "READY", f"{challengers} challenger(s) alive" if challengers else "Ready to create controlled mutations"),
        "forge": ("RUNNING" if population and health == "HEALTHY" else "PAUSED", f"{population} isolated paper accounts · market {health}"),
        "judge": ("READY" if evidence_ready else "WAITING", "Selection criteria satisfied" if evidence_ready else "Insufficient frozen evidence"),
        "mnemosyne": ("LEARNING" if lessons else "EMPTY", f"{len(lessons)} recent lesson(s) loaded" if lessons else "No completed epoch lesson yet"),
        "cerberus": ("ARMED" if execution_state.get("ready") else "LOCKED", "Execution checks armed" if execution_state.get("ready") else "External execution blocked"),
        "hermes": ("READY" if execution_state.get("ready") else "LOCKED", f"{execution_state.get('network', 'testnet')} · max ${execution_state.get('max_notional_usd', 0):.0f}"),
    }

    agents = []
    llm_states = llm_states or darwin_state.get("llm", {}) or {}
    for spec in AGENT_SPECS:
        status, detail = statuses[spec["id"]]
        brain = llm_states.get(spec["id"], {})
        agents.append({
            **spec,
            "status": status,
            "detail": detail,
            "llm": brain,
            "brain_status": ("DETERMINISTIC" if brain.get("runtime") == "deterministic" else ("ONLINE" if brain.get("available") else ("DISABLED" if not brain.get("enabled", True) else "WAITING_KEY"))),
        })

    return {
        "architecture": "OpenAI Brain: ATLAS → CURIE → EVOLVE · FORGE deterministic → JUDGE deterministic+critic → MNEMOSYNE ↺ · CERBERUS → HERMES deterministic capital path",
        "champion_id": champion.get("id") if isinstance(champion, dict) else None,
        "market_health": health,
        "agents": agents,
    }
