import json
import time
from types import SimpleNamespace
import pytest
from darwin.research_lab import ResearchLab
from research_worker import safe_policy, replay
from agents.demo_queue import DemoQueue
from test_darwin import state
from test_autocorrection import free, SCHEMA
import httpx


def test_pacing_reserve_and_global_budget(tmp_path,monkeypatch):
    p=free(tmp_path,monkeypatch,lambda r:httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]}))
    def ask(task,purpose='routine'):return p.ask(system='test',task=task,context={},schema=SCHEMA,purpose=purpose)
    assert ask('one')['real_call']
    assert ask('two')['status']=='paced'
    assert p.budget()['attempts_24h']==1
    with p.db() as db:
        db.execute('UPDATE calls SET ts=?',(time.time()-3600,))
        for i in range(15):db.execute('INSERT INTO calls(ts,digest,status) VALUES(?,?,?)',(time.time()-3600,str(i),'fallback'))
    assert ask('three')['status']=='reserved'
    assert ask('incident','incident')['real_call']
    assert p.budget()['attempts_24h']==17


def test_batch_deduplicates_evidence_and_uses_one_call(tmp_path):
    from darwin.scientist import ScientistAgent
    calls=[]
    def ask(**kw):
        calls.append(kw)
        return SimpleNamespace(ok=True,data=kw['fallback'],audit={'real_call':False},error='')
    lab=ResearchLab(tmp_path/'lab.sqlite')
    supervisor=SimpleNamespace(scientist=ScientistAgent(),_repair_diagnosis={'code':'FEE_DRAG','actionable':True},
        brains=SimpleNamespace(curie=SimpleNamespace(ask_json=ask)),_emit=lambda *a,**kw:None,_remember_agent=lambda *a:None)
    rows=[dict(strategy_id='a',family='Momentum',horizon=5,turnover_x=20,return_bps=-100,closed_trades=30)]
    assert lab.batch(supervisor,rows,[])['a'].parameter=='cooldown_seconds'
    lab.batch(supervisor,rows,[])
    assert len(calls)==1
    assert len(lab.recent('deferred'))==1
    # Restart does not spend a second call for unchanged data.
    ResearchLab(tmp_path/'lab.sqlite').batch(supervisor,rows,[])
    assert len(calls)==1


def test_shadow_pairs_keep_books_and_never_promote(tmp_path):
    lab=ResearchLab(tmp_path/'lab.sqlite')
    genome=dict(id='a',family='Book pressure',horizon=5,gain=2,threshold=.1)
    first=state(1,100);lab.observe(first,[genome])
    f,a,b=lab.pairs[0]
    assert a.position==1 and b.position==0
    assert first['features']['weighted_imbalance']==.15
    lab.observe(state(3602,101),[genome])
    report=lab.recent('ablation')[0]
    assert report['status']=='INSUFFICIENT_EVIDENCE' # Zero-trade ablation cannot be a winner.
    assert not lab.pairs
    assert report['variant']['closed_trades']==0


@pytest.mark.parametrize('code',[
    'import os',
    'def research_policy(raw_signal, spread, flow, imbalance):\n return __import__("os")',
    'def research_policy(raw_signal, spread, flow, imbalance):\n while True: pass',
    'def research_policy(raw_signal, spread, flow, imbalance):\n return 10**10',
    'def research_policy(raw_signal, spread, flow, imbalance):\n return raw_signal.__class__',
])
def test_generated_policy_cannot_escape(code):
    with pytest.raises(ValueError):safe_policy(code)


def test_identity_replay_matches_and_bad_policy_rejected():
    g=dict(id='a',family='Momentum',horizon=5,gain=2,threshold=.1)
    ticks=[state(1,100),state(2,101),state(3,101,'STALE')]
    code='def research_policy(raw_signal, spread, flow, imbalance):\n return raw_signal'
    result=replay(code,ticks,g,1000,3.5)
    assert result['delta_net_usd']==0
    assert result['verdict']=='INSUFFICIENT_EVIDENCE'
    with pytest.raises(ValueError):replay(code.replace('return raw_signal','return 10'),ticks,g,1000,3.5)


def test_automatic_code_job_is_once_per_day_even_after_failure(tmp_path):
    q=DemoQueue(tmp_path)
    first=q.enqueue({'incident':{'code':'FEE_DRAG'}},kind='research')
    q.update(first['id'],'REJECTED')
    second=q.enqueue({'incident':{'code':'FEE_DRAG'}},kind='research')
    assert second['id']==first['id']
    assert 'no defect injection' in first['evidence']
