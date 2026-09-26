import math
from pathlib import Path

import numpy as np
import pytest

from engine import Engine, GENOMES, HORIZONS
from darwin.signals import signal_for_genome
from darwin.paper import PaperAccount
from darwin.judge import JudgeConfig, judge
from darwin.store import DarwinStore


def features():
    return dict(
        returns={str(h): h / 10 for h in HORIZONS},
        ready={str(h): True for h in HORIZONS},
        volatility=1.2,
        flow=.25,
        micro_delta=.08,
        spread=.7,
        weighted_imbalance=.15,
    )


def test_arbitrary_signal_matches_base_engine():
    e = Engine()
    f = features()
    vector = e.votes(f)
    single = np.array([signal_for_genome(f, g) for g in GENOMES])
    assert np.allclose(vector, single)


def state(ts, mid, signal_health="HEALTHY"):
    spread = 1.0
    return dict(
        timestamp=ts,
        features={**features(), "mid": mid, "returns": {str(h): 5 for h in HORIZONS}},
        bids=[[mid-spread/2, 100]],
        asks=[[mid+spread/2, 100]],
        health={"status": signal_health},
        intent={"state": "NEUTRAL" if signal_health == "HEALTHY" else "RISK_OFF"},
    )


def test_paper_account_accounts_for_fees_and_closes_on_risk_off():
    g = dict(id="t", family="Momentum", horizon=1, threshold=.01, gain=2, generation=0, status="ACTIVE")
    a = PaperAccount(g, notional_usd=1000, fee_bps=10)
    a.observe(state(0, 100))
    assert a.position == 1
    a.observe(state(1, 101, "STALE"))
    assert a.position == 0
    m = a.metrics()
    assert m["orders"] == 2 and m["closed_trades"] == 1
    assert m["fees"] > 0


def test_judge_requires_evidence_then_selects_champion():
    rows=[]
    for i,ret in enumerate([50, 20, -80, 10, 5]):
        rows.append(dict(strategy_id=str(i),family="Momentum",horizon=5,generation=0,status="ACTIVE",pnl=ret/10,
                         return_bps=ret,max_drawdown_bps=10 if i!=2 else 100,turnover_x=3,fees=1,orders=20,
                         closed_trades=10,win_rate=.5,sample_seconds=1000,position=0,signal=0,
                         trade_z=9.0 if i == 0 else 0.5, profit_factor=1.5, payoff_ratio=1.0, mean_trade_bps=1.0))
    out, champion = judge(rows, JudgeConfig(min_sample_seconds=100,min_closed_trades=3,promotion_min_seconds=500,promotion_min_trades=5))
    assert champion == "0"
    assert next(r for r in out if r["strategy_id"]=="0")["decision"] == "SCALE"
    assert next(r for r in out if r["strategy_id"]=="2")["decision"] == "KILL"


def test_store_persists_strategy_and_memory(tmp_path):
    store=DarwinStore(tmp_path/"darwin.sqlite")
    store.seed_strategies([dict(id="a",family="Trend",horizon=5,threshold=.2,gain=1,generation=0,status="ACTIVE")])
    assert store.strategies()[0]["id"]=="a"
    store.add_lesson("test",{"works":True},strategy_id="a",confidence=.8)
    assert store.recent_lessons()[0]["payload"]["works"] is True


def test_scientist_and_strategist_create_interpretable_children():
    from darwin.scientist import ScientistAgent
    from darwin.strategist import StrategistAgent

    parent = dict(id="p", family="Momentum", horizon=5, threshold=.2, gain=1.0, generation=0, status="CHAMPION")
    evidence = dict(return_bps=20, max_drawdown_bps=10, turnover_x=10, closed_trades=20)
    plan = ScientistAgent().plan(evidence, [])
    assert plan.parameter == "cooldown_seconds"
    assert all(f > 1 for f in plan.factors)
    children = StrategistAgent().variants(parent, plan)
    assert len(children) == 2
    assert all(c["parent_id"] == "p" and c["generation"] == 1 for c in children)
    assert all(c["mutation"]["parameter"] == "cooldown_seconds" for c in children)
    assert all(c["cooldown_seconds"] > 0 for c in children)


