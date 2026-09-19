"""CURIE deterministic fallback scientist for Darwin Genome V2.

The LLM may enrich hypothesis generation, but the fallback itself can already
select several interpretable V2 genes. Every plan changes exactly one variable.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ExperimentPlan:
    parameter: str
    factors: tuple[float, ...]
    hypothesis: str
    rationale: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["factors"] = list(self.factors)
        return d


class ScientistAgent:
    """Chooses one interpretable Genome V2 variable near a successful parent."""

    def plan(self, parent_result: dict[str, Any] | None, recent_lessons: list[dict[str, Any]] | None = None) -> ExperimentPlan:
        row = parent_result or {}
        dd = float(row.get("max_drawdown_bps", 0.0))
        ret = float(row.get("return_bps", 0.0))
        turnover = float(row.get("turnover_x", 0.0))
        trades = int(row.get("closed_trades", 0))
        avg_hold = float(row.get("avg_holding_seconds", 0.0) or 0.0)
        exits = row.get("exit_reasons") or {}
        signal_decay = int(exits.get("signal_decay", 0) or 0)
        signal_flip = int(exits.get("signal_flip", 0) or 0)
        stopped = int(exits.get("stop_loss", 0) or 0)

        if turnover >= 8.0:
            return ExperimentPlan(
                parameter="cooldown_seconds",
                factors=(1.10, 1.25),
                hypothesis="A short post-trade cooldown may preserve edge while reducing churn and repeated fee-paying re-entry.",
                rationale=f"Turnover is high at {turnover:.1f}x; test one execution-policy gene instead of changing signal semantics.",
                confidence=min(0.90, 0.45 + trades / 80.0),
            )
        if dd > max(30.0, abs(ret) * 1.4):
            return ExperimentPlan(
                parameter="stop_loss_bps",
                factors=(0.80, 0.90),
                hypothesis="A tighter deterministic paper stop may reduce tail drawdown while preserving the signal's directional edge.",
                rationale=f"Drawdown ({dd:.1f} bp) dominates observed return ({ret:.1f} bp).",
                confidence=min(0.88, 0.42 + trades / 80.0),
            )
        if trades >= 8 and signal_decay > max(signal_flip, trades // 3):
            return ExperimentPlan(
                parameter="exit_threshold",
                factors=(0.85, 1.15),
                hypothesis="Entry edge may be sound while exit hysteresis is suboptimal; a nearby exit threshold could improve trade quality.",
                rationale=f"Signal-decay exits dominate the exit mix ({signal_decay}/{max(1,trades)} closed trades).",
                confidence=min(0.84, 0.38 + trades / 100.0),
            )
        if stopped >= max(3, trades // 3):
            return ExperimentPlan(
                parameter="confirmation_ticks",
                factors=(0.90, 1.10),
                hypothesis="Requiring one additional confirming tick may filter noisy entries that frequently reach the stop.",
                rationale=f"Stop-loss exits are frequent ({stopped}/{max(1,trades)}); test entry confirmation without changing the signal formula.",
                confidence=min(0.82, 0.36 + trades / 100.0),
            )
        if avg_hold > 150:
            return ExperimentPlan(
                parameter="max_holding_seconds",
                factors=(0.85, 1.15),
                hypothesis="The edge may depend on a narrower holding window than the current policy allows.",
                rationale=f"Average completed holding time is {avg_hold:.0f}s; test nearby time exits.",
                confidence=min(0.78, 0.34 + trades / 120.0),
            )
        return ExperimentPlan(
            parameter="threshold",
            factors=(0.92, 1.08),
            hypothesis="The current edge may improve with a nearby entry-selectivity change.",
            rationale="No dominant churn, drawdown or exit-policy failure mode detected; run symmetric local exploration.",
            confidence=min(0.82, 0.35 + trades / 100.0),
        )
