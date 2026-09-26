"""Deterministic strategy judge: evidence first, LLM opinions later.

V0.6 adds an explicit multiple-testing guard. With hundreds of genomes in the
same tournament, the best raw result is often partly selection noise. The judge
therefore separates raw performance from evidence quality and will only SCALE a
champion when its closed-trade evidence clears a conservative family-wise
selection threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt
from typing import Any


@dataclass(frozen=True)
class JudgeConfig:
    min_sample_seconds: float = 300.0
    min_closed_trades: int = 5
    kill_return_bps: float = -35.0
    kill_drawdown_bps: float = 80.0
    promotion_min_trades: int = 12
    promotion_min_seconds: float = 900.0
    keep_fraction: float = 0.25
    kill_fraction: float = 0.20
    multiple_testing_guard: bool = True
    require_positive_fee_stress: bool = True
    evidence_trade_scale: float = 20.0
    evidence_time_scale_seconds: float = 1800.0


def raw_fitness(row: dict[str, Any]) -> float:
    """Risk-adjusted score in basis-point-like units.

    Fees are already included in PnL. Drawdown is explicitly penalised and a
    small turnover penalty discourages noisy variants that only survive on gross
    edge.
    """
    return float(row["return_bps"] - 0.55 * row["max_drawdown_bps"] - 0.15 * row["turnover_x"])


def evidence_weight(row: dict[str, Any], cfg: JudgeConfig) -> float:
    """Continuous 0..1 shrinkage weight based on independent evidence volume."""
    n = max(0.0, float(row.get("closed_trades", 0)))
    seconds = max(0.0, float(row.get("sample_seconds", 0)))
    trade_term = n / (n + max(cfg.evidence_trade_scale, 1e-9))
    time_term = seconds / (seconds + max(cfg.evidence_time_scale_seconds, 1e-9))
    return float(sqrt(max(0.0, trade_term * time_term)))


def multiple_test_threshold(population_size: int) -> float:
    """Extreme-value z threshold for M simultaneous strategy candidates.

    sqrt(2 log M) is intentionally conservative and easy to explain. It is not
    presented as a formal p-value; it is a selection-bias guardrail.
    """
    return float(sqrt(2.0 * log(max(2, int(population_size)))))


def _selection_z(row: dict[str, Any]) -> float:
    z = row.get("trade_z")
    try:
        return float(z) if z is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def fitness(row: dict[str, Any], cfg: JudgeConfig | None = None) -> float:
    cfg = cfg or JudgeConfig()
    raw = raw_fitness(row)
    weight = evidence_weight(row, cfg)
    # Positive edges are shrunk toward zero until evidence accumulates. Negative
    # results remain fully visible so weak strategies are not artificially saved.
    return float(raw * weight if raw > 0 else raw)


def judge(rows: list[dict[str, Any]], cfg: JudgeConfig) -> tuple[list[dict[str, Any]], str | None]:
    population_size = max(1, len(rows))
    z_threshold = multiple_test_threshold(population_size)
    evaluated: list[dict[str, Any]] = []
    for r in rows:
        weight = evidence_weight(r, cfg)
        raw = raw_fitness(r)
        z = _selection_z(r)
        mt_pass = bool(z >= z_threshold) if cfg.multiple_testing_guard else True
        evaluated.append({
            **r,
            "raw_fitness": raw,
            "evidence_weight": weight,
            "fitness": raw * weight if raw > 0 else raw,
            "selection_z": z,
            "multiple_test_threshold_z": z_threshold,
            "multiple_test_pass": mt_pass,
            "decision": "RETEST",
            "eligible": r["sample_seconds"] >= cfg.min_sample_seconds and r["closed_trades"] >= cfg.min_closed_trades,
        })

    eligible = [r for r in evaluated if r["eligible"]]
    if not eligible:
        return evaluated, None

    ordered = sorted(eligible, key=lambda r: (r["fitness"], r["return_bps"]), reverse=True)
    champion = ordered[0]
    promote_ok = (
        champion["sample_seconds"] >= cfg.promotion_min_seconds
        and champion["closed_trades"] >= cfg.promotion_min_trades
        and champion["multiple_test_pass"]
        and (not cfg.require_positive_fee_stress or float(champion.get("fee_stress_return_bps", champion.get("return_bps", 0.0))) > 0)
    )
    champion["decision"] = "SCALE" if promote_ok else "KEEP"

    kill_count = max(1, int(len(ordered) * cfg.kill_fraction)) if len(ordered) >= 5 else 0
    bottom_ids = {r["strategy_id"] for r in ordered[-kill_count:]} if kill_count else set()
    keep_count = max(1, int(len(ordered) * cfg.keep_fraction))
    keep_ids = {r["strategy_id"] for r in ordered[:keep_count]}

    for r in ordered[1:]:
        explicit_bad = r["return_bps"] <= cfg.kill_return_bps or r["max_drawdown_bps"] >= cfg.kill_drawdown_bps
        if explicit_bad and r["strategy_id"] in bottom_ids:
            r["decision"] = "KILL"
        elif r["strategy_id"] in keep_ids:
            r["decision"] = "KEEP"
        else:
            r["decision"] = "RETEST"
    return evaluated, champion["strategy_id"]