def test_agent_registry_has_unique_human_colors_and_execution_boundary():
    from agents import AGENT_SPECS

    ids = [a["id"] for a in AGENT_SPECS]
    colors = [a["color"] for a in AGENT_SPECS]
    assert len(ids) == len(set(ids)) == 8
    assert len(colors) == len(set(colors)) == 8
    assert next(a for a in AGENT_SPECS if a["id"] == "hermes")["capital_permission"] == "TESTNET_OR_GUARDED_LIVE"
    assert next(a for a in AGENT_SPECS if a["id"] == "cerberus")["capital_permission"] == "GATEKEEPER"


def test_brain_policy_separates_reasoning_from_deterministic_authority(monkeypatch):
    monkeypatch.setenv("DARWIN_RESEARCH_PROVIDER", "openai")
    from agents import AGENT_SPECS, DarwinBrains

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    brains = DarwinBrains()
    states = brains.states()
    assert {a["id"] for a in AGENT_SPECS} == set(states)
    assert states["atlas"]["runtime"] == "openai"
    assert states["curie"]["model"] == "gpt-5.6-sol"
    assert states["evolve"]["model"] == "gpt-5.6-terra"
    assert states["mnemosyne"]["model"] == "gpt-5.6-luna"
    assert states["forge"]["runtime"] == "deterministic" and states["forge"]["available"]
    assert states["cerberus"]["runtime"] == "deterministic" and states["cerberus"]["available"]
    assert states["hermes"]["runtime"] == "deterministic" and states["hermes"]["available"]
    assert not states["atlas"]["available"]
    assert next(a for a in AGENT_SPECS if a["id"] == "forge")["llm_capable"] is False


def test_openai_fallback_is_structured_and_cerberus_fails_closed(monkeypatch):
    monkeypatch.setenv("DARWIN_RESEARCH_PROVIDER", "openai")
    from agents import DarwinBrains

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    brains = DarwinBrains()
    atlas = brains.select_parents([{"strategy_id":"x"}], [])
    assert atlas.ok is False
    assert atlas.data["selected_strategy_ids"] == ["x"]
    result = brains.cerberus_review(
        {"symbol": "BTC", "side": "BUY", "notional_usd": 25},
        {"allow": False, "checks": {"execution_enabled": False, "notional_within_cap": True}},
    )
    assert result.ok is True
    assert result.runtime == "deterministic"
    assert result.data["recommendation"] == "BLOCK"
    assert "execution_enabled" in result.data["risk_flags"]


def test_cost_estimate_and_engineer_task(tmp_path, monkeypatch):
    from agents import estimate_cost_usd
    from agents.codex_engineer import CodexEngineer

    assert estimate_cost_usd("gpt-5.6-sol", 1_000_000, 1_000_000) == pytest.approx(24.0)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    engineer = CodexEngineer()
    assert engineer.status()["auto_apply"] is False
    class Dummy:
        def research_state(self):
            return {"evidence":{"population":2},"benchmark":{"market_return_bps":1},"experiments":[],"llm_usage_24h":{}}
        def state(self):
            return {"population":2,"champion":{"id":"c"}}
    pack = engineer.task_pack(Dummy())
    assert pack["scope"] == "engineering only"
    assert any("CERBERUS" in x for x in pack["safety_invariants"])


def test_hyperliquid_marketdata_numeric_normalizer():
    from marketdata.hyperliquid import _num, SYMBOL_MAP

    assert SYMBOL_MAP["BTCUSDT"] == "BTC"
    assert _num("123.45") == pytest.approx(123.45)
    assert _num(None) is None


