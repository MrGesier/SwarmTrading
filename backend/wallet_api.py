"""Public Hyperliquid account inspection. No signer or exchange client."""
import asyncio
import time
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field


class AccountRequest(BaseModel):
    address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    network: Literal["mainnet", "testnet"] = "mainnet"


async def read_account(address, network, transport=None):
    endpoints = {"mainnet": "https://api.hyperliquid.xyz/info",
                 "testnet": "https://api.hyperliquid-testnet.xyz/info"}
    async with httpx.AsyncClient(timeout=12, transport=transport) as client:
        async def query(kind):
            result = await client.post(endpoints[network], json={"type": kind, "user": address})
            result.raise_for_status()
            return result.json()
        perps, spot, orders = await asyncio.gather(query("clearinghouseState"), query("spotClearinghouseState"), query("openOrders"))
    if not isinstance(perps, dict) or not isinstance(spot, dict) or not isinstance(orders, list):
        raise ValueError("Unexpected account response")
    return {"address": address, "network": network, "observed_at": time.time(),
            "access": "PUBLIC_READ_ONLY", "signing_enabled": False,
            "perps": perps, "spot": spot, "open_orders": orders,
            "scope": "Default perpetual DEX and spot; not an aggregate of all HIP-3 DEXs or subaccounts."}


def create_wallet_router():
    router = APIRouter(prefix="/api/hyperliquid")

    @router.post("/account")
    async def account(body: AccountRequest, request: Request, response: Response):
        # Local product endpoint; no arbitrary URL, credential, signature or storage.
        if request.url.hostname not in {"localhost", "127.0.0.1", "[::1]", "::1", "testserver"}:
            raise HTTPException(403, "Local access only")
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.url.netloc:
            raise HTTPException(403, "Same-origin access required")
        response.headers["Cache-Control"] = "no-store"
        try:
            return await read_account(body.address, body.network)
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, "Hyperliquid indisponible ou réponse invalide. Réessayer plus tard.") from None

    return router
