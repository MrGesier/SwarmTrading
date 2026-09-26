import asyncio
from contextlib import asynccontextmanager
from collections import deque
import json
import math
import os
from pathlib import Path
import random
import time
import uuid

import httpx
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    pa = None
    pq = None
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from engine import Engine, OrderBook, GENOMES, HORIZONS, SequenceGap
from analysis import technical_analysis, cost_preview
from darwin import DarwinSupervisor
from darwin.portfolio import SharedPortfolio
from darwin.capital_feedback import start_comparison, comparison
from marketdata.portfolio_service import PortfolioFeeds
from execution.hyperliquid import HyperliquidExecutor
from agents import agent_runtime_state, policy_state
from agents.openbot_agui import COWORKERS as OPENBOT_COWORKERS, AGUIAdapter as OPENBOT_AGUI_ADAPTER, authorised as openbot_authorised, available as openbot_available, get_agent as get_openbot_agent, state as openbot_bridge_state
from marketdata.hyperliquid import HyperliquidPublicStream
from darwin.factory import factory_state, decorate_events

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / '.env')
DEFAULT_DATA_DIR = '/tmp/swarmtrade-data' if os.getenv('VERCEL') else str(PROJECT_ROOT / 'data')
DATA = Path(os.getenv('DARWIN_DATA_DIR', DEFAULT_DATA_DIR))
DATA.mkdir(parents=True, exist_ok=True)
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
shared_portfolio = SharedPortfolio(DATA / 'shared-portfolio-v1.json')
fixed_portfolio = SharedPortfolio(DATA / "shared-portfolio-control-v1.json")
portfolio_feeds = PortfolioFeeds(shared_portfolio, fixed_portfolio)


class Recorder:
    def __init__(self, symbol, mode):
        self.enabled = os.getenv('DARWIN_RECORD_RAW', 'true').lower() in {'1','true','yes'}
        self.max_parts = max(0, int(os.getenv('DARWIN_RECORD_MAX_PARTS', '240')))
        self.directory = DATA / f'{mode}-{symbol}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}'
        if self.enabled:
            self.directory.mkdir(exist_ok=True)
        self.rows = []
        self.part = 0

    def add(self, event, ts):
        if self.enabled:
            self.rows.append(dict(received=ts, payload=json.dumps(event, separators=(',', ':'))))

    async def flush(self):
        if not self.enabled or not self.rows:
            return
        rows, self.rows = self.rows, []
        self.part += 1
        if pa is not None and pq is not None:
            path = self.directory / f'{self.part:06}.parquet'
            await asyncio.to_thread(pq.write_table, pa.Table.from_pylist(rows), path, compression='zstd')
        else:
            path = self.directory / f'{self.part:06}.jsonl'
            payload = ''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows)
            await asyncio.to_thread(path.write_text, payload, encoding='utf-8')
        if self.max_parts > 0:
            files = sorted([*self.directory.glob('*.parquet'), *self.directory.glob('*.jsonl')], key=lambda x: x.name)
            for old in files[:-self.max_parts]:
                try:
                    old.unlink()
                except OSError:
                    pass


