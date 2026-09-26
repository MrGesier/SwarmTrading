import json
from pathlib import Path

import pytest

from darwin.paper import PaperPopulation
from darwin.store import DarwinStore
from test_darwin import state


def test_open_position_checkpoint_roundtrip(tmp_path):
    genome = dict(id='g0', family='Momentum', horizon=1, threshold=.01, gain=2)
    pop = PaperPopulation([genome])
    pop.observe(state(1000, 100))
    assert pop.accounts['g0'].position == 1
    store = DarwinStore(tmp_path / 'checkpoint.sqlite')
    store.save_checkpoint(pop.snapshot())
    restored = PaperPopulation([genome])
    restored.restore(DarwinStore(store.path).load_checkpoint())
    assert restored.snapshot() == pop.snapshot()
    restored.observe(state(999, 80))
    assert restored.snapshot() == pop.snapshot()
    pop.observe(state(1001, 101))
    restored.observe(state(1001, 101))
    assert restored.snapshot() == pop.snapshot()


def test_history_reopen_and_event_ids(tmp_path):
    path = tmp_path / 'history.sqlite'
    store = DarwinStore(path)
    first = store.add_factory_event('test')
    reopened = DarwinStore(path)
    second = reopened.add_factory_event('test')
    assert second['id'] > first['id']
    assert len(reopened.recent_factory_events()) == 2
    evo = reopened.evolution_history()
    assert evo['formula_version'] == 'rqi-v1'
    assert evo['trend'] == 'WAITING'
    assert evo['confidence'] == 'LOW'


def test_evolution_not_consumed_by_capital_authority():
    root = Path(__file__).parent
    for path in (root / 'execution').glob('*.py'):
        code = path.read_text()
        assert 'research_quality_index' not in code
        assert 'evolution_history' not in code


def test_api_without_providers(tmp_path, monkeypatch):
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'false')
    monkeypatch.setenv('DARWIN_AUTOSTART_MODE', 'simulation')
    monkeypatch.setenv('HYPERLIQUID_ENABLED', 'false')
    monkeypatch.delenv('OPENBOT_AGENT_TOKEN', raising=False)
    monkeypatch.delenv('MANAGED_AGENT_TOKEN', raising=False)
    import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, 'DATA', tmp_path)
    monkeypatch.setattr(main, 'sessions', {})
    active = main.SharedPortfolio(tmp_path / 'shared.json')
    control = main.SharedPortfolio(tmp_path / 'control.json')
    feeds = main.PortfolioFeeds(active, control)
    monkeypatch.setattr(main, 'shared_portfolio', active)
    monkeypatch.setattr(main, 'fixed_portfolio', control)
    monkeypatch.setattr(main, 'portfolio_feeds', feeds)
    async def public_stream_stub(self):
        import asyncio
        await asyncio.Event().wait()
    monkeypatch.setattr(main.Session, 'run', public_stream_stub)
    monkeypatch.setattr(main.PortfolioFeeds, 'run', public_stream_stub)
    with TestClient(main.app) as client:
        health = client.get('/api/health').json()
        assert health['version'] == '0.11.0'
        assert health['paper_only'] is True
        assert client.get('/api/state?mode=simulation').status_code == 400
        for route in ('brains/state', 'engineer/state', 'factory/state', 'darwin/research', 'darwin/evolution'):
            response = client.get('/api/' + route)
            assert response.status_code == 200, response.text
        for agent in ('atlas', 'curie', 'evolve', 'mnemosyne'):
            assert client.get('/api/openbot/context/' + agent).status_code in (401, 403)
            assert client.post('/ag-ui/' + agent, json={}).status_code in (401, 403, 503)


def test_budget_is_persistent_and_fails_closed(tmp_path):
    path = tmp_path / 'budget.sqlite'
    store = DarwinStore(path)
    assert store.reserve_llm_budget(.7, 1)
    assert not DarwinStore(path).reserve_llm_budget(.4, 1)
    assert not store.reserve_llm_budget(float('nan'), 1)


