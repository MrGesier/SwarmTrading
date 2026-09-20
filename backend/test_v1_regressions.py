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
    with TestClient(main.app) as client:
        health = client.get('/api/health').json()
        assert health['version'] == '0.11.0'
        assert health['paper_only'] is True
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
    finally:
        supervisor.store.close()
    restarted = DarwinSupervisor('BTCUSDT', 'simulation', tmp_path)
    try:
        after = restarted.evolution_state(20)
        assert after['epochs_observed'] == before['epochs_observed']
        assert after['lineage'] == before['lineage']
    finally:
        restarted.store.close()
