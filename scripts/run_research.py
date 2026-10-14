"""Run the predeclared methodological reproduction, preserving every result."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from unicorn_edge.data import load_cache
from unicorn_edge.engine import BacktestConfig, NoTrainingVariationError, backtest, metrics, training_scale
from unicorn_edge.signals import SignalConfig, make_signals


def specs():
    signal = SignalConfig()
    engine = BacktestConfig()
    cases = [("primary",signal,engine,"close","own"),
             ("ungated_blend",replace(signal,mode="ungated"),engine,"close","own"),
             ("gated_inverse_price",replace(signal,mode="gated_value"),engine,"close","own"),
             ("gated_reversal",replace(signal,mode="gated_reversal"),engine,"close","own"),
             ("equal_side_weights",replace(signal,equal_side=True),engine,"close","own"),
             ("extra_execution_day",signal,replace(engine,signal_lag=2),"close","primary"),
             ("double_cost",signal,replace(engine,cost_bps=1.2),"close","primary"),
             ("cost_10bps",signal,replace(engine,cost_bps=10),"close","primary"),
             ("borrow_100bps",signal,replace(engine,borrow_bps_annual=100),"close","primary"),
             ("leverage_capped",signal,engine,"close","capped"),
             ("adjusted_price_rank",signal,engine,"adjusted","own"),
             ("close_return_signals",signal,engine,"close_signals","own"),
             ("nominal_unit_change",signal,engine,"units","own"),
             ("no_kill_switch",signal,replace(engine,kill_switch=False),"close","primary"),
             ("INVALID_same_day_leakage",signal,replace(engine,signal_lag=0),"close","primary")]
    for threshold in (.42,.51,.69,.78):
        cases.append((f"threshold_{threshold:.2f}",replace(signal,threshold=threshold),engine,"close","own"))
    for window in (44,54,72,82):
        cases.append((f"window_{window}",replace(signal,window=window),engine,"close","own"))
    for alpha in (.49,.60,.81,.91):
        cases.append((f"value_weight_{alpha:.2f}",replace(signal,value_weight=alpha),engine,"close","own"))
    for seed in range(20):
        cases.append((f"random_gate_{seed:02d}",replace(signal,mode="random_gate",random_seed=seed),engine,"close","own"))
    return cases


def bootstrap_sharpe(years: list[pd.Series], seed: int = 426, replications: int = 1000):
    """Conditional circular 20-session blocks, sampled separately within each year."""
    rng = np.random.default_rng(seed)
    estimates=[]
    for _ in range(replications):
        sample=[]
        for series in years:
            a=series.to_numpy()
            starts=rng.integers(0,len(a),int(np.ceil(len(a)/20)))
            positions=((starts[:,None]+np.arange(20))%len(a)).ravel()[:len(a)]
            sample.append(a[positions])
        joined=np.concatenate(sample)
        vol=joined.std(ddof=1)
        if vol>1e-14:estimates.append(joined.mean()/vol*np.sqrt(252))
    return {"low":float(np.quantile(estimates,.025)),"high":float(np.quantile(estimates,.975)),
            "replications":replications,"block_sessions":20,"seed":seed,
            "scope":"Conditional on these selected, survivor-biased years; not a correction for selection or data bias."}


def paper_arithmetic():
    growth=np.array([3.067,3.072,1.62])
    wealth=[1_000_000,3_067_000,9_415_000,110_376_000]
    year3=wealth[3]/wealth[2]
    return {"paper":"arXiv:2511.12490v1", "reported_year_returns":[2.067,2.072,.620],
            "wealth_multiple_if_geometric":float(np.prod(growth)),
            "reported_table3_final_multiple":wealth[-1]/wealth[0],
            "table3_implied_year3_return":year3-1,
            "reported_year3_return":.620,
            "upper_wealth_if_annual_arithmetic_mean_62pct_253_sessions":float(np.exp(.62*253/252)),
            "table3_year3_wealth_multiple":year3,
            "reason":"For daily returns above -100%, log(wealth) <= sum(simple returns). The final table3 step cannot be reconciled to a one-year 62% arithmetic annual mean, nor to a 62% geometric annual return.",
            "threshold_sensitivity":{"abstract_claim":"Sharpe above 7 under 30% perturbations", "table6_values":[3.2,4.1]},
            "scope":"Arithmetic incompatibility under the paper's stated one-year windows; no claim about intent."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('results/current'))
    parser.add_argument('--only-primary',action='store_true',help='Development smoke run, not the full promised suite')
    args=parser.parse_args()
    output=args.output
    output.mkdir(parents=True,exist_ok=True)
    if (output/'summary.csv').exists():
        raise SystemExit('Refusing to overwrite a prior result set; choose a new output directory')
    chosen=specs()[:1] if args.only_primary else specs()
    protocol={'windows':[2010,2015,2020], 'alternate_endpoints':[2011,2016,2021],
              'training_years':5,'random_gate_replicates':20,'unit_change_seed':314,
              'cases':[{'name':n,'signal':asdict(s),'engine':asdict(e),'price_mode':p,'scale_source':c} for n,s,e,p,c in chosen],
              'notes':['Signal-lag1 is optimistic same-close execution; lag2 adds a full session.',
                       'Cost, borrow and lag stress cases hold the primary training scale fixed.',
                       'Other specification baselines calibrate their own scale on their own five-year training sample.',
                       'Training scaling excludes kill switches; evaluation includes them except the named ablation.',
                       '20 random gates match daily counts, not spell lengths; this does not replicate the paper\'s 1000-gate null distribution.',
                       'Additional annual evaluation is retrospective, with year-end liquidation and annual restart, not an untouched holdout.',
                       'Missing provider histories are explicitly recorded; no substitution or synthetic fallback.',
                       'Amendment after partial v1: zero-variation training is recorded as uncalibratable, never assigned an invented scale or dropped silently. No aggregate is reported for an incomplete case.']}
    protocol_text=json.dumps(protocol,indent=2,sort_keys=True)
    (output/'run-specification.json').write_text(protocol_text,encoding='utf-8')
    print('Frozen run specification SHA256:',hashlib.sha256(protocol_text.encode()).hexdigest(),flush=True)
    close,adjusted,spy,receipt=load_cache(args.cache,Path('docs/universe.csv'))
    returns=adjusted.pct_change(fill_method=None)
    coverage=pd.DataFrame({'observed_prices':close.notna().sum(axis=1),'observed_returns':returns.notna().sum(axis=1)})
    coverage.to_csv(output/'coverage.csv',index_label='date')
    (output/'data-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    (output/'paper-arithmetic.json').write_text(json.dumps(paper_arithmetic(),indent=2),encoding='utf-8')
    summaries=[]; window_rows=[]; primary_scales={}; signals_cache={}; primary_years=[]; unavailable=[]
    all_daily={}
    for name,signal_config,engine_config,price_mode,scale_source in chosen:
        key=(signal_config,price_mode)
        if key not in signals_cache:
            signal_prices=close
            return_prices=adjusted
            if price_mode=='adjusted':signal_prices=adjusted
            if price_mode=='close_signals':return_prices=close
            if price_mode=='units':
                units=np.random.default_rng(314).choice([.1,1.,10.],len(close.columns))
                signal_prices=close*units
            signals=make_signals(signal_prices,return_prices,signal_config)
            if name=='primary':
                coverage['eligible']=signals['eligible'].sum(axis=1)
                coverage['gate_active']=signals['gate'].sum(axis=1)
                coverage.to_csv(output/'coverage.csv',index_label='date')
            weights=signals['weights']
            # Keep only reused primary weights to avoid retaining 47 large panels.
            if signal_config==SignalConfig() and price_mode=='close':signals_cache[key]=weights
        else:
            weights=signals_cache[key]
        paths=[]; failed_years=[]
        for year in (2010,2015,2020):
            training=backtest(returns,weights,f'{year-5}-01-01',f'{year}-01-01',replace(engine_config,scale=1,kill_switch=False))
            if scale_source in {'primary','capped'}:
                scale=primary_scales[year]
                if scale_source=='capped':scale=min(scale,1.)
            else:
                try:
                    scale=training_scale(training['net_return'])
                except NoTrainingVariationError as exc:
                    failed_years.append({'test_year':year,'reason':str(exc),
                                         'training_observations':len(training),
                                         'training_nonzero_returns':int(training.net_return.ne(0).sum())})
                    continue
            if name=='primary':primary_scales[year]=scale
            test=backtest(returns,weights,f'{year}-01-01',f'{year+1}-01-01',replace(engine_config,scale=scale))
            paths.append(test)
            window_rows.append({'case':name,'test_year':year,'scale':scale,
                                'train_sharpe':metrics(training['net_return'])['sharpe'],
                                **metrics(test['net_return']),'stop_events':int(test['stop_reason'].ne('').sum()),
                                'mean_long_names':test['long_count'].mean(),'mean_short_names':test['short_count'].mean(),
                                'mean_gross_exposure':test['gross_exposure'].mean(),'annual_turnover':test['turnover'].mean()*252,
                                'annual_cost_drag':test['trading_cost'].mean()*252})
            if name=='primary':primary_years.append(test['net_return'])
        if failed_years:
            failure={'case':name,'status':'uncalibratable','failed_windows':failed_years,
                     'completed_windows':len(paths),'aggregate_reported':False}
            unavailable.append(failure)
            (output/'unavailable-cases.json').write_text(json.dumps(unavailable,indent=2),encoding='utf-8')
            if paths:
                pd.concat(paths).to_csv(output/(name+'-PARTIAL-daily.csv'),index_label='date')
            print(name,json.dumps(failure),flush=True)
            continue
        joined=pd.concat(paths)
        joined.to_csv(output/(name+'-daily.csv'),index_label='date')
        summary={'case':name,**metrics(joined['net_return']),
                 'mean_gross_exposure':joined['gross_exposure'].mean(),'annual_turnover':joined['turnover'].mean()*252,
                 'annual_cost_drag':joined['trading_cost'].mean()*252,'stop_events':int(joined['stop_reason'].ne('').sum()),
                 'valid_timing':engine_config.signal_lag>0}
        summaries.append(summary)
        all_daily[name]=joined['net_return']
        print(name,json.dumps(summary,default=float),flush=True)
        pd.DataFrame(summaries).to_csv(output/'summary.csv',index=False)
        pd.DataFrame(window_rows).to_csv(output/'windows.csv',index=False)
    (output/'primary-sharpe-interval.json').write_text(json.dumps(bootstrap_sharpe(primary_years),indent=2))
    if not args.only_primary:
        equal=make_signals(close,adjusted,SignalConfig(mode='equal_weight'))['weights']
        equal_paths=[]
        for year in (2010,2015,2020):
            equal_paths.append(backtest(returns,equal,f'{year}-01-01',f'{year+1}-01-01',BacktestConfig(kill_switch=False)))
        ew=pd.concat(equal_paths)
        ew.to_csv(output/'equal-weight-universe-daily.csv',index_label='date')
        spy_returns=spy.pct_change(fill_method=None).reindex(ew.index)
        benchmarks=[{'case':'Equal weight current members with signal history; daily rebalanced; costed',**metrics(ew.net_return)},
                    {'case':'SPY adjusted-price buy-and-hold; no trading cost; metric-only',**metrics(spy_returns)}]
        pd.DataFrame(benchmarks).to_csv(output/'benchmarks.csv',index=False)
        other=[]; annual=[]
        weights=signals_cache[(SignalConfig(),'close')]
        for year in range(2010,2025):
            train=backtest(returns,weights,f'{year-5}-01-01',f'{year}-01-01',BacktestConfig(kill_switch=False))
            scale=training_scale(train.net_return)
            test=backtest(returns,weights,f'{year}-01-01',f'{year+1}-01-01',BacktestConfig(scale=scale))
            other.append({'year':year,'scale':scale,**metrics(test.net_return),'stopped':bool(test.stopped.any())})
            annual.append(test)
        pd.DataFrame(other).to_csv(output/'annual-walk-forward.csv',index=False)
        pd.concat(annual).to_csv(output/'annual-walk-forward-daily.csv',index_label='date')
        alternate=pd.concat([x for x in annual if x.index[0].year in (2011,2016,2021)])
        (output/'alternate-endpoints.json').write_text(json.dumps(metrics(alternate.net_return),indent=2))
    tracked=subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
    hashes={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in tracked if f and Path(f).is_file()}
    receipt={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
             'working_tree_clean':not bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
             'source_sha256':hashes,'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,
             'protocol_sha256':hashlib.sha256(protocol_text.encode()).hexdigest(),
             'output_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in output.iterdir() if f.is_file()},
             'scope':'Methodological reproduction; current membership and current-vintage public prices; no investability certification.'}
    (output/'run-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('Accounted for',len(summaries)+len(unavailable),'specified strategy cases:',len(summaries),'complete,',len(unavailable),'uncalibratable.',flush=True)


if __name__=='__main__':main()