def test_execution_boundary_fails_closed_without_credentials():
    from execution.hyperliquid import HyperliquidConfig, HyperliquidExecutor

    cfg = HyperliquidConfig(
        enabled=False, network="testnet", account_address="", api_private_key="",
        max_notional_usd=100, mainnet_ack="",
    )
    ex = HyperliquidExecutor(cfg)
    hard = ex.hard_checks("BTCUSDT", "BUY", 25, 100000)
    assert hard["allow"] is False
    assert hard["checks"]["notional_within_cap"] is True
    assert hard["checks"]["execution_ready"] is False


def test_multiple_testing_guard_blocks_scale_without_trade_evidence():
    rows = [dict(strategy_id=str(i), family="Trend", horizon=5, generation=0, status="ACTIVE", pnl=5,
                 return_bps=40-i, max_drawdown_bps=8, turnover_x=2, fees=1, orders=30, closed_trades=20,
                 win_rate=.55, sample_seconds=2000, position=0, signal=0, trade_z=.8, profit_factor=1.2,
                 payoff_ratio=1.0, mean_trade_bps=.5) for i in range(20)]
    out, champion = judge(rows, JudgeConfig(min_sample_seconds=100, min_closed_trades=3, promotion_min_seconds=500, promotion_min_trades=5))
    assert champion is not None
    winner = next(r for r in out if r["strategy_id"] == champion)
    assert winner["decision"] == "KEEP"
    assert winner["multiple_test_pass"] is False
    assert winner["fitness"] < winner["raw_fitness"]


def test_paper_metrics_include_quality_statistics_and_regimes():
    g = dict(id="quality", family="Momentum", horizon=1, threshold=.01, gain=2, generation=0, status="ACTIVE")
    a = PaperAccount(g, notional_usd=1000, fee_bps=1)
    s1 = state(0, 100)
    s1["regime"] = "EXPANSION"
    a.observe(s1)
    s2 = state(1, 101, "STALE")
    s2["regime"] = "EXPANSION"
    a.observe(s2)
    m = a.metrics()
    assert "profit_factor" in m and "trade_z" in m and "expectancy_usd" in m
    assert m["regime_stats"]["EXPANSION"]["trades"] == 1


def test_experiment_ledger_and_strategy_detail(tmp_path):
    store = DarwinStore(tmp_path/"ledger.sqlite")
    base = dict(id="p", family="Trend", horizon=5, threshold=.2, gain=1, generation=0, status="ACTIVE")
    child = dict(id="c", parent_id="p", family="Trend", horizon=5, threshold=.22, gain=1, generation=1, status="CHALLENGER")
    store.seed_strategies([base])
    store.insert_strategy(child)
    exp_id = store.add_experiment(created_epoch=None, parent_id="p", child_ids=["c"], plan={"parameter":"threshold","factors":[1.1],"hypothesis":"test","rationale":"local","confidence":.6})
    assert store.recent_experiments()[0]["id"] == exp_id
    row = dict(strategy_id="c", family="Trend", horizon=5, generation=1, status="CHALLENGER", pnl=1, return_bps=10, max_drawdown_bps=3, turnover_x=1, fees=.1, orders=2, closed_trades=1, win_rate=1.0, sample_seconds=500, fitness=4, decision="KEEP", raw_fitness=8, evidence_weight=.5, selection_z=1, multiple_test_threshold_z=2, multiple_test_pass=False, expectancy_usd=1, mean_trade_bps=10, trade_std_bps=0, trade_z=1, profit_factor=99, payoff_ratio=99, gross_profit=1, gross_loss=0, regime_stats={"NORMAL":{"trades":1}}, eligible=True)
    epoch = store.write_epoch("BTCUSDT", "simulation", "c", [row], created=0, config={})
    assert store.resolve_open_experiments([row], epoch) == 1
    assert store.recent_experiments()[0]["status"] == "RESOLVED"
    detail = store.strategy_detail("c")
    assert detail and [x["id"] for x in detail["lineage"]] == ["c", "p"]


