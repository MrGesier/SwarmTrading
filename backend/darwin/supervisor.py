"""ATLAS orchestration for SwarmTrade Darwin V0.11.

The LLM agents propose, interpret and compress. Deterministic components remain
responsible for numerical truth, strategy bounds, paper accounting and risk.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from agents import DarwinBrains
from agents.codex_engineer import CodexEngineer
from engine import GENOMES
from .judge import JudgeConfig, judge
from .genome import MUTABLE_GENES, gene_catalog, upgrade_genome
from .memory import write_epoch_memory
from .paper import PaperPopulation
from .store import DarwinStore
from .scientist import ExperimentPlan, ScientistAgent
from .strategist import StrategistAgent


class DarwinSupervisor:
    def __init__(self, symbol: str, mode: str, data_dir: Path):
        self.symbol = symbol
        self.mode = mode
        self.store = DarwinStore(data_dir / f"darwin-{mode.lower()}-{symbol.lower()}.sqlite")
        base = [upgrade_genome({**g, "generation": 0, "status": "ACTIVE"}) for g in GENOMES]
        self.store.seed_strategies(base)
        strategies = self.store.strategies(include_killed=False)
        self.population = PaperPopulation(
            strategies,
            notional_usd=float(os.getenv("DARWIN_PAPER_NOTIONAL_USD", "1000")),
            fee_bps=float(os.getenv("DARWIN_PAPER_FEE_BPS", "3.5")),
            fee_stress_multiplier=float(os.getenv("DARWIN_FEE_STRESS_MULTIPLIER", "1.5")),
        )
        checkpoint = self.store.load_checkpoint()
        if checkpoint:
            self.population.restore(checkpoint)
        # The frozen G0 control is never selected, retired or mutated.
        self.baseline = PaperPopulation(base, notional_usd=self.population.notional_usd,
            fee_bps=self.population.fee_bps, fee_stress_multiplier=self.population.fee_stress_multiplier)
        if checkpoint and checkpoint.get("fixed_g0"):
            self.baseline.restore(checkpoint["fixed_g0"])
        self.cfg = JudgeConfig(
            min_sample_seconds=float(os.getenv("DARWIN_MIN_SAMPLE_SECONDS", "300")),
            min_closed_trades=int(os.getenv("DARWIN_MIN_CLOSED_TRADES", "5")),
            promotion_min_seconds=float(os.getenv("DARWIN_PROMOTION_MIN_SECONDS", "900")),
            promotion_min_trades=int(os.getenv("DARWIN_PROMOTION_MIN_TRADES", "12")),
            multiple_testing_guard=os.getenv("DARWIN_MULTIPLE_TESTING_GUARD", "true").lower() in {"1", "true", "yes"},
            require_positive_fee_stress=os.getenv("DARWIN_REQUIRE_POSITIVE_FEE_STRESS", "true").lower() in {"1", "true", "yes"},
        )
        self.epoch_seconds = float(os.getenv("DARWIN_EPOCH_SECONDS", "86400"))
        self.max_active_strategies = int(os.getenv("DARWIN_MAX_ACTIVE_STRATEGIES", "400"))
        self.max_new_per_epoch = int(os.getenv("DARWIN_MAX_NEW_PER_EPOCH", "12"))
        self.auto_epoch_enabled = os.getenv("DARWIN_AUTO_EPOCH_ENABLED", "true").lower() in {"1", "true", "yes"}
        recent = self.store.recent_epochs(1)
        self.last_epoch = float(recent[0]["ts"]) if recent else self.store.initial_epoch_time()
        self._retry_epoch_at = 0.0
        self._last_state: dict[str, Any] | None = None
        self.scientist = ScientistAgent()  # deterministic fallback / validator
        self.strategist = StrategistAgent()  # deterministic mutation constructor
        self.brains = DarwinBrains()
        for brain in self.brains._by_id.values():
            brain.reserve_budget = lambda amount: self.store.reserve_llm_budget(amount, float(os.getenv("DARWIN_LLM_DAILY_BUDGET_USD", "1")))
        self.engineer = CodexEngineer()
        self.last_experiment_plans: list[dict[str, Any]] = []
        self.last_agent_events: dict[str, dict[str, Any]] = {}
        self._last_factory_activity = 0.0
        self._last_pnl_record = 0.0
        self._emit("factory_started", {"population": len(self.population.accounts)}, agent_id="atlas")

    def observe(self, state: dict[str, Any]) -> None:
        self._last_state = state
        self.population.observe(state)
        self.baseline.observe(state)
        now = time.time()
        if now - self._last_pnl_record >= 60:
            self.store.record_pnl(self.pnl_state())
            self._last_pnl_record = now
        if now - self._last_factory_activity >= 8.0:
            leaders = self.population.metrics(include_killed=False)[:3]
            self._emit("paper_activity", {"population": len(self.population.accounts), "leaders": [r.get("strategy_id") for r in leaders]}, agent_id="forge")
            self._last_factory_activity = now
            self.checkpoint()

    def checkpoint(self) -> None:
        self.persist_trades()
        payload = self.population.snapshot()
        payload["fixed_g0"] = self.baseline.snapshot()
        source = getattr(self, "source_snapshot", None)
        if source:
            payload["source"] = source()
        self.store.save_checkpoint(payload)

    def _emit(self, event_type: str, payload: dict[str, Any] | None = None, *, agent_id: str | None = None, strategy_id: str | None = None) -> dict[str, Any]:
        return self.store.add_factory_event(event_type, payload or {}, agent_id=agent_id, strategy_id=strategy_id)

    def persist_trades(self) -> None:
        rows = [r for account in self.population.accounts.values() for r in account.closed_trade_log]
        if rows:
            self.store.save_trades(rows)
            for account in self.population.accounts.values():
                account.closed_trade_log.clear()

    def pnl_state(self) -> dict[str, Any]:
        def summarize(rows):
            n = len(rows)
            return {"count": n, "mean_net_usd": sum(r["pnl"] for r in rows)/n if n else None,
                    "mean_fees_usd": sum(r["fees"] for r in rows)/n if n else None,
                    "mean_net_bps": sum(r["return_bps"] for r in rows)/n if n else None,
                    "trades": sum(r["closed_trades"] for r in rows)}
        rows = self.population.metrics()
        return {"window_start": self.population.epoch_start_ts,
                "baseline_window_start": self.baseline.epoch_start_ts,
                "control_window_matches": self.baseline.epoch_start_ts == self.population.epoch_start_ts,
                "market_timestamp": self.population.last_ts,
                "active": summarize(rows), "fixed_g0": summarize(self.baseline.metrics()),
                "descendants": summarize([r for r in rows if r["generation"] > 0]),
                "notional_per_strategy_usd": self.population.notional_usd,
                "fee_bps_per_fill": self.population.fee_bps,
                "funding_modeled": False,
                "execution_model": "visible-book VWAP; spread and partial fills; no queue/latency/market-impact model",
                "definition": "Mean independent strategy account, net of modeled fees. Not a funded portfolio. Resets at each epoch; active cohort may change."}

    def novel_plan(self, parent, proposed):
        """Bounded deterministic exploration if a proposal repeats existing children."""
        known = {s["id"] for s in self.store.strategies(include_killed=True)}
        def novel(plan):
            return any(c["id"] not in known and c["mutation"]["from"] != c["mutation"]["to"]
                       for c in self.strategist.variants(parent, plan))
        if novel(proposed):
            return proposed
        for gene in MUTABLE_GENES:
            candidate = ExperimentPlan(gene, (.85, 1.15),
                f"Test whether a bounded change to {gene} improves net paper results in the next window.",
                "Previous proposal repeats known variants; explore one different gene without changing numerical selection.", .2)
            if novel(candidate):
                return candidate
        return proposed  # finite exploration space may be exhausted; never invent success

    def cycle_state(self, rows=None) -> dict[str, Any]:
        rows = self.population.metrics() if rows is None else rows
        eligible = sum(r["sample_seconds"] >= self.cfg.min_sample_seconds and r["closed_trades"] >= self.cfg.min_closed_trades for r in rows)
        remaining = max(0.0, self.last_epoch + self.epoch_seconds - time.time())
        status = "DISABLED" if not self.auto_epoch_enabled else "COLLECTING" if remaining else "READY" if eligible else "WAITING_EVIDENCE"
        recent = self.store.recent_epochs(1)
        return {"status": status, "next_at": self.last_epoch + self.epoch_seconds,
                "seconds_remaining": remaining, "eligible": eligible, "population": len(rows),
                "min_sample_seconds": self.cfg.min_sample_seconds, "min_closed_trades": self.cfg.min_closed_trades,
                "last_epoch": recent[0] if recent else None,
                "max_generation": max((r["generation"] for r in rows), default=0)}

    def fixed_baseline_comparison(self, rows) -> dict[str, Any]:
        control = self.baseline.metrics()
        descendants = [r for r in rows if r["generation"] > 0]
        windows_match = (self.baseline.epoch_start_ts is not None
                         and self.baseline.epoch_start_ts == self.population.epoch_start_ts
                         and self.baseline.last_ts == self.population.last_ts)
        durations = [r["sample_seconds"] for r in control + descendants]
        matched = bool(windows_match and descendants and durations and max(durations) - min(durations) < 1)
        def mean(group, key):
            return sum(r[key] for r in group) / len(group) if group else None
        return {"version": "fixed-g0-v1", "status": "MATCHED_WINDOW" if matched else "WAITING",
                "g0_count": len(control), "descendant_count": len(descendants),
                "g0_mean_return_bps": mean(control, "return_bps") if matched else None,
                "descendant_mean_return_bps": mean(descendants, "return_bps") if matched else None,
                "g0_mean_drawdown_bps": mean(control, "max_drawdown_bps") if matched else None,
                "descendant_mean_drawdown_bps": mean(descendants, "max_drawdown_bps") if matched else None,
                "g0_trades": sum(r["closed_trades"] for r in control),
                "descendant_trades": sum(r["closed_trades"] for r in descendants),
                "market_return_bps": self.population.benchmark_metrics()["market_return_bps"] if matched else None,
                "sample_seconds": min(durations) if matched else None,
                "fee_bps": self.population.fee_bps,
                "uncertainty": "Not estimated. Correlated strategies and adaptive selection; future-window descriptive evidence, not independent proof.",
                "reason": "Full frozen G0 versus every descendant evaluated before this epoch's selection." if matched else "Waiting for descendants and a complete common observation window; historical results are not reconstructed."}

    def due(self) -> bool:
        return self.auto_epoch_enabled and time.time() >= self._retry_epoch_at and time.time() - self.last_epoch >= self.epoch_seconds

    def _remember_agent(self, agent_id: str, result: Any) -> None:
        try:
            payload = result.to_dict()
            self.last_agent_events[agent_id] = payload
            self.store.add_agent_run(payload)
            self._emit("agent_finished", {"ok": payload.get("ok"), "model": payload.get("model"), "latency_ms": payload.get("latency_ms"), "data": payload.get("data", {})}, agent_id=agent_id)
        except Exception:
            pass

    def _validated_plan(self, parent_row: dict[str, Any], recent_lessons: list[dict[str, Any]]) -> ExperimentPlan:
        fallback_plan = self.scientist.plan(parent_row, recent_lessons)
        fallback = fallback_plan.to_dict()
        self._emit("agent_started", {"task": "design controlled experiment"}, agent_id="curie", strategy_id=parent_row.get("strategy_id"))
        result = self.brains.curie_plan(parent_row, recent_lessons, fallback)
        self._remember_agent("curie", result)
        data = result.data if isinstance(result.data, dict) else fallback
        try:
            parameter = str(data["parameter"])
            if parameter not in MUTABLE_GENES:
                raise ValueError("unsupported parameter")
            factors = tuple(float(x) for x in data["factors"])
            if len(factors) != 2 or any(not 0.75 <= x <= 1.25 for x in factors):
                raise ValueError("invalid factors")
            confidence = min(1.0, max(0.0, float(data["confidence"])))
            return ExperimentPlan(
                parameter=parameter,
                factors=factors,
                hypothesis=str(data["hypothesis"])[:600],
                rationale=str(data["rationale"])[:800],
                confidence=confidence,
            )
        except Exception:
            return fallback_plan

    def _evolve_plan(self, parent: dict[str, Any], plan: ExperimentPlan) -> ExperimentPlan:
        fallback = {"factors": list(plan.factors), "mutation_note": "deterministic validated factors"}
        self._emit("agent_started", {"task": "forge challenger factors"}, agent_id="evolve", strategy_id=parent.get("id"))
        result = self.brains.evolve_variants(parent, plan.to_dict(), fallback)
        self._remember_agent("evolve", result)
        data = result.data if isinstance(result.data, dict) else fallback
        try:
            factors = tuple(float(x) for x in data.get("factors", plan.factors))
            if len(factors) != 2 or any(not 0.75 <= x <= 1.25 for x in factors):
                raise ValueError("invalid factors")
            # Keep the scientific variable/hypothesis fixed; EVOLVE can only refine nearby factors.
            return ExperimentPlan(
                parameter=plan.parameter,
                factors=factors,
                hypothesis=plan.hypothesis,
                rationale=plan.rationale + f" | EVOLVE: {str(data.get('mutation_note', ''))[:300]}",
                confidence=plan.confidence,
            )
        except Exception:
            return plan

    def run_epoch(self, *, force: bool = False) -> dict[str, Any]:
        if not force and not self.due():
            return {"ran": False, "seconds_until_next": max(0.0, self.epoch_seconds - (time.time() - self.last_epoch))}

        self._emit("epoch_started", {"force": force, "population": len(self.population.accounts)}, agent_id="atlas")
        preliminary = self.population.metrics(include_killed=False)
        prelim_eligible = [
            r for r in preliminary
            if r["sample_seconds"] >= self.cfg.min_sample_seconds
            and r["closed_trades"] >= self.cfg.min_closed_trades
        ]
        if not prelim_eligible:
            self._retry_epoch_at = time.time() + 60
            self._emit("epoch_deferred", {"reason": "NOT_ENOUGH_EVIDENCE", "max_sample_seconds": max((r["sample_seconds"] for r in preliminary), default=0.0), "max_closed_trades": max((r["closed_trades"] for r in preliminary), default=0)}, agent_id="judge")
            return {
                "ran": False,
                "reason": "NOT_ENOUGH_EVIDENCE",
                "eligible": 0,
                "min_sample_seconds": self.cfg.min_sample_seconds,
                "min_closed_trades": self.cfg.min_closed_trades,
                "max_sample_seconds": max((r["sample_seconds"] for r in preliminary), default=0.0),
                "max_closed_trades": max((r["closed_trades"] for r in preliminary), default=0),
            }

        if self._last_state is not None:
            self.population.flatten(self._last_state)
            self.baseline.flatten(self._last_state)
        rows = self.population.metrics(include_killed=False)
        benchmark = self.population.benchmark_metrics()
        market_return = float(benchmark.get("market_return_bps", 0.0))
        for row in rows:
            row["alpha_vs_market_bps"] = float(row.get("return_bps", 0.0)) - market_return

        comparison = self.fixed_baseline_comparison(rows)

        # Numerical selection is deterministic and frozen before any LLM sees it.
        evaluations, champion_id = judge(rows, self.cfg)
        strategy_map = {s["id"]: s for s in self.store.strategies(include_killed=True)}

        self._emit("agent_started", {"task": "audit frozen deterministic selection"}, agent_id="judge")
        judge_audit = self.brains.judge_audit(evaluations, champion_id)
        self._remember_agent("judge", judge_audit)
        self._emit("agent_started", {"task": "audit paper execution environment"}, agent_id="forge")
        forge_audit = self.brains.forge_audit(self._last_state or {}, rows)
        self._remember_agent("forge", forge_audit)

        for row in evaluations:
            sid = row["strategy_id"]
            if row["decision"] == "KILL":
                self.store.set_status(sid, "KILLED")
                self.population.set_status(sid, "KILLED")
            elif sid == champion_id:
                self.store.set_status(sid, "CHAMPION")
                self.population.set_status(sid, "CHAMPION")
            elif strategy_map.get(sid, {}).get("status") == "CHAMPION":
                self.store.set_status(sid, "ACTIVE")
                self.population.set_status(sid, "ACTIVE")

        created = 0
        experiment_plans: list[dict[str, Any]] = []
        experiment_records: list[dict[str, Any]] = []
        recent_lessons = self.store.recent_lessons(12)

        ranked = sorted(
            (r for r in evaluations if r["decision"] in {"SCALE", "KEEP"}),
            key=lambda r: r["fitness"],
            reverse=True,
        )[:6]
        def diverse(ids: list[str]) -> list[str]:
            result: list[str] = []
            seen_cells: set[tuple[str, int]] = set()
            for sid in ids:
                row = next((r for r in ranked if r["strategy_id"] == sid), None)
                if not row:
                    continue
                cell = (str(row.get("family")), int(row.get("horizon", 0)))
                if cell in seen_cells:
                    continue
                seen_cells.add(cell)
                result.append(sid)
                if len(result) >= 3:
                    break
            return result

        selected_ids: list[str] = diverse([r["strategy_id"] for r in ranked])
        if ranked:
            self._emit("agent_started", {"task": "select diverse experiment parents"}, agent_id="atlas")
            atlas = self.brains.select_parents(ranked, recent_lessons)
            self._remember_agent("atlas", atlas)
            allowed = {r["strategy_id"] for r in ranked}
            proposed = atlas.data.get("selected_strategy_ids", []) if isinstance(atlas.data, dict) else []
            valid = diverse([sid for sid in proposed if sid in allowed])
            if valid:
                # Preserve diversity even if ATLAS proposes several near-identical parents.
                selected_ids = valid + [sid for sid in selected_ids if sid not in valid]
                selected_ids = diverse(selected_ids)

        row_by_id = {r["strategy_id"]: r for r in evaluations}
        for parent_id in selected_ids:
            parent_row = row_by_id.get(parent_id)
            parent = strategy_map.get(parent_id)
            if not parent_row or not parent:
                continue
            plan = self._validated_plan(parent_row, recent_lessons)
            plan = self._evolve_plan(parent, plan)
            plan = self.novel_plan(parent, plan)
            plan_row = {"parent_id": parent["id"], **plan.to_dict()}
            experiment_plans.append(plan_row)
            self._emit("hypothesis_created", plan_row, agent_id="curie", strategy_id=parent["id"])
            child_ids: list[str] = []
            active_now = sum(1 for a in self.population.accounts.values() if a.strategy.get("status") != "KILLED")
            remaining_capacity = max(0, self.max_active_strategies - active_now)
            remaining_epoch_budget = max(0, self.max_new_per_epoch - created)
            child_budget = min(remaining_capacity, remaining_epoch_budget)
            for child in self.strategist.variants(parent, plan)[:child_budget]:
                if child["mutation"]["from"] == child["mutation"]["to"]:
                    continue
                if self.store.insert_strategy(child):
                    self.population.add_strategy(child)
                    created += 1
                    child_ids.append(child["id"])
            if child_ids:
                mutation_payload = {
                    "parent_id": parent["id"],
                    "child_ids": child_ids,
                    "parameter": plan.parameter,
                    "factors": list(plan.factors),
                    "children": [
                        {"id": cid, "mutation": self.store.strategy(cid).get("mutation", {}) if self.store.strategy(cid) else {}}
                        for cid in child_ids
                    ],
                }
                self._emit("mutation_created", mutation_payload, agent_id="evolve", strategy_id=parent["id"])
                experiment_records.append({"parent_id": parent["id"], "child_ids": child_ids, "plan": plan.to_dict()})
        self.last_experiment_plans = experiment_plans

        config = {
            "min_sample_seconds": self.cfg.min_sample_seconds,
            "min_closed_trades": self.cfg.min_closed_trades,
            "promotion_min_seconds": self.cfg.promotion_min_seconds,
            "promotion_min_trades": self.cfg.promotion_min_trades,
            "paper_notional_usd": self.population.notional_usd,
            "paper_fee_bps": self.population.fee_bps,
            "fee_stress_multiplier": self.population.fee_stress_multiplier,
            "llm_enabled": any(v.get("available") for v in self.brains.states().values()),
            "multiple_testing_guard": self.cfg.multiple_testing_guard,
            "max_active_strategies": self.max_active_strategies,
            "max_new_per_epoch": self.max_new_per_epoch,
            "auto_epoch_enabled": self.auto_epoch_enabled,
            "benchmark": benchmark,
            "fixed_baseline": comparison,
            "genome_version": 2,
            "mutable_genes": list(MUTABLE_GENES),
        }
        epoch_id = self.store.write_epoch(self.symbol, self.mode, champion_id, evaluations, created=created, config=config)
        resolved_experiments = self.store.resolve_open_experiments(evaluations, epoch_id)
        if resolved_experiments:
            for exp in self.store.recent_experiments(20):
                if exp.get("resolved_epoch") == epoch_id:
                    self._emit("experiment_resolved", {"experiment_id": exp.get("id"), "parent_id": exp.get("parent_id"), "winner_id": exp.get("winner_id"), "child_ids": exp.get("child_ids", [])}, agent_id="curie", strategy_id=exp.get("winner_id"))
        for row in evaluations:
            decision = row.get("decision")
            if decision in {"KILL", "KEEP", "SCALE", "RETEST"}:
                self._emit("judge_decision", {"decision": decision, "fitness": row.get("fitness"), "return_bps": row.get("return_bps"), "evidence_weight": row.get("evidence_weight")}, agent_id="judge", strategy_id=row.get("strategy_id"))
            if decision == "KILL":
                self._emit("strategy_killed", {"fitness": row.get("fitness"), "reason": "deterministic judge"}, agent_id="judge", strategy_id=row.get("strategy_id"))
        if champion_id:
            self._emit("champion_promoted", {"epoch_id": epoch_id, "champion_id": champion_id}, agent_id="atlas", strategy_id=champion_id)
        for exp in experiment_records:
            self.store.add_experiment(created_epoch=epoch_id, parent_id=exp["parent_id"], child_ids=exp["child_ids"], plan=exp["plan"])

        # Keep deterministic lessons and add an LLM-compressed lesson separately.
        write_epoch_memory(self.store, evaluations, champion_id)
        self._emit("agent_started", {"task": "compress evidence into memory"}, agent_id="mnemosyne", strategy_id=champion_id)
        memory = self.brains.memory_lesson(evaluations, champion_id, experiment_plans)
        self._remember_agent("mnemosyne", memory)
        if isinstance(memory.data, dict):
            self.store.add_lesson(
                "llm_epoch",
                memory.data,
                strategy_id=champion_id,
                confidence=float(memory.data.get("confidence", 0.2) or 0.2),
            )
            self._emit("lesson_saved", {"confidence": float(memory.data.get("confidence", 0.2) or 0.2), "lesson": memory.data}, agent_id="mnemosyne", strategy_id=champion_id)

        self._emit("epoch_completed", {"epoch_id": epoch_id, "champion_id": champion_id, "created": created, "killed": sum(r["decision"] == "KILL" for r in evaluations), "resolved_experiments": resolved_experiments}, agent_id="atlas", strategy_id=champion_id)
        # Queue evidence-backed engineering work automatically, outside capital authority.
        if created == 0 or not any(r.get("multiple_test_pass") for r in evaluations):
            pending = self.store.recent_engineer_tasks(12)
            if not any(t.get("status") == "PREPARED" for t in pending):
                self.prepare_engineer_task("Investigate research stagnation: compare fees, mutation coverage and next-window evidence. Propose isolated, tested code changes; never modify execution permissions.")
        self.persist_trades()
        self.population.reset_epoch()
        self.baseline.reset_epoch()
        self.checkpoint()
        self.last_epoch = time.time()
        return {
            "ran": True,
            "epoch_id": epoch_id,
            "champion_id": champion_id,
            "created": created,
            "killed": sum(r["decision"] == "KILL" for r in evaluations),
            "eligible": sum(bool(r.get("eligible")) for r in evaluations),
            "top": sorted(evaluations, key=lambda r: r["fitness"], reverse=True)[:12],
            "experiment_plans": experiment_plans,
            "atlas": self.last_agent_events.get("atlas"),
            "judge_audit": self.last_agent_events.get("judge"),
            "forge_audit": self.last_agent_events.get("forge"),
            "memory": self.last_agent_events.get("mnemosyne"),
            "resolved_experiments": resolved_experiments,
            "benchmark": benchmark,
        }


    def openbot_context(self, agent_id: str) -> dict[str, Any]:
        """Return a read-only, redacted research snapshot for an OpenBot coworker.

        The bridge intentionally exposes no exchange credential, private key or
        direct execution method. Each coworker receives only the evidence it
        needs for its standing research role.
        """
        research = self.research_state()
        state = self.state()
        common = {
            "symbol": self.symbol,
            "mode": self.mode,
            "paper_only": True,
            "champion": state.get("champion"),
            "genome": research.get("genome", {}),
            "evidence": research.get("evidence", {}),
            "benchmark": research.get("benchmark", {}),
        }
        if agent_id == "atlas":
            return {**common, "leaderboard": state.get("leaderboard", [])[:16], "experiments": state.get("experiments", [])[:12], "lessons": state.get("lessons", [])[:10]}
        if agent_id == "curie":
            return {**common, "leaderboard": state.get("leaderboard", [])[:12], "experiments": state.get("experiments", [])[:20], "lessons": state.get("lessons", [])[:16]}
        if agent_id == "evolve":
            return {**common, "experiments": state.get("experiments", [])[:20], "leaderboard": state.get("leaderboard", [])[:8]}
        if agent_id == "mnemosyne":
            return {**common, "epochs": state.get("epochs", [])[:12], "experiments": state.get("experiments", [])[:20], "lessons": state.get("lessons", [])[:24]}
        raise KeyError(agent_id)

    def prepare_engineer_task(self, objective: str | None = None) -> dict[str, Any]:
        task = self.engineer.task_pack(self, objective=objective)
        task_id = self.store.add_engineer_task(task)
        task = {**task, "id": task_id, "status": "PREPARED"}
        self._emit("engineer_task_prepared", {"task_id": task_id, "objective": task.get("objective")}, agent_id="codex")
        return task

    def engineer_state(self) -> dict[str, Any]:
        return {
            "engineer": self.engineer.status(),
            "tasks": self.store.recent_engineer_tasks(12),
        }


    def research_state(self) -> dict[str, Any]:
        from .judge import evidence_weight, fitness, multiple_test_threshold, raw_fitness

        rows = self.population.metrics(include_killed=False)
        benchmark = self.population.benchmark_metrics()
        market_return = float(benchmark.get("market_return_bps", 0.0))
        threshold_z = multiple_test_threshold(max(1, len(rows)))
        for row in rows:
            row["raw_fitness"] = raw_fitness(row)
            row["evidence_weight"] = evidence_weight(row, self.cfg)
            row["live_fitness"] = fitness(row, self.cfg)
            row["multiple_test_threshold_z"] = threshold_z
            row["multiple_test_pass"] = bool(float(row.get("trade_z", 0.0)) >= threshold_z) if self.cfg.multiple_testing_guard else True
            row["alpha_vs_market_bps"] = float(row.get("return_bps", 0.0)) - market_return
        eligible = [r for r in rows if r.get("sample_seconds", 0) >= self.cfg.min_sample_seconds and r.get("closed_trades", 0) >= self.cfg.min_closed_trades]
        weights = sorted(float(r.get("evidence_weight", 0.0)) for r in rows)
        median_weight = weights[len(weights) // 2] if weights else 0.0
        cells: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for row in rows:
            key = (str(row.get("family")), int(row.get("horizon", 0)))
            cells.setdefault(key, []).append(row)
        family_cells = []
        for (family, horizon), values in cells.items():
            family_cells.append({
                "family": family,
                "horizon": horizon,
                "n": len(values),
                "mean_live_fitness": sum(float(v.get("live_fitness", 0.0)) for v in values) / len(values),
                "mean_return_bps": sum(float(v.get("return_bps", 0.0)) for v in values) / len(values),
                "evidence_pass": sum(bool(v.get("multiple_test_pass")) for v in values),
            })
        family_cells.sort(key=lambda x: x["mean_live_fitness"], reverse=True)
        market = self._last_state or {}
        features = market.get("features", {}) if isinstance(market, dict) else {}
        return {
            "genome": {"version": 2, "mutable_genes": list(MUTABLE_GENES), "catalog": gene_catalog()},
            "evidence": {
                "population": len(rows),
                "eligible": len(eligible),
                "multiple_test_pass": sum(bool(r.get("multiple_test_pass")) for r in eligible),
                "threshold_z": threshold_z,
                "median_evidence_weight": median_weight,
                "best_trade_z": max((float(r.get("trade_z", 0.0)) for r in rows), default=0.0),
            },
            "benchmark": benchmark,
            "market": {
                "regime": market.get("regime", "WAITING") if isinstance(market, dict) else "WAITING",
                "health": market.get("health", {}).get("status", "WAITING") if isinstance(market, dict) else "WAITING",
                "volatility": features.get("volatility"),
                "spread_bps": features.get("spread"),
                "flow": features.get("flow"),
                "weighted_imbalance": features.get("weighted_imbalance"),
            },
            "family_cells": family_cells[:40],
            "experiments": self.store.recent_experiments(20),
            "llm_usage_24h": self.store.agent_usage_summary(24),
            "agent_runs": self.store.recent_agent_runs(16),
            "engineer": self.engineer_state(),
        }

    def evolution_state(self, limit: int = 120) -> dict[str, Any]:
        """Persistent, explainable view of Darwin's measured evolution."""
        evolution = self.store.evolution_history(limit)
        evolution["current_population"] = len(self.population.accounts)
        evolution["historical_population"] = len(self.store.strategies(include_killed=True))
        evolution["paper_only"] = True
        return evolution

    def state(self) -> dict[str, Any]:
        rows = self.population.metrics(include_killed=False)
        benchmark = self.population.benchmark_metrics()
        market_return = float(benchmark.get("market_return_bps", 0.0))
        from .judge import evidence_weight, fitness, multiple_test_threshold, raw_fitness
        summaries = self.store.strategy_summaries([r["strategy_id"] for r in rows])
        threshold_z = multiple_test_threshold(max(1, len(rows)))
        for row in rows:
            row["raw_fitness"] = raw_fitness(row)
            row["evidence_weight"] = evidence_weight(row, self.cfg)
            row["live_fitness"] = fitness(row, self.cfg)
            row["multiple_test_threshold_z"] = threshold_z
            row["multiple_test_pass"] = bool(float(row.get("trade_z", 0.0)) >= threshold_z) if self.cfg.multiple_testing_guard else True
            row["alpha_vs_market_bps"] = float(row.get("return_bps", 0.0)) - market_return
            row["lifetime"] = summaries.get(row["strategy_id"], {})
        rows.sort(key=lambda r: r["live_fitness"], reverse=True)
        strategies = self.store.strategies(include_killed=True)
        statuses: dict[str, int] = {}
        for s in strategies:
            statuses[s["status"]] = statuses.get(s["status"], 0) + 1
        champion = next((s for s in strategies if s["status"] == "CHAMPION"), None)
        return {
            "symbol": self.symbol,
            "mode": self.mode,
            "population": len(self.population.accounts),
            "historical_population": len(strategies),
            "status_counts": statuses,
            "champion": champion,
            "leaderboard": rows[:25],
            "recent_trades": self.store.recent_trades(),
            "trade_history_note": "Journal available only since trade logging was installed; last 10000 closes retained. Older individual trades cannot be reconstructed from epoch totals.",
            "cycle": self.cycle_state(rows),
            "epoch_seconds": self.epoch_seconds,
            "seconds_since_epoch": max(0.0, time.time() - self.last_epoch),
            "auto_epoch_enabled": self.auto_epoch_enabled,
            "max_active_strategies": self.max_active_strategies,
            "max_new_per_epoch": self.max_new_per_epoch,
            "lessons": self.store.recent_lessons(12),
            "epochs": self.store.recent_epochs(8),
            "paper": {"notional_usd": self.population.notional_usd, "fee_bps": self.population.fee_bps, "fee_stress_multiplier": self.population.fee_stress_multiplier},
            "benchmark": benchmark,
            "judge_config": {
                "min_sample_seconds": self.cfg.min_sample_seconds,
                "min_closed_trades": self.cfg.min_closed_trades,
                "promotion_min_seconds": self.cfg.promotion_min_seconds,
                "promotion_min_trades": self.cfg.promotion_min_trades,
                "multiple_testing_guard": self.cfg.multiple_testing_guard,
                "multiple_test_threshold_z": threshold_z,
                "require_positive_fee_stress": self.cfg.require_positive_fee_stress,
            },
            "experiment_plans": self.last_experiment_plans,
            "experiments": self.store.recent_experiments(12),
            "llm": self.brains.states(),
            "llm_usage_24h": self.store.agent_usage_summary(24),
            "agent_events": self.last_agent_events,
            "engineer": self.engineer_state(),
        }
