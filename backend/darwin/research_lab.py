"""Evidence-triggered batched research, persisted reports and matched shadow experiments."""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from .paper import PaperAccount
from .scientist import ExperimentPlan
from .genome import MUTABLE_GENES

class ResearchLab:
    def __init__(self, path, notional=1000, fees=3.5):
        self.path=Path(path); self.notional=notional; self.fees=fees
        self.pairs=[]; self.last_tick=0; self.window_start=None
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,ts REAL,kind TEXT,payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS ticks(ts REAL PRIMARY KEY,payload TEXT)')
        # An interrupted paired window is not resumed with reset accounts.
        self.record('session',{'status':'NEW_MATCHED_WINDOW','reason':'Restart starts new paired accounts; completed reports retained'})

    def db(self):return sqlite3.connect(self.path,timeout=15)
    def record(self,kind,payload):
        with self.db() as db:
            db.execute('INSERT INTO records(ts,kind,payload) VALUES(?,?,?)',(time.time(),kind,json.dumps(payload,default=str)))
            db.execute('DELETE FROM records WHERE id NOT IN (SELECT id FROM records ORDER BY id DESC LIMIT 1000)')
    def recent(self,kind=None,limit=30):
        with self.db() as db:
            rows=db.execute('SELECT id,ts,kind,payload FROM records WHERE (? IS NULL OR kind=?) ORDER BY id DESC LIMIT ?',(kind,kind,limit)).fetchall()
        return [dict(id=i,ts=t,kind=k,**json.loads(p)) for i,t,k,p in rows]

    def observe(self,state,strategies):
        ts=float(state['timestamp'])
        if ts<=self.last_tick:return
        # Record actual observations at one-second resolution for isolated replay.
        if ts-self.last_tick>=1:
            clean={k:state.get(k) for k in ('timestamp','features','bids','asks','health','intent','regime')}
            clean['bids']=clean['bids'][:10];clean['asks']=clean['asks'][:10]
            with self.db() as db:
                db.execute('INSERT OR IGNORE INTO ticks VALUES(?,?)',(ts,json.dumps(clean)))
                db.execute('DELETE FROM ticks WHERE ts<?',(ts-21600,))
            self.last_tick=ts
        if not self.pairs:
            # Freeze identical accounts before collecting future evidence, one intervention per pair.
            for feature,family in [('weighted_imbalance','Book pressure'),('flow','Breakout'),('micro_delta','Microprice'),('spread_filter','Momentum')]:
                parent=next((s for s in strategies if s['family']==family and s['horizon']==5),None)
                if parent:
                    g={**parent,'status':'ACTIVE'}
                    self.pairs.append((feature,PaperAccount(g,self.notional,self.fees),PaperAccount(g,self.notional,self.fees)))
            self.window_start=ts
        for feature,control,variant in self.pairs:
            control.observe(state)
            if feature=='spread_filter':variant.observe(state,risk_off=float(state['features'].get('spread',0))>2)
            else:
                modified={**state,'features':{**state['features'],feature:0.0}}
                variant.observe(modified)
        if self.window_start is not None and ts-self.window_start>=3600:
            for feature,control,variant in self.pairs:
                control._close(state,reason='paired_window_end');variant._close(state,reason='paired_window_end')
                a,b=control.metrics(),variant.metrics()
                sufficient=min(a['sample_seconds'],b['sample_seconds'])>=1800 and min(a['closed_trades'],b['closed_trades'])>=5
                self.record('ablation',{'feature':feature,'parent_id':control.strategy['id'],'start':self.window_start,'end':ts,
                    'control':a,'variant':b,'delta_net_usd':b['pnl']-a['pnl'],
                    'status':'MEASURED_NOT_PROVEN' if sufficient else 'INSUFFICIENT_EVIDENCE',
                    'interpretation':'Matched future window, same observed books and fees. No automatic promotion; correlated trials, no causal or profitability proof.'})
            self.pairs=[];self.window_start=None

    def batch(self, supervisor, ranked, lessons):
        defaults={r['strategy_id']:supervisor.scientist.plan(r,lessons) for r in ranked[:3]}
        if not ranked:return defaults
        incident=supervisor._repair_diagnosis
        # Quantized economic evidence avoids new questions from timestamps or ever-growing IDs.
        digest=hashlib.sha256(json.dumps({'incident':incident.get('code'), 'cells':sorted(
            (r['family'],r['horizon'],round(float(r.get('return_bps',0))/50),round(float(r.get('turnover_x',0))/10),int(r.get('closed_trades',0))//20)
            for r in ranked[:3]),'ablation_ids':[r['id'] for r in self.recent('ablation',4)]},sort_keys=True).encode()).hexdigest()
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute("SELECT value FROM meta WHERE key='batch'").fetchone()
            previous=json.loads(previous[0]) if previous else {}
            if previous.get('digest')==digest or now-previous.get('ts',0)<7200:
                db.commit()
                self.record('deferred',{'reason':'UNCHANGED_EVIDENCE' if previous.get('digest')==digest else 'COLLECTING_NEW_EVIDENCE','next_at':previous.get('ts',now)+7200})
                return defaults
            db.execute("INSERT OR REPLACE INTO meta VALUES('batch',?)",(json.dumps({'digest':digest,'ts':now}),))
        plan_schema={'type':'object','additionalProperties':False,'properties':{
            'parent_id':{'type':'string','enum':list(defaults)},'parameter':{'type':'string','enum':list(MUTABLE_GENES)},
            'factors':{'type':'array','minItems':2,'maxItems':2,'items':{'type':'number','minimum':.75,'maximum':1.25}},
            'hypothesis':{'type':'string'},'rationale':{'type':'string'},'confidence':{'type':'number','minimum':0,'maximum':1}},
            'required':['parent_id','parameter','factors','hypothesis','rationale','confidence']}
        fallback={'plans':[{'parent_id':sid,**p.to_dict()} for sid,p in defaults.items()],'summary':'Deterministic proposals; no LLM conclusion'}
        context={'questions':['Do fees consume gross edge?','Are holding durations and exit reasons appropriate?','What do matched indicator ablations show, and what remains unproven?'],
            'budget_priority':'incident' if incident.get('actionable') else 'routine',
            'candidates':ranked[:3],'recent_ablations':self.recent('ablation',4),'lessons':lessons[:3]}
        supervisor._emit('agent_started',{'task':'batched evidence review and controlled plans'},agent_id='curie')
        result=supervisor.brains.curie.ask_json(task='Review this evidence as one research batch: prioritize incidents, propose at most one permitted single-gene experiment per parent, explain falsifiable predictions and rejection criteria. Do not invent evidence or change code. Summarize unresolved questions.',
            context=context,schema_name='research_batch_v1',schema={'type':'object','additionalProperties':False,'properties':{'plans':{'type':'array','maxItems':3,'items':plan_schema},'summary':{'type':'string'}},'required':['plans','summary']},fallback=fallback)
        supervisor._remember_agent('curie',result)
        self.record('batch',{'digest':digest,'audit':result.audit,'ok':result.ok,'summary':result.data.get('summary'),'plans':result.data.get('plans',[]),'error':result.error})
        if result.ok:
            seen=set()
            for p in result.data.get('plans',[]):
                sid=p['parent_id']
                if sid in defaults and sid not in seen:
                    defaults[sid]=ExperimentPlan(p['parameter'],tuple(p['factors']),p['hypothesis'],p['rationale'],p['confidence']);seen.add(sid)
        return defaults

    def critique_due(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT value FROM meta WHERE key='critique'").fetchone()
            if row and time.time()-float(row[0])<86400:return False
            db.execute("INSERT OR REPLACE INTO meta VALUES('critique',?)",(str(time.time()),))
        return True

    def maybe_queue_code(self, supervisor):
        if os.getenv('DARWIN_AUTO_CODE_RESEARCH','false').lower()!='true':return
        incident=supervisor._repair_diagnosis
        reports=self.recent('epoch_report',2)
        if len(reports)<2:
            reports=[{'incident':e.get('config',{}).get('measured_incident',{})} for e in supervisor.store.recent_epochs(2)]
        if not incident.get('actionable') or len(reports)<2 or any(r.get('incident',{}).get('code')!=incident.get('code') for r in reports):return
        with self.db() as db:
            if db.execute('SELECT count(*) FROM ticks').fetchone()[0]<60:return
        rows=supervisor.population.metrics()
        candidates=[r for r in rows if r.get('closed_trades',0)>=5]
        if not candidates:return
        row=min(candidates,key=lambda r:r['pnl'])
        genome=supervisor.population.accounts[row['strategy_id']].strategy
        from agents.demo_queue import DemoQueue
        root=Path(__file__).resolve().parents[2]
        queue=DemoQueue(root/'data/autocorrection')
        job=queue.enqueue({'incident':incident,'genome':genome,'lab_path':str(self.path.resolve()),
            'notional':self.notional,'fees':self.fees,'symbol':supervisor.symbol},kind='research')
        with self.db() as db:db.execute("INSERT OR REPLACE INTO meta VALUES('code_job',?)",(json.dumps({'id':job['id'],'state':job['state']}),))

    def state(self):
        records=[r for r in self.recent(limit=100) if r['ts']>=time.time()-86400]
        return {'records':records,'active_ablations':[{'feature':f,'parent_id':a.strategy['id'],'started_at':self.window_start,'control':a.metrics(),'variant':b.metrics()} for f,a,b in self.pairs],
                'summary':{'batches':sum(r['kind']=='batch' for r in records),'comparisons':sum(r['kind']=='ablation' for r in records),'reports':sum(r['kind']=='epoch_report' for r in records)},
                'next_action':'Collect current Hyperliquid observations; batch new evidence at most once per two hours; review generated code before integration.'}
