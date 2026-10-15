"""Optional read-only adapter for the owner's private Backtest Autopsy install.

Run with that platform's existing Python environment. Its source is not copied
or required for the public factor/bootstrap/economic diagnostics. Raw reports
stay in --private-output; the selected, qualified receipt is --receipt.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--platform',type=Path,required=True)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    a = p.parse_args()
    if a.receipt.exists():
        raise FileExistsError(a.receipt)
    a.private_output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.platform/'src'))
    from backtest_autopsy.engine import run_audit, result_json
    from backtest_autopsy.metrics import performance_metrics, benchmark_metrics
    # Compatibility probes occur before the actual strategy audit.
    initial_loss = performance_metrics(np.array([-.1,.1]),252)['max_drawdown']
    active = benchmark_metrics(np.array([.1,.1]),np.array([0.,.1]),252)['active_total_return']
    probes = {'initial_loss_drawdown':{'platform':initial_loss,'accounting_reference':-.1,
               'compatible':bool(np.isclose(initial_loss,-.1))},
              'active_wealth':{'platform_active_total_return':active,'relative_wealth_reference':1.21/1.1-1,
               'wealth_difference_reference':1.21-1.1,
               'definition':'platform compounds daily arithmetic active returns; not wealth difference'}}
    sources = ['crsp_nominal_stale_freeze','crsp_split_stale_freeze','yahoo_close_quote_freeze']
    receipt = {'created_at':datetime.now(timezone.utc).isoformat(),
        'platform_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.platform,text=True).strip(),
        'platform_files':{str(f.relative_to(a.platform)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest()
                          for f in sorted((a.platform/'src/backtest_autopsy').glob('*.py'))},
        'compatibility_probes':probes, 'series':{},
        'withheld_statistics':{'drawdown_and_calmar':'Initial wealth omitted by reused metric. Use validated study ledger.',
            'sortino':'Different downside convention; not used.',
            'active_total_return':'Not relative wealth or wealth difference; no benchmark supplied.',
            'IID_bootstrap':'Use separate dependence-aware paired blocks.',
            'platform_cost_scenarios_and_COST_ECONOMIC_ERASURE':'No instrument trade records supplied; zero inferred turnover is not actual turnover.'},
        'scope':'Same-agent independent component, not an external review or clean audit badge. Only aggregate returns supplied.'}
    for source in sources:
        folder = a.private_output/source
        folder.mkdir()
        source_path = a.input/(source+'-annual-daily.csv')
        with source_path.open(encoding='utf-8',newline='') as handle:
            rows = list(csv.DictReader(handle))
        dates = [r['date'] for r in rows]
        if dates != sorted(set(dates)):
            raise ValueError('Unsorted/duplicate dates')
        values = np.array([[float(r['gross_pnl']),float(r['net_return'])] for r in rows])
        if not np.isfinite(values).all() or (values<=-1).any():
            raise ValueError('Invalid returns')
        with (folder/'returns.csv').open('w',encoding='utf-8',newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['date','gross_return','net_return'])
            writer.writerows(zip(dates,values[:,0],values[:,1]))
        cost = lambda b:{'commission_bps':0,'half_spread_bps':b,'slippage_bps':0,'impact_bps':0}
        config = {'schema_version':'1.0','strategy_name':source,'timezone':'UTC','return_unit':'decimal',
            'annualization_periods':252,'trading_calendar':'PROVIDED','execution_delay_seconds':0,'confidence_level':.95,
            'files':{'returns':'returns.csv','positions':None,'trades':None,'signals':None},
            'costs':{'low':cost(.6),'base':cost(2),'high':cost(10)},
            'research':{'sample_label':'MIXED','holdout_present':False,'walk_forward_present':True,'hypotheses_tested':None,
                'same_close_justification':'Optimistic reconstruction: prior-close signal executes at same close; extra-day sensitivity separately published.',
                'survivorship_bias_reviewed':True,'point_in_time_identifiers':False}}
        (folder/'config.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
        result = run_audit(folder/'config.json')
        raw = result_json(result)
        (folder/'raw-audit.json').write_text(raw,encoding='utf-8')
        perf = result.metrics['performance']['supplied_net']
        net = values[:,1]
        refs = {'observations':len(net),'total_return':float(np.prod(1+net)-1),
            'annualized_return':float(np.prod(1+net)**(252/len(net))-1),
            'annualized_volatility':float(net.std(ddof=1)*np.sqrt(252)),
            'sharpe':float(net.mean()/net.std(ddof=1)*np.sqrt(252))}
        for k,v in refs.items():
            if not np.isclose(perf[k],v,atol=5.1e-9,rtol=0):
                raise AssertionError(f'Metric mismatch: {source} {k}')
        stability = result.metrics['stability']
        gross = values[:,0]
        concentration = float(np.sort(gross)[-5:].sum()/gross.sum()) if gross.sum()>0 else None
        if concentration is not None and not np.isclose(concentration,stability['five_period_profit_concentration'],atol=5.1e-9,rtol=0):
            raise AssertionError('Concentration mismatch')
        receipt['series'][source] = {'input_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
            'raw_audit_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'verified_supplied_net_metrics':{k:perf[k] for k in refs},
            'gross_five_day_arithmetic_profit_share':stability['five_period_profit_concentration'],
            'gross_leave_one_year_out_sharpe':stability['leave_one_year_out_sharpe'],
            'gross_winsorized_1_99_sharpe':stability['winsorized_1_99']['sharpe'],
            'findings':[f.model_dump(mode='json') for f in result.findings if f.finding_id != 'COST_ECONOMIC_ERASURE'],
            'cost_interpretation':'COST_ZERO_TURNOVER means no optional trade file, not zero actual turnover. See separate ledger-based overlays.'}
    a.receipt.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'audited_series':len(sources),'receipt':a.receipt.name,'compatible_net_metrics_per_series':5}))


if __name__ == '__main__':
    main()
