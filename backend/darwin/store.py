"""SQLite-backed long-term memory for Darwin experiments.

V0.6 stores not only winners, but the experiment contract, child lineage,
statistical diagnostics and LLM usage. This makes every promotion auditable.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .genome import upgrade_genome, gene_values


class DarwinStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS llm_budget (ts REAL NOT NULL, reserved_usd REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS paper_checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), epoch_id INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS strategies (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    generation INTEGER NOT NULL DEFAULT 0,
                    family TEXT NOT NULL,
                    horizon INTEGER NOT NULL,
                    threshold REAL NOT NULL,
                    gain REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at REAL NOT NULL,
                    retired_at REAL,
                    mutation_json TEXT NOT NULL DEFAULT '{}',
                    genome_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS epochs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    symbol TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    champion_id TEXT,
                    eligible INTEGER NOT NULL,
                    active INTEGER NOT NULL,
                    killed INTEGER NOT NULL,
                    created INTEGER NOT NULL,
                    config_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS evaluations (
                    epoch_id INTEGER NOT NULL,
                    strategy_id TEXT NOT NULL,
                    pnl REAL NOT NULL,
                    return_bps REAL NOT NULL,
                    max_drawdown_bps REAL NOT NULL,
                    turnover_x REAL NOT NULL,
                    fees REAL NOT NULL,
                    orders INTEGER NOT NULL,
                    closed_trades INTEGER NOT NULL,
                    win_rate REAL,
                    sample_seconds REAL NOT NULL,
                    fitness REAL NOT NULL,
                    decision TEXT NOT NULL,
                    PRIMARY KEY (epoch_id, strategy_id)
                );
                CREATE TABLE IF NOT EXISTS evaluation_details (
                    epoch_id INTEGER NOT NULL,
                    strategy_id TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (epoch_id, strategy_id)
                );
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    strategy_id TEXT,
                    confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    agent_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    error TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS factory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    type TEXT NOT NULL,
                    agent_id TEXT,
                    strategy_id TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_factory_events_ts ON factory_events(ts, id);
                CREATE TABLE IF NOT EXISTS experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_ts REAL NOT NULL,
                    created_epoch INTEGER,
                    resolved_ts REAL,
                    resolved_epoch INTEGER,
                    parent_id TEXT NOT NULL,
                    child_ids_json TEXT NOT NULL DEFAULT '[]',
                    parameter TEXT NOT NULL,
                    factors_json TEXT NOT NULL DEFAULT '[]',
                    hypothesis TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RUNNING',
                    winner_id TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_eval_strategy ON evaluations(strategy_id, epoch_id);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_ts ON agent_runs(ts, agent_id);
                CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status, created_ts);
                CREATE TABLE IF NOT EXISTS engineer_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PREPARED',
                    objective TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            # Forward-compatible V0.8 migration for existing SQLite memories.
            existing = {r[1] for r in self._db.execute("PRAGMA table_info(agent_runs)").fetchall()}
            for name, sql_type, default in [
                ("runtime", "TEXT", "''"),
                ("provider", "TEXT", "''"),
                ("reasoning_effort", "TEXT", "''"),
                ("prompt_version", "TEXT", "''"),
                ("estimated_cost_usd", "REAL", "NULL"),
            ]:
                if name not in existing:
                    self._db.execute(f"ALTER TABLE agent_runs ADD COLUMN {name} {sql_type} DEFAULT {default}")
            strategy_columns = {r[1] for r in self._db.execute("PRAGMA table_info(strategies)").fetchall()}
            if "genome_json" not in strategy_columns:
                self._db.execute("ALTER TABLE strategies ADD COLUMN genome_json TEXT NOT NULL DEFAULT '{}'")
            self._db.commit()

    def record_pnl(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS pnl_timeline (id INTEGER PRIMARY KEY, ts REAL NOT NULL, payload TEXT NOT NULL)")
            self._db.execute("INSERT INTO pnl_timeline(ts,payload) VALUES (?,?)", (time.time(), json.dumps(payload)))
            self._db.execute("DELETE FROM pnl_timeline WHERE id NOT IN (SELECT id FROM pnl_timeline ORDER BY id DESC LIMIT 1440)")
            self._db.commit()

    def pnl_history(self) -> list[dict[str, Any]]:
        with self._lock:
            exists = self._db.execute("SELECT 1 FROM sqlite_master WHERE name='pnl_timeline'").fetchone()
            if not exists:
                return []
            return [{"recorded_at": r[0], **json.loads(r[1])} for r in self._db.execute("SELECT ts,payload FROM pnl_timeline ORDER BY id")]

    def initial_epoch_time(self) -> float:
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS runtime_metadata (key TEXT PRIMARY KEY, value REAL NOT NULL)")
            earliest = self._db.execute("SELECT MIN(ts) FROM factory_events WHERE type='factory_started'").fetchone()[0]
            self._db.execute("INSERT OR IGNORE INTO runtime_metadata VALUES ('initial_epoch_time', ?)", (earliest if earliest is not None else time.time(),))
            self._db.commit()
            return float(self._db.execute("SELECT value FROM runtime_metadata WHERE key='initial_epoch_time'").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def reserve_llm_budget(self, amount: float, daily_limit: float) -> bool:
        if not math.isfinite(amount) or amount < 0 or not math.isfinite(daily_limit) or daily_limit <= 0:
            return False
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("DELETE FROM llm_budget WHERE ts<?", (time.time()-86400,))
                spent = self._db.execute("SELECT COALESCE(SUM(reserved_usd),0) FROM llm_budget").fetchone()[0]
                if spent + amount > daily_limit:
                    self._db.rollback()
                    return False
                self._db.execute("INSERT INTO llm_budget VALUES(?,?)", (time.time(), amount))
                self._db.commit()
                return True
            except Exception:
                self._db.rollback()
                raise

    def save_checkpoint(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        with self._lock:
            epoch = self._db.execute("SELECT COALESCE(MAX(id),0) FROM epochs").fetchone()[0]
            self._db.execute("INSERT OR REPLACE INTO paper_checkpoint VALUES(1,?,?)", (epoch, encoded))
            self._db.commit()

    def load_checkpoint(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT payload FROM paper_checkpoint WHERE epoch_id=(SELECT COALESCE(MAX(id),0) FROM epochs)").fetchone()
        return json.loads(row[0]) if row else None

    def seed_strategies(self, strategies: Iterable[dict[str, Any]]) -> None:
        now = time.time()
        upgraded = [upgrade_genome(dict(s)) for s in strategies]
        rows = [
            (
                s["id"], s.get("parent_id"), int(s.get("generation", 0)), s["family"], int(s["horizon"]),
                float(s["threshold"]), float(s["gain"]), s.get("status", "ACTIVE"), float(s.get("created_at", now)),
                None, json.dumps(s.get("mutation", {}), separators=(",", ":")),
                json.dumps({"genome_version": s.get("genome_version", 2), **gene_values(s)}, separators=(",", ":")),
            )
            for s in upgraded
        ]
        with self._lock:
            self._db.executemany(
                """INSERT OR IGNORE INTO strategies
                (id,parent_id,generation,family,horizon,threshold,gain,status,created_at,retired_at,mutation_json,genome_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            self._db.commit()

    def strategies(self, *, include_killed: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM strategies" + ("" if include_killed else " WHERE status!='KILLED'") + " ORDER BY generation,id"
        with self._lock:
            rows = self._db.execute(sql).fetchall()
        return [self._strategy(dict(r)) for r in rows]

    def strategy(self, strategy_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM strategies WHERE id=?", (strategy_id,)).fetchone()
        return self._strategy(dict(row)) if row else None

    def _strategy(self, row: dict[str, Any]) -> dict[str, Any]:
        base = {
            "id": row["id"], "parent_id": row["parent_id"], "generation": row["generation"],
            "family": row["family"], "horizon": row["horizon"], "threshold": row["threshold"],
            "gain": row["gain"], "status": row["status"], "created_at": row["created_at"],
            "retired_at": row["retired_at"], "mutation": json.loads(row["mutation_json"] or "{}"),
        }
        try:
            extra = json.loads(row.get("genome_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            extra = {}
        base.update(extra)
        return upgrade_genome(base)

    def insert_strategy(self, strategy: dict[str, Any]) -> bool:
        now = time.time()
        strategy = upgrade_genome(dict(strategy))
        with self._lock:
            cur = self._db.execute(
                """INSERT OR IGNORE INTO strategies
                (id,parent_id,generation,family,horizon,threshold,gain,status,created_at,retired_at,mutation_json,genome_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    strategy["id"], strategy.get("parent_id"), int(strategy.get("generation", 0)), strategy["family"], int(strategy["horizon"]),
                    float(strategy["threshold"]), float(strategy["gain"]), strategy.get("status", "CHALLENGER"), now, None,
                    json.dumps(strategy.get("mutation", {}), separators=(",", ":")),
                    json.dumps({"genome_version": strategy.get("genome_version", 2), **gene_values(strategy)}, separators=(",", ":")),
                ),
            )
            self._db.commit()
            return cur.rowcount > 0

    def set_status(self, strategy_id: str, status: str) -> None:
        retired = time.time() if status == "KILLED" else None
        with self._lock:
            self._db.execute("UPDATE strategies SET status=?, retired_at=? WHERE id=?", (status, retired, strategy_id))
            self._db.commit()

    def write_epoch(self, symbol: str, mode: str, champion_id: str | None, evaluations: list[dict[str, Any]], *, created: int, config: dict[str, Any]) -> int:
        killed = sum(1 for r in evaluations if r["decision"] == "KILL")
        eligible = sum(1 for r in evaluations if r.get("eligible"))
        active = sum(1 for r in evaluations if r["decision"] != "KILL")
        with self._lock:
            self._db.execute("SAVEPOINT epoch_write")
            try:
                cur = self._db.execute(
                    "INSERT INTO epochs(ts,symbol,mode,champion_id,eligible,active,killed,created,config_json) VALUES (?,?,?,?,?,?,?,?,?)",
                    (time.time(), symbol, mode, champion_id, eligible, active, killed, created, json.dumps(config, separators=(",", ":"))),
                )
                epoch_id = int(cur.lastrowid)
                self._db.executemany(
                    """INSERT INTO evaluations
                    (epoch_id,strategy_id,pnl,return_bps,max_drawdown_bps,turnover_x,fees,orders,closed_trades,win_rate,sample_seconds,fitness,decision)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [
                        (
                            epoch_id, r["strategy_id"], r["pnl"], r["return_bps"], r["max_drawdown_bps"], r["turnover_x"], r["fees"],
                            r["orders"], r["closed_trades"], r["win_rate"], r["sample_seconds"], r["fitness"], r["decision"],
                        )
                        for r in evaluations
                    ],
                )
                detail_keys = {
                    "raw_fitness", "evidence_weight", "selection_z", "multiple_test_threshold_z", "multiple_test_pass",
                    "expectancy_usd", "mean_trade_bps", "trade_std_bps", "trade_z", "profit_factor", "payoff_ratio",
                    "gross_profit", "gross_loss", "regime_stats", "fee_stress_multiplier", "fee_stress_return_bps", "alpha_vs_market_bps", "eligible",
                    "genome_version", "genes", "exit_reasons", "last_exit_reason", "avg_holding_seconds", "unobserved_seconds", "observation_policy",
                }
                self._db.executemany(
                    "INSERT OR REPLACE INTO evaluation_details(epoch_id,strategy_id,details_json) VALUES (?,?,?)",
                    [
                        (epoch_id, r["strategy_id"], json.dumps({k: r.get(k) for k in detail_keys if k in r}, separators=(",", ":"), default=str))
                        for r in evaluations
                    ],
                )
                self._db.execute("RELEASE SAVEPOINT epoch_write")
            except BaseException:
                self._db.execute("ROLLBACK TO SAVEPOINT epoch_write")
                self._db.execute("RELEASE SAVEPOINT epoch_write")
                raise
        return epoch_id

    def add_lesson(self, kind: str, payload: dict[str, Any], *, strategy_id: str | None = None, confidence: float = 0.5) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO lessons(ts,kind,strategy_id,confidence,payload_json) VALUES (?,?,?,?,?)",
                (time.time(), kind, strategy_id, float(confidence), json.dumps(payload, separators=(",", ":"))),
            )
            self._db.commit()

    def recent_lessons(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM lessons ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [
            {"id": r["id"], "ts": r["ts"], "kind": r["kind"], "strategy_id": r["strategy_id"], "confidence": r["confidence"], "payload": json.loads(r["payload_json"])}
            for r in rows
        ]

    def add_agent_run(self, result: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO agent_runs(ts,agent_id,model,ok,latency_ms,prompt_tokens,completion_tokens,error,payload_json,
                                           runtime,provider,reasoning_effort,prompt_version,estimated_cost_usd)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (time.time(), result.get("agent_id", "unknown"), result.get("model", ""), 1 if result.get("ok") else 0,
                 int(result.get("latency_ms", 0)), result.get("prompt_tokens"), result.get("completion_tokens"),
                 str(result.get("error", ""))[:500], json.dumps(result.get("data", {}), separators=(",", ":"), default=str),
                 str(result.get("runtime", "")), str(result.get("provider", "")), str(result.get("reasoning_effort", "")),
                 str(result.get("prompt_version", "")), result.get("estimated_cost_usd")),
            )
            self._db.commit()

    def recent_agent_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [
            {**dict(r), "ok": bool(r["ok"]), "payload": json.loads(r["payload_json"] or "{}")}
            for r in rows
        ]

    def agent_usage_summary(self, hours: float = 24.0) -> dict[str, Any]:
        since = time.time() - max(0.1, float(hours)) * 3600
        with self._lock:
            rows = self._db.execute(
                """SELECT agent_id, model, runtime, provider, COUNT(*) calls, SUM(ok) ok_calls,
                          COALESCE(SUM(prompt_tokens),0) prompt_tokens,
                          COALESCE(SUM(completion_tokens),0) completion_tokens,
                          COALESCE(SUM(estimated_cost_usd),0) estimated_cost_usd,
                          COALESCE(AVG(latency_ms),0) avg_latency_ms
                   FROM agent_runs WHERE ts>=? GROUP BY agent_id, model, runtime, provider ORDER BY calls DESC""",
                (since,),
            ).fetchall()
        agents = [dict(r) for r in rows]
        return {
            "hours": hours,
            "calls": sum(int(r["calls"]) for r in agents),
            "ok_calls": sum(int(r["ok_calls"] or 0) for r in agents),
            "prompt_tokens": sum(int(r["prompt_tokens"] or 0) for r in agents),
            "completion_tokens": sum(int(r["completion_tokens"] or 0) for r in agents),
            "estimated_cost_usd": sum(float(r["estimated_cost_usd"] or 0.0) for r in agents),
            "agents": agents,
        }

    def add_engineer_task(self, task: dict[str, Any], *, status: str = "PREPARED") -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO engineer_tasks(ts,status,objective,payload_json) VALUES (?,?,?,?)",
                (time.time(), status, str(task.get("objective", ""))[:1000], json.dumps(task, separators=(",", ":"), default=str)),
            )
            self._db.commit()
            return int(cur.lastrowid)

    def recent_engineer_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM engineer_tasks ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload_json"] or "{}")} for r in rows]

    def recent_epochs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM epochs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [{**dict(r), "config": json.loads(r["config_json"] or "{}")} for r in rows]


    def evolution_history(self, limit: int = 120) -> dict[str, Any]:
        """Summarize how Darwin changes over epochs without claiming live edge.

        The score is a *research quality* index, not a profitability forecast. It
        rewards paper alpha, evidence quality, fee-stress survival, drawdown
        control and multiple-testing evidence. Every component is returned so the
        UI can explain why the index moved.
        """
        limit = max(1, min(int(limit), 500))
        with self._lock:
            epoch_rows = self._db.execute(
                "SELECT * FROM epochs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            epoch_rows = list(reversed(epoch_rows))

            strategies = self._db.execute(
                "SELECT id,status,generation,family,horizon,mutation_json,genome_json FROM strategies"
            ).fetchall()

        def clamp01(x: float) -> float:
            return min(1.0, max(0.0, float(x)))

        def centered(x: float, scale: float) -> float:
            # 0 bp -> 0.5, positive -> 1, negative -> 0.
            return clamp01(0.5 + 0.5 * math.tanh(float(x) / max(1e-9, scale)))

        history: list[dict[str, Any]] = []
        comparisons = []
        family_wins: dict[str, int] = {}
        previous_champion: str | None = None
        champion_changes = 0

        for ep in epoch_rows:
            epoch_id = int(ep["id"])
            with self._lock:
                rows = self._db.execute(
                    """SELECT e.*, d.details_json, s.family, s.horizon, s.generation
                       FROM evaluations e
                       LEFT JOIN evaluation_details d ON d.epoch_id=e.epoch_id AND d.strategy_id=e.strategy_id
                       LEFT JOIN strategies s ON s.id=e.strategy_id
                       WHERE e.epoch_id=? ORDER BY e.fitness DESC""",
                    (epoch_id,),
                ).fetchall()
            if not rows:
                continue

            decoded = []
            for row in rows:
                item = dict(row)
                try:
                    item["details"] = json.loads(item.pop("details_json") or "{}")
                except Exception:
                    item["details"] = {}
                decoded.append(item)

            baseline = [r for r in decoded if r["generation"] == 0]
            descendants = [r for r in decoded if r["generation"] > 0]
            durations = [float(r["sample_seconds"]) for r in baseline + descendants]
            comparable = bool(baseline and descendants and max(durations) - min(durations) < 1.0)
            comparisons.append({
                "epoch_id": epoch_id, "status": "MATCHED_WINDOW" if comparable else "WAITING",
                "g0_count": len(baseline), "descendant_count": len(descendants),
                "g0_mean_return_bps": sum(r["return_bps"] for r in baseline) / len(baseline) if comparable else None,
                "descendant_mean_return_bps": sum(r["return_bps"] for r in descendants) / len(descendants) if comparable else None,
                "g0_trades": sum(r["closed_trades"] for r in baseline),
                "descendant_trades": sum(r["closed_trades"] for r in descendants),
                "sample_seconds": min(durations) if comparable else None,
                "uncertainty": "Not estimated; selected survivors, correlated strategies and multiple testing. Missing/retired G0 are not imputed; this is not a fixed-cohort causal baseline.",
            })
            champion_id = ep["champion_id"]
            champion = next((r for r in decoded if r["strategy_id"] == champion_id), decoded[0])
            details = champion.get("details") or {}
            config = json.loads(ep["config_json"] or "{}")
            benchmark = config.get("benchmark") or {}
            market_return = float(benchmark.get("market_return_bps", 0.0) or 0.0)
            alpha = float(details.get("alpha_vs_market_bps", float(champion.get("return_bps", 0.0)) - market_return) or 0.0)
            fee_stress = float(details.get("fee_stress_return_bps", champion.get("return_bps", 0.0)) or 0.0)
            evidence = clamp01(float(details.get("evidence_weight", 0.0) or 0.0))
            drawdown = max(0.0, float(champion.get("max_drawdown_bps", 0.0) or 0.0))
            trade_z = float(details.get("trade_z", 0.0) or 0.0)
            threshold_z = max(1e-9, float(details.get("multiple_test_threshold_z", 1.0) or 1.0))
            significance = clamp01(trade_z / threshold_z)
            alpha_score = centered(alpha, 35.0)
            fee_score = centered(fee_stress, 35.0)
            drawdown_score = 1.0 / (1.0 + drawdown / 75.0)
            quality = 100.0 * (
                0.25 * alpha_score
                + 0.25 * evidence
                + 0.20 * fee_score
                + 0.15 * drawdown_score
                + 0.15 * significance
            )

            fitnesses = [float(r.get("fitness", 0.0) or 0.0) for r in decoded]
            returns = [float(r.get("return_bps", 0.0) or 0.0) for r in decoded]
            evidence_rows = [float((r.get("details") or {}).get("evidence_weight", 0.0) or 0.0) for r in decoded]
            passed = [bool((r.get("details") or {}).get("multiple_test_pass", False)) for r in decoded]
            family = str(champion.get("family") or "Unknown")
            family_wins[family] = family_wins.get(family, 0) + 1
            if previous_champion and champion_id and previous_champion != champion_id:
                champion_changes += 1
            if champion_id:
                previous_champion = str(champion_id)

            history.append({
                "epoch_id": epoch_id,
                "ts": float(ep["ts"]),
                "champion_id": champion_id,
                "champion_family": family,
                "champion_generation": int(champion.get("generation") or 0),
                "champion_fitness": float(champion.get("fitness", 0.0) or 0.0),
                "champion_return_bps": float(champion.get("return_bps", 0.0) or 0.0),
                "champion_alpha_bps": alpha,
                "champion_fee_stress_bps": fee_stress,
                "champion_drawdown_bps": drawdown,
                "champion_evidence_weight": evidence,
                "champion_trade_z": trade_z,
                "champion_closed_trades": int(champion["closed_trades"]),
                "champion_sample_seconds": float(champion["sample_seconds"]),
                "champion_fees": float(champion["fees"]),
                "quality_components": {"alpha": alpha_score, "evidence": evidence, "fee_stress": fee_score, "drawdown": drawdown_score, "multiple_testing": significance},
                "research_quality_index": quality,
                "best_fitness": max(fitnesses) if fitnesses else 0.0,
                "mean_fitness": sum(fitnesses) / len(fitnesses) if fitnesses else 0.0,
                "mean_return_bps": sum(returns) / len(returns) if returns else 0.0,
                "mean_evidence_weight": sum(evidence_rows) / len(evidence_rows) if evidence_rows else 0.0,
                "multiple_test_pass_rate": sum(passed) / len(passed) if passed else 0.0,
                "eligible": int(ep["eligible"]),
                "active": int(ep["active"]),
                "killed": int(ep["killed"]),
                "created": int(ep["created"]),
                "market_return_bps": market_return,
            })

        # Evolution of genome structure across all descendants.
        from .genome import GENE_SPECS
        mutation_counts = {name: 0 for name in GENE_SPECS}
        active_gene_values: dict[str, list[float]] = {name: [] for name in GENE_SPECS}
        generation_counts: dict[int, int] = {}
        active_generation_counts: dict[int, int] = {}
        max_generation = 0
        for row in strategies:
            generation = int(row["generation"] or 0)
            max_generation = max(max_generation, generation)
            generation_counts[generation] = generation_counts.get(generation, 0) + 1
            if row["status"] != "KILLED":
                active_generation_counts[generation] = active_generation_counts.get(generation, 0) + 1
            try:
                mutation = json.loads(row["mutation_json"] or "{}")
            except Exception:
                mutation = {}
            parameter = mutation.get("parameter")
            if parameter in mutation_counts:
                mutation_counts[parameter] += 1
            if row["status"] != "KILLED":
                try:
                    genome = json.loads(row["genome_json"] or "{}")
                except Exception:
                    genome = {}
                for name in GENE_SPECS:
                    value = genome.get(name)
                    if isinstance(value, (int, float)):
                        active_gene_values[name].append(float(value))

        def med(values: list[float]) -> float | None:
            if not values:
                return None
            ordered = sorted(values)
            n = len(ordered)
            m = n // 2
            return ordered[m] if n % 2 else (ordered[m - 1] + ordered[m]) / 2.0

        gene_evolution = []
        for name, spec in GENE_SPECS.items():
            vals = active_gene_values[name]
            gene_evolution.append({
                "name": name,
                "label": spec.get("label", name),
                "unit": spec.get("unit", ""),
                "mutations": mutation_counts[name],
                "active_median": med(vals),
                "active_min": min(vals) if vals else None,
                "active_max": max(vals) if vals else None,
            })
        gene_evolution.sort(key=lambda x: (-int(x["mutations"]), x["name"]))

        def avg(items: list[dict[str, Any]], key: str) -> float:
            vals = [float(x.get(key, 0.0) or 0.0) for x in items]
            return sum(vals) / len(vals) if vals else 0.0

        trend = "WAITING"
        confidence = "LOW"
        deltas: dict[str, float] = {}
        if history:
            window = min(3, len(history))
            early, recent = history[:window], history[-window:]
            deltas = {
                "research_quality_index": avg(recent, "research_quality_index") - avg(early, "research_quality_index"),
                "champion_alpha_bps": avg(recent, "champion_alpha_bps") - avg(early, "champion_alpha_bps"),
                "champion_fitness": avg(recent, "champion_fitness") - avg(early, "champion_fitness"),
                "champion_evidence_weight": avg(recent, "champion_evidence_weight") - avg(early, "champion_evidence_weight"),
                "champion_fee_stress_bps": avg(recent, "champion_fee_stress_bps") - avg(early, "champion_fee_stress_bps"),
                "champion_drawdown_bps": avg(recent, "champion_drawdown_bps") - avg(early, "champion_drawdown_bps"),
            }
            q_delta = deltas["research_quality_index"]
            if len(history) < 6:
                trend = "WAITING"
            elif q_delta >= 4.0:
                trend = "IMPROVING"
            elif q_delta <= -4.0:
                trend = "REGRESSING"
            else:
                trend = "FLAT"
            confidence = "LOW"  # Correlated epochs do not establish independent evidence.

        latest = history[-1] if history else None
        best_quality = max(history, key=lambda x: x["research_quality_index"]) if history else None
        return {
            "definition": "Paper-research quality only; not a forecast of live profitability.",
            "formula_version": "rqi-v1",
            "trend_version": "descriptive-v2",
            "limitations": "Correlated epochs and selected champions; changes across market periods are not causal evidence of improvement. Independent out-of-sample uncertainty has not been estimated.",
            "trend": trend,
            "confidence": confidence,
            "epochs_observed": len(history),
            "champion_changes": champion_changes,
            "latest": latest,
            "best_quality_epoch": best_quality,
            "deltas": deltas,
            "history": history,
            "lineage": {
                "max_generation": max_generation,
                "generation_counts": [{"generation": g, "total": generation_counts[g], "active": active_generation_counts.get(g, 0)} for g in sorted(generation_counts)],
                "family_champion_epochs": [{"family": k, "epochs": v} for k, v in sorted(family_wins.items(), key=lambda kv: (-kv[1], kv[0]))],
            },
            "gene_evolution": gene_evolution,
            "baseline_comparisons": comparisons,
            "fixed_baseline_comparisons": [{"epoch_id": ep["id"], **json.loads(ep["config_json"])["fixed_baseline"]} for ep in epoch_rows if "fixed_baseline" in json.loads(ep["config_json"])],
        }

    def strategy_summaries(self, strategy_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not strategy_ids:
            return {}
        placeholders = ",".join("?" for _ in strategy_ids)
        with self._lock:
            rows = self._db.execute(
                f"""SELECT strategy_id, COUNT(*) epochs_seen,
                           SUM(return_bps) cumulative_return_bps,
                           AVG(fitness) mean_fitness,
                           MAX(fitness) best_fitness,
                           MIN(fitness) worst_fitness,
                           SUM(closed_trades) lifetime_closed_trades,
                           SUM(CASE WHEN decision='SCALE' THEN 1 ELSE 0 END) scale_epochs,
                           SUM(CASE WHEN decision='KILL' THEN 1 ELSE 0 END) kill_epochs,
                           MAX(epoch_id) last_epoch
                    FROM evaluations WHERE strategy_id IN ({placeholders}) GROUP BY strategy_id""",
                tuple(strategy_ids),
            ).fetchall()
        return {r["strategy_id"]: dict(r) for r in rows}

    def strategy_detail(self, strategy_id: str) -> dict[str, Any] | None:
        strategy = self.strategy(strategy_id)
        if not strategy:
            return None
        with self._lock:
            rows = self._db.execute(
                """SELECT e.*, ep.ts, ep.champion_id, d.details_json
                   FROM evaluations e JOIN epochs ep ON ep.id=e.epoch_id
                   LEFT JOIN evaluation_details d ON d.epoch_id=e.epoch_id AND d.strategy_id=e.strategy_id
                   WHERE e.strategy_id=? ORDER BY e.epoch_id DESC LIMIT 50""",
                (strategy_id,),
            ).fetchall()
        history = []
        for r in rows:
            item = dict(r)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            history.append(item)
        lineage = []
        cursor = strategy
        seen: set[str] = set()
        while cursor and cursor["id"] not in seen and len(lineage) < 30:
            lineage.append(cursor)
            seen.add(cursor["id"])
            cursor = self.strategy(cursor.get("parent_id")) if cursor.get("parent_id") else None
        with self._lock:
            children = [r[0] for r in self._db.execute("SELECT id FROM strategies WHERE parent_id=? ORDER BY created_at", (strategy_id,))]
        return {"strategy": strategy, "lineage": lineage, "children": children, "history": history}

    def add_experiment(self, *, created_epoch: int | None, parent_id: str, child_ids: list[str], plan: dict[str, Any]) -> int:
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO experiments(created_ts,created_epoch,parent_id,child_ids_json,parameter,factors_json,hypothesis,rationale,confidence,status)
                   VALUES (?,?,?,?,?,?,?,?,?, 'RUNNING')""",
                (
                    time.time(), created_epoch, parent_id, json.dumps(child_ids, separators=(",", ":")),
                    str(plan.get("parameter", "")), json.dumps(plan.get("factors", []), separators=(",", ":")),
                    str(plan.get("hypothesis", ""))[:1200], str(plan.get("rationale", ""))[:1600], float(plan.get("confidence", 0.0)),
                ),
            )
            self._db.commit()
            return int(cur.lastrowid)

    def resolve_open_experiments(self, evaluations: list[dict[str, Any]], resolved_epoch: int) -> int:
        by_id = {r["strategy_id"]: r for r in evaluations}
        resolved = 0
        with self._lock:
            open_rows = self._db.execute("SELECT * FROM experiments WHERE status='RUNNING' ORDER BY id").fetchall()
            for exp in open_rows:
                child_ids = json.loads(exp["child_ids_json"] or "[]")
                child_rows = [by_id[c] for c in child_ids if c in by_id]
                if not child_ids or len(child_rows) < len(child_ids):
                    continue
                # Keep the experiment RUNNING until every challenger has met the
                # same evidence floor. A forced epoch must not resolve a sparse arm.
                if not all(bool(r.get("eligible")) for r in child_rows):
                    continue
                ranked = sorted(child_rows, key=lambda r: r.get("fitness", -1e18), reverse=True)
                winner = ranked[0] if ranked else None
                result = {
                    "children": [{
                        "strategy_id": r["strategy_id"], "fitness": r.get("fitness"), "return_bps": r.get("return_bps"),
                        "decision": r.get("decision"), "evidence_weight": r.get("evidence_weight"),
                        "multiple_test_pass": r.get("multiple_test_pass"),
                    } for r in ranked],
                    "parent_id": exp["parent_id"],
                }
                self._db.execute(
                    """UPDATE experiments SET status='RESOLVED',resolved_ts=?,resolved_epoch=?,winner_id=?,result_json=? WHERE id=?""",
                    (time.time(), resolved_epoch, winner.get("strategy_id") if winner else None, json.dumps(result, separators=(",", ":"), default=str), exp["id"]),
                )
                resolved += 1
            self._db.commit()
        return resolved


    def add_factory_event(self, event_type: str, payload: dict[str, Any] | None = None, *, agent_id: str | None = None, strategy_id: str | None = None, ts: float | None = None) -> dict[str, Any]:
        stamp = float(ts or time.time())
        payload = payload or {}
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO factory_events(ts,type,agent_id,strategy_id,payload_json) VALUES (?,?,?,?,?)",
                (stamp, str(event_type), agent_id, strategy_id, json.dumps(payload, separators=(",", ":"), default=str)),
            )
            event_id = int(cur.lastrowid)
            self._db.commit()
        return {"id": event_id, "ts": stamp, "type": str(event_type), "agent_id": agent_id, "strategy_id": strategy_id, "payload": payload}

    def recent_factory_events(self, limit: int = 120, *, after_id: int | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            if after_id is None:
                rows = self._db.execute("SELECT * FROM factory_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
                rows = list(reversed(rows))
            else:
                rows = self._db.execute("SELECT * FROM factory_events WHERE id>? ORDER BY id ASC LIMIT ?", (int(after_id), limit)).fetchall()
        return [{"id": r["id"], "ts": r["ts"], "type": r["type"], "agent_id": r["agent_id"], "strategy_id": r["strategy_id"], "payload": json.loads(r["payload_json"] or "{}")} for r in rows]

    def recent_experiments(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM experiments ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["child_ids"] = json.loads(d.pop("child_ids_json") or "[]")
            d["factors"] = json.loads(d.pop("factors_json") or "[]")
            d["result"] = json.loads(d.pop("result_json") or "{}")
            result.append(d)
        return result