def test_bad_provider_schema_falls_back_without_secret_error(monkeypatch):
    monkeypatch.setenv("DARWIN_BRAIN_CURIE", "openai")
    from agents.llm import AgentBrain
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only-placeholder')
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'true')
    brain = AgentBrain('curie', 'research')
    monkeypatch.setattr(brain, '_openai_json', lambda **kw: ({'answer': 'wrong'}, 1, 1))
    result = brain.ask_json(task='test', context={}, schema_name='test', schema={'type':'object','properties':{'answer':{'type':'integer'}},'required':['answer']}, fallback={'answer':0})
    assert not result.ok
    assert result.data == {'answer':0}
    assert 'test-only-placeholder' not in result.error


@pytest.mark.parametrize('gene', ['threshold','gain','exit_threshold','max_holding_seconds','cooldown_seconds','stop_loss_bps','take_profit_bps','confirmation_ticks'])
def test_single_gene_mutation_survives_storage(gene, tmp_path):
    from darwin.genome import upgrade_genome, mutate_gene, gene_values, GENE_SPECS
    base = upgrade_genome(dict(id='base', family='Momentum', horizon=1, threshold=.2, gain=1))
    child = mutate_gene(base, gene, 1.1)
    changed = [k for k in GENE_SPECS if child[k] != base[k]]
    assert changed == [gene]
    child.update(id='child', parent_id='base', generation=1, status='CHALLENGER')
    store = DarwinStore(tmp_path / 'gene.sqlite')
    store.insert_strategy(child)
    assert gene_values(store.strategy('child')) == gene_values(child)


@pytest.mark.parametrize('price,reason', [(98,'stop_loss'), (102,'take_profit')])
def test_gap_exit_and_cooldown(price, reason):
    from darwin.paper import PaperAccount
    genome = dict(id='gap', family='Momentum', horizon=1, threshold=.03, gain=2,
                  stop_loss_bps=50, take_profit_bps=50, cooldown_seconds=10)
    account = PaperAccount(genome, fee_bps=3.5)
    account.observe(state(0,100))
    account.observe(state(5,price))
    assert account.position == 0
    assert account.last_exit_reason == reason
    assert account.orders == 2 and account.fees > 0
    account.observe(state(6,price))
    assert account.position == 0
    account.observe(state(16,price))
    assert account.position == 1


def test_confirmation_is_reset_by_stale_tick():
    from darwin.paper import PaperAccount
    account = PaperAccount(dict(id='confirmation', family='Momentum', horizon=1, threshold=.03, gain=2, confirmation_ticks=2))
    account.observe(state(0,100))
    assert account.position == 0
    account.observe(state(1,100,'STALE'))
    account.observe(state(2,100))
    assert account.position == 0
    account.observe(state(3,100))
    assert account.position == 1


def test_restart_gap_is_not_counted_as_observed_evidence():
    from darwin.paper import PaperAccount
    account = PaperAccount(dict(id='gap', family='Momentum', horizon=1, threshold=.03, gain=2))
    account.observe(state(0,100))
    account.observe(state(3600,100))
    assert account.metrics()['sample_seconds'] == 3
    assert account.unobserved_seconds == 3597


def test_restore_rejects_changed_fee_policy():
    genome = dict(id='fee', family='Momentum', horizon=1, threshold=.03, gain=2)
    original = PaperPopulation([genome], fee_bps=3.5)
    changed = PaperPopulation([genome], fee_bps=7)
    with pytest.raises(ValueError, match='accounting configuration'):
        changed.restore(original.snapshot())


def test_failed_epoch_write_cannot_leak_into_next_commit(tmp_path):
    store = DarwinStore(tmp_path / 'atomic.sqlite')
    account = PaperPopulation([dict(id='g0', family='Momentum', horizon=1, threshold=.01, gain=2)])
    account.observe(state(1000, 100))
    row = {**account.metrics()[0], 'decision': 'KEEP', 'fitness': 0, 'eligible': False}
    # Duplicate primary key fails after the epoch and first evaluation were inserted.
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.write_epoch('BTCUSDT', 'simulation', None, [row, row], created=0, config={})
    store.add_factory_event('after_failed_epoch')
    assert store.recent_epochs(10) == []
    assert store._db.execute('SELECT COUNT(*) FROM evaluations').fetchone()[0] == 0
    epoch_id = store.write_epoch('BTCUSDT', 'simulation', None, [row], created=0, config={})
    store.close()
    reopened = DarwinStore(store.path)
    assert reopened.recent_epochs(10)[0]['id'] == epoch_id
    assert reopened._db.execute('SELECT COUNT(*) FROM evaluations').fetchone()[0] == 1
    reopened.close()


