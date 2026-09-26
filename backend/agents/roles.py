"""Darwin V0.11 brain roles.

Only ATLAS, CURIE, EVOLVE, JUDGE and MNEMOSYNE use model reasoning by default.
FORGE, CERBERUS and HERMES remain deterministic authority components.
"""
from __future__ import annotations

from typing import Any

from .llm import AgentBrain, LLMResult


OBJ = {"type": "object", "additionalProperties": False}


class DarwinBrains:
    def __init__(self):
        self.atlas = AgentBrain(
            "atlas",
            """You are ATLAS, CEO of a quantitative research lab. Allocate research attention, never capital. Select evidence-rich and diverse parents for controlled experiments. Prefer reproducibility over headline PnL. Never invent metrics, never alter measured evidence, never authorize live trading, and never weaken deterministic risk limits.""",
            prompt_version="atlas-v0.8",
        )
        self.curie = AgentBrain(
            "curie",
            """You are CURIE, a skeptical quantitative scientist. Form one falsifiable local hypothesis from measured results and stored memory. Change one permitted variable at a time, keep mutations small, and explicitly avoid hindsight, multiple-testing traps and repeated failed experiments. You never place orders or promote strategies.""",
            prompt_version="curie-v0.12-trade-context",
        )
        self.evolve = AgentBrain(
            "evolve",
            """You are EVOLVE, a bounded strategy mutation engineer. Refine only the numerical mutation factors for an already approved experiment. Preserve lineage and the scientific variable under test. Stay close to the parent. You never send orders and never alter measured evidence.""",
            prompt_version="evolve-v0.8",
        )
        self.forge = AgentBrain(
            "forge",
            "FORGE is deterministic paper-execution code. It never delegates authoritative fills, PnL, fees or positions to a model.",
            prompt_version="forge-v0.8",
        )
        self.judge = AgentBrain(
            "judge",
            """You are JUDGE's independent model-risk critic. Deterministic code already computed fitness and KEEP/KILL/SCALE. Audit the frozen results for overfitting, selection bias, weak sample size, regime concentration, unstable turnover and fee fragility. You may flag concerns but you cannot override numerical decisions.""",
            prompt_version="judge-v0.8",
        )
        self.mnemosyne = AgentBrain(
            "mnemosyne",
            """You are MNEMOSYNE, long-term experimental memory. Compress one completed epoch into one reusable evidence-backed lesson. Separate observation from hypothesis, state uncertainty, and identify what should not be repeated. Never alter historical measurements.""",
            prompt_version="mnemosyne-v0.8",
        )
        self.cerberus = AgentBrain(
            "cerberus",
            "CERBERUS is a deterministic risk gate. No model can override failed hard checks.",
            prompt_version="cerberus-v0.8",
        )
        self.hermes = AgentBrain(
            "hermes",
            "HERMES is a deterministic execution translator. It never invents or modifies approved order parameters.",
            prompt_version="hermes-v0.8",
        )
        self._by_id = {
            x.agent_id: x
            for x in [
                self.atlas,
                self.curie,
                self.evolve,
                self.forge,
                self.judge,
                self.mnemosyne,
                self.cerberus,
                self.hermes,
            ]
        }

    def states(self) -> dict[str, dict[str, Any]]:
        return {k: v.state() for k, v in self._by_id.items()}

    def select_parents(self, candidates: list[dict[str, Any]], lessons: list[dict[str, Any]]) -> LLMResult:
        allowed = [r["strategy_id"] for r in candidates[:6]]
        fallback = {
            "selected_strategy_ids": allowed[:3],
            "focus": "local robustness",
            "reason": "deterministic top-ranked diverse fallback",
        }
        schema = {
            **OBJ,
            "properties": {
                "selected_strategy_ids": {"type": "array", "items": {"type": "string", "enum": allowed}, "maxItems": 3},
                "focus": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["selected_strategy_ids", "focus", "reason"],
        }
        return self.atlas.ask_json(
            task="Choose up to three parent strategy IDs worth spending the next experiment budget on. Prefer distinct family/horizon cells and reproducible evidence. If a measured_incident is present, prioritize a falsifiable repair experiment on affected strategies; do not describe a hypothesis as a proven fix.",
            context={"candidates": candidates[:6], "recent_lessons": lessons[:12]},
            schema_name="atlas_parent_selection",
            schema=schema,
            fallback=fallback,
        )

    def curie_plan(self, parent_result: dict[str, Any], lessons: list[dict[str, Any]], fallback: dict[str, Any]) -> LLMResult:
        schema = {
            **OBJ,
            "properties": {
                "parameter": {"type": "string", "enum": ["threshold", "gain", "exit_threshold", "max_holding_seconds", "cooldown_seconds", "stop_loss_bps", "take_profit_bps", "confirmation_ticks"]},
                "factors": {
                    "type": "array",
                    "items": {"type": "number", "minimum": 0.75, "maximum": 1.25},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "hypothesis": {"type": "string"},
                "rationale": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["parameter", "factors", "hypothesis", "rationale", "confidence"],
        }
        return self.curie.ask_json(
            task="Design exactly one controlled two-arm Genome V2 experiment around this parent. Change one permitted gene only, prefer small local mutations, use memory to avoid repeated failures, and make the hypothesis falsifiable. Explicitly assess the supplied research_questions, fees, holding time and exit reasons in the rationale. Distinguish measured evidence from missing indicator ablations. Do not claim to introduce a new indicator or rewrite code.",
            context={"parent_result": parent_result, "recent_lessons": lessons[:12]},
            schema_name="curie_experiment",
            schema=schema,
            fallback=fallback,
        )

    def evolve_variants(self, parent: dict[str, Any], plan: dict[str, Any], fallback: dict[str, Any]) -> LLMResult:
        schema = {
            **OBJ,
            "properties": {
                "factors": {
                    "type": "array",
                    "items": {"type": "number", "minimum": 0.75, "maximum": 1.25},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "mutation_note": {"type": "string"},
            },
            "required": ["factors", "mutation_note"],
        }
        return self.evolve.ask_json(
            task="Refine only the two numerical mutation factors for the approved experiment. Stay close to the parent and do not change the parameter under test.",
            context={"parent": parent, "plan": plan},
            schema_name="evolve_mutation",
            schema=schema,
            fallback=fallback,
        )

    def forge_audit(self, market: dict[str, Any], leaders: list[dict[str, Any]]) -> LLMResult:
        """Deterministic execution-quality summary; no LLM participates in paper truth."""
        health = (market.get("health") or {}).get("status", "WAITING") if isinstance(market, dict) else "WAITING"
        regime = market.get("regime", "unknown") if isinstance(market, dict) else "unknown"
        warning = "none" if health == "HEALTHY" else f"market data health={health}"
        fallback = {
            "regime": str(regime),
            "paper_quality": f"deterministic engine active · {len(leaders)} measured strategies",
            "warning": warning,
        }
        schema = {
            **OBJ,
            "properties": {
                "regime": {"type": "string"},
                "paper_quality": {"type": "string"},
                "warning": {"type": "string"},
            },
            "required": ["regime", "paper_quality", "warning"],
        }
        return self.forge.ask_json(
            task="Return the deterministic paper engine status.",
            context={"market": market, "top_paper": leaders[:5]},
            schema_name="forge_audit",
            schema=schema,
            fallback=fallback,
        )

    def judge_audit(self, evaluations: list[dict[str, Any]], champion_id: str | None) -> LLMResult:
        fallback = {"assessment": "deterministic selection retained", "overfit_risk": "unknown", "concerns": []}
        schema = {
            **OBJ,
            "properties": {
                "assessment": {"type": "string"},
                "overfit_risk": {"type": "string", "enum": ["low", "medium", "high", "unknown"]},
                "concerns": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            },
            "required": ["assessment", "overfit_risk", "concerns"],
        }
        return self.judge.ask_json(
            task="Audit the frozen deterministic selection. Identify evidence weaknesses; do not change KEEP/KILL/SCALE labels.",
            context={
                "champion_id": champion_id,
                "evaluations": sorted(evaluations, key=lambda r: r.get("fitness", 0), reverse=True)[:20],
            },
            schema_name="judge_audit",
            schema=schema,
            fallback=fallback,
        )

    def memory_lesson(self, evaluations: list[dict[str, Any]], champion_id: str | None, plans: list[dict[str, Any]]) -> LLMResult:
        fallback = {"observation": "epoch completed", "hypothesis": "none", "avoid_next": "none", "confidence": 0.2}
        schema = {
            **OBJ,
            "properties": {
                "observation": {"type": "string"},
                "hypothesis": {"type": "string"},
                "avoid_next": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["observation", "hypothesis", "avoid_next", "confidence"],
        }
        return self.mnemosyne.ask_json(
            task="Write one compact reusable lesson from this completed experiment epoch. Ground it only in supplied evidence.",
            context={
                "champion_id": champion_id,
                "top": sorted(evaluations, key=lambda r: r.get("fitness", 0), reverse=True)[:10],
                "plans": plans,
            },
            schema_name="memory_lesson",
            schema=schema,
            fallback=fallback,
        )

    def cerberus_review(self, intent: dict[str, Any], deterministic_checks: dict[str, Any]) -> LLMResult:
        """Deterministic gate result. A model is deliberately absent from capital authority."""
        allow = bool(deterministic_checks.get("allow"))
        checks = deterministic_checks.get("checks") or {}
        failed = [name for name, passed in checks.items() if not passed]
        fallback = {
            "recommendation": "ALLOW" if allow else "BLOCK",
            "risk_flags": failed,
            "reason": "all hard checks passed" if allow else "failed hard checks: " + ", ".join(failed),
        }
        schema = {
            **OBJ,
            "properties": {
                "recommendation": {"type": "string", "enum": ["ALLOW", "BLOCK"]},
                "risk_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                "reason": {"type": "string"},
            },
            "required": ["recommendation", "risk_flags", "reason"],
        }
        return self.cerberus.ask_json(
            task="Return deterministic hard-gate result.",
            context={"intent": intent, "hard_checks": deterministic_checks},
            schema_name="cerberus_review",
            schema=schema,
            fallback=fallback,
        )

    def hermes_note(self, approved_intent: dict[str, Any]) -> LLMResult:
        fallback = {
            "execution_note": "approved parameters will be submitted unchanged",
            "watch": "exchange acknowledgement, fill status and slippage",
        }
        schema = {
            **OBJ,
            "properties": {"execution_note": {"type": "string"}, "watch": {"type": "string"}},
            "required": ["execution_note", "watch"],
        }
        return self.hermes.ask_json(
            task="Return deterministic execution note without modifying intent.",
            context={"approved_intent": approved_intent},
            schema_name="hermes_note",
            schema=schema,
            fallback=fallback,
        )
