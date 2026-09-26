import time
from darwin.capital_feedback import evidence,scale_for,start_comparison,comparison,update_decisions
from darwin.portfolio import SharedPortfolio
import pytest


def rows(net=-1,n=5):
    now=time.time()
    return [dict(strategy_id="BTCUSDT:momentum_5_00",kind="directional",net_eur=net,fees_eur=.2,opened_at=now-3600+i*60,closed_at=now-3550+i*60) for i in range(n)]


def test_reduce_losses_but_do_not_promote_low_sample_or_fee_stress():
    data={"closed":rows()}
    assert scale_for(data,"BTCUSDT:momentum_5_00__g1_0",time.time())==.25
    data["closed"]=rows(net=1,n=5)
    assert scale_for(data,"BTCUSDT:momentum_5_00",time.time())==.5
    data["closed"]=rows(net=.05,n=20)
    assert scale_for(data,"BTCUSDT:momentum_5_00",time.time())==.5
    data["closed"]=rows(net=1,n=20)
    data["closed"][-1]["closed_at"]=time.time()
    assert scale_for(data,"BTCUSDT:momentum_5_00",time.time())==1
    assert scale_for(data,"ETHUSDT:momentum_5_00",time.time())==.5


def test_comparison_preserves_capital_and_cannot_claim_initial_gain(tmp_path):
    a=SharedPortfolio(tmp_path/"active.json"); a.data["cash_eur"]=972;a.set_fx(1,"2026-09-25")
    b=SharedPortfolio(tmp_path/"control.json");start_comparison(a,b)
    assert a.adaptive and not b.adaptive
    assert b.totals()["equity_eur"]==972
    assert comparison(a,b)["status"]=="COLLECTING"
    assert comparison(a,b)["delta_vs_fixed_eur"]==0
    a.data["cash_eur"]-=1;b.data["cash_eur"]-=2
    c=comparison(a,b)
    assert c["gain_since_start_eur"]==-1 and c["delta_vs_fixed_eur"]==1
    a.save();b.save();a2=SharedPortfolio(a.path);b2=SharedPortfolio(b.path)
    start_comparison(a2,b2)
    assert a2.data["allocation_comparison"]["start_equity_eur"]==972
    assert comparison(a2,b2)["gain_since_start_eur"]==-1


def test_missing_control_is_not_silently_reset(tmp_path):
    a=SharedPortfolio(tmp_path/"active.json");a.data["allocation_comparison"]={"started_at":1}
    with pytest.raises(ValueError):start_comparison(a,SharedPortfolio(tmp_path/"missing.json"))


def test_decisions_are_transitions_not_per_tick_spam():
    data={"closed":rows()};update_decisions(data,time.time());update_decisions(data,time.time())
    assert len(data["allocation_decisions"])==1


def test_lower_loss_is_not_labelled_capital_gain(tmp_path):
    a=SharedPortfolio(tmp_path/"active.json");b=SharedPortfolio(tmp_path/"control.json")
    start_comparison(a,b)
    a.data["allocation_comparison"]["started_at"]=time.time()-1900
    a.data["closed"]=rows(n=10);b.data["closed"]=rows(n=10)
    a.data["cash_eur"]=999;b.data["cash_eur"]=998
    assert comparison(a,b)["status"]=="LOWER_LOSS"
    a.data["cash_eur"]=1001
    assert comparison(a,b)["status"]=="CAPITAL_GAIN"
    b.data["cash_eur"]=1002
    assert comparison(a,b)["status"]=="NO_IMPROVEMENT"