def test_population_benchmark_tracks_common_market_window():
    from darwin.paper import PaperPopulation
    g = dict(id="bench", family="Momentum", horizon=1, threshold=.01, gain=2, generation=0, status="ACTIVE")
    pop = PaperPopulation([g], notional_usd=1000, fee_bps=4)
    pop.observe(state(0, 100))
    pop.observe(state(10, 101))
    b = pop.benchmark_metrics()
    assert b["market_return_bps"] == pytest.approx(100.0)
    assert b["buy_hold_after_entry_fee_bps"] == pytest.approx(96.0)
    pop.reset_epoch()
    assert pop.benchmark_metrics()["market_return_bps"] == 0


def test_experiment_waits_until_all_children_are_eligible(tmp_path):
    store = DarwinStore(tmp_path/"pending.sqlite")
    store.add_experiment(created_epoch=None, parent_id="p", child_ids=["a", "b"], plan={"parameter":"gain","factors":[.9,1.1],"hypothesis":"x","rationale":"x","confidence":.5})
    rows = [
        {"strategy_id":"a","fitness":2,"return_bps":3,"decision":"KEEP","evidence_weight":.5,"multiple_test_pass":False,"eligible":True},
        {"strategy_id":"b","fitness":1,"return_bps":2,"decision":"RETEST","evidence_weight":.2,"multiple_test_pass":False,"eligible":False},
    ]
    assert store.resolve_open_experiments(rows, 1) == 0
    assert store.recent_experiments()[0]["status"] == "RUNNING"


def test_factory_events_persist_and_decorate(tmp_path):
    from darwin.store import DarwinStore
    from darwin.factory import decorate_events
    store = DarwinStore(tmp_path / 'factory.sqlite')
    e1 = store.add_factory_event('hypothesis_created', {'parent_id':'S1'}, agent_id='curie', strategy_id='S1')
    e2 = store.add_factory_event('strategy_killed', {'reason':'weak'}, agent_id='judge', strategy_id='S2')
    rows = store.recent_factory_events(10)
    assert [r['id'] for r in rows] == [e1['id'], e2['id']]
    decorated = decorate_events(rows)
    assert decorated[0]['agent_name'] == 'CURIE'
    assert 'hypothesis' in decorated[0]['label']
    assert decorated[1]['icon'] == '🦁'


def test_factory_events_after_id(tmp_path):
    from darwin.store import DarwinStore
    store = DarwinStore(tmp_path / 'factory.sqlite')
    a = store.add_factory_event('factory_started', {}, agent_id='atlas')
    b = store.add_factory_event('paper_activity', {}, agent_id='forge')
    rows = store.recent_factory_events(10, after_id=a['id'])
    assert len(rows) == 1 and rows[0]['id'] == b['id']


def test_openai_responses_payload_is_schema_constrained(monkeypatch):
    from agents.llm import AgentBrain
    import agents.llm as llm_mod

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "output_text": '{"ok":true}',
                "usage": {"input_tokens": 100, "output_tokens": 10},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setenv("DARWIN_LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DARWIN_BRAIN_ATLAS", "openai")
    monkeypatch.setattr(llm_mod.httpx, "Client", FakeClient)
    brain = AgentBrain("atlas", "system")
    result = brain.ask_json(
        task="Return ok",
        context={"evidence": 1},
        schema_name="probe",
        schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        fallback={"ok": False},
    )
    assert result.ok and result.data == {"ok": True}
    assert captured["url"].endswith("/responses")
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["type"] == "json_schema"
    assert captured["json"]["reasoning"]["effort"] == "high"
    assert result.prompt_tokens == 100 and result.completion_tokens == 10
    assert result.estimated_cost_usd == pytest.approx(0.0006)


def test_openbot_bridge_is_advisory_and_has_four_coworkers():
    from agents.openbot_agui import COWORKERS, state
    s = state()
    assert set(COWORKERS) == {'atlas', 'curie', 'evolve', 'mnemosyne'}
    assert s['authority'] == 'advisory-only'
    assert s['capital_access'] is False
    assert all(x['endpoint'].startswith('/ag-ui/') for x in s['coworkers'])


