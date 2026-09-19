"""Darwin Genome V2 schema, defaults and mutation bounds.

The base 320 SwarmTrade genomes remain valid. V2 adds optional execution-policy
parameters that are interpreted deterministically by FORGE. LLMs may choose a
single permitted gene to test, but they never define its semantics or bounds.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

GENOME_VERSION = 2

# Multiplicative mutation bounds are deliberately local. Absolute bounds are
# authoritative and enforced again after every mutation.
GENE_SPECS: dict[str, dict[str, Any]] = {
    "threshold": {
        "label": "Entry threshold",
        "kind": "float",
        "min": 0.03,
        "max": 0.95,
        "default_from": "threshold",
        "description": "Minimum absolute signal strength required to open a position.",
    },
    "gain": {
        "label": "Signal gain",
        "kind": "float",
        "min": 0.15,
        "max": 4.0,
        "default_from": "gain",
        "description": "Non-linear gain applied before signal saturation.",
    },
    "exit_threshold": {
        "label": "Exit threshold",
        "kind": "float",
        "min": 0.0,
        "max": 0.90,
        "default": 0.06,
        "description": "Close when absolute signal decays below this level.",
    },
    "max_holding_seconds": {
        "label": "Max holding time",
        "kind": "float",
        "min": 2.0,
        "max": 3600.0,
        "default": 1800.0,
        "description": "Maximum paper position age before a deterministic exit.",
        "unit": "s",
    },
    "cooldown_seconds": {
        "label": "Cooldown",
        "kind": "float",
        "min": 0.0,
        "max": 600.0,
        "default": 0.0,
        "description": "Minimum wait after a close before a new entry.",
        "unit": "s",
    },
    "stop_loss_bps": {
        "label": "Stop loss",
        "kind": "float",
        "min": 2.0,
        "max": 2000.0,
        "default": 1000.0,
        "description": "Paper-only adverse move from entry that forces a close.",
        "unit": "bp",
    },
    "take_profit_bps": {
        "label": "Take profit",
        "kind": "float",
        "min": 2.0,
        "max": 3000.0,
        "default": 2000.0,
        "description": "Paper-only favourable move from entry that forces a close.",
        "unit": "bp",
    },
    "confirmation_ticks": {
        "label": "Entry confirmation",
        "kind": "int",
        "min": 1,
        "max": 12,
        "default": 1,
        "description": "Consecutive same-direction qualifying signals required before entry.",
        "unit": "ticks",
    },
}

MUTABLE_GENES = tuple(GENE_SPECS)


def clamp_gene(name: str, value: Any) -> float | int:
    spec = GENE_SPECS[name]
    x = float(value)
    x = min(float(spec["max"]), max(float(spec["min"]), x))
    if spec["kind"] == "int":
        return int(round(x))
    return float(x)


def upgrade_genome(genome: dict[str, Any]) -> dict[str, Any]:
    """Return a V2-compatible copy without changing legacy strategy identity."""
    g = deepcopy(genome)
    g.setdefault("genome_version", GENOME_VERSION)
    for name, spec in GENE_SPECS.items():
        if name in g:
            g[name] = clamp_gene(name, g[name])
            continue
        if spec.get("default_from") and spec["default_from"] in g:
            g[name] = clamp_gene(name, g[spec["default_from"]])
        else:
            g[name] = clamp_gene(name, spec.get("default", spec["min"]))
    # Exit hysteresis should not normally be stricter than entry. Preserve an
    # explicit user value, but make legacy defaults sensible.
    if "exit_threshold" not in genome:
        # Legacy Generation-0 behaviour: leave as soon as the signal falls back
        # below the same threshold used for entry. Hysteresis appears only after
        # Darwin explicitly mutates this gene.
        g["exit_threshold"] = float(g["threshold"])
    return g


def mutate_gene(parent: dict[str, Any], parameter: str, factor: float) -> dict[str, Any]:
    if parameter not in GENE_SPECS:
        raise ValueError(f"Unsupported mutation parameter: {parameter}")
    child = upgrade_genome(parent)
    current = float(child[parameter])
    # Cooldown can legitimately be zero; multiplicative mutation cannot leave
    # zero, so use a small absolute seed before applying the requested factor.
    if parameter == "cooldown_seconds" and current <= 0:
        current = 5.0
    if GENE_SPECS[parameter]["kind"] == "int":
        if float(factor) > 1.0:
            candidate = current + 1
        elif float(factor) < 1.0:
            candidate = current - 1
        else:
            candidate = current
        child[parameter] = clamp_gene(parameter, candidate)
    else:
        child[parameter] = clamp_gene(parameter, current * float(factor))
    child["genome_version"] = GENOME_VERSION
    return child


def gene_catalog() -> list[dict[str, Any]]:
    return [{"name": name, **spec} for name, spec in GENE_SPECS.items()]


def gene_values(genome: dict[str, Any]) -> dict[str, Any]:
    g = upgrade_genome(genome)
    return {name: g[name] for name in GENE_SPECS}
