import asyncio
import copy
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from execution.hyperliquid import HyperliquidExecutor, HyperliquidConfig
from execution.validation import TestnetValidation, ValidationRequest, create_validation_router

ADDRESS='0x'+'1'*40
AGENT='0x'+'2'*40


@pytest.fixture
def service(tmp_path,monkeypatch):
    cfg=HyperliquidConfig(False,'testnet',ADDRESS,'',100,'')
    executor=HyperliquidExecutor(cfg)
    monkeypatch.setattr(executor,'status',lambda:{'sdk_installed':True})
    svc=TestnetValidation(executor,tmp_path/'validation.sqlite')
    monkeypatch.setattr(svc,'identity',lambda:AGENT)
    monkeypatch.setenv('HYPERLIQUID_TESTNET_VALIDATION','true')
    return svc


def snapshot():
    return dict(meta=[{'universe':[{'name':'BTC','szDecimals':5}]},[{'markPx':'50000','funding':'0.0001'}]],
                book={'time':time.time()*1000,'levels':[[{'px':'49999'}],[{'px':'50001'}]]},
                account={'marginSummary':{'accountValue':'1000'},'assetPositions':[]},orders=[],
                fees={'userAddRate':'0.00015','userCrossRate':'0.00045'},agents=[{'address':AGENT,'validUntil':(time.time()+3600)*1000}])


def test_readiness_rounds_down_and_keeps_trading_disabled(service):
    result=service.assess(ValidationRequest(),snapshot())
    assert result['ready'] and not result['mainnet_enabled']
    assert 10<=result['plan']['notional_usd']<=12
    assert result['plan']['limit_price']<49999
    assert result['costs']['funding_hourly_bps']==1
    assert service.executor.config.enabled is False


@pytest.mark.parametrize('change,failed',[
    (lambda d:d['book'].update(time=(time.time()-30)*1000),'fresh_book'),
    (lambda d:d.update(agents=[]),'api_wallet_approved'),
    (lambda d:d['account']['marginSummary'].update(accountValue='0'),'funded_test_account'),
    (lambda d:d.update(fees={}),'fees_available'),
    (lambda d:d.update(orders=[{'sz':'1','limitPx':'50000'}]),'exposure_cap'),
    (lambda d:d['agents'][0].update(validUntil=0),'api_wallet_approved'),
])
def test_preflight_fail_closed(service,change,failed):
    data=snapshot();change(data)
    result=service.assess(ValidationRequest(),data)
    assert not result['ready'] and result['checks'][failed] is False


def test_mainnet_and_master_key_are_blocked(service,monkeypatch):
    service.executor.config=replace(service.executor.config,network='mainnet',enabled=True,mainnet_ack='I_UNDERSTAND_LIVE_TRADING')
    assert not service.assess(ValidationRequest(),snapshot())['ready']
    with pytest.raises(ValueError):service.clients()
    service.executor.config=replace(service.executor.config,network='testnet')
    monkeypatch.setattr(service,'identity',lambda:ADDRESS)
    assert not service.assess(ValidationRequest(),snapshot())['checks']['dedicated_api_wallet']


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,0,101])
def test_bad_notional_is_rejected(value):
    with pytest.raises(ValueError):ValidationRequest(notional_usd=value)


def run_with_fake_exchange(service,monkeypatch,mode):
    calls=[]
    async def preflight(request):return service.assess(request,snapshot())
    monkeypatch.setattr(service,'preflight',preflight)
    def order(*args,**kwargs):
        calls.append(('order',kwargs['cloid'].to_raw()))
        assert service.history()[0]['status']=='RUNNING'
        if mode=='timeout':raise TimeoutError('do not expose credentials')
        return {'response':{'data':{'statuses':[{'resting':{'oid':123}}]}}}
    def cancel(coin,cloid):calls.append(('cancel',cloid.to_raw()))
    info=SimpleNamespace(query_order_by_cloid=lambda *a: {'status':'unknownOid'} if mode=='timeout' else {'order':{'status':'canceled'}},
                         open_orders=lambda *a:[],user_state=lambda *a:{'assetPositions':[{'position':{'szi':'0.001'}}] if mode=='filled' else []})
    exchange=SimpleNamespace(order=order,cancel_by_cloid=cancel)
    monkeypatch.setattr(service,'clients',lambda:(info,exchange))
    return asyncio.run(service.run(ValidationRequest())),calls


def test_order_cancel_reconcile_and_durable_journal(service,monkeypatch):
    result,calls=run_with_fake_exchange(service,monkeypatch,'success')
    assert result['status']=='PASSED'
    assert calls==[('order','0x'+result['id']),('cancel','0x'+result['id'])]
    assert TestnetValidation(service.executor,service.path).history()[0]['status']=='PASSED'


@pytest.mark.parametrize('mode',['timeout','filled'])
def test_ambiguous_or_filled_order_blocks_retry(service,monkeypatch,mode):
    result,calls=run_with_fake_exchange(service,monkeypatch,mode)
    assert result['status']=='RECONCILIATION_REQUIRED'
    assert 'credentials' not in str(result)
    again=asyncio.run(service.run(ValidationRequest()))
    assert again['status']=='BLOCKED' and len(calls)==2
    with pytest.raises(ValueError):service.reserve(result['plan'])


def test_api_requires_local_origin_and_explicit_ack(service,monkeypatch):
    app=FastAPI();app.include_router(create_validation_router(service))
    with TestClient(app) as client:
        assert client.post('/api/hyperliquid/validation/run',json={}).status_code==422
        assert client.post('/api/hyperliquid/validation/preflight',json={},headers={'Origin':'https://evil.test'}).status_code==403
        assert client.get('/api/hyperliquid/validation/history').json()['mainnet_enabled'] is False


def test_atomic_reservation_and_expired_snapshot_do_not_send(service,monkeypatch):
    preflight=service.assess(ValidationRequest(),snapshot())
    run=service.reserve(preflight['plan']);run['preflight']=copy.deepcopy(preflight);run['preflight']['observed_at']-=20
    with pytest.raises(ValueError):service.reserve(preflight['plan'])
    monkeypatch.setattr(service,'clients',lambda:(None,None))
    assert service.execute(run)['status']=='BLOCKED'


def test_config_defaults_leave_validation_locked(service,monkeypatch):
    monkeypatch.delenv('HYPERLIQUID_TESTNET_VALIDATION',raising=False)
    assert not service.assess(ValidationRequest(),snapshot())['ready']
    with pytest.raises(ValueError):service.clients()


def test_unread_account_is_not_treated_as_zero_exposure(service):
    data=snapshot();data['account']={}
    result=service.assess(ValidationRequest(),data)
    assert not result['ready'] and not result['checks']['clean_test_account']
    assert not result['checks']['exposure_cap']
    assert result['exposure']['projected_usd'] is None
