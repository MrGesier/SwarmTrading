"""Causal, time-windowed market memory; separate features for every horizon."""
from collections import deque
from dataclasses import asdict, dataclass
import math
import numpy as np


def normalized_entropy(values):
    p=np.asarray(values,dtype=float)
    if len(p)<2 or p.sum()<=0:return 0.0
    p=p/p.sum()
    return float(-np.sum(p[p>0]*np.log(p[p>0]))/np.log(len(p)))


def quote_ofi(previous,current):
    """Cont-style best-quote OFI, in base units; not trade-flow imbalance."""
    bp,bq,ap,aq=previous
    nbp,nbq,nap,naq=current
    return (nbq if nbp>=bp else 0)-(bq if nbp<=bp else 0)-(naq if nap<=ap else 0)+(aq if nap>=ap else 0)


@dataclass
class HorizonState:
    horizon_s:int
    ready:bool
    remaining_s:float
    return_bps:float
    realized_vol:float
    path_efficiency:float
    range_bps:float
    drawdown_bps:float
    trend_slope:float
    trade_flow:float
    buy_volume:float
    sell_volume:float
    trade_intensity:float
    ofi:float
    ofi_normalized:float
    ofi_ewma:float
    book_imbalance_mean:float
    book_imbalance_last:float
    book_imbalance_slope:float
    microprice_pressure_mean:float
    spread_mean:float
    bid_depth_change:float
    ask_depth_change:float
    price_entropy:float
    flow_entropy:float
    book_entropy:float
    market_entropy:float
    bullish_pressure_duty_cycle:float
    bearish_pressure_duty_cycle:float
    pressure_run_length:float
    buy_pressure_capacity:float
    sell_pressure_capacity:float


class HorizonMemory:
    def __init__(self,horizons):
        self.horizons=horizons
        self.books=deque()
        self.trades=deque()
        self.previous_quote=None
        self.started=None

    def trade(self,ts,quantity,sell):
        self.trades.append((ts,float(quantity),bool(sell)))
        self.trim(ts)

    def trim(self,ts):
        cutoff=ts-max(self.horizons)-3
        while len(self.books)>1 and self.books[1][0]<cutoff:self.books.popleft()
        while self.trades and self.trades[0][0]<cutoff:self.trades.popleft()

    def observe(self,book,ts):
        bids,asks=book.levels(40)
        if not bids or not asks:return
        if self.books and ts<self.books[-1][0]:return
        bp,bq=bids[0];ap,aq=asks[0]
        if bp>=ap:return
        mid=(bp+ap)/2
        wb=sum(q/(i+1) for i,(_,q) in enumerate(bids));wa=sum(q/(i+1) for i,(_,q) in enumerate(asks))
        micro=(ap*bq+bp*aq)/(bq+aq)
        quote=(bp,bq,ap,aq)
        ofi=quote_ofi(self.previous_quote,quote) if self.previous_quote else 0
        self.previous_quote=quote
        # time, mid, weighted imbalance, micro delta, spread, bid/ask depth, entropy, OFI
        self.books.append((ts,mid,(wb-wa)/(wb+wa),(micro/mid-1)*1e4,(ap-bp)/mid*1e4,
                           sum(q for _,q in bids),sum(q for _,q in asks),normalized_entropy([q for _,q in bids+asks]),ofi))
        if self.started is None:self.started=ts
        self.trim(ts)

    def states(self,ts):
        if not self.books:return {}
        all_books=np.array([b for b in self.books if b[0]<=ts],dtype=float)
        trades=np.array([t for t in self.trades if t[0]<=ts],dtype=float).reshape(-1,3)
        result={}
        for h in self.horizons:
            cutoff=ts-h
            idx=max(0,int(np.searchsorted(all_books[:,0],cutoff,side='right'))-1)
            b=all_books[idx:]
            # Piecewise-constant book levels, weighted by observed duration and half-life h/2.
            starts=np.maximum(b[:,0],cutoff)
            ends=np.minimum(np.r_[b[1:,0],ts],ts)
            duration=np.maximum(ends-starts,0)
            ages=ts-(starts+ends)/2
            decay=duration*np.exp(-math.log(2)*ages/max(h/2,.01))
            if decay.sum()==0:decay=np.ones(len(b))
            mean=lambda col:float(np.average(b[:,col],weights=decay))
            rr=np.diff(np.log(b[:,1]))*1e4
            ret=float((b[-1,1]/b[0,1]-1)*1e4)
            rv=float(np.sqrt(np.sum(rr**2)))
            trade_window=trades[trades[:,0]>cutoff] if len(trades) else trades
            buy=float(trade_window[trade_window[:,2]==0,1].sum()) if len(trade_window) else 0
            sell=float(trade_window[trade_window[:,2]==1,1].sum()) if len(trade_window) else 0
            flow=(buy-sell)/max(buy+sell,1e-12)
            x=b[:,0]-b[0,0]
            slope=float(np.polyfit(x,b[:,2],1)[0]*60) if len(b)>1 and x[-1]>0 else 0
            price_h=normalized_entropy([(rr<0).sum(),(rr==0).sum(),(rr>0).sum()])
            flow_h=normalized_entropy([buy,sell]);book_h=mean(7)
            sign=np.sign(b[-1,2]);run=0
            for value,dt in zip(b[::-1,2],duration[::-1]):
                if np.sign(value)!=sign:break
                run+=dt
            ofi=float(b[b[:,0]>cutoff,8].sum())
            observed=max(min(h,ts-self.started),0)
            ready=ts-self.started>=h and ts-b[-1,0]<3 and (len(b)<2 or float(np.max(np.diff(b[:,0])))<=3)
            state=HorizonState(h,ready,max(0,h-(ts-self.started)),ret,rv,
                abs(float(np.log(b[-1,1]/b[0,1]))*1e4)/max(float(np.abs(rr).sum()),1e-9),
                float((b[:,1].max()-b[:,1].min())/b[-1,1]*1e4),float((b[-1,1]/b[:,1].max()-1)*1e4),
                ret/max(observed,1)*60,flow,buy,sell,len(trade_window)/max(observed,1),ofi,
                float(np.tanh(ofi/max(mean(5)+mean(6),1e-9))),mean(8),mean(2),float(b[-1,2]),slope,
                mean(3),mean(4),float((b[-1,5]/max(b[0,5],1e-9)-1)),float((b[-1,6]/max(b[0,6],1e-9)-1)),
                price_h,flow_h,book_h,(price_h+flow_h+book_h)/3,
                float(duration[b[:,2]>0].sum()/max(duration.sum(),1e-9)),
                float(duration[b[:,2]<0].sum()/max(duration.sum(),1e-9)),float(run),
                buy/max(mean(6),1e-9),sell/max(mean(5),1e-9))
            result[str(h)]=asdict(state)
        return result


