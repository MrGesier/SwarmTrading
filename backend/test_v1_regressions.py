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