class Session:
    def __init__(self, symbol, mode):
        self.symbol, self.mode = symbol, mode
        self.book, self.engine = OrderBook(), Engine()
        self.health = 'CONNECTING'
        self.error = ''
        self.last_depth = 0
        self.latest = None
        self.states = deque(maxlen=1200)
        self.recorder = Recorder(symbol, mode)
        self.task = None
        self.research_task = None
        self.rng = random.Random(42)
        self.price = {'BTCUSDT': 64280, 'ETHUSDT': 2680, 'SOLUSDT': 148}[symbol]
        self.n = 0
        self.last_quote = None
        self.darwin = DarwinSupervisor(symbol, mode, DATA)
        self.darwin.portfolio_feedback = lambda: shared_portfolio.research_feedback(self.symbol)
        self.darwin_error = ""
        checkpoint = self.darwin.store.load_checkpoint()
        source = (checkpoint or {}).get('source')
        self.resumed = bool(source and mode == 'simulation')
        if self.resumed:
            def tuples(value):
                return tuple(tuples(x) for x in value) if isinstance(value, list) else value
            self.rng.setstate(tuples(source['rng']))
            self.price, self.n = source['price'], source['n']
        self.darwin.source_snapshot = lambda: dict(rng=self.rng.getstate(), price=self.price, n=self.n)

        self.market_source = os.getenv("DARWIN_MARKET_SOURCE", "hyperliquid" if mode == "live" else "simulation").lower()
        self.venue_context: dict[str, object] = {}

    def ingest(self, event, ts, record=True):
        if record:
            self.recorder.add(event, ts)
        if event['type'] == 'snapshot':
            self.book.snapshot(event['data'])
            if event.get('source') == 'hyperliquid':
                # Hyperliquid l2Book is itself a complete pushed snapshot.
                bids, asks = self.book.levels(1)
                self.book.valid = bool(bids and asks and bids[0][0] < asks[0][0])
                self.last_depth = ts
        elif event['type'] == 'context':
            self.venue_context = {**dict(event.get('data') or {}), 'received_at': ts}
        elif event['type'] == 'depth':
            if self.book.update(event['data']):
                self.last_depth = ts
        elif event['type'] == 'trade':
            d = event['data']
            self.engine.trade(ts, float(d['p']), float(d['q']), d['m'])
        elif event['type'] == 'quote':
            self.last_quote = event['data']

    def derive(self, ts):
        self.recorder.add(dict(type='clock', valid=self.book.valid, health=self.health), ts)
        age = max(0, (ts-self.last_depth)*1000)
        health = dict(status='HEALTHY' if self.book.valid and age < 3000 and self.health == 'HEALTHY' else 'STALE' if self.latest else self.health,
                      age_ms=round(age) if self.last_depth else None, sequence=self.book.sequence, message=self.error,
                      recording=self.recorder.directory.name if self.recorder.enabled else 'disabled')
        state = self.engine.calculate(self.book, ts, self.mode, self.symbol, health)
        if state:
            if self.mode == 'live' and self.market_source == 'hyperliquid':
                state['venue'] = 'HYPERLIQUID'
                state['venue_context'] = self.venue_context
            self.latest = state
            self.states.append(state)
            try:
                self.darwin.observe(state)
                portfolio_feeds.observe(state, [a.strategy for a in self.darwin.population.accounts.values()])
                if self.darwin.due() and (self.research_task is None or self.research_task.done()):
                    self.research_task = asyncio.create_task(self.research_cycle())
                self.darwin_error = ""
            except Exception as exc:
                self.darwin_error = f"{type(exc).__name__}: {str(exc)[:180]}"

    async def research_cycle(self):
        try:
            await self.darwin.run_epoch_async()
            self.darwin_error = ''
        except Exception as exc:
            self.darwin_error = f'{type(exc).__name__}: research cycle failed'

    def simulate(self, ts):
        self.n += 1
        drift = math.sin(self.n / 42) * .000026
        self.price *= 1 + drift + self.rng.gauss(0, .000047)
        step = self.price * .000025
        pressure = math.sin(self.n/32) * .65
        bids = [[round(self.price-step*(i+1), 5), round((1+pressure)*(1+self.rng.random()*3)*(3 if i in [12,28] else 1), 5)] for i in range(40)]
        asks = [[round(self.price+step*(i+1), 5), round((1-pressure)*(1+self.rng.random()*3)*(4 if i in [16,32] else 1), 5)] for i in range(40)]
        self.ingest(dict(type='snapshot', data=dict(lastUpdateId=self.n, bids=bids, asks=asks)), ts)
        self.book.valid = True
        self.last_depth = ts
        self.health = 'HEALTHY'
        for _ in range(3):
            self.ingest(dict(type='trade', data=dict(p=self.price, q=self.rng.uniform(.01, 1.5), m=self.rng.random() > .5+pressure*.4)), ts)
        self.derive(ts)

    async def run(self):
        try:
            if self.mode == 'simulation':
                now = time.time()
                for i in range(0 if self.resumed else 400):
                    self.simulate(now - (400-i)*.5)
                while True:
                    self.simulate(time.time())
                    if len(self.recorder.rows) >= 400:
                        await self.recorder.flush()
                    await asyncio.sleep(.5)
            else:
                if self.market_source == 'hyperliquid':
                    await self.live_hyperliquid()
                else:
                    await self.live_binance()
        finally:
            self.darwin.checkpoint()
            await self.recorder.flush()

    async def live_binance(self):
        delay = 1
        while True:
            self.health = 'CONNECTING'
            self.book = OrderBook()
            self.engine = Engine()
            self.last_depth = 0
            self.recorder.add(dict(type='reset'),time.time())
            try:
                symbol = self.symbol.lower()
                url = f'wss://stream.binance.com:9443/stream?streams={symbol}@depth@100ms/{symbol}@trade/{symbol}@bookTicker'
                async with websockets.connect(url, ping_interval=20, max_queue=4096) as ws:
                    queue = asyncio.Queue(maxsize=20000)
                    async def receive():
                        async for raw in ws:
                            queue.put_nowait((time.time(), json.loads(raw)['data']))
                    reader = asyncio.create_task(receive())
                    try:
                        async with httpx.AsyncClient(timeout=20) as client:
                            response = await client.get('https://api.binance.com/api/v3/depth', params=dict(symbol=self.symbol, limit=5000))
                            response.raise_for_status()
                        self.ingest(dict(type='snapshot', data=response.json()), time.time())
                        last_emit = 0
                        while True:
                            if reader.done():
                                reader.result()
                                raise ConnectionError('Exchange stream closed')
                            ts, d = await asyncio.wait_for(queue.get(), timeout=5)
                            if d.get('e') == 'depthUpdate':
                                self.ingest(dict(type='depth', data=d), ts)
                            elif d.get('e') == 'trade':
                                self.ingest(dict(type='trade', data=d), ts)
                            elif 'b' in d and 'a' in d:
                                self.ingest(dict(type='quote', data=d), ts)
                            if self.book.valid:
                                self.health, self.error, delay = 'HEALTHY', '', 1
                            now=time.time()
                            if now-last_emit >= .5 and self.book.valid:
                                self.derive(now)
                                last_emit = now
                            if len(self.recorder.rows) >= 1000:
                                await self.recorder.flush()
                    finally:
                        reader.cancel()
                        await asyncio.gather(reader, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.health, self.error = 'RECONNECTING', f'{type(exc).__name__}: {str(exc)[:180]}'
                self.book.valid = False
                if self.latest:
                    self.derive(time.time())
                await self.recorder.flush()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)


    async def live_hyperliquid(self):
        """Consume Hyperliquid public perp data and paper-trade the population."""
        stream = HyperliquidPublicStream(self.symbol)
        self.health = 'CONNECTING'
        self.error = ''
        last_emit = 0.0
        async for ts, event in stream.events():
            try:
                self.ingest(event, ts)
                if event['type'] == 'snapshot' and self.book.valid:
                    self.health = 'HEALTHY'
                    self.error = ''
                now = time.time()
                if self.book.valid and now - last_emit >= .5:
                    self.derive(now)
                    # Schedule from completion, not start: an expensive derivation must
                    # not trigger another one immediately for every buffered event.
                    last_emit = time.time()
                    await asyncio.sleep(0)
                if len(self.recorder.rows) >= 1000:
                    await self.recorder.flush()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.health = 'RECONNECTING'
                self.error = f'{type(exc).__name__}: {str(exc)[:180]}'
                self.book.valid = False
                await self.recorder.flush()



