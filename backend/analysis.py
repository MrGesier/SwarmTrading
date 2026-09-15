"""Counterfactual sensitivity and visible-book execution cost, without orders."""
import numpy as np


def technical_analysis(engine, state, horizon):
    from engine import GENOMES
    f = state['features']
    mask = np.array([g['horizon']==horizon for g in GENOMES])
    weights = engine.weights * mask
    total = max(float(weights.sum()),1e-9)
    baseline = engine.votes(f)
    base_consensus = float(np.dot(baseline,weights)/total)
    surface=[]
    for vol in [.5,.75,1,1.25,1.5,2]:
        row=[]
        for bp in range(-24,25,6):
            votes=engine.votes(f,price_bp=bp,vol_scale=vol)
            row.append(dict(bp=bp,vol=vol,consensus=float(np.dot(votes,weights)/total),
                            flips=float(weights[np.sign(votes)!=np.sign(baseline)].sum())))
        surface.append(row)
    fragility=None
    if abs(base_consensus)>=.05:
        direction=-1 if base_consensus>0 else 1
        for bp in range(1,51):
            projected=engine.votes(f,price_bp=bp*direction)
            consensus=float(np.dot(projected,weights)/total)
            if consensus*base_consensus<=0:
                fragility=dict(bp=bp*direction,consensus=consensus)
                break
    return dict(timestamp=state['timestamp'],horizon=horizon,ready=f['ready'][str(horizon)],
                baseline=base_consensus,surface=surface,fragility=fragility,
                fragility_status='NEUTRAL' if abs(base_consensus)<.05 else 'FOUND' if fragility else 'OUTSIDE_RANGE')


def cost_preview(bids, asks, mid, notional, fee_bps):
    target=notional/mid
    result=[]
    for side,levels in [('BUY',asks),('SELL',bids)]:
        remaining,quote=target,0.0
        for price,available in levels:
            quantity=min(remaining,available)
            quote+=quantity*price
            remaining-=quantity
            if remaining<=1e-12:
                break
        filled=target-remaining
        vwap=quote/filled if filled else None
        impact=((vwap/mid-1) if side=='BUY' else (1-vwap/mid))*1e4 if vwap else None
        result.append(dict(side=side,requested=target,filled=filled,fill_ratio=filled/target,
                           complete=remaining<=1e-10,vwap=vwap,impact_bps=impact,
                           fee_bps=fee_bps,total_bps=impact+fee_bps if impact is not None else None,
                           fee_quote=quote*fee_bps/1e4))
    return result
