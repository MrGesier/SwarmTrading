"""Normalized public Hyperliquid market-data stream.

The adapter emits exchange-independent events understood by Session/Engine:
- snapshot: full top-of-book depth snapshot
- trade: normalized price/size/aggressor side
- context: funding, open interest, mark/oracle/premium metadata

No wallet or private key is required for this module.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, AsyncIterator

import websockets


SYMBOL_MAP = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}


def websocket_url() -> str:
    network = os.getenv("HYPERLIQUID_DATA_NETWORK", "mainnet").lower()
    if network == "testnet":
        return "wss://api.hyperliquid-testnet.xyz/ws"
    return "wss://api.hyperliquid.xyz/ws"


class HyperliquidPublicStream:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.coin = SYMBOL_MAP.get(symbol, symbol.replace("USDT", ""))
        self.url = websocket_url()

    async def events(self) -> AsyncIterator[tuple[float, dict[str, Any]]]:
        """Reconnect forever and yield normalized events.

        Hyperliquid l2Book is a snapshot feed, so sequence-bridging logic used for
        Binance incremental books is intentionally not used here.
        """
        delay = 1.0
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20, max_queue=4096) as ws:
                    for subscription in (
                        {"type": "l2Book", "coin": self.coin},
                        {"type": "trades", "coin": self.coin},
                        {"type": "activeAssetCtx", "coin": self.coin},
                    ):
                        await ws.send(json.dumps({"method": "subscribe", "subscription": subscription}, separators=(",", ":")))
                    delay = 1.0
                    async for raw in ws:
                        msg = json.loads(raw)
                        channel = msg.get("channel")
                        data = msg.get("data")
                        ts = time.time()
                        if channel == "l2Book" and isinstance(data, dict):
                            levels = data.get("levels") or [[], []]
                            if len(levels) != 2:
                                continue
                            bids = [[x.get("px"), x.get("sz")] for x in levels[0] if x.get("px") and x.get("sz")]
                            asks = [[x.get("px"), x.get("sz")] for x in levels[1] if x.get("px") and x.get("sz")]
                            if bids and asks:
                                yield ts, {
                                    "type": "snapshot",
                                    "source": "hyperliquid",
                                    "data": {
                                        "lastUpdateId": int(data.get("time") or ts * 1000),
                                        "bids": bids,
                                        "asks": asks,
                                    },
                                }
                        elif channel == "trades" and isinstance(data, list):
                            for trade in data:
                                # Hyperliquid SDK uses A=Ask and B=Bid. Treat Ask-side
                                # public trades as sell pressure for the normalized engine.
                                yield ts, {
                                    "type": "trade",
                                    "source": "hyperliquid",
                                    "data": {
                                        "p": trade.get("px"),
                                        "q": trade.get("sz"),
                                        "m": trade.get("side") == "A",
                                        "trade_time": trade.get("time"),
                                        "tid": trade.get("tid"),
                                    },
                                }
                        elif channel == "activeAssetCtx" and isinstance(data, dict):
                            ctx = data.get("ctx") or {}
                            yield ts, {
                                "type": "context",
                                "source": "hyperliquid",
                                "data": {
                                    "coin": data.get("coin", self.coin),
                                    "funding": _num(ctx.get("funding")),
                                    "open_interest": _num(ctx.get("openInterest")),
                                    "premium": _num(ctx.get("premium")),
                                    "oracle_price": _num(ctx.get("oraclePx")),
                                    "mark_price": _num(ctx.get("markPx")),
                                    "mid_price": _num(ctx.get("midPx")),
                                    "day_notional_volume": _num(ctx.get("dayNtlVlm")),
                                },
                            }
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, 30.0)


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
