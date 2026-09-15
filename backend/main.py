import asyncio
from contextlib import asynccontextmanager
from collections import deque
import json
import math
from pathlib import Path
import random
import time
import uuid

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from engine import Engine, OrderBook, GENOMES, HORIZONS, SequenceGap
from analysis import technical_analysis, cost_preview

DATA = Path(__file__).resolve().parents[1] / 'data'
DATA.mkdir(exist_ok=True)
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']


class Recorder:
    def __init__(self, symbol, mode):
        self.directory = DATA / f'{mode}-{symbol}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}'
        self.directory.mkdir()
        self.rows = []
        self.part = 0

    def add(self, event, ts):
        self.rows.append(dict(received=ts, payload=json.dumps(event, separators=(',', ':'))))

    async def flush(self):
        if not self.rows:
            return
        rows, self.rows = self.rows, []
        self.part += 1
        path = self.directory / f'{self.part:06}.parquet'
        await asyncio.to_thread(pq.write_table, pa.Table.from_pylist(rows), path, compression='zstd')


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
        self.rng = random.Random(42)
        self.price = {'BTCUSDT': 64280, 'ETHUSDT': 2680, 'SOLUSDT': 148}[symbol]
        self.n = 0
        self.last_quote = None

    def ingest(self, event, ts, record=True):
        if record:
            self.recorder.add(event, ts)
        if event['type'] == 'snapshot':
            self.book.snapshot(event['data'])
            self.engine.memory.observe(self.book,ts)
        elif event['type'] == 'depth':
            if self.book.update(event['data']):
                self.last_depth = ts
                self.engine.memory.observe(self.book,ts)
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
                      recording=self.recorder.directory.name)
        state = self.engine.calculate(self.book, ts, self.mode, self.symbol, health)
        if state:
            self.latest = state
            self.states.append(state)

    def simulate(self, ts, derive=True):
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
        if derive:self.derive(ts)

    async def run(self):
        try:
            if self.mode == 'simulation':
                now = time.time()
                for i in range(400):
                    self.simulate(now - (400-i)*.5, derive=i>=350)
                while True:
                    self.simulate(time.time())
                    if len(self.recorder.rows) >= 400:
                        await self.recorder.flush()
                    await asyncio.sleep(.5)
            else:
                await self.live()
        finally:
            await self.recorder.flush()

    async def live(self):
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


sessions = {}


def get_session(symbol='BTCUSDT', mode='simulation'):
    if symbol not in SYMBOLS or mode not in ['simulation', 'live']:
        raise HTTPException(400, 'Unsupported symbol or mode')
    key = (symbol, mode)
    if key not in sessions:
        s = sessions[key] = Session(symbol, mode)
        s.task = asyncio.create_task(s.run())
    return sessions[key]


@asynccontextmanager
async def lifespan(app):
    get_session()
    yield
    for s in sessions.values():
        s.task.cancel()
    await asyncio.gather(*(s.task for s in sessions.values()), return_exceptions=True)


app = FastAPI(title='SwarmTrade V0.3', lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=3)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000'], allow_methods=['GET','POST'], allow_headers=['Content-Type'])


@app.get('/api/health')
def health():
    return dict(status='ok', execution='read-only', version='0.3.0', project_root=str(Path(__file__).resolve().parents[1]))


@app.get('/api/state')
async def state(symbol: str = 'BTCUSDT', mode: str = 'simulation', prediction_horizon: int=5, display_interval: int=5):
    s = get_session(symbol, mode)
    if prediction_horizon not in HORIZONS or display_interval not in [1,5,30,60,180]:raise HTTPException(400,'Unsupported horizon or display interval')
    result=fresh_state(s)
    if 'horizons' in result:
        candles=[]
        for candle in result['candles']:
            bucket=int(candle['time']//display_interval)*display_interval
            if candles and candles[-1]['time']==bucket:
                last=candles[-1]
                last.update(high=max(last['high'],candle['high']),low=min(last['low'],candle['low']),close=candle['close'],volume=last['volume']+candle['volume'])
            else:candles.append({**candle,'time':bucket})
        result={**result,'prediction_horizon':prediction_horizon,'display_interval':display_interval,
                'candles':candles,
                'selected_intent':result['horizons'][str(prediction_horizon)]['intent']}
    return result


def fresh_state(s):
    if not s.latest:return dict(status=s.health,message=s.error)
    if not s.book.valid or time.time()-s.last_depth>3:
        return {**s.latest,'health':{**s.latest['health'],'status':'STALE','message':s.error},
            'intent':{**s.latest['intent'],'state':'RISK_OFF'},
            'horizons':{h:{**v,'intent':{**v['intent'],'state':'RISK_OFF','entry':'WAIT','direction':'NO_TRADE'}} for h,v in s.latest['horizons'].items()}}
    return s.latest


@app.websocket('/ws')
async def stream(ws: WebSocket, symbol: str = 'BTCUSDT', mode: str = 'simulation'):
    if ws.headers.get('origin') not in ['http://localhost:3000', 'http://127.0.0.1:3000']:
        await ws.close(code=1008)
        return
    await ws.accept()
    if symbol not in SYMBOLS or mode not in ['simulation', 'live']:
        await ws.close(code=1008)
        return
    s = get_session(symbol, mode)
    try:
        while True:
            await ws.send_json(fresh_state(s))
            await asyncio.sleep(.5)
    except (WebSocketDisconnect, RuntimeError):
        pass


class Counterfactual(BaseModel):
    symbol: str = 'BTCUSDT'
    mode: str = 'simulation'
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
async def analysis(symbol: str='BTCUSDT',mode: str='simulation',horizon: int=5):
    s=get_session(symbol,mode)
    if horizon not in HORIZONS:
        raise HTTPException(400,'Unsupported horizon')
    if not s.latest:
        raise HTTPException(409,'Waiting for market state')
    return technical_analysis(s.engine,s.latest,horizon)


class CostRequest(BaseModel):
    symbol: str='BTCUSDT'
    mode: str='simulation'
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
async def replay(symbol: str = 'BTCUSDT', mode: str = 'simulation'):
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
async def export(symbol: str = 'BTCUSDT', mode: str = 'simulation'):
    from fastapi.responses import Response
    s = get_session(symbol, mode)
    await s.recorder.flush()
    return Response(json.dumps(s.latest), media_type='application/json', headers={'Content-Disposition':f'attachment; filename="swarmtrade-{symbol}-{mode}.json"'})


@app.post('/api/flush')
async def flush_recordings():
    for s in sessions.values():await s.recorder.flush()
    return dict(flushed=len(sessions))
