"""Explicit testnet-only order lifecycle validation; never used by agents/paper loop."""
import asyncio
import json
import math
import os
import sqlite3
import time
import threading
import uuid
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal
from urllib.parse import urlparse

URL = 'https://api.hyperliquid-testnet.xyz'


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Non-finite value')
    return value


class ValidationRequest(BaseModel):
    coin: Literal['BTC', 'ETH', 'SOL'] = 'BTC'
    notional_usd: float = Field(default=12, ge=11, le=100, allow_inf_nan=False)


class RunRequest(ValidationRequest):
    acknowledgement: Literal['TESTNET_ORDER_AND_CANCEL']


class TestnetValidation:
    __test__ = False

    def __init__(self, executor, path):
        self.executor = executor
        self.operation = threading.Lock()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, ts REAL, status TEXT, payload TEXT)')

    def db(self):
        return sqlite3.connect(self.path, timeout=10)

    def history(self):
        with self.db() as db:
            return [{**json.loads(p), 'id': i, 'ts': t, 'status': s} for i,t,s,p in db.execute('SELECT * FROM runs ORDER BY ts DESC LIMIT 20')]

    def save(self, run):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?)', (run['id'],run['ts'],run['status'],json.dumps(run)))

    def identity(self):
        cfg = self.executor.config
        agent = None
        try:
            from eth_account import Account
            if cfg.api_private_key:
                agent = Account.from_key(cfg.api_private_key).address
        except Exception:
            pass  # Never include key/parser exception in logs or response.
        return agent

    async def snapshot(self, coin, transport=None):
        address = self.executor.config.account_address
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            async def query(kind, **args):
                r = await client.post(URL+'/info', json={'type':kind, **args})
                r.raise_for_status()
                return r.json()
            meta, book = await asyncio.gather(query('metaAndAssetCtxs'),query('l2Book',coin=coin))
            account, orders, fees, agents = ({},[],{},[])
            if address:
                account, orders, fees, agents = await asyncio.gather(*[query(k,user=address) for k in ('clearinghouseState','openOrders','userFees','extraAgents')])
        return dict(meta=meta,book=book,account=account,orders=orders,fees=fees,agents=agents)

    def assess(self, request, data):
        cfg = self.executor.config
        now = time.time()
        agent = self.identity()
        universe, contexts = data['meta'][0]['universe'], data['meta'][1]
        index = next(i for i,r in enumerate(universe) if r['name']==request.coin)
        ctx = contexts[index]
        mark, funding = number(ctx['markPx']), number(ctx['funding'])
        decimals = int(universe[index]['szDecimals'])
        bid = number(data['book']['levels'][0][0]['px'])
        ask = number(data['book']['levels'][1][0]['px'])
        age = now - number(data['book']['time'])/1000
        # Five significant figures, then exchange's 6-szDecimals price rule.
        px = Decimal(format(bid*0.99, '.5g')).quantize(Decimal(10)**-max(0,6-decimals), rounding=ROUND_DOWN)
        size = (Decimal(str(request.notional_usd))/px).quantize(Decimal(10)**-decimals, rounding=ROUND_DOWN)
        value = float(size*px)
        positions = data['account'].get('assetPositions', [])
        gross = sum(abs(number(p['position']['positionValue'])) for p in positions)
        pending = sum(abs(number(o['sz'])*number(o['limitPx'])) for o in data['orders'])
        balance = number(data['account'].get('marginSummary',{}).get('accountValue',0))
        account_read = bool(cfg.account_address and 'marginSummary' in data['account'] and 'assetPositions' in data['account'])
        maker = number(data['fees']['userAddRate']) if 'userAddRate' in data['fees'] else None
        taker = number(data['fees']['userCrossRate']) if 'userCrossRate' in data['fees'] else None
        approved = bool(agent and any(a.get('address','').lower()==agent.lower() and number(a.get('validUntil',0))>now*1000 for a in data['agents']))
        unresolved = any(r['status'] in {'RUNNING','RECONCILIATION_REQUIRED'} for r in self.history())
        checks = {
            'testnet_network': cfg.network=='testnet',
            'validation_enabled': os.getenv('HYPERLIQUID_TESTNET_VALIDATION','false').lower()=='true',
            'sdk_installed': self.executor.status()['sdk_installed'],
            'account_configured': bool(cfg.account_address),
            'dedicated_api_wallet': bool(agent and agent.lower()!=cfg.account_address.lower()),
            'api_wallet_approved': approved,
            'funded_test_account': balance>=request.notional_usd,
            'fresh_book': 0<=age<=10 and 0<bid<=ask and mark>0,
            'fees_available': maker is not None and taker is not None,
            'finite_funding': math.isfinite(funding),
            'exposure_cap': account_read and 0<value<=request.notional_usd<=cfg.max_notional_usd and gross+pending+value<=cfg.max_notional_usd,
            'minimum_order': value>=10 and size>0,
            'clean_test_account': account_read and gross==0 and not data['orders'],
            'previous_run_resolved': not unresolved,
        }
        return dict(network='testnet',observed_at=now,account=cfg.account_address,agent_address=agent,
                    checks=checks,ready=all(checks.values()),mainnet_enabled=False,
                    plan=dict(coin=request.coin,side='BUY',size=float(size),limit_price=float(px),notional_usd=value,tif='Alo'),
                    costs=dict(maker_bps=None if maker is None else maker*10000,taker_bps=None if taker is None else taker*10000,
                               funding_hourly_bps=funding*10000,estimated_maker_usd=None if maker is None else value*maker),
                    exposure=dict(positions_usd=gross if account_read else None,orders_usd=pending if account_read else None,projected_usd=gross+pending+value if account_read else None,cap_usd=cfg.max_notional_usd),
                    account_value_usd=balance,book_age_seconds=age)

    async def preflight(self, request):
        return self.assess(request, await self.snapshot(request.coin))

    def clients(self):
        cfg=self.executor.config
        if cfg.network!='testnet' or os.getenv('HYPERLIQUID_TESTNET_VALIDATION','false').lower()!='true':
            raise ValueError('Testnet validation locked')
        from eth_account import Account
        from hyperliquid.info import Info
        from hyperliquid.exchange import Exchange
        return (Info(URL,skip_ws=True,timeout=10),
                Exchange(Account.from_key(cfg.api_private_key),URL,account_address=cfg.account_address,timeout=10))

    def reserve(self, plan):
        run=dict(id=uuid.uuid4().hex,ts=time.time(),status='RUNNING',network='testnet',account=self.executor.config.account_address,plan=plan,steps=[])
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM runs WHERE status IN ('RUNNING','RECONCILIATION_REQUIRED')").fetchone():
                raise ValueError('Unresolved previous validation')
            db.execute('INSERT INTO runs VALUES (?,?,?,?)',(run['id'],run['ts'],run['status'],json.dumps(run)))
        return run

    async def run(self, request):
        preflight=await self.preflight(request)
        if not preflight['ready']:
            return dict(status='BLOCKED',preflight=preflight)
        run=self.reserve(preflight['plan'])
        run['preflight']=preflight
        self.save(run)
        return await asyncio.to_thread(self.execute,run)

    def execute(self,run):
        with self.operation:
            return self._execute(run)

    def _execute(self,run):
        from hyperliquid.utils.types import Cloid
        cloid=Cloid.from_str('0x'+run['id'])
        plan=run['plan']
        try:
            info,exchange=self.clients()
            if time.time()-run['preflight']['observed_at']>10:
                run['status']='BLOCKED';run['steps'].append('Snapshot expired; no order sent');self.save(run);return run
            # Persist the identity BEFORE submission; never blindly retry an ambiguous request.
            run['steps'].append('Submission started');self.save(run)
            result=exchange.order(plan['coin'],True,plan['size'],plan['limit_price'],{'limit':{'tif':'Alo'}},cloid=cloid)
            statuses=result.get('response',{}).get('data',{}).get('statuses',[])
            run['accepted']=bool(statuses and 'resting' in statuses[0])
            run['steps'].append('Exchange response received')
        except Exception:
            run['steps'].append('Submission unconfirmed; reconciliation required')
        self.save(run)
        return self._reconcile(run)

    def reconcile(self,run):
        if not self.operation.acquire(blocking=False):
            return run
        try:
            return self._reconcile(run)
        finally:
            self.operation.release()

    def _reconcile(self,run):
        from hyperliquid.utils.types import Cloid
        try:
            info,exchange=self.clients()
            if run['account'].lower()!=self.executor.config.account_address.lower():
                raise ValueError('Account changed')
            cloid=Cloid.from_str('0x'+run['id'])
            # Only cancel this validation's client order id, never unrelated orders.
            exchange.cancel_by_cloid(run['plan']['coin'],cloid)
            remote=info.query_order_by_cloid(run['account'],cloid)
            terminal=remote.get('order',{}).get('status')
            orders=info.open_orders(run['account'])
            positions=info.user_state(run['account']).get('assetPositions',[])
            flat=all(number(p['position']['szi'])==0 for p in positions)
            absent=not any(o.get('cloid')==cloid.to_raw() for o in orders) and not orders
            run.update(remote_status=terminal or remote.get('status'),positions_flat=flat,open_orders=len(orders))
            passed=run.get('accepted') and terminal=='canceled' and flat and absent
            rejected=terminal in {'rejected','postOnlyCanceled'} and flat and absent
            run['status']='PASSED' if passed else 'FAILED' if rejected else 'RECONCILIATION_REQUIRED'
            run['steps'].append('Order and account reconciled')
        except Exception:
            run['status']='RECONCILIATION_REQUIRED'
            run['steps'].append('Reconciliation unavailable; inspect official testnet before retry')
        self.save(run)
        return run


