import numpy as np
import pytest
from engine import Engine, HORIZONS, GENOMES
from analysis import cost_preview, technical_analysis


def test_horizon_180_has_no_signal_before_full_history():
    e=Engine()
    f=dict(returns={str(h):10 for h in HORIZONS},ready={str(h):h<=30 for h in HORIZONS},
           volatility=1,flow=.5,micro_delta=.1,spread=.5,weighted_imbalance=.5)
    v=e.votes(f)
    for g,signal in zip(GENOMES,v):
        if g['horizon']>30:
            assert signal==0
    f['ready']['180']=True
    v=e.votes(f)
    assert any(v[i]!=0 for i,g in enumerate(GENOMES) if g['horizon']==180)
    assert len(v)==320


def test_cost_walks_levels_and_does_not_invent_fill():
    result=cost_preview([(99,1),(98,1)],[(101,1),(102,1)],100,300,10)
    buy,sell=result
    assert buy['filled']==2 and not buy['complete']
    assert buy['fill_ratio']==pytest.approx(2/3)
    assert buy['vwap']==101.5
    assert buy['total_bps']==pytest.approx(160)
    assert sell['vwap']==98.5 and sell['total_bps']==pytest.approx(160)
    small=cost_preview([(99,1)],[(101,1)],100,50,0)
    assert small[0]['complete'] and small[0]['filled']==.5


def test_surface_uses_selected_horizon_and_baseline():
    e=Engine()
    e.weights=np.ones(320)/320
    f=dict(returns={str(h):h/20 for h in HORIZONS},ready={str(h):True for h in HORIZONS},
           volatility=1,flow=.1,micro_delta=.1,spread=.5,weighted_imbalance=.2)
    result=technical_analysis(e,dict(features=f,timestamp=100),180)
    zero=next(c for row in result['surface'] for c in row if c['bp']==0 and c['vol']==1)
    assert zero['flips']==0
    assert zero['consensus']==pytest.approx(result['baseline'])
    assert result['horizon']==180 and result['ready']
    assert len(result['surface'])==6 and len(result['surface'][0])==9
