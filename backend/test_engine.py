import asyncio
import json
import numpy as np
import pytest
from engine import OrderBook, SequenceGap, effective_count, entropy


def book():
    b = OrderBook()
    b.snapshot(dict(lastUpdateId=10, bids=[['99','2'],['98','3']], asks=[['101','4'],['102','5']]))
    return b


def test_snapshot_must_bridge_and_deletes_apply():
    b = book()
    assert not b.valid
    assert not b.update(dict(U=8,u=10,b=[],a=[]))
    assert b.update(dict(U=9,u=12,b=[['99','0'],['98','4']],a=[]))
    assert b.valid and b.sequence==12 and 99 not in b.bids and b.bids[98]==4


def test_gap_invalidates_book_and_snapshot_recovers():
    b = book()
    with pytest.raises(SequenceGap):
        b.update(dict(U=12,u=13,b=[],a=[]))
    assert not b.valid
    b.snapshot(dict(lastUpdateId=13,bids=[['99','2']],asks=[['101','2']]))
    assert b.update(dict(U=14,u=14,b=[],a=[]))


def test_crossed_book_is_rejected():
    b = book()
    with pytest.raises(SequenceGap):
        b.update(dict(U=11,u=11,b=[['102','1']],a=[]))
    assert not b.valid


def test_effective_count_duplicates_do_not_add_independence():
    rng=np.random.default_rng(1)
    x=rng.normal(size=(1000,1))
    n,w=effective_count(np.repeat(x,20,axis=1))
    assert n==pytest.approx(1)
    assert w.sum()==pytest.approx(1)
    n,_=effective_count(rng.normal(size=(5000,10)))
    assert n>9.8
    n,w=effective_count(np.ones((20,10)))
    assert n==0 and w.sum()==0


def test_entropy_limits():
    assert entropy([1,0,0])==0
    assert entropy([1,1,1])==pytest.approx(1)


def test_raw_replay_matches_state_and_no_candle_lookahead(tmp_path,monkeypatch):
    import main
    from replay import replay_events
    monkeypatch.setattr(main,'DATA',tmp_path)
    s=main.Session('BTCUSDT','simulation')
    for i in range(35):
        s.simulate(1000+i*.5)
    old=json.dumps(s.states[0])
    for i in range(5):
        s.simulate(1017.5+i*.5)
    assert json.dumps(s.states[0])==old
    asyncio.run(s.recorder.flush())
    replay=list(replay_events(s.recorder.directory))
    assert len(replay)==len(s.states)
    for got,expected in zip(replay,s.states):
        assert got['features']==expected['features']
        assert got['swarm']==expected['swarm']
        assert got['intent']==expected['intent']
        assert got['candles']==expected['candles']
    s.book.valid=False
    s.derive(1025)
    assert s.latest['intent']['state']=='RISK_OFF'


def test_risk_diagnostics_explain_warmup_and_recovery_without_bypassing_gate(monkeypatch):
    from engine import Engine, GENOMES
    e=Engine()
    monkeypatch.setattr(e,"votes",lambda *_args,**_kwargs:np.zeros(len(GENOMES)))
    def frame(t):return e.calculate(book(),t,"live","BTCUSDT",{"status":"HEALTHY"})["intent"]
    first=frame(1000)
    assert first["state"]=="RISK_OFF" and first["risk_causes"]==["DIVERSITY_WARMUP"]
    e.neff=2
    recovery=frame(1001)
    assert recovery["state"]=="RISK_OFF" and recovery["risk_causes"]==["RECOVERY_CONFIRMATION"]
    assert frame(1002)["state"]=="RISK_OFF"
    released=frame(1003)
    assert released["state"]=="NEUTRAL" and released["risk_causes"]==[]
