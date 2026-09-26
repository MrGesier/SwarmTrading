"""EVOLVE: controlled Genome V2 mutation from a CURIE experiment plan."""
from __future__ import annotations

from typing import Any

from .genome import mutate_gene, upgrade_genome
from .scientist import ExperimentPlan


class StrategistAgent:
    def variants(self, parent: dict[str, Any], plan: ExperimentPlan) -> list[dict[str, Any]]:
        parent = upgrade_genome(parent)
        generation = int(parent.get("generation", 0)) + 1
        children: list[dict[str, Any]] = []
        for index, factor in enumerate(plan.factors):
            child = mutate_gene(parent, plan.parameter, float(factor))
            value = child[plan.parameter]
            compact = str(value).replace(".", "p")[:10]
            suffix = f"g{generation}_{index}_{plan.parameter[:4]}_{compact}"
            child.update({
                "id": f"{parent['id']}__{suffix}",
                "parent_id": parent["id"],
                "generation": generation,
                "family": parent["family"],
                "horizon": int(parent["horizon"]),
                "status": "CHALLENGER",
                "mutation": {
                    "parameter": plan.parameter,
                    "factor": float(factor),
                    "from": parent.get(plan.parameter),
                    "to": value,
                    "hypothesis": plan.hypothesis,
                    "rationale": plan.rationale,
                    "scientist_confidence": plan.confidence,
                },
            })
            children.append(child)
        return children
