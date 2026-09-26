"""Free-only Chat Completions adapter with a process-shared request ledger."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

import httpx
from jsonschema import validate


class FreeProvider:
    BASE = "https://openrouter.ai/api/v1"

    def __init__(self, path=None, client=None):
        # Deliberately independent of a symbol/mode or caller DARWIN_DATA_DIR.
        root = Path(__file__).resolve().parents[2]
        self.path = Path(path or root / "data" / "research-provider.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.limit = max(1, min(50, int(os.getenv("DARWIN_FREE_CALLS_PER_DAY", "40"))))
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, ts REAL, digest TEXT, status TEXT, result TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

    def db(self):
        return sqlite3.connect(self.path, timeout=15)

    def budget(self):
        with self.db() as db:
            used = db.execute("SELECT count(*) FROM calls WHERE ts>?", (time.time()-86400,)).fetchone()[0]
            row = db.execute("SELECT value FROM settings WHERE key='blocked_until'").fetchone()
        return {"limit": self.limit, "attempts_24h": used, "remaining": max(0,self.limit-used),
                "blocked_until": float(row[0]) if row else 0,
                "reserve": min(4,max(0,self.limit//5)),
                "window": "rolling_24h", "scope": "all agents/symbols/processes in this installation"}

    def remote_budget(self, refresh=False):
        """Read account limits, never expose key/account identity; cache outside the UI poll."""
        with self.db() as db:
            row=db.execute("SELECT value FROM settings WHERE key='remote_budget'").fetchone()
        cached=json.loads(row[0]) if row else {}
        if not refresh and cached.get('checked_at',0)>time.time()-3600:return cached
        result={'checked_at':time.time(),'status':'unavailable'}
        if self.key:
            try:
                with httpx.Client(timeout=10) as client:
                    r=client.get(self.BASE+'/key',headers={'Authorization':'Bearer '+self.key})
                    r.raise_for_status(); data=r.json().get('data',{}).get('free_model_daily_requests')
                    if isinstance(data,dict):result.update(status='observed',**{k:data.get(k) for k in ('used','limit','remaining')})
            except Exception:pass
        with self.db() as db:db.execute("INSERT OR REPLACE INTO settings VALUES('remote_budget',?)",(json.dumps(result),))
        return result

    def models(self, refresh=False):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='models'").fetchone()
        cached = json.loads(row[0]) if row else None
        if cached and not refresh and cached['ts'] > time.time()-3600:
            return cached['models']
        def fetch(client):
            response = client.get(self.BASE+"/models")
            response.raise_for_status()
            models = []
            for model in response.json().get('data', []):
                prices = model.get('pricing', {})
                if model['id'].endswith(':free') and all(float(prices.get(k, '1')) == 0 for k in ('prompt','completion')) and float(prices.get('request',0)) == 0:
                    models.append({"id":model['id'], "name":model.get('name',model['id']), "context_length":model.get('context_length'), "structured":'structured_outputs' in model.get('supported_parameters',[])})
            if not models:
                raise ValueError('no free models')
            return sorted(models, key=lambda m: (not ('cod' in m['id'].lower()), not m['structured'], m['id']))
        if self.client:
            models = fetch(self.client)
        else:
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                models = fetch(client)
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('models',?)", (json.dumps({'ts':time.time(),'models':models}),))
        return models

    def ask(self, *, system, task, context, schema, purpose="routine"):
        started = time.time()
        model = os.getenv('OPENROUTER_FREE_MODEL','').strip()
        def result(status, **extra):
            return {"provider":"openrouter-free", "model":model or None, "status":status,
                    "real_call":False, "latency_ms":int((time.time()-started)*1000), "budget":self.budget(), **extra}
        if not self.key:
            return result('unavailable', reason='OPENROUTER_API_KEY missing')
        try:
            models = self.models()
            if not model:
                model = models[0]['id']
            if model not in {m['id'] for m in models}:
                return result('unavailable', reason='Configured model is not in the current free catalogue')
        except Exception:
            return result('unavailable', reason='Free model catalogue unavailable')
        payload = {"model":model, "max_tokens":2048,
                   "messages":[{"role":"system","content":system[:4000]},
                               {"role":"user","content":task[:4000]+"\nContext: "+json.dumps(context)[:12000]+"\nReturn only JSON matching: "+json.dumps(schema)}],
                   "provider":{"max_price":{"prompt":0,"completion":0},"allow_fallbacks":False}}
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            cached = db.execute("SELECT status,result FROM calls WHERE digest=? AND ts>? ORDER BY id DESC LIMIT 1",(digest,started-86400)).fetchone()
            if cached and cached[0]=='connected':
                body=json.loads(cached[1]); body.update(status='cached',real_call=False,budget=self.budget()); return body
            if cached and cached[0]=='pending':
                return result('unavailable', reason='Identical request already attempted; pending or interrupted')
            used=db.execute('SELECT count(*) FROM calls WHERE ts>?',(started-86400,)).fetchone()[0]
            blocked=db.execute("SELECT value FROM settings WHERE key='blocked_until'").fetchone()
            if blocked and float(blocked[0])>started:
                return result('rate-limited',reason='Persistent backoff / circuit breaker')
            reserve=min(4, max(0,self.limit//5))
            last=db.execute('SELECT max(ts) FROM calls').fetchone()[0]
            interval=max(60,int(os.getenv('DARWIN_RESEARCH_MIN_INTERVAL_SECONDS','1800')))
            if purpose!='incident' and used>=self.limit-reserve:
                return result('reserved',reason='Remaining attempts reserved for measured incidents')
            spacing=300 if purpose=='incident' else interval
            if last and started-last<spacing:
                return result('paced',reason='Research calls distributed over time; next slot '+str(last+spacing))
            if used>=self.limit:
                return result('quota',reason='Local 24-hour attempt ceiling reached')
            call_id=db.execute("INSERT INTO calls(ts,digest,status) VALUES(?,?,'pending')",(started,digest)).lastrowid
        try:
            def send(client):
                return client.post(self.BASE+'/chat/completions',json=payload,headers={'Authorization':'Bearer '+self.key})
            if self.client:
                response=send(self.client)
            else:
                with httpx.Client(timeout=90,follow_redirects=False) as client:
                    response=send(client)
            if response.status_code==429:
                try: retry=max(60,min(86400,float(response.headers.get('retry-after','300'))))
                except ValueError: retry=300
                with self.db() as db:
                    db.execute("INSERT OR REPLACE INTO settings VALUES('blocked_until',?)",(str(time.time()+retry),))
                output=result('rate-limited',real_call=True,reason='Provider HTTP 429')
            else:
                response.raise_for_status()
                raw=response.json()
                data=json.loads(raw['choices'][0]['message']['content'])
                validate(data,schema)
                usage=raw.get('usage',{})
                output=result('connected',real_call=True,data=data,usage={k:usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')})
        except Exception as exc:
            output=result('fallback',real_call=True,reason=type(exc).__name__+'; provider/JSON validation failed')
        with self.db() as db:
            db.execute('UPDATE calls SET status=?,result=? WHERE id=?',(output['status'],json.dumps(output),call_id))
            failures=db.execute("SELECT status FROM calls ORDER BY id DESC LIMIT 3").fetchall()
            if len(failures)==3 and all(r[0]!='connected' for r in failures):
                current=db.execute("SELECT value FROM settings WHERE key='blocked_until'").fetchone()
                until=max(float(current[0]) if current else 0,time.time()+900)
                db.execute("INSERT OR REPLACE INTO settings VALUES('blocked_until',?)",(str(until),))
        return output

    def ping(self):
        return self.ask(system='Connectivity test. Return JSON.',task='Return {"message":"Darwin connected"}.',context={},
                        schema={'type':'object','properties':{'message':{'type':'string'}},'required':['message'],'additionalProperties':False})