sessions = {}


def get_session(symbol='BTCUSDT', mode='live'):
    if symbol not in SYMBOLS or mode != 'live':
        raise HTTPException(400, 'Only current Hyperliquid data with paper trading is supported')
    key = (symbol, mode)
    if key not in sessions:
        s = sessions[key] = Session(symbol, mode)
        s.task = asyncio.create_task(s.run())
    return sessions[key]


@asynccontextmanager
async def lifespan(app):
    start_comparison(shared_portfolio, fixed_portfolio)
    autostart_symbol = os.getenv('DARWIN_AUTOSTART_SYMBOL', 'BTCUSDT')
    autostart_mode = 'live'
    for symbol in SYMBOLS:
        get_session(symbol, autostart_mode)
    portfolio_task = asyncio.create_task(portfolio_feeds.run())
    yield
    portfolio_task.cancel()
    await asyncio.gather(portfolio_task, return_exceptions=True)
    await asyncio.gather(*(s.research_task for s in sessions.values() if s.research_task), return_exceptions=True)
    for s in sessions.values():
        s.task.cancel()
    await asyncio.gather(*(s.task for s in sessions.values()), return_exceptions=True)


hyperliquid_executor = HyperliquidExecutor()

app = FastAPI(title='SwarmTrade V0.11 OpenAI Brain + OpenBot Bridge', lifespan=lifespan)
from demo_api import create_demo_router
from wallet_api import create_wallet_router
app.include_router(create_wallet_router())
from execution.validation import TestnetValidation, create_validation_router
app.include_router(create_validation_router(TestnetValidation(hyperliquid_executor, DATA / 'testnet-validation.sqlite')))
def select_research_provider(provider):
    os.environ['DARWIN_RESEARCH_PROVIDER']=provider
    cognitive=('atlas','curie','evolve','judge','mnemosyne')
    for session in list(sessions.values()):
        for identity in cognitive:
            brain=session.darwin.brains._by_id[identity]
            brain.runtime=provider
            brain.provider_trace=None
            brain.last_result=None
            if provider=='openrouter-free':brain.model=os.getenv('OPENROUTER_FREE_MODEL','unselected :free model')
    return provider
