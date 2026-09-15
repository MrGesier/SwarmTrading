"""Exchange-independent book and transparent, uncalibrated research engine."""
from collections import deque
import math
import numpy as np
from horizons import HorizonMemory, term_structure, selected_intent


class SequenceGap(ValueError):
    pass


class OrderBook:
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.sequence = None
        self.valid = False

    def snapshot(self, data):
        self.bids = {float(p): float(q) for p, q in data['bids'] if float(q) > 0}
        self.asks = {float(p): float(q) for p, q in data['asks'] if float(q) > 0}
        self.sequence = data['lastUpdateId']
        self.valid = False  # Only a bridged incremental event makes a live book ready.

    def update(self, event):
        if self.sequence is None:
            raise SequenceGap('Snapshot required')
        if event['u'] <= self.sequence:
            return False
        if not event['U'] <= self.sequence + 1 <= event['u']:
            self.valid = False
            raise SequenceGap('Depth sequence gap; resnapshot required')
        for key, side in [('b', self.bids), ('a', self.asks)]:
            for price, quantity in event[key]:
                p, q = float(price), float(quantity)
                if q == 0:
                    side.pop(p, None)
                else:
                    side[p] = q
        self.sequence = event['u']
        self.valid = bool(self.bids and self.asks and max(self.bids) < min(self.asks))
        if not self.valid:
            raise SequenceGap('Crossed or empty book')
        return True

    def levels(self, n=40):
        return (sorted(self.bids.items(), reverse=True)[:n], sorted(self.asks.items())[:n])


def entropy(weights):
    p = np.asarray(weights, dtype=float)
    if len(p) < 2 or p.sum() <= 0:
        return 0.0
    p = p / p.sum()
    return float(-np.sum(p[p > 0] * np.log(p[p > 0])) / np.log(len(p)))


def effective_count(history):
    """Participation ratio: (tr C)^2 / tr(C^2), equal to eigenvalue formula."""
    a = np.asarray(history, dtype=float)
    if len(a) < 10:
        return None, None
    sd = a.std(axis=0)
    active = sd > 1e-8
    if not active.any():
        return 0.0, np.zeros(a.shape[1])
    z = (a[:, active] - a[:, active].mean(axis=0)) / sd[active]
    corr = z.T @ z / len(a)
    n = float(np.trace(corr) ** 2 / np.sum(corr ** 2))
    w = np.zeros(a.shape[1])
    w[active] = 1 / np.maximum(np.sum(corr ** 2, axis=1), 1)
    w *= n / max(w.sum(), 1e-12)
    return n, w


FAMILIES = ['Momentum', 'Mean reversion', 'Breakout', 'Trend', 'Order flow', 'Microprice', 'Book pressure', 'Volatility']
HORIZONS = [1, 5, 30, 60, 180]
GENOMES = [dict(id=f'{name.lower().replace(" ", "_")}_{h}_{j:02}', family=name, horizon=h,
                threshold=0.12 + j * 0.055, gain=0.75 + j * 0.14)
           for name in FAMILIES for h in HORIZONS for j in range(8)]
GAINS = np.array([g['gain'] for g in GENOMES])
THRESHOLDS = np.array([g['threshold'] for g in GENOMES])