def create_validation_router(service):
    router=APIRouter(prefix='/api/hyperliquid/validation')

    def local(request):
        if request.url.hostname not in {'localhost','127.0.0.1','::1','testserver'} or request.client.host not in {'127.0.0.1','::1','testclient'}:
            raise HTTPException(403,'Local access only')
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc!=request.url.netloc:
            raise HTTPException(403,'Same-origin required')

    @router.get('/history')
    def history(request:Request):
        local(request)
        return {'runs':service.history(),'mainnet_enabled':False}

    @router.post('/preflight')
    async def preflight(body:ValidationRequest,request:Request):
        local(request)
        try:
            return await service.preflight(body)
        except Exception:
            raise HTTPException(502,'Testnet unavailable or incomplete data; no order sent') from None

    @router.post('/run')
    async def run(body:RunRequest,request:Request):
        local(request)
        try:
            return await service.run(body)
        except Exception:
            raise HTTPException(409,'Validation unavailable; inspect history before retry') from None

    @router.post('/{run_id}/reconcile')
    async def reconcile(run_id:str,request:Request):
        local(request)
        run=next((r for r in service.history() if r['id']==run_id),None)
        if not run:
            raise HTTPException(404,'Unknown validation')
        if run['status'] not in {'RUNNING','RECONCILIATION_REQUIRED'}:
            return run
        if run['status']=='RUNNING' and time.time()-run['ts']<120:
            raise HTTPException(409,'Validation still running; wait before reconciling')
        return await asyncio.to_thread(service.reconcile,run)

    return router
