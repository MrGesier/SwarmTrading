import time
import pytest
from darwin.portfolio import SharedPortfolio


def setup(tmp_path):
    p=SharedPortfolio(tmp_path/"portfolio.json")
    p.set_fx(1.0,"2026-09-25")
    return p


def book(p,key,now,mid=100,depth=1000):
    p.book(key,[[mid-.1,depth]],[[mid+.1,depth]],now,3)


def leg(key,qty,kind="perp"):
    return dict(instrument=key,qty=qty,kind=kind)


def test_one_capital_multiple_strategies_and_restart(tmp_path):
    p=setup(tmp_path);now=time.time()
    book(p,"perp:BTC",now);book(p,"perp:ETH",now)
    assert p.open("a",[leg("perp:BTC",2)],now)
    assert p.open("b",[leg("perp:ETH",-2)],now)
    assert len(p.state()["positions"])==2
    assert p.totals()["equity_eur"] < 1000
    restored=SharedPortfolio(p.path)
    assert restored.state()["equity_eur"]==pytest.approx(p.state()["equity_eur"])
    assert restored.data["initial_eur"]==1000
    assert len(restored.data["positions"])==2


def test_gross_leverage_cannot_be_hidden_by_opposite_positions(tmp_path):
    p=setup(tmp_path);now=time.time();book(p,"perp:BTC",now)
    assert p.open("a",[leg("perp:BTC",14)],now)
    assert p.open("b",[leg("perp:BTC",-14)],now)
    assert not p.open("c",[leg("perp:BTC",3)],now)
    assert p.totals()["leverage"]<=3
    assert p.totals()["net_exposure_eur"]==0


def test_pair_atomic_depth_and_cash_and_roundtrip(tmp_path):
    p=setup(tmp_path);now=time.time()
    book(p,"spot:@107",now);book(p,"perp:HYPE",now,depth=1)
    legs=[leg("spot:@107",2,"spot"),leg("perp:HYPE",-2)]
    assert not p.open("pair",legs,now,kind="delta_neutral")
    assert p.data["cash_eur"]==1000 and not p.data["positions"]
    book(p,"perp:HYPE",now)
    assert p.open("pair",legs,now,kind="delta_neutral")
    assert p.data["cash_eur"]<800
    assert p.state()["positions"][0]["delta_units"]==0
    book(p,"spot:@107",now+1,mid=110);book(p,"perp:HYPE",now+1,mid=110)
    assert p.close(p.data["positions"][0],now+1,"test")
    assert not p.data["positions"]
    assert p.data["cash_eur"]==pytest.approx(1000+p.data["closed"][0]["net_eur"])
    assert p.data["closed"][0]["net_eur"]<0  # spread and all four fees


def test_stale_books_tick_size_and_spot_borrow_rejected(tmp_path):
    p=setup(tmp_path);now=time.time();book(p,"spot:@107",now)
    assert not p.open("bad",[leg("spot:@107",-1,"spot")],now)
    assert not p.open("bad",[leg("spot:@107",1.0001,"spot")],now)
    assert not p.open("bad",[leg("spot:@107",1,"spot")],now+4)
    assert not p.open("bad",[leg("spot:@107",11,"spot")],now)
    assert p.data["cash_eur"]==1000


def test_funding_sign_and_no_invented_offline_income(tmp_path):
    p=setup(tmp_path);now=time.time();book(p,"perp:HYPE",now)
    assert p.open("short",[leg("perp:HYPE",-1)],now)
    p.funding["perp:HYPE"]=(.001,now)
    p.accrue_funding(now+10)
    assert p.data["funding_eur"]==pytest.approx(100*.001*10/3600)
    funded=p.data["funding_eur"]
    p.accrue_funding(now+3600)
    assert p.data["funding_eur"]==funded
    assert p.data["funding_unobserved_seconds"]>0


def test_real_observed_pair_signal_not_forced(tmp_path):
    p=setup(tmp_path);now=time.time();book(p,"spot:@107",now);book(p,"perp:HYPE",now)
    p.funding["perp:HYPE"]=(.00001,now)
    p.pair("spot:@107",now)
    assert not p.data["positions"]
    book(p,"perp:HYPE",now,mid=101)
    p.pair("spot:@107",now)
    assert len(p.data["positions"])==1
    assert p.state()["positions"][0]["delta_units"]==0


def test_signal_can_recover_on_same_fresh_book_without_refilling_depth(tmp_path, monkeypatch):
    from engine import GENOMES
    from darwin.genome import upgrade_genome
    import darwin.portfolio as module
    p=setup(tmp_path);now=time.time()
    monkeypatch.setattr(module.time,"time",lambda:now)
    monkeypatch.setattr(module,"raw_signal_for_genome",lambda *_:1.0)
    g=upgrade_genome(dict(GENOMES[0]))
    s=dict(symbol="BTCUSDT",venue="HYPERLIQUID",timestamp=now,
        health=dict(status="HEALTHY",age_ms=0,sequence=123),
        bids=[[99.99,100]],asks=[[100.01,100]],features={},intent=dict(state="RISK_OFF"))
    p.observe(s,[g],3)
    assert not p.data["positions"]
    s["intent"]["state"]="LONG_EARLY"
    p.observe(s,[g],3)
    assert len(p.data["positions"])==1
    remaining=p.books["perp:BTC"]["asks"][0][1]
    p.observe(s,[g],3)
    assert p.books["perp:BTC"]["asks"][0][1]==remaining
