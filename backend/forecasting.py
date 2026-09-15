"""Offline triple-barrier labels and purged chronological score calibration.

This module never injects in-sample probabilities into the live UI.
"""
import argparse
import json
from pathlib import Path
import numpy as np


def triple_barrier(times,prices,horizon,upper_bps,lower_bps,cost_bps=0):
    times=np.asarray(times,dtype=float);prices=np.asarray(prices,dtype=float)
    if len(times)!=len(prices) or np.any(np.diff(times)<=0) or np.any(prices<=0):
        raise ValueError('Strictly chronological timestamps and positive prices required')
    if horizon<=0 or upper_bps<=0 or lower_bps<=0 or cost_bps<0:raise ValueError('Invalid barriers or horizon')
    output=[]
    for i,t in enumerate(times):
        if t+horizon>times[-1]:break  # Right-censored labels must not be called NO_TRADE.
        end=int(np.searchsorted(times,t+horizon,side='right'))-1
        label=0;exit_i=end
        for j in range(i+1,end+1):
            ret=(prices[j]/prices[i]-1)*1e4
            if ret>=upper_bps+cost_bps:label=1;exit_i=j;break
            if ret<=-(lower_bps+cost_bps):label=-1;exit_i=j;break
        path=(prices[i+1:end+1]/prices[i]-1)*1e4
        output.append(dict(index=i,start=float(t),end=float(times[exit_i] if label else t+horizon),label=label,
                           return_bps=float((prices[exit_i]/prices[i]-1)*1e4),
                           mfe_bps=float(max(0,path.max())) if len(path) else 0,mae_bps=float(min(0,path.min())) if len(path) else 0))
    return output


def walk_forward(labels,scores,folds=3,min_train=100,embargo_s=0,bins=5):
    if len(labels)<min_train+folds*20:return dict(status='INSUFFICIENT_DATA',samples=len(labels),folds=[])
    scores=np.asarray(scores,dtype=float)
    boundaries=np.linspace(min_train,len(labels),folds+1,dtype=int)
    reports=[]
    for lo,hi in zip(boundaries[:-1],boundaries[1:]):
        test=labels[lo:hi];start=test[0]['start']
        train=[r for r in labels[:lo] if r['end']<start-embargo_s]
        if len(train)<min_train:continue
        train_scores=np.array([scores[r['index']] for r in train])
        edges=np.quantile(train_scores,np.linspace(0,1,bins+1)[1:-1])
        bucket=np.searchsorted(edges,train_scores)
        counts=np.ones((bins,3))  # Laplace smoothing, fitted using earlier labels only.
        baseline=np.ones(3)
        for b,r in zip(bucket,train):counts[b,r['label']+1]+=1;baseline[r['label']+1]+=1
        probs=counts/counts.sum(axis=1,keepdims=True);baseline/=baseline.sum()
        pred=np.array([probs[np.searchsorted(edges,scores[r['index']])] for r in test])
        actual=np.eye(3)[[r['label']+1 for r in test]]
        reports.append(dict(train_samples=len(train),test_samples=len(test),train_end=max(r['end'] for r in train),
            test_start=start,test_end=test[-1]['end'],brier=float(np.mean(np.sum((pred-actual)**2,axis=1))),
            baseline_brier=float(np.mean(np.sum((baseline-actual)**2,axis=1))),
            accuracy=float(np.mean(pred.argmax(axis=1)==actual.argmax(axis=1)))))
    return dict(status='EVALUATED' if reports else 'INSUFFICIENT_PURGED_DATA',samples=len(labels),folds=reports,
                probability_order=['SHORT','NO_TRADE','LONG'],deployment='NOT_APPROVED')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Offline chronological evaluation of recorded state JSONL')
    parser.add_argument('input',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--horizon',type=int,default=180);parser.add_argument('--barrier-bps',type=float,default=10)
    parser.add_argument('--cost-bps',type=float,default=20);args=parser.parse_args()
    states=[json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
    labels=triple_barrier([s['timestamp'] for s in states],[s['features']['mid'] for s in states],args.horizon,args.barrier_bps,args.barrier_bps,args.cost_bps)
    scores=[s['horizons'][str(args.horizon)]['swarm']['consensus'] for s in states]
    result=walk_forward(labels,scores,embargo_s=args.horizon)
    result.update(horizon=args.horizon,cost_bps=args.cost_bps,barrier_bps=args.barrier_bps,source=str(args.input))
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result['status'])