def test_genome_v2_defaults_and_mutations_are_bounded():
    from darwin.genome import upgrade_genome, mutate_gene, MUTABLE_GENES
    base = dict(id="v2", family="Momentum", horizon=5, threshold=.2, gain=1.0)
    g = upgrade_genome(base)
    assert g["genome_version"] == 2
    assert set(["exit_threshold","max_holding_seconds","cooldown_seconds","stop_loss_bps","take_profit_bps","confirmation_ticks"]).issubset(g)
    assert set(MUTABLE_GENES).issuperset({"threshold","gain","confirmation_ticks"})
    c = mutate_gene(g, "confirmation_ticks", 1.1)
    assert c["confirmation_ticks"] == 2
    c2 = mutate_gene(g, "stop_loss_bps", 0.01)
    assert c2["stop_loss_bps"] >= 2


def test_genome_v2_paper_exit_hysteresis_and_time_stop():
    g = dict(id="v2paper", family="Momentum", horizon=1, threshold=.01, gain=2, generation=0, status="ACTIVE",
             exit_threshold=.0, max_holding_seconds=2, cooldown_seconds=0, stop_loss_bps=500, take_profit_bps=1000, confirmation_ticks=1)
    a = PaperAccount(g, notional_usd=1000, fee_bps=0)
    a.observe(state(0, 100))
    assert a.position == 1
    a.observe(state(3, 100.2))
    assert a.position == 0
    m = a.metrics()
    assert m["last_exit_reason"] == "max_holding"
    assert m["genes"]["max_holding_seconds"] == 2


def test_store_roundtrips_genome_v2(tmp_path):
    store = DarwinStore(tmp_path/"v2.sqlite")
    g = dict(id="persist-v2", family="Trend", horizon=30, threshold=.2, gain=1.1, generation=1, status="CHALLENGER",
             exit_threshold=.08, cooldown_seconds=12, stop_loss_bps=44, take_profit_bps=120, max_holding_seconds=90, confirmation_ticks=2)
    assert store.insert_strategy(g)
    got = store.strategy("persist-v2")
    assert got["genome_version"] == 2
    assert got["cooldown_seconds"] == pytest.approx(12)
    assert got["confirmation_ticks"] == 2


def test_openbot_context_is_read_only_and_role_scoped(tmp_path, monkeypatch):
    from darwin.supervisor import DarwinSupervisor
    monkeypatch.setenv("DARWIN_LLM_ENABLED", "false")
    sup = DarwinSupervisor("BTCUSDT", "simulation", tmp_path)
    ctx = sup.openbot_context("curie")
    assert ctx["paper_only"] is True
    assert "genome" in ctx and "leaderboard" in ctx
    rendered = str(ctx).lower()
    assert "private_key" not in rendered and "api_private_key" not in rendered
    with pytest.raises(KeyError):
        sup.openbot_context("hermes")