app.include_router(create_demo_router(PROJECT_ROOT, get_session, select_research_provider))
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=3)
ALLOWED_ORIGINS = [x.strip() for x in os.getenv('DARWIN_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=['GET','POST'], allow_headers=['*'])


@app.get('/api/health')
def health():
    return dict(status='ok', execution='paper' if not hyperliquid_executor.config.enabled else 'guarded-hyperliquid',
                paper_only=not hyperliquid_executor.config.enabled, project_root=str(PROJECT_ROOT),
                data_dir=str(DATA.resolve()), pid=os.getpid(),
                market_source=os.getenv('DARWIN_MARKET_SOURCE','hyperliquid'), version='0.11.0')


@app.get('/api/state')
async def state(symbol: str = 'BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    return s.latest or dict(status=s.health, message=s.error)


@app.websocket('/ws')
async def stream(ws: WebSocket, symbol: str = 'BTCUSDT', mode: str='live'):
    origin = ws.headers.get('origin')
    forwarded_host = ws.headers.get('x-forwarded-host') or ws.headers.get('host')
    same_host = bool(origin and forwarded_host and origin.split('://')[-1].rstrip('/') == forwarded_host)
    if origin and origin not in ALLOWED_ORIGINS and not same_host:
        await ws.close(code=1008)
        return
    await ws.accept()
    if symbol not in SYMBOLS or mode != 'live':
        await ws.close(code=1008)
        return
    s = get_session(symbol, mode)
    try:
        while True:
            if s.latest and time.time() - s.last_depth > 3:
                s.latest = {**s.latest, 'health': {**s.latest['health'], 'status':'STALE', 'age_ms':round((time.time()-s.last_depth)*1000), 'message':s.error}, 'intent':{**s.latest['intent'], 'state':'RISK_OFF', 'risk_causes':['FEED_STALE']}}
            await ws.send_json(s.latest or dict(status=s.health, message=s.error))
            await asyncio.sleep(.5)
    except (WebSocketDisconnect, RuntimeError):
        pass


class Counterfactual(BaseModel):
    symbol: str = 'BTCUSDT'
    mode: str='live'
    price_bp: float = Field(0, ge=-100, le=100)
    vol_scale: float = Field(1, ge=.2, le=3)
    flow_delta: float = Field(0, ge=-1, le=1)
    horizon: int = 5


@app.post('/api/counterfactual')
async def counterfactual(c: Counterfactual):
    import numpy as np
    s = get_session(c.symbol, c.mode)
    if c.horizon not in HORIZONS:
        raise HTTPException(400,'Unsupported horizon')
    if not s.latest:
        raise HTTPException(409, 'Waiting for market state')
    v = s.engine.votes(s.latest['features'], c.price_bp, c.vol_scale, c.flow_delta)
    base = s.engine.votes(s.latest['features'])
    w = s.engine.weights * np.array([g['horizon']==c.horizon for g in GENOMES])
    return dict(consensus=float(np.dot(v,w)/max(w.sum(),1e-9)), flips=float(w[np.sign(v)!=np.sign(base)].sum()),
                base_consensus=float(np.dot(base,w)/max(w.sum(),1e-9)), timestamp=s.latest['timestamp'], ready=s.latest['features']['ready'][str(c.horizon)])


@app.get('/api/analysis')
async def analysis(symbol: str='BTCUSDT',mode: str='live',horizon: int=5):
    s=get_session(symbol,mode)
    if horizon not in HORIZONS:
        raise HTTPException(400,'Unsupported horizon')
    if not s.latest:
        raise HTTPException(409,'Waiting for market state')
    return technical_analysis(s.engine,s.latest,horizon)


class CostRequest(BaseModel):
    symbol: str='BTCUSDT'
    mode: str='live'
    notional: float=Field(10000,gt=0,le=10000000)
    fee_bps: float=Field(10,ge=0,le=100)


@app.post('/api/cost-preview')
async def preview(c:CostRequest):
    s=get_session(c.symbol,c.mode)
    if not s.latest or not s.book.valid or time.time()-s.last_depth>3:
        raise HTTPException(409,'Cost preview requires a healthy, fresh book')
    bids,asks=s.book.levels(40)
    mid=(bids[0][0]+asks[0][0])/2
    return dict(timestamp=s.last_depth,notional=c.notional,mid=mid,rows=cost_preview(bids,asks,mid,c.notional,c.fee_bps))


@app.get('/api/replay')
async def replay(symbol: str = 'BTCUSDT', mode: str='live'):
    from fastapi.responses import Response
    s = get_session(symbol, mode)
    # Compact state frames preserve every panel at that instant, without future history.
    frames = [{**x, 'history':x['history'][-80:], 'candles':x['candles'][-100:]} for x in list(s.states)[-300:]]
    body = await asyncio.to_thread(json.dumps, frames, separators=(',', ':'))
    return Response(body, media_type='application/json')


@app.get('/api/recordings')
def recordings():
    return [dict(id=d.name, parts=len(list(d.glob('*.parquet')))) for d in sorted(DATA.iterdir()) if d.is_dir()]


@app.get('/api/export')
async def export(symbol: str = 'BTCUSDT', mode: str='live'):
    from fastapi.responses import Response
    s = get_session(symbol, mode)
    await s.recorder.flush()
    return Response(json.dumps(s.latest), media_type='application/json', headers={'Content-Disposition':f'attachment; filename="swarmtrade-{symbol}-{mode}.json"'})


@app.get('/api/darwin/state')
async def darwin_state(symbol: str='BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    result = s.darwin.state()
    result['error'] = s.darwin_error
    result['shared_portfolio'] = shared_portfolio.state()
    result['shared_portfolio']['comparison'] = comparison(shared_portfolio, fixed_portfolio)
    return result


@app.get('/api/darwin/evolution')
async def darwin_evolution(symbol: str='BTCUSDT', mode: str='live', limit: int=120):
    s = get_session(symbol, mode)
    return s.darwin.evolution_state(max(1, min(limit, 500)))


@app.post('/api/darwin/epoch')
async def darwin_epoch(symbol: str='BTCUSDT', mode: str='live', force: bool=True):
    s = get_session(symbol, mode)
    return await s.darwin.run_epoch_async(force=force)


@app.get('/api/darwin/memory')
async def darwin_memory(symbol: str='BTCUSDT', mode: str='live', limit: int=20):
    s = get_session(symbol, mode)
    return dict(lessons=s.darwin.store.recent_lessons(max(1,min(limit,100))), epochs=s.darwin.store.recent_epochs(20))


@app.get('/api/darwin/agent-runs')
async def agent_run_history(symbol: str = 'BTCUSDT', mode: str = 'live', before_id: int | None = None):
    rows = get_session(symbol, mode).darwin.store.recent_agent_runs(50, before_id)
    return {'runs': rows, 'next_before_id': rows[-1]['id'] if len(rows) == 50 else None}


@app.get('/api/darwin/research')
async def darwin_research(symbol: str='BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    result = s.darwin.research_state()
    result['paper_only'] = not hyperliquid_executor.status().get('ready', False)
    return result


@app.get('/api/darwin/strategy/{strategy_id}')
async def darwin_strategy(strategy_id: str, symbol: str='BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    detail = s.darwin.store.strategy_detail(strategy_id)
    if not detail:
        raise HTTPException(404, 'Unknown Darwin strategy')
    return detail


@app.get('/api/brains/state')
async def brains_state(symbol: str='BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    return {
        'policy': policy_state(),
        'brains': s.darwin.brains.states(),
        'usage_24h': s.darwin.store.agent_usage_summary(24),
        'engineer': s.darwin.engineer_state(),
    }


class EngineerTaskRequest(BaseModel):
    symbol: str = 'BTCUSDT'
    mode: str='live'
    objective: str | None = Field(default=None, max_length=1200)


@app.get('/api/engineer/state')
async def engineer_state(symbol: str='BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    return s.darwin.engineer_state()


@app.post('/api/engineer/task')
async def engineer_task(req: EngineerTaskRequest):
    s = get_session(req.symbol, req.mode)
    return s.darwin.prepare_engineer_task(req.objective)


@app.get('/api/openbot/state')
async def openbot_state():
    return openbot_bridge_state()


@app.get('/api/openbot/context/{agent_id}')
async def openbot_context(agent_id: str, request: Request, symbol: str='BTCUSDT', mode: str='live'):
    if agent_id not in OPENBOT_COWORKERS:
        raise HTTPException(404, 'Unknown OpenBot coworker')
    if not openbot_authorised(request.headers):
        raise HTTPException(401, 'Unauthorised OpenBot context request')
    s = get_session(symbol, mode)
    return s.darwin.openbot_context(agent_id)


@app.post('/ag-ui/{agent_id}')
async def openbot_ag_ui(agent_id: str, request: Request):
    if agent_id not in OPENBOT_COWORKERS:
        raise HTTPException(404, 'Unknown OpenBot coworker')
    if not openbot_available():
        raise HTTPException(503, 'OpenBot AG-UI extras are not installed; install backend/requirements-openbot.txt')
    if not openbot_authorised(request.headers):
        raise HTTPException(401, 'Unauthorised OpenBot agent request')
    return await OPENBOT_AGUI_ADAPTER.dispatch_request(request, agent=get_openbot_agent(agent_id))


@app.get('/api/agents/state')
async def agents_state(symbol: str='BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    dstate = s.darwin.state()
    return agent_runtime_state(
        darwin_state=dstate,
        execution_state=hyperliquid_executor.status(),
        market_state=s.latest,
        darwin_error=s.darwin_error,
        llm_states=s.darwin.brains.states(),
    )



@app.get('/api/factory/state')
async def factory_state_api(symbol: str='BTCUSDT', mode: str='live'):
    s = get_session(symbol, mode)
    dstate = s.darwin.state()
    agents = agent_runtime_state(
        darwin_state=dstate,
        execution_state=hyperliquid_executor.status(),
        market_state=s.latest,
        darwin_error=s.darwin_error,
        llm_states=s.darwin.brains.states(),
    )
    return factory_state(s.darwin, agents, hyperliquid_executor.status(), s.latest)


@app.get('/api/factory/events')
async def factory_events(symbol: str='BTCUSDT', mode: str='live', limit: int=120, after_id: int | None=None):
    s = get_session(symbol, mode)
    events = s.darwin.store.recent_factory_events(limit=max(1, min(limit, 500)), after_id=after_id)
    return {'events': decorate_events(events)}


@app.websocket('/ws/factory')
async def factory_stream(ws: WebSocket, symbol: str='BTCUSDT', mode: str='live'):
    origin = ws.headers.get('origin')
    forwarded_host = ws.headers.get('x-forwarded-host') or ws.headers.get('host')
    same_host = bool(origin and forwarded_host and origin.split('://')[-1].rstrip('/') == forwarded_host)
    if origin and origin not in ALLOWED_ORIGINS and not same_host:
        await ws.close(code=1008)
        return
    if symbol not in SYMBOLS or mode != 'live':
        await ws.close(code=1008)
        return
    await ws.accept()
    s = get_session(symbol, mode)
    last_id = 0
    recent = s.darwin.store.recent_factory_events(50)
    if recent:
        last_id = recent[-1]['id']
        await ws.send_json({'type': 'bootstrap', 'events': decorate_events(recent)})
    try:
        while True:
            events = s.darwin.store.recent_factory_events(100, after_id=last_id)
            if events:
                last_id = events[-1]['id']
                await ws.send_json({'type': 'events', 'events': decorate_events(events)})
            else:
                await ws.send_json({'type': 'heartbeat', 'ts': time.time()})
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        pass

@app.get('/api/execution/hyperliquid/status')
def hyperliquid_status():
    return hyperliquid_executor.status()


@app.get('/api/runtime')
def runtime_state():
    return {
        'version': '0.11.0',
        'data_dir': str(DATA),
        'autostart_symbol': os.getenv('DARWIN_AUTOSTART_SYMBOL', 'BTCUSDT'),
        'autostart_mode': 'live',
        'market_source': os.getenv('DARWIN_MARKET_SOURCE', 'hyperliquid'),
        'paper_only': not hyperliquid_executor.status().get('ready', False),
    }

# In Docker/Railway the Vite build is copied here and served by the same process.
FRONTEND_DIST = PROJECT_ROOT / 'frontend' / 'dist'
if FRONTEND_DIST.exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND_DIST / 'assets'), name='assets')

    @app.get('/')
    def frontend_index():
        return FileResponse(FRONTEND_DIST / 'index.html')

    @app.get('/{path:path}')
    def frontend_spa(path: str):
        candidate = (FRONTEND_DIST / path).resolve()
        if not candidate.is_relative_to(FRONTEND_DIST.resolve()) or path.startswith(('api/', 'ag-ui/')):
            raise HTTPException(404, 'Not found')
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / 'index.html')
