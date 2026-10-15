"""Run every fixed public-output diagnostic; never consumes licensed securities."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels

from unicorn_edge.engine import metrics
from unicorn_edge.stress import (read_french_zip, factor_regression, paired_bootstrap,
                                cost_overlay, cost_summary, check_dates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--factors',type=Path,required=True)
    parser.add_argument('--input',type=Path,default=Path('results/2026-10-14/crsp-followup'))
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    ff = read_french_zip(args.factors/'ff5-daily.zip',['Mkt-RF','SMB','HML','RMW','CMA','RF'])
    mom = read_french_zip(args.factors/'momentum-daily.zip',['MOM'])
    # Outer join preserves uncovered dates; select exact study dates before validation.
    factors = ff.join(mom,how='outer')
    sources = {'crsp_nominal':'crsp_nominal_stale_freeze', 'crsp_split':'crsp_split_stale_freeze',
               'yahoo_matched':'yahoo_close_quote_freeze'}
    hashes = {}
    def read(name):
        path = args.input/name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = pd.read_csv(path,index_col='date',parse_dates=True)
        check_dates(frame[['net_return','gross_pnl']])
        return frame
    annual = {k:read(v+'-annual-daily.csv') for k,v in sources.items()}
    calendar = annual['crsp_nominal'].index
    if not all(f.index.equals(calendar) for f in annual.values()):
        raise ValueError('Annual calendars differ')
    aligned = factors.reindex(calendar)
    check_dates(aligned)
    regressions, periods, costs, ledgers = {}, [], [], {}
    for name, frame in annual.items():
        ledgers[name] = cost_summary(frame)
        regressions[name] = {}
        for model,cols in [('CAPM',['Mkt-RF']),('FF5_MOM',['Mkt-RF','SMB','HML','RMW','CMA','MOM'])]:
            for lag in (5,20):
                regressions[name][f'{model}_HAC{lag}'] = factor_regression(frame.net_return,aligned,cols,lag)
        for year in range(2010,2025):
            sample = frame.loc[frame.index.year == year]
            if sample.empty:
                raise ValueError(f'Missing year {year}')
            periods.append({'source':name,'period':str(year),'kind':'year',**metrics(sample.net_return)})
        for first,last in [(2010,2014),(2015,2019),(2020,2024)]:
            sample = frame.loc[(frame.index.year>=first)&(frame.index.year<=last)]
            periods.append({'source':name,'period':f'{first}-{last}','kind':'era',**metrics(sample.net_return)})
        for fee in (.6,1,2,5,10):
            for borrow in (0,.01,.03):
                costs.append({'source':name,'fee_bps':fee,'annual_borrow_rate':borrow,
                              'mode':'fixed_decision_overlay',**metrics(cost_overlay(frame,fee,borrow))})
    comparisons = {}
    pairs = [(f'annual_nominal_minus_{name}',annual['crsp_nominal'].net_return,annual[name].net_return,False)
             for name in ('crsp_split','yahoo_matched')]
    for name,source in sources.items():
        main_frame = read(source+'_gated_blend-daily.csv')
        reversal = read(source+'_gated_reversal-daily.csv')
        pairs.append((f'three_year_{name}_blend_minus_reversal',main_frame.net_return,reversal.net_return,True))
    for name,left,right,segmented in pairs:
        comparisons[name] = [paired_bootstrap(left,right,block=b,segmented_years=segmented) for b in (5,20,60)]
    def write(name,value):
        (args.output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    write('factor-regressions.json',regressions)
    write('paired-block-bootstrap.json',comparisons)
    write('ledger-and-economic-summary.json',ledgers)
    pd.DataFrame(periods).to_csv(args.output/'periods.csv',index=False)
    pd.DataFrame(costs).to_csv(args.output/'fixed-path-cost-overlays.csv',index=False)
    write('run-receipt.json',{'plan_commit':'a84c3ef','code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'input_hashes':hashes, 'factor_archives':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.factors.glob('*.zip'))},
        'factor_first':str(aligned.index[0].date()),'factor_last':str(aligned.index[-1].date()),'factor_observations':len(aligned),
        'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'statsmodels':statsmodels.__version__,
        'factor_vintage':'202608 CRSP database; current-vintage retrospective factors',
        'scope':'annual-reset current-member reconstruction; modeled missing-quote freezes; no new holdout',
        'cost_scope':'fixed recorded holdings/decisions; not rerun with new stops/scales; borrow rates illustrative',
        'cash_convention':'zero cash yield preserved; factor regressions subtract daily RF',
        'unavailable':['historical constituent membership','real borrow quotes and availability','empirical capacity','author code/extract']})
    print(json.dumps({'annual_series':len(annual),'regressions':12,'bootstrap_specifications':15,'cost_overlays':len(costs),'period_rows':len(periods)}))


if __name__ == '__main__':
    main()
