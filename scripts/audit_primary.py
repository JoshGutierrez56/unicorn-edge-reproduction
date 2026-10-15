"""Numerical challenger: direct-window signals and shares/cash with Brent fees.

This is a separate implementation, not an independent human review. It imports
the production signal builder only as the object under comparison, not the ledger.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import rankdata

from unicorn_edge.data import load_cache
from unicorn_edge.signals import SignalConfig, make_signals


def direct_weights(close, adjusted, t):
    prices=close[t]
    available=np.isfinite(prices)
    value=np.full(len(prices),np.nan)
    value[available]=rankdata(1/prices[available],method='average')/available.sum()
    reversal=-(adjusted[t]/adjusted[t-10]-1)
    reversal=(reversal-np.nanmean(reversal))/np.nanstd(reversal)
    base=.7*value+.3*reversal
    past=adjusted[t-63:t]/adjusted[t-64:t-1]-1
    eligible=np.isfinite(past).all(axis=0)&np.isfinite(base)&available&np.isfinite(adjusted[t])
    active=eligible&((past>0).mean(axis=0)>.6)&(base!=0)
    result=np.zeros(len(prices))
    if active.sum()<2 or np.std(base[active])<1e-12:
        return result
    score=(base[active]-base[active].mean())/base[active].std()
    positive=np.maximum(score,0);negative=np.maximum(-score,0)
    if positive.sum()>0 and negative.sum()>0:
        result[active]=.5*(positive/positive.sum()-negative/negative.sum())
    return result


def share_ledger(prices, targets, dates, start, end, scale, stops):
    locations=np.flatnonzero((dates>=pd.Timestamp(start))&(dates<pd.Timestamp(end)))
    shares=np.zeros(prices.shape[1]);cash=1.;path=[1.];peak=1.;stopped=False;rows=[]
    rate=.00006
    for n,t in enumerate(locations):
        before=prices[t-1];after=prices[t]
        prior_values=shares*np.where(np.isfinite(before),before,0)
        opening=cash+prior_values.sum()
        target=np.zeros(prices.shape[1]) if stopped else targets[t-1]*scale
        fee=brentq(lambda f: f-rate*np.abs(target*(opening-f)-prior_values).sum(),
                   0,opening,xtol=5e-15)
        desired=target*(opening-fee)
        if np.any((desired!=0)&(~np.isfinite(before)|~np.isfinite(after))):
            raise AssertionError('Missing price in independent held position')
        shares=np.divide(desired,before,out=np.zeros_like(desired),where=np.isfinite(before))
        cash=opening-fee-desired.sum()
        closing_values=shares*np.where(np.isfinite(after),after,0)
        nav=cash+closing_values.sum()
        peak=max(peak,nav)
        breached=stops and not stopped and (nav/peak-1<=-.30 or (len(path)>=63 and nav/path[-63]-1<=-.10))
        stopped=stopped or breached
        if breached or n==len(locations)-1:
            exit_fee=rate*np.abs(closing_values).sum()
            nav-=exit_fee;fee+=exit_fee
            cash=nav;shares[:]=0
        rows.append([nav,nav/opening-1,fee/opening,stopped])
        path.append(nav)
    return pd.DataFrame(rows,index=dates[locations],columns=['nav','net_return','trading_cost','stopped'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    close,adjusted,_,_=load_cache(args.cache,Path('docs/universe.csv'))
    weights=make_signals(close,adjusted,SignalConfig())['weights']
    # Evenly spaced deterministic dates cover the full available history.
    selected=np.linspace(65,len(close)-1,100,dtype=int)
    errors=[]
    for t in selected:
        errors.append(float(np.max(np.abs(direct_weights(close.to_numpy(),adjusted.to_numpy(),t)-weights.iloc[t].to_numpy()))))
    assert max(errors)<1e-12, max(errors)
    windows=pd.read_csv(args.results/'windows.csv').query("case == 'primary'")
    published=pd.read_csv(args.results/'primary-daily.csv',index_col='date',parse_dates=True)
    ledger_errors=[];scale_errors=[];training_count=0
    for year in (2010,2015,2020):
        train=share_ledger(adjusted.to_numpy(),weights.to_numpy(),weights.index,f'{year-5}-01-01',f'{year}-01-01',1.,False)
        training_count+=len(train)
        ret=train.net_return.to_numpy(dtype=float)
        wealth=np.r_[1.,train.nav.to_numpy(dtype=float)]
        dd=abs(np.min(wealth/np.maximum.accumulate(wealth)-1))
        scale=min(.12/(np.std(ret,ddof=1)*np.sqrt(252)),.15/dd)
        expected=float(windows.loc[windows.test_year==year,'scale'].iloc[0])
        scale_errors.append(abs(scale-expected))
        test=share_ledger(adjusted.to_numpy(),weights.to_numpy(),weights.index,f'{year}-01-01',f'{year+1}-01-01',scale,True)
        target=published.loc[test.index]
        differences={c:float(np.max(np.abs(test[c].to_numpy(dtype=float)-target[c].to_numpy(dtype=float)))) for c in ('nav','net_return','trading_cost')}
        assert np.array_equal(test.stopped.to_numpy(dtype=bool),target.stopped.to_numpy(dtype=bool))
        assert max(differences.values())<1e-10,differences
        ledger_errors.append({'year':year,'observations':len(test),'maximum_absolute_errors':differences})
    assert max(scale_errors)<1e-10,scale_errors
    result={'status':'passed','signal_dates_checked':len(selected),'signal_weight_max_absolute_error':max(errors),
            'training_return_observations':training_count,'evaluation_return_observations':len(published),
            'training_scale_max_absolute_error':max(scale_errors),'ledger_comparisons':ledger_errors,
            'method':'Direct array slices and scipy rankdata versus pandas rolling/rank; independent share/cash ledger and Brent root versus dollar-holdings fixed-point engine.',
            'scope':'Separate numerical implementation by the same authoring agent; not independent human validation and not a repair of membership/price-vintage bias.',
            'audited_run_sha256':hashlib.sha256((args.results/'run-receipt.json').read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
