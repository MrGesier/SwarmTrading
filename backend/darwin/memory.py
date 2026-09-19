"""Create compact evidence-backed lessons from each Darwin epoch."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .store import DarwinStore


def write_epoch_memory(store: DarwinStore, evaluations: list[dict[str, Any]], champion_id: str | None) -> None:
    if not evaluations:
        return
    eligible = [r for r in evaluations if r.get("eligible")]
    if champion_id:
        champion = next((r for r in evaluations if r["strategy_id"] == champion_id), None)
        if champion:
            confidence = min(0.99, 0.35 + champion["closed_trades"] / 50.0 + champion["sample_seconds"] / 14400.0)
            store.add_lesson(
                "champion",
                {
                    "family": champion["family"], "horizon": champion["horizon"], "return_bps": round(champion["return_bps"], 3),
                    "max_drawdown_bps": round(champion["max_drawdown_bps"], 3), "closed_trades": champion["closed_trades"],
                    "fitness": round(champion["fitness"], 3), "raw_fitness": round(champion.get("raw_fitness", champion["fitness"]), 3),
                    "evidence_weight": round(champion.get("evidence_weight", 0.0), 3),
                    "selection_z": round(champion.get("selection_z", 0.0), 3),
                    "multiple_test_pass": bool(champion.get("multiple_test_pass", False)),
                    "fee_stress_return_bps": round(champion.get("fee_stress_return_bps", champion["return_bps"]), 3),
                    "alpha_vs_market_bps": round(champion.get("alpha_vs_market_bps", 0.0), 3),
                    "profit_factor": champion.get("profit_factor"), "regime_stats": champion.get("regime_stats", {}),
                    "decision": champion["decision"],
                },
                strategy_id=champion_id,
                confidence=confidence,
            )

    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        groups[(row["family"], row["horizon"])].append(row)
    if groups:
        ranked = sorted(
            ((sum(r["fitness"] for r in rs) / len(rs), family, horizon, len(rs)) for (family, horizon), rs in groups.items()),
            reverse=True,
        )
        best = ranked[0]
        worst = ranked[-1]
        store.add_lesson(
            "population_pattern",
            {
                "best_cell": {"family": best[1], "horizon": best[2], "mean_fitness": round(best[0], 3), "n": best[3]},
                "weakest_cell": {"family": worst[1], "horizon": worst[2], "mean_fitness": round(worst[0], 3), "n": worst[3]},
                "eligible": len(eligible),
            },
            confidence=min(0.9, 0.4 + len(eligible) / 200.0),
        )
