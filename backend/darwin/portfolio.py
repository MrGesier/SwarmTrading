"""One persistent, shared EUR paper ledger. No exchange order API is used.

Research accounts remain independent controls; only allocations in this ledger
consume the common capital. USDC is modelled at USD parity; FX is frozen at the
initial dated ECB reference so trading PnL is not confused with FX changes.
"""
from __future__ import annotations
import json
import math
import time
from pathlib import Path
from .paper import _walk
from .signals import raw_signal_for_genome

class SharedPortfolio:
    VERSION = 1
    LEVERAGE = 3.0
    MAX_SLEEVES = 19

    def __init__(self, path: Path):
        self.path = path
        self.error = ""
        self.books = {}
        self.funding = {}
        self.last_sequences = {}
        self.data = dict(version=1, initial_eur=1000.0, cash_eur=1000.0,
                         fx=None, positions=[], closed=[], fees_eur=0.0,
                         funding_eur=0.0, next_id=1, history=[], cooldown={},
                         funding_unobserved_seconds=0.0, created_at=time.time())
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
            if self.data.get("version") != self.VERSION:
                raise ValueError("Unsupported shared portfolio version; never reset capital silently")
        self.reason = "En attente de carnets frais et du change BCE"
        self.last_history = 0

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, allow_nan=False), encoding="utf-8")
        tmp.replace(self.path)

    def set_fx(self, rate, date):
        if self.data["fx"] is None:
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError("Invalid ECB FX")
            self.data["fx"] = {"usd_per_eur": rate, "date": date, "source": "ECB", "policy": "fixed_initial_reference"}
            self.save()

    @property
    def fx(self):
        return (self.data["fx"] or {}).get("usd_per_eur", 0)

    def book(self, key, bids, asks, ts, sz_decimals=6):
        bids = [[float(p), float(q)] for p,q in bids if float(p)>0 and float(q)>0]
        asks = [[float(p), float(q)] for p,q in asks if float(p)>0 and float(q)>0]
        if not bids or not asks or bids[0][0] >= asks[0][0]:
            return
        if not all(math.isfinite(x) for row in bids+asks for x in row):
            return
        self.books[key] = dict(bids=bids, asks=asks, ts=ts, mid=(bids[0][0]+asks[0][0])/2, decimals=sz_decimals)
        for p in self.data["positions"]:
            for leg in p["legs"]:
                if leg["instrument"] == key:
                    leg["mark"] = self.books[key]["mid"]
                    leg["marked_at"] = ts

    def fresh(self, key, now):
        return key in self.books and 0 <= now-self.books[key]["ts"] <= 3

    def leg_pnl(self, leg):
        return leg["qty"] * (leg["mark"]-leg["entry"]) / self.fx

    def totals(self):
        spot = unrealized = gross = margin = delta = 0.0
        for p in self.data["positions"]:
            for l in p["legs"]:
                value = l["qty"] * l["mark"] / self.fx
                gross += abs(value)
                delta += value
                unrealized += self.leg_pnl(l)
                if l["kind"] == "spot": spot += value
                else: margin += abs(value)/self.LEVERAGE
        equity = self.data["cash_eur"] + spot + sum(self.leg_pnl(l) for p in self.data["positions"] for l in p["legs"] if l["kind"]=="perp")
        available = self.data["cash_eur"] + sum(self.leg_pnl(l) for p in self.data["positions"] for l in p["legs"] if l["kind"]=="perp") - margin
        return dict(equity_eur=equity, cash_eur=self.data["cash_eur"], available_eur=available,
                    margin_eur=margin, gross_exposure_eur=gross, net_exposure_eur=delta,
                    unrealized_eur=unrealized, leverage=gross/max(equity,1e-9))

    def open(self, strategy_id, legs, now, policy=None, kind="directional"):
        if not self.fx or len(self.data["positions"]) >= self.MAX_SLEEVES:
            return False
        if kind=="directional" and sum(p["kind"]=="directional" for p in self.data["positions"])>=18: return False
        if any(p["strategy_id"]==strategy_id for p in self.data["positions"]): return False
        if now-self.data["cooldown"].get(strategy_id,0) < 60: return False
        if any(not self.fresh(l["instrument"],now) for l in legs): return False
        fills=[]
        for l in legs:
            b=self.books[l["instrument"]]
            qty=abs(l["qty"])
            rounded=math.floor(qty*10**b["decimals"])/10**b["decimals"]
            if abs(rounded-qty)>1e-9 or qty<=0: return False
            filled,px=_walk(b["asks"] if l["qty"]>0 else b["bids"], qty)
            if filled+1e-10 < qty or px*qty < 10: return False
            fee=qty*px*(7 if l["kind"]=="spot" else 4.5)/10000/self.fx
            fills.append({**l,"entry":px,"mark":b["mid"],"marked_at":b["ts"],"fee":fee})
        cost=sum(l["qty"]*l["entry"]/self.fx for l in fills if l["kind"]=="spot")
        fees=sum(l["fee"] for l in fills)
        t=self.totals()
        added_gross=sum(abs(l["qty"]*l["mark"])/self.fx for l in fills)
        added_margin=sum(abs(l["qty"]*l["mark"])/self.fx/self.LEVERAGE for l in fills if l["kind"]=="perp")
        impact=sum(self.leg_pnl(l) for l in fills)
        if any(l["qty"]<0 for l in fills if l["kind"]=="spot"): return False
        if t["available_eur"] - cost - fees - added_margin + impact < 0: return False
        if t["gross_exposure_eur"]+added_gross > self.LEVERAGE*(t["equity_eur"]-fees+impact): return False
        self.data["cash_eur"] -= cost+fees
        self.data["fees_eur"] += fees
        self.data["positions"].append(dict(id=self.data["next_id"],strategy_id=strategy_id,kind=kind,
            opened_at=now,legs=fills,entry_fees_eur=fees,funding_eur=0.0,policy=policy or {}, funding_at=now))
        self.data["next_id"]+=1
        # Consume observed depth, preventing multiple sleeves reusing the same liquidity.
        for l in fills: self.consume(l["instrument"], l["qty"])
        self.save()
        return True

    def consume(self,key,qty):
        levels=self.books[key]["asks" if qty>0 else "bids"]
        remaining=abs(qty)
        for row in levels:
            take=min(remaining,row[1]); row[1]-=take; remaining-=take
            if remaining<=1e-12: break

    def close(self,p,now,reason):
        if any(not self.fresh(l["instrument"],now) for l in p["legs"]): return False
        fills=[]
        for l in p["legs"]:
            b=self.books[l["instrument"]]
            filled,px=_walk(b["bids"] if l["qty"]>0 else b["asks"],abs(l["qty"]))
            if filled+1e-10<abs(l["qty"]): return False
            fee=abs(l["qty"])*px*(7 if l["kind"]=="spot" else 4.5)/10000/self.fx
            fills.append((l,px,fee))
        pnl=sum(l["qty"]*(px-l["entry"])/self.fx for l,px,f in fills)
        exit_fees=sum(f for l,px,f in fills)
        for l,px,fee in fills:
            self.data["cash_eur"] += (l["qty"]*px/self.fx if l["kind"]=="spot" else l["qty"]*(px-l["entry"])/self.fx)-fee
            self.consume(l["instrument"],-l["qty"])
        self.data["fees_eur"]+=exit_fees
        self.data["closed"].append(dict(id=p["id"],strategy_id=p["strategy_id"],kind=p["kind"],opened_at=p["opened_at"],closed_at=now,
            net_eur=pnl-p["entry_fees_eur"]-exit_fees+p["funding_eur"],fees_eur=p["entry_fees_eur"]+exit_fees,reason=reason,legs=[{**l,"exit":px,"exit_fee_eur":fee} for l,px,fee in fills]))
        self.data["positions"].remove(p)
        self.data["cooldown"][p["strategy_id"]]=now
        self.save()
        return True

    def accrue_funding(self, now):
        # Continuous estimate using observed hourly rate; not an exchange settlement claim.
        for p in self.data["positions"]:
            dt=max(0,now-p["funding_at"])
            rates=[self.funding.get(l["instrument"]) for l in p["legs"] if l["kind"]=="perp"]
            covered=dt<=15 and all(r and 0<=now-r[1]<=120 for r in rates)
            if covered:
                payment=sum(-l["qty"]*l["mark"]*self.funding[l["instrument"]][0]*dt/3600/self.fx for l in p["legs"] if l["kind"]=="perp")
                self.data["cash_eur"]+=payment; self.data["funding_eur"]+=payment; p["funding_eur"]+=payment
            else: self.data["funding_unobserved_seconds"]+=dt
            p["funding_at"]=now

    def observe(self, state, strategies, decimals):
        if not self.fx: return
        now=time.time(); symbol=state["symbol"]; key="perp:"+symbol.replace("USDT","")
        if state.get("venue")!="HYPERLIQUID" or state.get("health",{}).get("status")!="HEALTHY": return
        ts=state["timestamp"]-float(state.get("health",{}).get("age_ms") or 0)/1000
        sequence=state.get("health",{}).get("sequence")
        if sequence!=self.last_sequences.get(key):
            self.last_sequences[key]=sequence
            self.book(key,state["bids"],state["asks"],ts,decimals)
        ctx=state.get("venue_context",{})
        if ctx.get("funding") is not None:
            self.funding[key]=(float(ctx["funding"]),float(ctx.get("received_at",0)))
        if not self.fresh(key,now): return
        self.accrue_funding(now)
        active={s["id"]:s for s in strategies if s.get("status")!="KILLED"}
        for p in list(self.data["positions"]):
            if p["kind"]!="directional" or p["legs"][0]["instrument"]!=key: continue
            g=p["policy"];l=p["legs"][0];age=now-p["opened_at"]
            raw=raw_signal_for_genome(state["features"],g)
            move=(l["mark"]/l["entry"]-1)*(1 if l["qty"]>0 else -1)*10000
            reason=None
            if state.get("intent",{}).get("state")=="RISK_OFF": reason="risk_off"
            elif self.totals()["leverage"]>3 or self.totals()["available_eur"]<0: reason="exposure_limit"
            elif p["policy"]["id"] not in active: reason="strategy_retired"
            elif move<=-g["stop_loss_bps"]: reason="stop_loss"
            elif move>=g["take_profit_bps"]: reason="take_profit"
            elif age>=g["max_holding_seconds"]: reason="max_holding"
            elif age>=60 and (raw*l["qty"]<=0 or abs(raw)<g["exit_threshold"]): reason="signal_decay"
            if reason: self.close(p,now,reason)
        if state.get("intent",{}).get("state")=="RISK_OFF": return
        # One sleeve per family and market; every sleeve draws on the same ledger.
        used={p["policy"].get("family") for p in self.data["positions"] if p["kind"]=="directional" and p["legs"][0]["instrument"]==key}
        candidates=sorted(active.values(),key=lambda g:abs(raw_signal_for_genome(state["features"],g)),reverse=True)
        for g in candidates:
            if g["family"] in used: continue
            raw=raw_signal_for_genome(state["features"],g)
            if abs(raw)<g["threshold"]: continue
            b=self.books[key]
            if (b["asks"][0][0]/b["bids"][0][0]-1)*10000>3: continue
            budget=min(100,self.totals()["equity_eur"]*.1)
            qty=math.floor(budget*self.fx/b["mid"]*10**decimals)/10**decimals
            if self.open(symbol+":"+g["id"],[dict(instrument=key,kind="perp",qty=qty*(1 if raw>0 else -1))],now,dict(g)):
                used.add(g["family"])
        self.record(now)

    def pair(self,spot_key,now):
        if not self.fx: return
        self.accrue_funding(now)
        keys=[spot_key,"perp:HYPE"]
        if not all(self.fresh(k,now) for k in keys):
            self.reason="Delta neutral : attente des deux carnets frais";return
        funding=self.funding.get("perp:HYPE")
        if not funding or now-funding[1]>120:
            self.reason="Delta neutral : attente du funding observé";return
        spot,perp=[self.books[k] for k in keys]
        basis=(perp["mid"]/spot["mid"]-1)*10000
        existing=next((p for p in self.data["positions"] if p["kind"]=="delta_neutral"),None)
        if existing:
            pnl=sum(self.leg_pnl(l) for l in existing["legs"])-existing["entry_fees_eur"]+existing["funding_eur"]
            if self.totals()["leverage"]>3 or self.totals()["available_eur"]<0 or pnl < -10 or now-existing["opened_at"]>=86400 or (now-existing["opened_at"]>=300 and funding[0]<0):
                self.close(existing,now,"pair_risk_or_funding_exit")
            self.reason="Delta neutral : paire HYPE spot/perp suivie";self.record(now);return
        # Avoid manufacturing a trade just to populate the dashboard.
        if funding[0]<=0 or basis<30:
            self.reason=f"Delta neutral prêt : basis {basis:.1f} bp / minimum 30 bp, funding {funding[0]:.6f}";return
        dec=min(spot["decimals"],perp["decimals"])
        qty=math.floor(min(250,self.totals()["equity_eur"]*.25)*self.fx/spot["mid"]*10**dec)/10**dec
        _, spot_entry = _walk(spot["asks"], qty)
        _, perp_entry = _walk(perp["bids"], qty)
        if spot_entry<=0 or (perp_entry/spot_entry-1)*10000 < 30:
            self.reason="Delta neutral : basis exécutable insuffisant après spread";return
        ok=self.open("delta_neutral_HYPE",[dict(instrument=spot_key,kind="spot",qty=qty),dict(instrument="perp:HYPE",kind="perp",qty=-qty)],now,kind="delta_neutral")
        self.reason="Delta neutral : deux jambes ouvertes" if ok else "Delta neutral : capital, précision ou liquidité insuffisants"
        self.record(now)

    def record(self,now):
        if now-self.last_history>=60:
            self.data["history"].append({"ts":now,**self.totals()})
            self.data["history"]=self.data["history"][-10080:]
            self.last_history=now
            self.save()

    def state(self):
        now=time.time(); t=self.totals()
        positions=[]
        for p in self.data["positions"]:
            positions.append({**p,"net_eur":sum(self.leg_pnl(l) for l in p["legs"])-p["entry_fees_eur"]+p["funding_eur"],
                "fresh":all(self.fresh(l["instrument"],now) for l in p["legs"]),
                "delta_units":sum(l["qty"] for l in p["legs"]) if p["kind"]=="delta_neutral" else None})
        return dict(initial_eur=1000,**t,pnl_eur=t["equity_eur"]-1000,max_leverage=3,
            positions=positions,closed=self.data["closed"][-100:],closed_count=len(self.data["closed"]),
            fees_eur=self.data["fees_eur"],funding_eur=self.data["funding_eur"],fx=self.data["fx"],
            funding_unobserved_seconds=self.data["funding_unobserved_seconds"],history=self.data["history"],
            books={k:{"age_seconds":max(0,now-b["ts"]),"fresh":self.fresh(k,now)} for k,b in self.books.items()},
            status="BLOCKED" if self.error else "PAPER",error=self.error,pair_status=self.reason,
            gamma_status="Non implémenté : aucune option ni grecque d’option dans ce moteur",paper_only=True)
