"""Local session-protected API. Queues data only; never launches commands."""
import secrets
import os
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from agents.demo_queue import DemoQueue
from agents.openrouter_free import FreeProvider


def create_demo_router(root, get_session, select_provider=None):
    router=APIRouter(prefix='/api/autocorrection')
    queue=DemoQueue(root/'data/autocorrection')
    token=secrets.token_urlsafe(32)
    with queue.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY,value TEXT)')
        saved=db.execute("SELECT value FROM config WHERE key='provider'").fetchone()
    if saved and not os.getenv('DARWIN_RESEARCH_PROVIDER') and select_provider:
        select_provider(saved[0])

    def local(request):
        if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):
            raise HTTPException(403,'Local demonstration only')
        host=request.url.hostname
        if host not in ('127.0.0.1','localhost','::1','testserver'):
            raise HTTPException(403,'Untrusted host')
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc!=request.headers.get('host'):
            raise HTTPException(403,'Cross-origin demonstration request rejected')

    def auth(request,write=False):
        local(request)
        if not secrets.compare_digest(request.cookies.get('darwin_demo',''),token):
            raise HTTPException(401,'Open the local Factory to initialise the session')
        if write and not secrets.compare_digest(request.headers.get('x-darwin-demo',''),token):
            raise HTTPException(403,'Missing local session header')

    @router.get('/session')
    def session(request:Request,response:Response):
        local(request)
        response.set_cookie('darwin_demo',token,httponly=True,samesite='strict')
        response.headers['Cache-Control']='no-store'
        return {'csrf':token}

    @router.get('/state')
    def state(request:Request):
        auth(request)
        provider=FreeProvider()
        return {**queue.state(),'openrouter':{'configured':bool(provider.key),'budget':provider.budget()},
                'providers':['deterministic','openrouter-free','ollama'],
                'selected_provider':os.getenv('DARWIN_RESEARCH_PROVIDER','openai'),
                'ollama':'not installed in this demonstration','integration':'HUMAN_REVIEW_REQUIRED'}

    class DemoRequest(BaseModel):
        provider:str='codex-cli'

    @router.post('/demo')
    async def demo(req:DemoRequest,request:Request):
        auth(request,True)
        if req.provider not in ('codex-cli','mock'):raise HTTPException(400,'Unsupported demo provider')
        supervisor=get_session('BTCUSDT','live').darwin
        pack=supervisor.engineer.task_pack(supervisor,objective='V3 controlled display-helper defect, isolated patch, independent tests, human review')
        job=queue.enqueue(pack,req.provider)
        supervisor._emit('engineer_task_prepared',{'demo_id':job['id'],'state':job['state'],'provider':req.provider},agent_id='codex')
        return job

    @router.post('/provider')
    def provider(req:DemoRequest,request:Request):
        auth(request,True)
        if req.provider not in ('deterministic','openrouter-free','ollama'):
            raise HTTPException(400,'Unsupported research provider')
        if select_provider:select_provider(req.provider)
        with queue.db() as db:db.execute("INSERT OR REPLACE INTO config VALUES('provider',?)",(req.provider,))
        return {'selected_provider':req.provider}

    @router.post('/ping')
    def ping(request:Request):
        auth(request,True)
        return FreeProvider().ping()

    @router.get('/models')
    def models(request:Request):
        auth(request)
        try:return {'models':FreeProvider().models()}
        except Exception:return {'models':[],'status':'unavailable'}

    @router.get('/proposal/{identity}')
    def proposal(identity:str,request:Request):
        auth(request)
        for job in queue.state()['jobs']:
            if job['id']==identity:return job
        raise HTTPException(404,'Unknown proposal')

    return router
