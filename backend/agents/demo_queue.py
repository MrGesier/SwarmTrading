"""Persistent, single-candidate engineering queue shared by API and local worker."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import time
import uuid

ACTIVE = ('DETECTED','QUEUED','LLM_CONNECTED','PROPOSED','PATCHING','TESTING')


class DemoQueue:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'demo.sqlite'
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT, updated REAL, payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY, heartbeat REAL)')

    def db(self):
        return sqlite3.connect(self.path,timeout=15)

    def enqueue(self, task_pack, provider='codex-cli'):
        if provider not in ('codex-cli','mock'):
            raise ValueError('unsupported engineer provider')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT payload FROM jobs ORDER BY updated DESC'):
                job=json.loads(row[0])
                if job['state'] in ACTIVE:
                    return job
            stamp=time.time(); identity=uuid.uuid4().hex
            job={'id':identity,'state':'QUEUED','created_at':stamp,'updated_at':stamp,'provider':provider,
                 'model':None,'real_call':False,'task_pack':task_pack,'prompt_version':'demo-code-v3',
                 'history':[{'state':'DETECTED','ts':stamp},{'state':'QUEUED','ts':stamp}],
                 'evidence':'Controlled defect: zero completed validation checks is incorrectly labelled PASSED in an isolated display helper.',
                 'checks':[], 'diff':'', 'files':[], 'integration':'HUMAN_REVIEW_REQUIRED',
                 'reason':None}
            db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(identity,'QUEUED',stamp,json.dumps(job)))
        return job

    def update(self, identity, state=None, **values):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM jobs WHERE id=?',(identity,)).fetchone()
            if not row: raise KeyError(identity)
            job=json.loads(row[0]); job.update(values); job['updated_at']=time.time()
            if state and job['state']!=state:
                job['state']=state; job['history'].append({'state':state,'ts':job['updated_at']})
            db.execute('UPDATE jobs SET state=?,updated=?,payload=? WHERE id=?',(job['state'],job['updated_at'],json.dumps(job),identity))
        return job

    def claim(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # In-flight jobs are never replayed, even after worker restart.
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('LLM_CONNECTED','PROPOSED','PATCHING','TESTING')").fetchone(): return None
            row=db.execute("SELECT id,payload FROM jobs WHERE state='QUEUED' ORDER BY updated LIMIT 1").fetchone()
            if not row:return None
            job=json.loads(row[1]); job['state']='PATCHING'; job['updated_at']=time.time()
            job['history'].append({'state':'PATCHING','ts':job['updated_at']})
            db.execute('UPDATE jobs SET state=?,updated=?,payload=? WHERE id=?',('PATCHING',job['updated_at'],json.dumps(job),row[0]))
            return job

    def heartbeat(self):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO worker VALUES(1,?)',(time.time(),))

    def state(self):
        with self.db() as db:
            jobs=[json.loads(r[0]) for r in db.execute('SELECT payload FROM jobs ORDER BY updated DESC LIMIT 12')]
            heartbeat=db.execute('SELECT heartbeat FROM worker WHERE id=1').fetchone()
        return {'worker_online':bool(heartbeat and heartbeat[0]>time.time()-30),'jobs':jobs}

    def recover(self):
        # Called only after the worker's OS lock has been acquired.
        for job in self.state()['jobs']:
            if job['state'] in ACTIVE and job['state']!='QUEUED':
                self.update(job['id'],'REJECTED',reason='Worker interrupted; candidate not retried or integrated. Inspect retained artifacts.')
