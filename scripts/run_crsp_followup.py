"""Frozen paired-source diagnostic; no parameter search and no licensed exports."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from unicorn_edge.crsp_data import load_crsp_cache
from unicorn_edge.data import load_cache
from unicorn_edge.engine import BacktestConfig,backtest,metrics,training_scale
from unicorn_edge.signals import SignalConfig,make_signals


def dump(path,value):path.write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crsp',type=Path,required=True)
    parser.add_argument('--yahoo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output
    if out.exists() and list(out.iterdir()):raise ValueError('Use a new output directory; prior outcomes are never overwritten.')
    out.mkdir(parents=True,exist_ok=True)
    versions=subprocess.check_output(['git','status','--porcelain'],text=True)
    if versions.strip():raise ValueError('Freeze/commit the implementation before evaluating outcomes.')
    cases=[]
    for source in ('yahoo_close','crsp_nominal','crsp_split_adjusted'):
        for mode in ('gated_blend','gated_reversal','ungated'):
            cases.append({'name':f'{source}_{mode}','source':source,'mode':mode,'lag':1,'cost_bps':.6})
        cases.extend([{'name':f'{source}_extra_day','source':source,'mode':'gated_blend','lag':2,'cost_bps':.6},
                      {'name':f'{source}_cost_10bps','source':source,'mode':'gated_blend','lag':1,'cost_bps':10.}])
    specification={'cases':cases,'test_years':[2010,2015,2020],'training_years':5,
                   'annual_retrospective':{'years':list(range(2010,2025)),'modes':['gated_blend'],'sources':['yahoo_close','crsp_nominal','crsp_split_adjusted']},
                   'signal':asdict(SignalConfig()),'engine_default':asdict(BacktestConfig()),
                   'common_observation_rule':'Same permanent-ID-resolved current symbols, with valid observed Yahoo/CIZ prices and returns on the signal date; same mask applies before cross-sectional ranking. Past return lookbacks retain each provider observations. Missing held returns fail, never zero fill.',
                   'original_results_seen':True,'historical_membership':'BLOCKED: crsp_a_indexes permission denied; no PIT membership result',
                   'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                   'started_utc':datetime.now(timezone.utc).isoformat()}
    dump(out/'specification.json',specification)
    nominal,adjusted,crsp_returns,quality=load_crsp_cache(args.crsp)
    yahoo_close,yahoo_adjusted,_,yahoo_receipt=load_cache(args.yahoo,Path('docs/universe.csv'))
    if not nominal.index.equals(yahoo_close.index):raise ValueError('Provider calendars differ; inspect before pairing.')
    common=sorted(set(nominal.columns)&set(yahoo_close.columns))
    common=[s for s in common if nominal[s].notna().any() and adjusted[s].notna().any()]
    nominal,adjusted,crsp_returns=[f[common] for f in (nominal,adjusted,crsp_returns)]
    yahoo_close,yahoo_adjusted=yahoo_close[common],yahoo_adjusted[common]
    yahoo_returns=yahoo_adjusted.pct_change(fill_method=None)
    mask=nominal.notna()&adjusted.notna()&crsp_returns.notna()&yahoo_close.notna()&yahoo_adjusted.notna()&yahoo_returns.notna()
    quality.update({'common_symbols':len(common),'common_signal_observations':int(mask.sum().sum()),
                    'yahoo_receipt_sha256':sha(args.yahoo/'receipt.json'),
                    'scope':'Retrospective current-member intersection, not historical S&P membership or exact author data.'})
    # Remove licensed candidate identifiers from the public aggregate receipt.
    quality['unresolved_mappings']=[{k:v for k,v in row.items() if k in ('symbol','status')} for row in quality['unresolved_mappings']]
    dump(out/'data-quality.json',quality)
    pd.DataFrame({'common_observed_names':mask.sum(axis=1)}).to_csv(out/'coverage.csv',index_label='date')
    differences=(crsp_returns-yahoo_returns).where(mask).stack()
    dump(out/'provider-return-comparison.json',{'paired_security_days':len(differences),
         'median_absolute_difference':float(differences.abs().median()),
         'mean_absolute_difference':float(differences.abs().mean()),
         'fraction_abs_difference_above_1bp':float(differences.abs().gt(.0001).mean()),
         'note':'Aggregate observation comparison, not proof of equivalent security histories, prices or execution.'})
    inputs={'yahoo_close':(yahoo_close,yahoo_returns),
            'crsp_nominal':(nominal,crsp_returns),'crsp_split_adjusted':(adjusted,crsp_returns)}
    weights_cache={};summaries=[];windows=[];failures=[]
    for case in cases:
        key=(case['source'],case['mode'])
        if key not in weights_cache:
            price,returns=inputs[case['source']]
            signal=make_signals(price,None,SignalConfig(mode=case['mode']),explicit_returns=returns,universe_mask=mask)
            weights_cache[key]=signal['weights']
            pd.DataFrame({'eligible':signal['eligible'].sum(axis=1),'active_gate':signal['gate'].sum(axis=1)}).to_csv(out/f"{case['name']}-gate-counts.csv",index_label='date')
        weights=weights_cache[key];returns=inputs[case['source']][1];paths=[];bad=[]
        for year in (2010,2015,2020):
            try:
                train=backtest(returns,weights,f'{year-5}-01-01',f'{year}-01-01',BacktestConfig(signal_lag=case['lag'],cost_bps=case['cost_bps'],kill_switch=False))
                scale=training_scale(train.net_return)
                daily=backtest(returns,weights,f'{year}-01-01',f'{year+1}-01-01',BacktestConfig(signal_lag=case['lag'],cost_bps=case['cost_bps'],scale=scale))
                paths.append(daily)
                windows.append({'case':case['name'],'year':year,'scale':scale,**metrics(daily.net_return)})
            except ValueError as e:
                bad.append({'case':case['name'],'year':year,'reason':str(e)})
        failures.extend(bad)
        if paths:
            path=pd.concat(paths)
            path.to_csv(out/f"{'PARTIAL-' if bad else ''}{case['name']}-daily.csv",index_label='date')
            if not bad:summaries.append({'case':case['name'],**metrics(path.net_return),'annual_turnover':float(path.turnover.mean()*252),'annual_cost_drag':float(path.trading_cost.mean()*252)})
        print(f"{case['name']}: {'BLOCKED '+str(len(bad))+' windows' if bad else 'complete'}",flush=True)
    pd.DataFrame(summaries).to_csv(out/'summary.csv',index=False)
    pd.DataFrame(windows).to_csv(out/'windows.csv',index=False)
    annual=[]
    for source in inputs:
        weights=weights_cache[(source,'gated_blend')];returns=inputs[source][1];paths=[]
        for year in range(2010,2025):
            try:
                train=backtest(returns,weights,f'{year-5}-01-01',f'{year}-01-01',BacktestConfig(kill_switch=False))
                scale=training_scale(train.net_return)
                path=backtest(returns,weights,f'{year}-01-01',f'{year+1}-01-01',BacktestConfig(scale=scale))
                paths.append(path);annual.append({'source':source,'year':year,'scale':scale,**metrics(path.net_return)})
            except ValueError as e:failures.append({'case':source+'_annual','year':year,'reason':str(e)})
        if len(paths)==15:
            daily=pd.concat(paths);daily.to_csv(out/f'{source}-annual-daily.csv',index_label='date')
            dump(out/f'{source}-annual-summary.json',metrics(daily.net_return))
        print(f'{source}: {len(paths)}/15 annual windows complete',flush=True)
    pd.DataFrame(annual).to_csv(out/'annual-windows.csv',index=False)
    dump(out/'blocked-windows.json',failures)
    receipt={'completed_utc':datetime.now(timezone.utc).isoformat(),'complete_cases':len(summaries),'declared_cases':len(cases),
             'failed_windows':len(failures),'files':{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()},
             'code_commit':specification['commit'],'source_hashes':{str(p):sha(p) for p in sorted(Path('src/unicorn_edge').glob('*.py'))}}
    dump(out/'receipt.json',receipt)
    print(json.dumps({'complete_cases':len(summaries),'failed_windows':len(failures),'common_symbols':len(common)}),flush=True)


if __name__=='__main__':main()
