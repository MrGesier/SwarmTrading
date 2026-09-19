"""Optional OpenBot / AG-UI bridge for SwarmTrade Darwin.

This module follows CopilotKit/OpenBot's Pydantic AI harness pattern while keeping
OpenBot out of the authoritative trading path. It is intentionally optional:
base Darwin runs without pydantic-ai, and these coworkers become available only
when backend/requirements-openbot.txt is installed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    from pydantic_ai import Agent
    from pydantic_ai.ui.ag_ui import AGUIAdapter
except Exception:  # optional integration, never break the trading engine
    Agent = None  # type: ignore[assignment]
    AGUIAdapter = None  # type: ignore[assignment]

TOKEN_HEADER = "x-openbot-agent-token"


@dataclass(frozen=True)
class OpenBotCoworker:
    id: str
    name: str
    title: str
    model: str
    reasoning: str
    role: str


COWORKERS: dict[str, OpenBotCoworker] = {
    "atlas": OpenBotCoworker(
        "atlas", "ATLAS", "Research Supervisor", "gpt-5.6-sol", "high",
        "Supervise evolutionary research. Allocate research attention, compare evidence, and choose bounded research directions. Never submit orders, alter PnL, or bypass deterministic risk controls.",
    ),
    "curie": OpenBotCoworker(
        "curie", "CURIE", "Research Scientist", "gpt-5.6-sol", "high",
        "Formulate falsifiable trading-research hypotheses from supplied evidence. Propose bounded experiments only. Never treat model intuition as measured market evidence.",
    ),
    "evolve": OpenBotCoworker(
        "evolve", "EVOLVE", "Strategy Mutation Designer", "gpt-5.6-terra", "medium",
        "Translate approved hypotheses into small, testable strategy mutations. Preserve experiment reproducibility and never change execution or capital permissions.",
    ),
    "mnemosyne": OpenBotCoworker(
        "mnemosyne", "MNEMOSYNE", "Research Archivist", "gpt-5.6-luna", "low",
        "Compress experiment history into concise lessons while preserving uncertainty and provenance. Database evidence remains authoritative.",
    ),
}

_AGENTS: dict[str, Any] = {}


def _model_id(coworker: OpenBotCoworker) -> str:
    override = (os.getenv(f"OPENBOT_{coworker.id.upper()}_MODEL") or "").strip()
    model = override or coworker.model
    return model if ":" in model else f"openai:{model}"


def available() -> bool:
    return Agent is not None and AGUIAdapter is not None


def expected_token() -> str:
    return (os.getenv("OPENBOT_AGENT_TOKEN") or os.getenv("MANAGED_AGENT_TOKEN") or "").strip()


def authorised(headers: Any) -> bool:
    expected = expected_token()
    offered = (headers.get(TOKEN_HEADER) or "").strip()
    return bool(expected and offered == expected)


def get_agent(agent_id: str):
    if agent_id not in COWORKERS:
        raise KeyError(agent_id)
    if not available():
        raise RuntimeError("OpenBot AG-UI extras are not installed")
    if agent_id not in _AGENTS:
        coworker = COWORKERS[agent_id]
        _AGENTS[agent_id] = Agent(_model_id(coworker), system_prompt=coworker.role)
    return _AGENTS[agent_id]


def state() -> dict[str, Any]:
    token_configured = bool(expected_token())
    return {
        "enabled": available() and token_configured,
        "ag_ui_installed": available(),
        "token_configured": token_configured,
        "authority": "advisory-only",
        "capital_access": False,
        "coworkers": [
            {
                "id": c.id,
                "name": c.name,
                "title": c.title,
                "model": _model_id(c),
                "reasoning": c.reasoning,
                "endpoint": f"/ag-ui/{c.id}",
            }
            for c in COWORKERS.values()
        ],
    }
