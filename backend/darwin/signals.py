"""Signal evaluation for arbitrary SwarmTrade genomes.

The base Engine evaluates the fixed 320-genome population with vectorised numpy.
Darwin needs to evaluate descendants whose gain/threshold can mutate, so this
module mirrors the same transparent feature functions one genome at a time.
"""
from __future__ import annotations

import math
from typing import Mapping, Any

FAMILY_INDEX = {
    "Momentum": 0,
    "Mean reversion": 1,
    "Breakout": 2,
    "Trend": 3,
    "Order flow": 4,
    "Microprice": 5,
    "Book pressure": 6,
    "Volatility": 7,
}


def raw_signal_for_genome(
    features: Mapping[str, Any],
    genome: Mapping[str, Any],
    *,
    price_bp: float = 0.0,
    vol_scale: float = 1.0,
    flow_delta: float = 0.0,
) -> float:
    """Return the continuous tanh signal before entry/exit policy filters."""
    horizon = int(genome["horizon"])
    if not features.get("ready", {}).get(str(horizon), True):
        return 0.0

    momentum = float(features["returns"][str(horizon)]) + float(price_bp)
    volatility = float(features.get("volatility", 0.0))
    norm = max(volatility * math.sqrt(horizon * 2.0) * float(vol_scale), 0.5)
    flow = max(-1.0, min(1.0, float(features.get("flow", 0.0)) + float(flow_delta)))
    family = str(genome["family"])

    if family == "Momentum":
        raw = momentum / norm
    elif family == "Mean reversion":
        raw = -momentum / norm * 0.7
    elif family == "Breakout":
        raw = momentum / norm * (1.0 + abs(flow))
    elif family == "Trend":
        raw = momentum / max(norm, 1.0)
    elif family == "Order flow":
        raw = flow * 1.5
    elif family == "Microprice":
        raw = float(features.get("micro_delta", 0.0)) / max(float(features.get("spread", 0.0)), 0.01) * 2.0
    elif family == "Book pressure":
        raw = float(features.get("weighted_imbalance", 0.0)) * 1.7
    elif family == "Volatility":
        raw = momentum / norm * max(0.2, float(vol_scale) - 0.5)
    else:
        raise ValueError(f"Unknown genome family: {family}")

    return math.tanh(raw * float(genome["gain"]))


def signal_for_genome(
    features: Mapping[str, Any],
    genome: Mapping[str, Any],
    *,
    price_bp: float = 0.0,
    vol_scale: float = 1.0,
    flow_delta: float = 0.0,
) -> float:
    """Legacy-compatible entry signal for one genome.

    Genome V2 execution hysteresis lives in FORGE/PaperAccount; callers that
    only need a stateless vote still receive the familiar thresholded signal.
    """
    value = raw_signal_for_genome(
        features, genome, price_bp=price_bp, vol_scale=vol_scale, flow_delta=flow_delta
    )
    threshold = float(genome.get("threshold", genome.get("entry_threshold", 0.12)))
    return value if abs(value) > threshold else 0.0
