"""Fixed 1,000-seed descriptive supplement, declared after the first 20 seeds.

Count matching is not spell/turnover matching. This is not a calibrated p-value
or a claim to recover the paper's unspecified randomization procedure.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from unicorn_edge.data import load_cache
from unicorn_edge.engine import BacktestConfig, backtest, metrics, training_scale
from unicorn_edge.signals import SignalConfig, make_signals


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    archive=Path('results/2026-10-14')
    baseline=pd.read_csv(archive/'summary.csv').set_index('case')
    original_windows=pd.read_csv(archive/'windows.csv').set_index(['case','test_year'])
    specification={'seeds':list(range(1000)),'test_years':[2010,2015,2020],
        'training_years':5,'reuse_original_seeds':list(range(20)),
        'original_summary_sha256':hashlib.sha256((archive/'summary.csv').read_bytes()).hexdigest(),
        'scope':'Descriptive supplemental null after the original 20 seeds were observed. Daily eligible counts matched; spell lengths, turnover and risk exposures are not. Not an inferential p-value or exact replication of the paper randomization.',
        'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}
    spec_path=args.output/'specification.json'
    if spec_path.exists():
        old=json.loads(spec_path.read_text())
        # A changed code commit is not silently accepted by a resumed experiment.
        if old!=specification:raise ValueError('Supplement specification changed; use a fresh directory')
    else:spec_path.write_text(json.dumps(specification,indent=2),encoding='utf-8')
    target=args.output/'seeds.csv';rows=pd.read_csv(target).to_dict('records') if target.exists() else []
    completed={int(r['seed']) for r in rows}
    close,adjusted,_,receipt=load_cache(args.cache,Path('docs/universe.csv'))
    returns=adjusted.pct_change(fill_method=None)
    for seed in range(1000):
        if seed in completed:continue
        row={'seed':seed,'source':'original frozen study' if seed<20 else 'supplement'}
        if seed<20:
            original=baseline.loc[f'random_gate_{seed:02d}']
            for key in ('sharpe','annual_mean','annual_volatility','total_return','max_drawdown','annual_turnover','annual_cost_drag'):
                row[key]=original[key]
            for year in (2010,2015,2020):row[f'scale_{year}']=original_windows.loc[(f'random_gate_{seed:02d}',year),'scale']
        else:
            weights=make_signals(close,adjusted,SignalConfig(mode='random_gate',random_seed=seed))['weights']
            paths=[]
            for year in (2010,2015,2020):
                train=backtest(returns,weights,f'{year-5}-01-01',f'{year}-01-01',BacktestConfig(kill_switch=False))
                scale=training_scale(train.net_return);row[f'scale_{year}']=scale
                paths.append(backtest(returns,weights,f'{year}-01-01',f'{year+1}-01-01',BacktestConfig(scale=scale)))
            result=pd.concat(paths);m=metrics(result.net_return)
            for key in ('sharpe','annual_mean','annual_volatility','total_return','max_drawdown'):row[key]=m[key]
            row['annual_turnover']=result.turnover.mean()*252
            row['annual_cost_drag']=result.trading_cost.mean()*252
        rows.append(row)
        temporary=target.with_suffix('.tmp');pd.DataFrame(rows).to_csv(temporary,index=False);temporary.replace(target)
        if seed%25==0 or seed==999:print(f'{len(rows)}/1000 seeds accounted for',flush=True)
    frame=pd.DataFrame(rows);primary=float(baseline.loc['primary','sharpe'])
    exceed=int(frame.sharpe.ge(primary).sum())
    report={'completed':len(frame),'seed_min':int(frame.seed.min()),'seed_max':int(frame.seed.max()),
        'primary_sharpe':primary,'at_least_primary':exceed,'descriptive_tail_fraction':exceed/len(frame),
        'random_sharpe_mean':float(frame.sharpe.mean()),'random_sharpe_min':float(frame.sharpe.min()),
        'random_sharpe_max':float(frame.sharpe.max()),
        'random_sharpe_quantiles':{str(q):float(frame.sharpe.quantile(q)) for q in (.025,.5,.975)},
        'mean_random_annual_turnover':float(frame.annual_turnover.mean()),
        'primary_annual_turnover':float(baseline.loc['primary','annual_turnover']),
        'interpretation':specification['scope'],
        'seed_table_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'specification_sha256':hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        'data_receipt_sha256':hashlib.sha256((args.cache/'receipt.json').read_bytes()).hexdigest()}
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
