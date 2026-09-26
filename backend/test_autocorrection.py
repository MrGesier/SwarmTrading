import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from agents.demo_queue import DemoQueue
from agents.openrouter_free import FreeProvider
from demo_worker import TARGET, execute, safe_code, clean_env, redacted

SCHEMA={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}


def free(tmp_path,monkeypatch,handler):
    monkeypatch.setenv('OPENROUTER_API_KEY','sk-test-secret')
    monkeypatch.setenv('DARWIN_FREE_CALLS_PER_DAY','20')
    monkeypatch.delenv('OPENROUTER_FREE_MODEL',raising=False)
    def dispatch(req):
        if req.url.path.endswith('/models'):
            return httpx.Response(200,json={'data':[{'id':'fixture/coder:free','pricing':{'prompt':'0','completion':'0'}}]})
        assert req.url.path.endswith('/chat/completions')
        assert json.loads(req.content)['model'].endswith(':free')
        return handler(req)
    return FreeProvider(tmp_path/'provider.sqlite',httpx.Client(transport=httpx.MockTransport(dispatch)))


def ask(p,task='test'):
    with p.db() as db:db.execute('UPDATE calls SET ts=ts-301')
    return p.ask(system='test',task=task,context={},schema=SCHEMA,purpose='incident')


def test_free_shared_budget_cache_and_real_attempts(tmp_path,monkeypatch):
    calls=[]
    def respond(req):
        calls.append(req);return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}],'usage':{'total_tokens':4}})
    p=free(tmp_path,monkeypatch,respond)
    assert ask(p)['status']=='connected'
    assert ask(p)['status']=='cached'
    second=free(tmp_path,monkeypatch,respond)
    assert second.budget()['attempts_24h']==1
    for i in range(19):assert ask(second,str(i))['status']=='connected'
    assert ask(p,'overflow')['status']=='quota'
    assert len(calls)==20


def test_free_429_and_secret_redaction(tmp_path,monkeypatch):
    p=free(tmp_path,monkeypatch,lambda req:httpx.Response(429,headers={'retry-after':'600'},text='sk-test-secret'))
    assert ask(p)['status']=='rate-limited'
    assert ask(p,'different')['real_call'] is False
    assert p.budget()['attempts_24h']==1
    assert 'sk-test-secret' not in json.dumps(ask(p))
    assert 'sk-test-secret' not in redacted('Bearer sk-test-secret')


def test_free_malformed_json_circuit_and_missing_key(tmp_path,monkeypatch):
    p=free(tmp_path,monkeypatch,lambda req:httpx.Response(200,json={'choices':[{'message':{'content':'not JSON'}}]}))
    for i in range(3):assert ask(p,str(i))['status']=='fallback'
    assert ask(p,'fourth')['status']=='rate-limited'
    monkeypatch.delenv('OPENROUTER_API_KEY')
    assert FreeProvider(tmp_path/'missing.sqlite').ping()['status']=='unavailable'


def test_queue_claim_dedup_and_restart(tmp_path):
    q=DemoQueue(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=list(pool.map(lambda _:DemoQueue(tmp_path).enqueue({'objective':'demo'}),range(4)))
    assert len({j['id'] for j in jobs})==1
    assert q.claim()
    assert DemoQueue(tmp_path).claim() is None
    q.recover()
    assert q.state()['jobs'][0]['state']=='REJECTED'
    assert q.claim() is None


def test_candidate_guard_and_environment(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','secret')
    monkeypatch.setenv('GH_TOKEN','secret')
    env=clean_env()
    assert 'GH_TOKEN' not in env and 'OPENROUTER_API_KEY' not in env
    assert env['HYPERLIQUID_ENABLED']=='false'
    with pytest.raises(ValueError):safe_code('import os\ndef validation_label(passed,failed): return os.getenv("GH_TOKEN")')
    with pytest.raises(ValueError):safe_code('def validation_label(passed,failed): return eval("1")')


@pytest.fixture
def demo_repo(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    target=repo/TARGET;target.parent.mkdir(parents=True)
    target.write_text((Path(__file__).parent/'darwin/demo_report.py').read_text(encoding='utf-8'),encoding='utf-8')
    for args in [['init'],['add','.'],['-c','user.name=Test','-c','user.email=test@localhost','commit','-m','baseline']]:
        subprocess.run(['git',*args],cwd=repo,check=True,capture_output=True)
    return repo


@pytest.mark.parametrize('kind,expected',[('good','READY_FOR_REVIEW'),('wrong','REJECTED'),('outside','REJECTED')])
def test_isolated_patch_pipeline(demo_repo,tmp_path,kind,expected):
    original=(demo_repo/TARGET).read_bytes()
    queue=DemoQueue(tmp_path/'queue');queue.enqueue({'objective':'controlled demo'},'mock');job=queue.claim()
    def proposal(broken):
        return {'hypothesis':'fixture','path':TARGET if kind!='outside' else 'backend/darwin/judge.py',
                'code':original.decode() if kind=='good' else broken+'\n# intentionally wrong\n'}
    output=execute(queue,job,demo_repo,proposer=proposal,regression=lambda work:True)
    assert output['state']==expected, output.get('reason')
    assert output['real_call'] is False
    assert (demo_repo/TARGET).read_bytes()==original
    assert output['checks'][0]['exit_code']==0
    assert output['checks'][1]['exit_code']!=0
    if kind=='good':assert output['candidate_sha'] and output['diff']
    else:assert not (tmp_path/'queue/worktrees'/job['id']).exists()


def test_local_demo_auth(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from demo_api import create_demo_router
    app=FastAPI();app.include_router(create_demo_router(tmp_path,lambda *args:None))
    with TestClient(app) as client:
        assert client.get('/api/autocorrection/state').status_code==401
        assert client.get('/api/autocorrection/session',headers={'Origin':'https://evil.test'}).status_code==403
        assert client.get('/api/autocorrection/session').status_code==200
        assert client.get('/api/autocorrection/state').status_code==200
        assert client.post('/api/autocorrection/demo',json={}).status_code==403


def test_desktop_codex_discovery_without_path(tmp_path,monkeypatch):
    import demo_worker
    monkeypatch.delenv('DARWIN_CODEX_BIN',raising=False)
    monkeypatch.setattr(demo_worker.shutil,'which',lambda _:None)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    cli=tmp_path/'OpenAI/Codex/bin/version/codex.exe'
    cli.parent.mkdir(parents=True);cli.write_bytes(b'fixture')
    assert demo_worker.resolve_codex()==str(cli)
    monkeypatch.setenv('DARWIN_CODEX_BIN',str(tmp_path/'missing.exe'))
    assert demo_worker.resolve_codex() is None
