"""Human-readable brain and authority policy for Darwin V0.11."""
from __future__ import annotations

from typing import Any


POLICY: dict[str, dict[str, Any]] = {
    "atlas": {
        "brain_class": "RESEARCH",
        "default_runtime": "openai",
        "default_model": "gpt-5.6-sol",
        "authority": "Allocate research attention only",
        "may": ["select experiment parents", "set research focus"],
        "may_not": ["calculate authoritative PnL", "place orders", "change hard risk limits"],
    },
    "curie": {
        "brain_class": "RESEARCH",
        "default_runtime": "openai",
        "default_model": "gpt-5.6-sol",
        "authority": "Propose falsifiable experiments",
        "may": ["form hypotheses", "choose one bounded variable to test"],
        "may_not": ["place orders", "promote a strategy", "rewrite measured evidence"],
    },
    "evolve": {
        "brain_class": "RESEARCH",
        "default_runtime": "openai",
        "default_model": "gpt-5.6-terra",
        "authority": "Refine bounded mutation proposals",
        "may": ["refine mutation factors", "explain mutation intent"],
        "may_not": ["change the approved experiment variable", "place orders"],
    },
    "forge": {
        "brain_class": "DETERMINISTIC",
        "default_runtime": "deterministic",
        "default_model": "deterministic-paper-engine",
        "authority": "Authoritative paper fills and accounting",
        "may": ["simulate fills", "calculate PnL/fees/positions"],
        "may_not": ["use an LLM to invent fills", "submit external orders"],
    },
    "judge": {
        "brain_class": "HYBRID",
        "default_runtime": "openai",
        "default_model": "gpt-5.6-terra",
        "authority": "Deterministic selection; LLM audit is advisory",
        "may": ["calculate deterministic fitness", "flag overfit risk"],
        "may_not": ["let LLM override KEEP/KILL/SCALE", "place orders"],
    },
    "mnemosyne": {
        "brain_class": "RESEARCH",
        "default_runtime": "openai",
        "default_model": "gpt-5.6-luna",
        "authority": "Compress evidence into reusable memory",
        "may": ["summarize completed epochs", "tag uncertainty"],
        "may_not": ["alter historical measurements", "place orders"],
    },
    "cerberus": {
        "brain_class": "DETERMINISTIC",
        "default_runtime": "deterministic",
        "default_model": "deterministic-risk-gate",
        "authority": "Hard execution permission boundary",
        "may": ["block external execution", "enforce notional/network/credential limits"],
        "may_not": ["be overridden by an LLM", "increase risk limits autonomously"],
    },
    "hermes": {
        "brain_class": "DETERMINISTIC",
        "default_runtime": "deterministic",
        "default_model": "deterministic-executor",
        "authority": "Translate already-approved intents exactly",
        "may": ["submit an approved order through the guarded adapter"],
        "may_not": ["change side/size", "bypass CERBERUS", "invent an order"],
    },
}


def policy_state() -> dict[str, Any]:
    return {
        "principle": "Models reason; deterministic code measures, selects numerically, gates risk and executes.",
        "capital_path": ["CERBERUS", "HERMES"],
        "research_path": ["ATLAS", "CURIE", "EVOLVE", "FORGE", "JUDGE", "MNEMOSYNE"],
        "agents": POLICY,
    }