def test_evolution_history_tracks_measured_progress(tmp_path):
    store = DarwinStore(tmp_path / "evolution.sqlite")
    store.seed_strategies([
        dict(id="g0", family="Trend", horizon=30, threshold=.2, gain=1.0, generation=0, status="ACTIVE"),
        dict(id="g1", parent_id="g0", family="Trend", horizon=30, threshold=.22, gain=1.0, generation=1, status="CHALLENGER", mutation={"parameter":"threshold","from":.2,"to":.22,"factor":1.1}),
    ])
    def row(sid, fitness, ret, alpha, fee, evidence, dd, trade_z, decision="KEEP"):
        return dict(strategy_id=sid, family="Trend", horizon=30, generation=1 if sid=="g1" else 0, status="ACTIVE",
                    pnl=ret/10, return_bps=ret, max_drawdown_bps=dd, turnover_x=1, fees=.2, orders=10,
                    closed_trades=8, win_rate=.6, sample_seconds=2000, fitness=fitness, decision=decision,
                    raw_fitness=fitness+1, evidence_weight=evidence, selection_z=trade_z, multiple_test_threshold_z=2.0,
                    multiple_test_pass=trade_z>=2.0, expectancy_usd=1, mean_trade_bps=2, trade_std_bps=1,
                    trade_z=trade_z, profit_factor=1.5, payoff_ratio=1.2, gross_profit=5, gross_loss=2,
                    regime_stats={}, fee_stress_multiplier=1.5, fee_stress_return_bps=fee,
                    alpha_vs_market_bps=alpha, eligible=True, genome_version=2, genes={})
    store.write_epoch("BTCUSDT", "simulation", "g0", [row("g0", 2, 10, 2, 1, .25, 30, 1.0)], created=0,
                      config={"benchmark":{"market_return_bps":8}})
    store.write_epoch("BTCUSDT", "simulation", "g1", [row("g1", 8, 35, 25, 20, .85, 10, 3.5, "SCALE")], created=1,
                      config={"benchmark":{"market_return_bps":10}})
    evo = store.evolution_history()
    assert evo["epochs_observed"] == 2
    assert evo["latest"]["champion_id"] == "g1"
    assert evo["latest"]["research_quality_index"] > evo["history"][0]["research_quality_index"]
    assert evo["lineage"]["max_generation"] == 1
    threshold_gene = next(x for x in evo["gene_evolution"] if x["name"] == "threshold")
    assert threshold_gene["mutations"] == 1
    assert evo["definition"].startswith("Paper-research")


@pytest.mark.parametrize("direction", [1, -1])
def test_trade_context_excursions_and_gross_accounting(direction, tmp_path):
    g = dict(id="telemetry", family="Momentum", horizon=180, threshold=.01, gain=2,
             stop_loss_bps=200, take_profit_bps=200, max_hold_seconds=1000)
    a = PaperAccount(g, notional_usd=1000, fee_bps=3.5)
    a._open(direction, state(0, 100))
    # A risk-off closure still records the final observed excursion for either side.
    a.observe(state(10, 100 + direction * .1, "STALE"))
    t = a.closed_trade_log[-1]
    assert t["mfe_bps"] == pytest.approx(10)
    assert t["mae_bps"] == 0
    assert t["entry_context"]["weighted_imbalance"] == .15
    assert t["gross_pnl_usd"] == pytest.approx(t["net_pnl_usd"] + t["fees_usd"])
    assert t["closed_at"] - t["opened_at"] == 10
    store = DarwinStore(tmp_path / "trades.sqlite")
    store.save_trades([t])
    assert store.recent_trades()[0] == t


def test_agent_audit_roundtrip_and_history_cursor(tmp_path, monkeypatch):
    from agents.llm import AgentBrain
    from agents.openrouter_free import FreeProvider
    monkeypatch.setenv("DARWIN_LLM_ENABLED", "true")
    monkeypatch.setenv("DARWIN_BRAIN_CURIE", "openrouter-free")
    brain = AgentBrain("curie", "system")
    store = DarwinStore(tmp_path / "audit.sqlite")
    for status, real in [("connected", True), ("cached", False), ("quota_exhausted", False)]:
        monkeypatch.setattr(FreeProvider, "ask", lambda self, **kw: {
            "status": status, "real_call": real, "data": {"ok": True}, "model": "test:free"})
        result = brain.ask_json(task="Assess fees and imbalance", context={"fees": 12},
            schema_name="test", schema={}, fallback={"ok": False})
        assert result.audit["real_call"] is real
        assert result.audit["provider_status"] == status
        store.add_agent_run(result.to_dict())
    newest = store.recent_agent_runs(2)
    older = store.recent_agent_runs(2, before_id=newest[-1]["id"])
    assert len(older) == 1 and older[0]["id"] < newest[-1]["id"]
    assert older[0]["audit"]["task"] == "Assess fees and imbalance"
    assert '12' in older[0]["audit"]["context_preview"]
    assert newest[0]["ok"] is False
