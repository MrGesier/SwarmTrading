"""Public-data wiring for the single shared paper portfolio (no credentials)."""
import asyncio
import os
import time
import xml.etree.ElementTree as ET
import httpx
from .hyperliquid import HyperliquidPublicStream

class PortfolioFeeds:
    def __init__(self, portfolio, control=None):
        self.portfolio=portfolio
        self.portfolios=[portfolio]+([control] if control else [])
        self.decimals={}
        self.spot_key=None
        self.tasks=[]

    async def run(self):
        while True:
            try:
                if os.getenv("HYPERLIQUID_DATA_NETWORK", "mainnet").lower() != "mainnet":
                    raise ValueError("Shared portfolio currently requires mainnet public data")
                async with httpx.AsyncClient(timeout=20) as client:
                    if not self.portfolio.fx:
                        r=await client.get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")
                        r.raise_for_status();root=ET.fromstring(r.text)
                        rate=next(float(n.get("rate")) for n in root.iter() if n.get("currency")=="USD")
                        date=next(n.get("time") for n in root.iter() if n.get("time"))
                        for p in self.portfolios: p.set_fx(rate,date)
                    async def info(kind):
                        r=await client.post("https://api.hyperliquid.xyz/info",json={"type":kind});r.raise_for_status();return r.json()
                    meta,spot=await asyncio.gather(info("meta"),info("spotMeta"))
                    self.decimals={u["name"]:int(u["szDecimals"]) for u in meta["universe"]}
                    tokens={u["index"]:u for u in spot["tokens"]}
                    pair=next(u for u in spot["universe"] if [tokens[i]["name"] for i in u["tokens"]]==["HYPE","USDC"])
                    coin=pair["name"]; self.spot_key="spot:"+coin
                    spot_dec=int(tokens[pair["tokens"][0]]["szDecimals"])
                    self.portfolio.error=""
                self.tasks=[asyncio.create_task(self.stream("HYPE","perp:HYPE",self.decimals["HYPE"])),
                            asyncio.create_task(self.stream(coin,self.spot_key,spot_dec)),asyncio.create_task(self.heartbeat())]
                await asyncio.gather(*self.tasks)
            except asyncio.CancelledError:
                for t in self.tasks: t.cancel()
                await asyncio.gather(*self.tasks,return_exceptions=True)
                for p in self.portfolios: p.save()
                raise
            except Exception as exc:
                self.portfolio.error=f"Public portfolio feeds: {type(exc).__name__}"
                for t in self.tasks:t.cancel()
                await asyncio.gather(*self.tasks,return_exceptions=True)
                await asyncio.sleep(15)

    async def stream(self,coin,key,decimals):
        async for received,event in HyperliquidPublicStream(coin).events():
            if event["type"]=="snapshot":
                d=event["data"]
                exchange_ts=float(d["lastUpdateId"])/1000
                if exchange_ts > received+2:
                    continue  # clock disagreement outside the bounded transport tolerance
                for p in self.portfolios: p.book(key,d["bids"],d["asks"],min(exchange_ts,received),decimals)
            elif event["type"]=="context" and event["data"].get("funding") is not None:
                for p in self.portfolios: p.funding[key]=(float(event["data"]["funding"]),received)

    async def heartbeat(self):
        while True:
            for p in self.portfolios:
                p.pair(self.spot_key,time.time())
                p.record(time.time())
            await asyncio.sleep(1)

    def observe(self,state,strategies):
        coin=state["symbol"].replace("USDT","")
        if coin in self.decimals and not self.portfolio.error:
            for p in self.portfolios: p.observe(state,strategies,self.decimals[coin])