def test_three_research_epochs_survive_restart(tmp_path, monkeypatch):
    from darwin.supervisor import DarwinSupervisor
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'false')
    monkeypatch.setenv('HYPERLIQUID_ENABLED', 'false')
    supervisor = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        price = 100.0
        for epoch in range(3):
            for tick in range(620):
                direction = 1 if (tick // 20) % 2 == 0 else -1
                price += direction * .05
                frame = state(epoch * 620 + tick, price)
                frame['features']['returns'] = {k: direction * 5 for k in frame['features']['returns']}
                frame['bids'] = [[price - .005, 10000]]
                frame['asks'] = [[price + .005, 10000]]
                supervisor.observe(frame)
            result = supervisor.run_epoch(force=True)
            assert result['ran'] and result['epoch_id'] == epoch + 1
            if epoch == 0:
                assert result['created'] > 0
        before = supervisor.evolution_state(20)
        assert before['epochs_observed'] == 3
        assert before['lineage']['max_generation'] >= 1
        comparisons = before['fixed_baseline_comparisons']
        assert comparisons[0]['status'] == 'WAITING'
        assert comparisons[1]['status'] == 'MATCHED_WINDOW'
        assert comparisons[1]['g0_count'] == 320
        assert comparisons[1]['descendant_count'] > 0
        assert len(supervisor.baseline.accounts) == 320
    finally:
        supervisor.store.close()
    restarted = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        after = restarted.evolution_state(20)
        assert after['epochs_observed'] == before['epochs_observed']
        assert after['lineage'] == before['lineage']
    finally:
        restarted.store.close()


def test_first_cycle_schedule_survives_restart(tmp_path, monkeypatch):
    from darwin.supervisor import DarwinSupervisor
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'false')
    first = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    anchor = first.last_epoch
    first.store.close()
    second = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        assert second.last_epoch == anchor
        second.last_epoch -= second.epoch_seconds + 1
        assert second.cycle_state()['status'] == 'WAITING_EVIDENCE'
        assert second.run_epoch()['reason'] == 'NOT_ENOUGH_EVIDENCE'
        assert not second.due()  # retry is throttled, not one event per tick
    finally:
        second.store.close()


def test_shadow_baseline_checkpoint_and_partial_window(tmp_path, monkeypatch):
    from darwin.supervisor import DarwinSupervisor
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'false')
    first = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    first.observe(state(1000, 100))
    first.checkpoint()
    snapshot = first.baseline.snapshot()
    first.store.close()
    second = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        assert second.baseline.snapshot() == snapshot
        second.baseline.epoch_start_ts = 1001
        assert second.fixed_baseline_comparison(second.population.metrics())['status'] == 'WAITING'
    finally:
        second.store.close()


def test_descendant_can_become_parent_without_changing_other_genes():
    from darwin.strategist import StrategistAgent
    from darwin.scientist import ExperimentPlan
    from darwin.genome import upgrade_genome, gene_values
    parent = upgrade_genome(dict(id='root',family='Momentum',horizon=1,threshold=.2,gain=2))
    plan = ExperimentPlan('threshold', (.9, 1.1), 'test', 'synthetic test', .2)
    child = StrategistAgent().variants(parent, plan)[0]
    grandchild = StrategistAgent().variants(child, plan)[0]
    assert grandchild['generation'] == 2
    assert grandchild['parent_id'] == child['id']
    assert [k for k,v in gene_values(child).items() if v != gene_values(grandchild)[k]] == ['threshold']