def term_structure(horizons,history):
    pairs=[(int(h),s['swarm']['consensus']) for h,s in horizons.items() if s['ready']]
    if not pairs:return dict(alignment=0,sign_changes=0,slope=0,curvature=0,front_direction='WARMUP',front_horizon=None,front_velocity=0)
    x=np.log([p[0] for p in pairs]);y=np.array([p[1] for p in pairs])
    signs=np.where(abs(y)<.1,0,np.sign(y))
    nonzero=signs[signs!=0]
    changes=int(np.sum(nonzero[1:]!=nonzero[:-1])) if len(nonzero)>1 else 0
    slope=float(np.polyfit(x,y,1)[0]) if len(pairs)>1 else 0
    curve=float(np.polyfit(x,y,2)[0]*2) if len(pairs)>2 else 0
    front=None
    direction='NEUTRAL'
    if signs[0]:
        direction='BULLISH' if signs[0]>0 else 'BEARISH'
        for (h,_),sign in zip(pairs,signs):
            if sign!=signs[0]:break
            front=h
    velocity=0
    prior=history[-1].get('term_structure') if history else None
    if prior and front and prior.get('front_horizon') and prior['front_direction']==direction:
        dt=max(horizons[str(pairs[0][0])]['timestamp']-history[-1]['time'],.001)
        velocity=float((math.log(front)-math.log(prior['front_horizon']))/dt)
    return dict(alignment=float(abs(nonzero.sum())/max(len(nonzero),1)),sign_changes=changes,
                slope=slope,curvature=curve,front_direction=direction,front_horizon=front,front_velocity=velocity)


def selected_intent(local,entry,health):
    f=local['features'];swarm=local['swarm'];c=swarm['consensus']
    score=float(np.clip(c*70+f['trade_flow']*15+f['book_imbalance_mean']*15,-100,100))
    direction='LONG' if score>15 else 'SHORT' if score<-15 else 'NO_TRADE'
    entry_c=entry['swarm']['consensus']
    good=direction!='NO_TRADE' and entry['ready'] and entry_c*(1 if direction=='LONG' else -1)>.1 and f['spread_mean']<5
    state='NO_EDGE' if direction=='NO_TRADE' else f'{direction}_ENTRY_WINDOW' if good else f'{direction}_BIAS_WAIT'
    if not local['ready'] or health!='HEALTHY' or not swarm['effective'] or swarm['effective']<1:state='RISK_OFF'
    return dict(state=state,score=score,direction=direction if state!='RISK_OFF' else 'NO_TRADE',
                entry='FAVORABLE' if good and state!='RISK_OFF' else 'WAIT',calibrated=False,p_long=None,p_short=None,p_no_trade=None,
                calibration_status='NOT_CALIBRATED',
                reasons=[f"Consensus local {c:+.2f} ; N_eff {swarm['effective'] or 0:.2f}",
                         f"Flux {f['trade_flow']:+.2f} ; pression moyenne {f['book_imbalance_mean']:+.2f}",
                         f"Entrée {entry['horizon_s']}s : consensus {entry_c:+.2f}"],
                invalidation=f"Biais invalidé si le score local repasse dans [-15, +15] ; RISK_OFF si carnet incohérent ou obsolète.")