class Engine:
    def __init__(self):
        self.memory=HorizonMemory(HORIZONS)
        self.local_history={h:deque(maxlen=120) for h in HORIZONS}
        self.local_neff={h:None for h in HORIZONS}
        self.local_weights={h:np.zeros(64) for h in HORIZONS}
        self.local_timelines={h:deque(maxlen=60) for h in HORIZONS}
        self.local_previous={h:'RISK_OFF' for h in HORIZONS}
        self.local_pending={h:('',0) for h in HORIZONS}
        self.prices = deque(maxlen=900)
        self.trades = deque(maxlen=20000)
        self.signals = deque(maxlen=120)
        self.history = deque(maxlen=600)
        self.timeline = deque(maxlen=60)
        self.candles = deque(maxlen=3600)
        self.previous = 'NEUTRAL'
        self.pending = None
        self.pending_count = 0
        self.weights = np.ones(len(GENOMES)) / 24
        self.neff = None
        self.tick = 0

    def trade(self, timestamp, price, quantity, sell):
        self.trades.append((timestamp, price, quantity, -1 if sell else 1))
        self.memory.trade(timestamp,quantity,sell)
        bucket = int(timestamp)
        if not self.candles or self.candles[-1]['time'] != bucket:
            self.candles.append(dict(time=bucket, open=price, high=price, low=price, close=price, volume=quantity))
        else:
            c = self.candles[-1]
            c.update(high=max(c['high'], price), low=min(c['low'], price), close=price, volume=c['volume'] + quantity)

    def votes(self, features, price_bp=0, vol_scale=1, flow_delta=0):
        local=features.get('horizon_states')
        if local:
            momentum=np.array([local[str(h)]['return_bps']+price_bp for h in HORIZONS])
            norm=np.maximum(np.array([local[str(h)]['realized_vol'] for h in HORIZONS])*vol_scale,.5)
            flow=np.clip(np.array([local[str(h)]['trade_flow'] for h in HORIZONS])+flow_delta,-1,1)
            ofi=np.array([local[str(h)]['ofi_normalized'] for h in HORIZONS])
            micro=np.array([local[str(h)]['microprice_pressure_mean']/max(local[str(h)]['spread_mean'],.01)*2 for h in HORIZONS])
            pressure=np.array([local[str(h)]['book_imbalance_mean'] for h in HORIZONS])
        else:  # Legacy feature fixtures and old research clients.
            momentum=np.array([features['returns'][str(h)]+price_bp for h in HORIZONS])
            norm=np.maximum(features['volatility']*np.sqrt(np.array(HORIZONS)*2)*vol_scale,.5)
            flow=np.full(len(HORIZONS),np.clip(features['flow']+flow_delta,-1,1))
            ofi=flow
            micro=np.full(len(HORIZONS),features['micro_delta']/max(features['spread'],.01)*2)
            pressure=np.full(len(HORIZONS),features['weighted_imbalance'])
        raw=np.array([momentum/norm,-momentum/norm*.7,momentum/norm*(1+np.abs(flow)),
                      momentum/np.maximum(norm,1),flow+ofi*.5,micro,pressure*1.7,
                      momentum/norm*max(.2,vol_scale-.5)])
        ready = np.array([features.get('ready', {}).get(str(h), True) for h in HORIZONS])
        raw *= ready
        values = np.tanh(np.repeat(raw.ravel(),8)*GAINS)
        return np.where(np.abs(values)>THRESHOLDS,values,0)

    def calculate(self, book, ts, mode, symbol, health):
        bids, asks = book.levels()
        if not bids or not asks:
            return None
        mid = (bids[0][0] + asks[0][0]) / 2
        self.prices.append((ts, mid))
        spread = (asks[0][0] - bids[0][0]) / mid * 1e4
        bq, aq = sum(q for _, q in bids), sum(q for _, q in asks)
        wb = sum(q / (i + 1) for i, (_, q) in enumerate(bids))
        wa = sum(q / (i + 1) for i, (_, q) in enumerate(asks))
        micro = (asks[0][0] * bids[0][1] + bids[0][0] * asks[0][1]) / (bids[0][1] + asks[0][1])
        returns = {}
        elapsed = ts-self.prices[0][0]
        ready = {str(h): elapsed >= h for h in HORIZONS}
        for h in HORIZONS:
            old = next((p for t, p in reversed(self.prices) if t <= ts - h), self.prices[0][1])
            returns[str(h)] = (mid / old - 1) * 1e4
        recent = [t for t in self.trades if ts - 30 <= t[0] <= ts]
        volume = sum(t[2] for t in recent)
        flow = sum(t[2] * t[3] for t in recent) / max(volume, 1e-9)
        prices = np.array([p for t, p in self.prices if t >= ts - 60])
        r = np.diff(np.log(prices)) * 1e4
        volatility = float(np.std(r)) if len(r) else 0
        f = dict(mid=mid, spread=spread, microprice=micro, micro_delta=(micro / mid - 1) * 1e4,
                 imbalance=(bq-aq)/(bq+aq), weighted_imbalance=(wb-wa)/(wb+wa), flow=flow,
                 volatility=volatility, returns=returns, volume=volume, intensity=len(recent)/30,
                 bid_depth=bq, ask_depth=aq, ready=ready, history_seconds=elapsed,
                 bid_concentration=sum(q for _,q in bids[:5])/bq, ask_concentration=sum(q for _,q in asks[:5])/aq,
                 vacuum_up=max((asks[i+1][0]-asks[i][0])/mid*1e4 for i in range(len(asks)-1)) if len(asks)>1 else 0,
                 vacuum_down=max((bids[i][0]-bids[i+1][0])/mid*1e4 for i in range(len(bids)-1)) if len(bids)>1 else 0)
        if not self.memory.books:self.memory.observe(book,ts)
        local_features=self.memory.states(ts)
        f['horizon_states']=local_features
        f['ready']={h:v['ready'] for h,v in local_features.items()}
        ready=f['ready']
        votes = self.votes(f)
        self.signals.append(votes.tolist())
        self.tick += 1
        if self.tick % 5 == 0:
            n, w = effective_count(self.signals)
            if w is not None:
                self.neff = n
        for h in HORIZONS:
            ix=np.array([g['horizon']==h for g in GENOMES])
            if ready[str(h)]:self.local_history[h].append(votes[ix].tolist())
            if self.tick%5==0:
                n,weights=effective_count(self.local_history[h])
                if weights is not None:self.local_neff[h],self.local_weights[h]=n,weights
            self.weights[ix]=self.local_weights[h] if ready[str(h)] else 0
        w = self.weights
        total = max(float(w.sum()), 1e-9)
        support = [float(w[votes < 0].sum()), float(w[votes == 0].sum()), float(w[votes > 0].sum())]
        consensus = float(np.dot(votes, w) / total)
        hs = entropy(support)
        hp = entropy([int((r < 0).sum()), int((r == 0).sum()), int((r > 0).sum())])
        hb = entropy([q for _, q in bids + asks])
        ht = entropy([sum(t[2] for t in recent if t[3] < 0), sum(t[2] for t in recent if t[3] > 0)])
        hm = (hp + hb + ht) / 3
        prev = self.history[-1] if self.history else None
        dt = max(ts - prev['time'], .001) if prev else 1
        velocity = (consensus-prev['consensus'])/dt if prev else 0
        slope = (hm-prev['market_entropy'])/dt if prev else 0
        score = float(np.clip(consensus * 70 + f['flow'] * 15 + f['weighted_imbalance'] * 15, -100, 100))
        direction = 'LONG' if score >= 0 else 'SHORT'
        state = f'{direction}_CONFIRMED' if abs(score) > 55 else f'{direction}_EARLY' if abs(score) > 30 else f'WATCH_{direction}' if abs(score) > 15 else 'NEUTRAL'
        if health['status'] != 'HEALTHY' or self.neff is None or self.neff < 1:
            state = 'RISK_OFF'
        if state == self.pending:
            self.pending_count += 1
        else:
            self.pending, self.pending_count = state, 1
        reasons = [f'Weighted consensus {consensus:+.2f} across {len(FAMILIES)} families',
                   f'Trade-flow imbalance {flow:+.2f}; book imbalance {f["weighted_imbalance"]:+.2f}',
                   f'Swarm entropy {hs:.2f}; observed effective count {self.neff or 0:.1f}']
        if state == 'RISK_OFF' or self.pending_count >= 3:
            if state != self.previous:
                self.timeline.appendleft(dict(time=ts, state=state, previous=self.previous, score=score, reasons=reasons))
            self.previous = state
        families = []
        for family in FAMILIES:
            ix = np.array([g['family'] == family for g in GENOMES])
            families.append(dict(name=family, short=float(w[ix & (votes < 0)].sum()), neutral=float(w[ix & (votes == 0)].sum()),
                                 long=float(w[ix & (votes > 0)].sum()), consensus=float(np.dot(w[ix], votes[ix])/max(w[ix].sum(), 1e-9))))
        triggers = []
        local_triggers={str(h):[] for h in HORIZONS}
        for bp in range(-30, 31, 2):
            projected = self.votes(f, price_bp=bp)
            flips = np.sign(projected) != np.sign(votes)
            price = mid * (1 + bp / 1e4)
            depth = sum(q for p, q in (asks if bp > 0 else bids) if min(mid, price) <= p <= max(mid, price))
            triggers.append(dict(bp=bp, price=price, density=float(w[flips].sum()), resistance=depth))
            for h in HORIZONS:
                mask=np.array([g['horizon']==h for g in GENOMES])
                local_triggers[str(h)].append(dict(bp=bp,price=price,density=float(w[flips&mask].sum()),resistance=depth))
        horizon_consensus = {}
        for h in HORIZONS:
            ix = np.array([g['horizon']==h for g in GENOMES])
            horizon_consensus[str(h)] = float(np.dot(w[ix],votes[ix])/max(w[ix].sum(),1e-9))
        horizons={}
        for h in HORIZONS:
            ix=np.array([g['horizon']==h for g in GENOMES]);lv=votes[ix];lw=w[ix]
            sup=[float(lw[lv<0].sum()),float(lw[lv==0].sum()),float(lw[lv>0].sum())]
            lf=local_features[str(h)]
            horizons[str(h)]=dict(timestamp=ts,horizon_s=h,ready=ready[str(h)],features=lf,
                swarm=dict(raw=64,active=int(np.count_nonzero(lv)),effective=self.local_neff[h],support=sup,
                    consensus=horizon_consensus[str(h)],entropy=entropy(sup)),
                entropy=dict(swarm=entropy(sup),market=lf['market_entropy'],price=lf['price_entropy'],
                    trade=lf['flow_entropy'],book=lf['book_entropy'],slope=0),triggers=local_triggers[str(h)])
        for h in HORIZONS:
            loc=horizons[str(h)];entry=horizons[str(min(5,h))]
            intent=selected_intent(loc,entry,health['status'])
            pending,count=self.local_pending[h]
            count=count+1 if pending==intent['state'] else 1
            self.local_pending[h]=(intent['state'],count)
            if intent['state']=='RISK_OFF' or count>=3:
                if intent['state']!=self.local_previous[h]:
                    self.local_timelines[h].appendleft(dict(time=ts,state=intent['state'],previous=self.local_previous[h],score=intent['score'],reasons=intent['reasons']))
                self.local_previous[h]=intent['state']
            intent['state']=self.local_previous[h]
            loc['intent']=intent
            loc['timeline']=list(self.local_timelines[h])
        term=term_structure(horizons,self.history)
        row = dict(time=ts, mid=mid, consensus=consensus, horizon_consensus=horizon_consensus, market_entropy=hm, swarm_entropy=hs, slope=slope,
                   levels=[[p, q] for p, q in bids + asks])
        row['term_structure']=term
        row['horizon_metrics']={h:dict(market_entropy=v['entropy']['market'],swarm_entropy=v['entropy']['swarm'],effective=v['swarm']['effective'],ready=v['ready']) for h,v in horizons.items()}
        self.history.append(row)
        strategies = [{**g, 'signal':float(v), 'weight':float(ww)} for g, v, ww in zip(GENOMES, votes, w)]
        cone = []
        for h in HORIZONS:
            ix = np.array([g['horizon'] == h for g in GENOMES])
            cone.append(dict(horizon=h, consensus=horizon_consensus[str(h)], ready=ready[str(h)],
                             remaining=max(0,round(h-elapsed))))
        return dict(timestamp=ts, mode=mode, symbol=symbol, venue='SIMULATOR' if mode == 'simulation' else 'BINANCE',
                    horizons=horizons,term_structure=term,health=health, features=f, bids=bids[:20], asks=asks[:20], candles=[dict(c) for c in self.candles],
                    history=list(self.history)[-180:], families=families, strategies=strategies, triggers=triggers, cone=cone,
                    entropy=dict(market=hm, swarm=hs, price=hp, book=hb, trade=ht, slope=slope),
                    swarm=dict(raw=len(votes), active=int(np.count_nonzero(votes)), effective=self.neff, support=support,
                               consensus=consensus, velocity=velocity),
                    intent=dict(state=self.previous, score=score, reasons=reasons, calibrated=False),
                    timeline=list(self.timeline), regime='EXPANSION' if volatility > 1.5 else 'COMPRESSION' if volatility < .5 else 'NORMAL')