def test_repeated_mutation_explores_new_bounded_gene(tmp_path, monkeypatch):
    from darwin.supervisor import DarwinSupervisor
    from darwin.scientist import ExperimentPlan
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'false')
    supervisor = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        parent = supervisor.store.strategies()[0]
        plan = ExperimentPlan('threshold', (.9, 1.1), 'probe', 'test', .2)
        for child in supervisor.strategist.variants(parent, plan):
            supervisor.store.insert_strategy(child)
        fresh = supervisor.novel_plan(parent, plan)
        known = {r['id'] for r in supervisor.store.strategies(include_killed=True)}
        assert any(c['id'] not in known for c in supervisor.strategist.variants(parent, fresh))
        supervisor.observe(state(1000,100))
        saved = supervisor.store.pnl_history()
        assert len(saved) == 1 and saved[0]['fixed_g0']['count'] == 320
        assert saved[0]['active']['mean_fees_usd'] > 0
    finally:
        supervisor.store.close()


def test_trade_journal_net_fees_and_idempotent_persistence(tmp_path):
    from darwin.paper import PaperAccount
    account = PaperAccount(dict(id='journal',family='Momentum',horizon=1,threshold=.01,gain=2))
    account.observe(state(1000,100))
    account.observe(state(1001,101,'STALE'))
    trade = account.closed_trade_log[0]
    assert trade['direction'] == 'LONG'
    assert trade['opened_at'] == 1000 and trade['closed_at'] == 1001
    assert trade['fees_usd'] == pytest.approx(account.fees)
    assert trade['net_pnl_usd'] == pytest.approx(account.cash)
    store = DarwinStore(tmp_path/'trades.sqlite')
    store.save_trades([trade]); store.save_trades([trade]); store.close()
    reopened = DarwinStore(tmp_path/'trades.sqlite')
    assert reopened.recent_trades() == [trade]
    reopened.close()

def test_autonomous_incident_requires_observed_evidence():
    from darwin.autonomy import diagnose
    row = dict(strategy_id='loss', sample_seconds=1800, closed_trades=20, pnl=-20, fees=30, return_bps=-200)
    assert diagnose([row], min_seconds=1800, min_trades=20)['code'] == 'FEE_DRAG'
    assert not diagnose([{**row, 'sample_seconds': 1799}], min_seconds=1800, min_trades=20)['actionable']
    assert not diagnose([{**row, 'pnl': 2, 'return_bps': 20}], min_seconds=1800, min_trades=20)['actionable']
    assert not diagnose([{**row, 'pnl': float('nan')}], min_seconds=1800, min_trades=20)['actionable']


def test_autonomous_repair_advances_cycle_and_survives_restart(tmp_path, monkeypatch):
    import time
    from darwin.supervisor import DarwinSupervisor
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'false')
    supervisor = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    account = next(iter(supervisor.population.accounts.values()))
    account.started_at = time.time() - 4000
    account.last_ts = time.time()
    account.cash = -20
    account.fees = 30
    account.closed_trades = 20
    supervisor.last_epoch = time.time() - 4000
    from darwin.autonomy import diagnose
    supervisor._repair_diagnosis = diagnose(supervisor.population.metrics(), min_seconds=1800, min_trades=20)
    assert supervisor.due()
    assert supervisor.cycle_state()['trigger'] == 'AUTO_REPAIR'
    supervisor._retry_epoch_at = time.time() + 60
    assert not supervisor.due()
    supervisor.auto_epoch_enabled = False
    supervisor._retry_epoch_at = 0
    assert not supervisor.due()
    supervisor.checkpoint()
    supervisor.store.close()
    restarted = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        # A fresh process reconstructs incidents from measured account checkpoints.
        issue = diagnose(restarted.population.metrics(), min_seconds=1800, min_trades=20)
        assert issue['code'] == 'FEE_DRAG'
        assert issue['mean_fees_usd'] == 30
    finally:
        restarted.store.close()

