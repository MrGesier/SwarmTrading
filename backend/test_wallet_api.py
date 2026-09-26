import asyncio
import json
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import wallet_api

ADDRESS = "0x" + "1" * 40

@pytest.mark.parametrize("network,host",[("mainnet","api.hyperliquid.xyz"),("testnet","api.hyperliquid-testnet.xyz")])
def test_public_account_uses_only_info_queries(network, host):
    requests=[]
    def respond(request):
        body=json.loads(request.content); requests.append(body)
        assert request.url.host==host and request.url.path=="/info"
        assert set(body)=={"type","user"} and body["user"]==ADDRESS
        assert "authorization" not in request.headers
        values={"clearinghouseState":{"marginSummary":{"accountValue":"42"},"assetPositions":[]},"spotClearinghouseState":{"balances":[]},"openOrders":[]}
        return httpx.Response(200,json=values[body["type"]])
    data=asyncio.run(wallet_api.read_account(ADDRESS,network,httpx.MockTransport(respond)))
    assert len(requests)==3 and data["signing_enabled"] is False
    assert data["perps"]["marginSummary"]["accountValue"]=="42"


def test_account_route_validation_origin_and_upstream_failure(monkeypatch):
    calls=[]
    async def fake(address,network):
        calls.append((address,network))
        raise httpx.ConnectError("private upstream detail")
    monkeypatch.setattr(wallet_api,"read_account",fake)
    app=FastAPI();app.include_router(wallet_api.create_wallet_router())
    with TestClient(app) as client:
        for body in [{"address":"not-an-address"},{"address":ADDRESS,"network":"https://evil.test"}]:
            assert client.post("/api/hyperliquid/account",json=body).status_code==422
        assert client.post("/api/hyperliquid/account",json={"address":ADDRESS},headers={"Origin":"https://evil.test"}).status_code==403
        assert calls==[]
        response=client.post("/api/hyperliquid/account",json={"address":ADDRESS})
        assert response.status_code==502 and "private upstream" not in response.text
        assert calls==[(ADDRESS,"mainnet")]
