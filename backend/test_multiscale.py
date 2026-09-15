import numpy as np
import pytest
from engine import Engine,OrderBook,HORIZONS
from horizons import HorizonMemory,quote_ofi,selected_intent
from forecasting import triple_barrier,walk_forward


def test_flow_and_pressure_retain_independent_horizon_memory():
    memory=HorizonMemory(HORIZONS);book=OrderBook()
    for t in range(201):
        bidq,askq=(10,1) if t<195 else (1,10)
        book.snapshot(dict(lastUpdateId=t,bids=[[99,bidq]],asks=[[101,askq]]))
        memory.observe(book,float(t));memory.trade(float(t),1,t>=195)
    states=memory.states(200)
    assert states['5']['trade_flow']==-1
    assert states['180']['trade_flow']>.8
    assert states['5']['book_imbalance_mean']<0
    assert states['180']['book_imbalance_mean']>0
    assert states['180']['ready']
    assert states['5']['bullish_pressure_duty_cycle']==0


def test_quote_ofi_price_and_quantity_changes():
    assert quote_ofi((99,2,101,3),(99,5,101,1))==5
    assert quote_ofi((99,2,101,3),(100,4,102,5))==7


def test_no_future_trade_leaks_into_horizon():
    m=HorizonMemory([5]);b=OrderBook()
    for t in range(7):
        b.snapshot(dict(lastUpdateId=t,bids=[[99,1]],asks=[[101,1]]));m.observe(b,t)
    m.trade(4,2,False);m.trade(7,10000,True)
    assert m.states(6)['5']['trade_flow']==1


def test_barriers_censor_and_cost_adjust():
    labels=triple_barrier([0,1,2,3],[100,101,99,100],2,50,50,0)
    assert len(labels)==2 and labels[0]['label']==1 and labels[0]['end']==1
    cost=triple_barrier([0,1,2],[100,100.1,100],2,5,5,20)
    assert cost[0]['label']==0


def test_walkforward_purges_overlapping_labels():
    labels=[dict(index=i,start=i,end=i+5,label=(i%3)-1) for i in range(400)]
    result=walk_forward(labels,np.sin(np.arange(400)),min_train=50,embargo_s=5)
    assert result['status']=='EVALUATED'
    assert all(f['train_end']<f['test_start']-5 for f in result['folds'])
    assert result['deployment']=='NOT_APPROVED'


def test_barrier_does_not_use_tick_after_deadline():
    labels=triple_barrier([0,1,4],[100,100,110],2,50,50)
    assert labels[0]['label']==0
    assert labels[0]['end']==2
    assert labels[0]['mfe_bps']==0


def test_direction_can_wait_for_opposing_entry():
    local=dict(ready=True,horizon_s=180,features=dict(trade_flow=.6,book_imbalance_mean=.5,spread_mean=1),swarm=dict(consensus=.7,effective=4))
    entry=dict(ready=True,horizon_s=5,swarm=dict(consensus=-.6))
    intent=selected_intent(local,entry,'HEALTHY')
    assert intent['state']=='LONG_BIAS_WAIT'
    assert intent['p_long'] is None
    assert selected_intent(local,entry,'STALE')['state']=='RISK_OFF'
