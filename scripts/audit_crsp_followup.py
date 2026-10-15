"""Separate direct-slice/share ledger check of the completed CRSP primary cases.

Same authoring agent, not independent human review. This checks calculations,
not the original author's code, provider accuracy or future investment usefulness.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import rankdata

from unicorn_edge.crsp_data import load_crsp_cache
from unicorn_edge.data import load_cache
from unicorn_edge.signals import SignalConfig, make_signals


def direct_weights(price, returns, mask, t):
    available=mask[t] & np.isfinite(price[t])
    value=np.full(price.shape[1],np.nan)
    value[available]=rankdata(1/price[t,available],method='average')/available.sum()
    short_history=returns[t-9:t+1]
    good_short=np.isfinite(short_history).all(axis=0) & available
    reversal=np.full(price.shape[1],np.nan)
    reversal[good_short]=1-np.prod(1+short_history[:,good_short],axis=0)
    if good_short.sum()<2 or np.nanstd(reversal)<=1e-12:return np.zeros(price.shape[1])
    reversal=(reversal-np.nanmean(reversal))/np.nanstd(reversal)
    base=.7*value+.3*reversal
    past=returns[t-63:t]
    gate=np.isfinite(past).all(axis=0) & (np.sum(past>0,axis=0)>=38)
    active=gate & available & np.isfinite(returns[t]) & np.isfinite(base) & (base!=0)
    result=np.zeros(price.shape[1])
    if active.sum()<2 or np.std(base[active])<=1e-12:return result
    score=(base[active]-base[active].mean())/base[active].std()
    pos=np.maximum(score,0);neg=np.maximum(-score,0)
    if pos.sum()>0 and neg.sum()>0:result[active]=.5*(pos/pos.sum()-neg/neg.sum())
    return result


def independent_ledger(returns, weights, quotes, start, end, scale, stops):
    dates=returns.index
    values=returns.to_numpy(float)
    # Unit indices are bookkeeping coordinates, NOT substituted signal returns.
    # An exposed missing return below is still a hard failure.
    units=np.cumprod(1+np.where(np.isfinite(values),values,0.),axis=0)
    targets=weights.to_numpy(float);available=quotes.to_numpy(bool)
    locations=np.flatnonzero((dates>=pd.Timestamp(start))&(dates<pd.Timestamp(end)))
    shares=np.zeros(values.shape[1]);cash=1.;history=[1.];peak=1.;stopped=False;rows=[]
    rate=.00006
    for n,t in enumerate(locations):
        before=units[t-1];after=units[t]
        marked=shares*before;opening=cash+marked.sum()
        target=np.zeros_like(shares) if stopped else targets[t-1]*scale
        can_trade=available[t-1]
        fee=brentq(lambda f:f-rate*np.abs(target[can_trade]*(opening-f)-marked[can_trade]).sum(),
                   0.,opening,xtol=5e-15)
        new_shares=shares.copy()
        new_shares[can_trade]=target[can_trade]*(opening-fee)/before[can_trade]
        cash-=np.sum((new_shares-shares)*before)+fee
        shares=new_shares
        if np.any((np.abs(shares*before)>1e-14)&~np.isfinite(values[t])):
            raise AssertionError('Independent ledger has an unresolved held return')
        closing=shares*after;nav=cash+closing.sum();peak=max(peak,nav)
        breached=stops and not stopped and (nav/peak-1<=-.30 or (len(history)>=63 and nav/history[-63]-1<=-.10))
        stopped=stopped or breached
        if stopped or n==len(locations)-1:
            can_close=available[t]
            exit_fee=rate*np.abs(closing[can_close]).sum()
            cash+=closing[can_close].sum()-exit_fee
            shares[can_close]=0.;fee+=exit_fee
            nav=cash+(shares*after).sum()
            if n==len(locations)-1 and np.any(np.abs(shares*after)>1e-14):
                raise AssertionError('Independent final exit unavailable')
        rows.append([nav,nav/opening-1,fee/opening,stopped]);history.append(nav)
    return pd.DataFrame(rows,index=dates[locations],columns=['nav','net_return','trading_cost','stopped'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('crsp','yahoo','results','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Audit output already exists')
    nominal,adjusted,observed,valuation,quotes,_=load_crsp_cache(args.crsp)
    yc,ya,_,_=load_cache(args.yahoo,Path('docs/universe.csv'))
    common=sorted(s for s in set(nominal)&set(yc) if nominal[s].notna().any() and adjusted[s].notna().any())
    nominal,adjusted,observed,valuation,quotes,yc,ya=[x[common] for x in (nominal,adjusted,observed,valuation,quotes,yc,ya)]
    yr=ya.pct_change(fill_method=None)
    mask=nominal.notna()&adjusted.notna()&observed.notna()&yc.notna()&ya.notna()&yr.notna()
    panels={'yahoo_close_quote_freeze':(yc,yr,yr),'crsp_nominal_stale_freeze':(nominal,observed,valuation),
            'crsp_split_stale_freeze':(adjusted,observed,valuation)}
    windows=pd.read_csv(args.results/'windows.csv')
    audits=[];max_signal=0.;max_scale=0.;training_count=0;test_count=0
    selected=np.linspace(65,len(nominal)-1,100,dtype=int)
    for source,(price,signal_returns,valuation_returns) in panels.items():
        weights=make_signals(price,None,SignalConfig(),explicit_returns=signal_returns,universe_mask=mask)['weights']
        for t in selected:
            error=float(np.max(np.abs(direct_weights(price.to_numpy(),signal_returns.to_numpy(),mask.to_numpy(),t)-weights.iloc[t].to_numpy())))
            max_signal=max(max_signal,error)
        assert max_signal<1e-12,max_signal
        case=source+'_gated_blend'
        published=pd.read_csv(args.results/(case+'-daily.csv'),index_col='date',parse_dates=True)
        for year in (2010,2015,2020):
            train=independent_ledger(valuation_returns,weights,quotes,f'{year-5}-01-01',f'{year}-01-01',1.,False)
            r=train.net_return.to_numpy(float);wealth=np.r_[1.,train.nav.to_numpy(float)]
            drawdown=abs(np.min(wealth/np.maximum.accumulate(wealth)-1))
            scale=min(.12/(np.std(r,ddof=1)*np.sqrt(252)),.15/drawdown if drawdown>1e-14 else np.inf)
            expected=float(windows.loc[(windows.case==case)&(windows.year==year),'scale'].iloc[0])
            max_scale=max(max_scale,abs(scale-expected));training_count+=len(train)
            test=independent_ledger(valuation_returns,weights,quotes,f'{year}-01-01',f'{year+1}-01-01',scale,True)
            target=published.loc[test.index];test_count+=len(test)
            errors={c:float(np.max(np.abs(test[c].to_numpy(float)-target[c].to_numpy(float)))) for c in ('nav','net_return','trading_cost')}
            assert max(errors.values())<1e-10,errors
            assert np.array_equal(test.stopped.to_numpy(bool),target.stopped.to_numpy(bool))
            audits.append({'case':case,'year':year,'observations':len(test),'maximum_absolute_errors':errors})
        print(f'{source}: direct signals and three training/test ledgers reconciled',flush=True)
    assert max_scale<1e-10,max_scale
    result={'status':'passed','signal_dates_checked':3*len(selected),'signal_weight_max_absolute_error':max_signal,
            'training_return_observations':training_count,'evaluation_return_observations':test_count,
            'training_scale_max_absolute_error':max_scale,'ledger_comparisons':audits,
            'method':'Direct return slices and scipy rankdata; separate total-return-unit shares/cash ledger with Brent fee solver and explicit quote locks.',
            'scope':'Same authoring agent; not independent human review, source-data certification or removal of survivorship bias.',
            'audited_run_sha256':hashlib.sha256((args.results/'receipt.json').read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='ledger_comparisons'},indent=2))


if __name__=='__main__':main()
