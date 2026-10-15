"""Check that frozen public claims reconcile to the published daily records."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]/'results'/'2026-10-14'


def test_random_gate_supplement_preserves_all_seeds_and_original_results():
    folder=ROOT/'random-gate-1000'
    spec=json.loads((folder/'specification.json').read_text())
    report=json.loads((folder/'report.json').read_text())
    seeds=pd.read_csv(folder/'seeds.csv')
    assert sorted(seeds.seed)==spec['seeds']==list(range(1000))
    assert seeds.seed.is_unique
    assert np.isfinite(seeds.select_dtypes('number')).all().all()
    assert hashlib.sha256((folder/'seeds.csv').read_bytes()).hexdigest()==report['seed_table_sha256']
    assert hashlib.sha256((folder/'specification.json').read_bytes()).hexdigest()==report['specification_sha256']
    assert hashlib.sha256((ROOT/'summary.csv').read_bytes()).hexdigest()==spec['original_summary_sha256']
    original=pd.read_csv(ROOT/'summary.csv').set_index('case')
    for row in seeds.loc[seeds.seed<20].itertuples():
        for key in ('sharpe','annual_mean','annual_volatility','total_return','max_drawdown','annual_turnover','annual_cost_drag'):
            assert getattr(row,key)==pytest.approx(original.loc[f'random_gate_{row.seed:02d}',key],abs=1e-12)


def test_random_gate_report_is_a_reconciled_descriptive_summary():
    folder=ROOT/'random-gate-1000'
    report=json.loads((folder/'report.json').read_text())
    seeds=pd.read_csv(folder/'seeds.csv')
    original=pd.read_csv(ROOT/'summary.csv').set_index('case')
    assert report['primary_sharpe']==pytest.approx(original.loc['primary','sharpe'])
    assert report['completed']==len(seeds)==1000
    assert report['at_least_primary']==int(seeds.sharpe.ge(report['primary_sharpe']).sum())==142
    assert report['descriptive_tail_fraction']==report['at_least_primary']/len(seeds)
    for key,actual in [('mean',seeds.sharpe.mean()),('min',seeds.sharpe.min()),('max',seeds.sharpe.max())]:
        assert report[f'random_sharpe_{key}']==pytest.approx(actual)
    for q,value in report['random_sharpe_quantiles'].items():
        assert value==pytest.approx(seeds.sharpe.quantile(float(q)))
    assert report['mean_random_annual_turnover']==pytest.approx(seeds.annual_turnover.mean())
    assert 'Not an inferential p-value' in report['interpretation']


def test_every_original_run_output_retains_its_recorded_bytes():
    receipt=json.loads((ROOT/'run-receipt.json').read_text())
    assert receipt['working_tree_clean']
    for name,digest in receipt['output_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    audit=json.loads((ROOT/'numerical-audit.json').read_text())
    assert audit['audited_run_sha256']==hashlib.sha256((ROOT/'run-receipt.json').read_bytes()).hexdigest()


def test_all_summary_claims_reconcile_to_daily_records_and_cash_identity():
    for row in pd.read_csv(ROOT/'summary.csv').itertuples():
        daily=pd.read_csv(ROOT/f'{row.case}-daily.csv')
        r=daily.net_return.to_numpy()
        assert len(r)==row.observations
        assert np.isfinite(r).all()
        assert (daily.gross_pnl-daily.trading_cost-daily.borrow_cost).to_numpy()==pytest.approx(r,abs=1e-13)
        assert np.prod(1+r)-1==pytest.approx(row.total_return,abs=1e-12)
        assert np.mean(r)/np.std(r,ddof=1)*np.sqrt(252)==pytest.approx(row.sharpe,abs=1e-12)
        wealth=np.r_[1.,np.cumprod(1+r)]
        assert np.min(wealth/np.maximum.accumulate(wealth)-1)==pytest.approx(row.max_drawdown,abs=1e-12)


def test_all_declared_cases_are_accounted_for_without_claiming_invalid_timing():
    protocol=json.loads((ROOT/'run-specification.json').read_text())
    completed=pd.read_csv(ROOT/'summary.csv')
    unavailable=json.loads((ROOT/'unavailable-cases.json').read_text())
    expected={s['name'] for s in protocol['cases']}
    assert len(expected)==47
    assert set(completed.case)|{s['case'] for s in unavailable}==expected
    assert set(completed.loc[~completed.valid_timing,'case'])=={'INVALID_same_day_leakage'}
    assert unavailable[0]['case']=='threshold_0.78'
    assert all(w['training_nonzero_returns']==0 for w in unavailable[0]['failed_windows'])


def test_test_years_and_separately_frozen_scales_reconcile_to_daily_returns():
    windows=pd.read_csv(ROOT/'windows.csv')
    for row in windows.itertuples():
        daily=pd.read_csv(ROOT/f'{row.case}-daily.csv',parse_dates=['date'])
        r=daily.loc[daily.date.dt.year==row.test_year,'net_return'].to_numpy()
        assert len(r)==row.observations
        assert np.prod(1+r)-1==pytest.approx(row.total_return,abs=1e-12)
    audit=json.loads((ROOT/'numerical-audit.json').read_text())
    assert audit['status']=='passed'
    assert audit['evaluation_return_observations']==757
    assert audit['training_scale_max_absolute_error']<1e-10
