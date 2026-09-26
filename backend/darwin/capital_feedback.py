"""Deterministic allocation feedback and forward comparison. Never an LLM order."""
import copy
import re
import time


def group(strategy_id):
    market,_,genome=strategy_id.partition(":")
    if not genome: return strategy_id
    family=re.sub(r"_\d.*", "",genome.split("__")[0]).replace("_"," ").lower()
    return market+":"+family


def evidence(data, now):
    groups={}
    for row in data["closed"]:
        if row["closed_at"] < now-86400 or row.get("kind")!="directional": continue
        groups.setdefault(group(row["strategy_id"]),[]).append(row)
    results=[]
    for key,all_rows in groups.items():
        rows=all_rows[-20:]
        net=sum(r["net_eur"] for r in rows); fees=sum(r["fees_eur"] for r in rows)
        span=rows[-1]["closed_at"]-rows[0]["opened_at"]
        # More fees are stress-tested on top of the already net PnL.
        qualified=len(rows)>=20 and span>=1800 and net-fees*.5>0
        losing=len(rows)>=5 and net<0
        scale=1.0 if qualified else .25 if losing else .5
        results.append(dict(group=key,trades=len(rows),net_eur=net,fees_eur=fees,
            stressed_net_eur=net-fees*.5,sample_seconds=span,scale=scale,
            status="EVIDENCE_POSITIVE" if qualified else "REDUCED_LOSSES" if losing else "EXPLORING",
            affected_ids=list(dict.fromkeys(r["strategy_id"] for r in rows))[-5:]))
    return sorted(results,key=lambda x:x["net_eur"])


def scale_for(data, strategy_id, now):
    return next((r["scale"] for r in evidence(data,now) if r["group"]==group(strategy_id)),.5)


def update_decisions(data, now):
    log=data.setdefault("allocation_decisions",[])
    previous=data.setdefault("allocation_states",{})
    for row in evidence(data,now):
        if previous.get(row["group"])!=row["status"]:
            log.append({**row,"ts":now,"action":"allocation_multiplier","reason":"Observed portfolio net PnL after modeled fees; descriptive, not proof of future edge"})
            previous[row["group"]]=row["status"]
    data["allocation_decisions"]=log[-200:]


def start_comparison(active, control):
    if "allocation_comparison" not in active.data:
        if control.path.exists():
            raise ValueError("Orphan control ledger; reconcile before starting a comparison")
        now=time.time()
        metadata=dict(started_at=now,start_equity_eur=active.totals()["equity_eur"],
                      start_closed=len(active.data["closed"]),version="allocation-feedback-v1")
        control.data=copy.deepcopy(active.data)
        control.data["allocation_comparison"]=metadata
        control.save()
        active.data["allocation_comparison"]=metadata
        active.save()
    elif not control.path.exists() or control.data.get("allocation_comparison")!=active.data["allocation_comparison"]:
        raise ValueError("Missing or mismatched forward control; never restart evidence silently")
    active.adaptive=True
    control.adaptive=False
    update_decisions(active.data,time.time())
    active.save()


def comparison(active, control):
    if "allocation_comparison" not in active.data: return None
    m=active.data["allocation_comparison"]; a=active.totals()["equity_eur"]; b=control.totals()["equity_eur"]
    n=len(active.data["closed"])-m["start_closed"]; age=time.time()-m["started_at"]
    ready=age>=1800 and n>=10 and len(control.data["closed"])-m["start_closed"]>=10
    gain=a-m["start_equity_eur"]; delta=a-b
    status="COLLECTING" if not ready else "CAPITAL_GAIN" if gain>0 and delta>0 else "LOWER_LOSS" if delta>0 else "NO_IMPROVEMENT"
    return {**m,"active_equity_eur":a,"fixed_equity_eur":b,"gain_since_start_eur":gain,"delta_vs_fixed_eur":delta,
            "closed_since_start":n,"status":status,"seconds_observed":age,
            "interpretation":"Forward descriptive comparison of allocation only, same evolving genomes/data/cost model; not statistical proof or a profitability forecast"}