def test_incident_runs_brains_creates_challengers_and_records_reason(tmp_path, monkeypatch):
    import time
    from darwin.supervisor import DarwinSupervisor
    from darwin.autonomy import diagnose
    monkeypatch.setenv('DARWIN_LLM_ENABLED', 'false')
    supervisor = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        for account in supervisor.population.accounts.values():
            account.started_at = time.time() - 4000
            account.last_ts = time.time()
            account.cash = -20
            account.fees = 30
            account.closed_trades = 25
            account.turnover = 80000
        supervisor._repair_diagnosis = diagnose(supervisor.population.metrics(), min_seconds=1800, min_trades=20)
        supervisor.last_epoch = time.time() - 4000
        captured = []
        original = supervisor.brains.curie.ask_json
        def capture(**kwargs):
            captured.append(kwargs['context']['incident']['code'])
            return original(**kwargs)
        monkeypatch.setattr(supervisor.brains.curie, 'ask_json', capture)
        result = supervisor.run_epoch()
        assert result['ran'] and result['created'] > 0
        assert captured and set(captured) == {'FEE_DRAG'}
        epoch = supervisor.store.recent_epochs(1)[0]
        assert epoch['config']['research_trigger'] == 'AUTO_REPAIR'
        assert epoch['config']['measured_incident']['mean_fees_usd'] == 30
        assert supervisor.store.recent_experiments(1)[0]['status'] == 'RUNNING'
        assert not supervisor.due()
        assert not supervisor._repair_diagnosis
    finally:
        supervisor.store.close()


def test_async_epoch_keeps_event_loop_responsive_and_deduplicates(tmp_path,monkeypatch):
    import asyncio
    import threading
    from darwin.supervisor import DarwinSupervisor
    monkeypatch.setenv('DARWIN_LLM_ENABLED','false')
    sup=DarwinSupervisor('BTCUSDT','live',tmp_path)
    entered=threading.Event();release=threading.Event()
    def slow_model():
        entered.set()
        assert release.wait(3)
        return 'validated advice'
    def steps(**kwargs):
        result=yield slow_model
        return {'ran':True,'advice':result}
    monkeypatch.setattr(sup,'_epoch_steps',steps)
    async def scenario():
        task=asyncio.create_task(sup.run_epoch_async(force=True))
        while not entered.is_set():await asyncio.sleep(.005)
        assert (await sup.run_epoch_async(force=True))['reason']=='RESEARCH_RUNNING'
        assert sup.cycle_state()['status']=='RESEARCH_RUNNING'
        sup.observe({'should_not_be_counted_as_market_evidence':True})
        assert sup._last_state is None
        release.set()
        result=await task
        assert result['advice']=='validated advice'
        assert not sup._epoch_running
    asyncio.run(scenario())


def test_control_trade_archive_is_durable_separate_and_deduplicated(tmp_path, monkeypatch):
    from darwin.supervisor import DarwinSupervisor
    monkeypatch.setenv('DARWIN_LLM_ENABLED','false')
    sup=DarwinSupervisor('BTCUSDT','live',tmp_path)
    row=dict(strategy_id='control',opened_at=1,closed_at=2,net_pnl_usd=3)
    account=next(iter(sup.baseline.accounts.values()))
    account.closed_trade_log.append(row)
    sup.persist_trades()
    assert not account.closed_trade_log
    assert sup.store.recent_trades()==[]
    account.closed_trade_log.append(row)
    sup.persist_trades()
    assert sup.store._db.execute('SELECT count(*) FROM baseline_trades').fetchone()[0]==1
    account.closed_trade_log.append(row)
    monkeypatch.setattr(sup.store,'save_baseline_trades',lambda rows: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError):sup.persist_trades()
    assert list(account.closed_trade_log)==[row]
    sup.store.close()


def test_snapshot_detaches_nested_trade_and_statistical_history():
    pop=PaperPopulation([dict(id='g0',family='Momentum',horizon=1,threshold=.01,gain=2)])
    a=pop.accounts['g0']
    a.closed_trade_log.append({'nested':{'values':[1]}})
    a.closed_pnls.append(2)
    snapshot=pop.snapshot()
    a.closed_trade_log[0]['nested']['values'].append(3)
    a.closed_pnls.append(4)
    assert snapshot['accounts']['g0']['closed_trade_log']==[{'nested':{'values':[1]}}]
    assert snapshot['accounts']['g0']['closed_pnls']==[2]
