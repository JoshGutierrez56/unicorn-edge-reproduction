import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]/'results/2026-10-14/crsp-followup'


def test_crsp_release_retains_every_declared_case_and_distinguishes_incomplete_runs():
    spec=json.loads((ROOT/'specification.json').read_text())
    complete=pd.read_csv(ROOT/'summary.csv')
    blocked=json.loads((ROOT/'blocked-windows.json').read_text())
    expected={r['name'] for r in spec['cases']}
    failed={r['case'] for r in blocked if r['case'] in expected}
    assert len(expected)==30 and len(complete)==17 and len(failed)==13
    assert not set(complete.case)&failed
    assert set(complete.case)|failed==expected
    assert 'BLOCKED' in spec['historical_membership']
    assert not complete.case.isin(['crsp_nominal_gated_blend','crsp_split_adjusted_gated_blend']).any()


def test_crsp_publication_hashes_and_untransformed_bytes_match_frozen_run():
    receipt=json.loads((ROOT/'publication-receipt.json').read_text())
    source=json.loads((ROOT/'source-run-receipt.json').read_text())
    for name,digest in receipt['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    for name,digest in source['files'].items():
        if name!='blocked-windows.json':assert receipt['files'][name]==digest,name
    quality=json.loads((ROOT/'data-quality.json').read_text())
    assert quality['common_symbols']==490
    assert quality['modeled_gap_valuation']['bridged_intervals']==6
    assert quality['modeled_gap_valuation']['stale_valuation_sessions']==7
    assert {x['symbol'] for x in quality['excluded_identity_candidates']}=={'BNY','ECHO','P'}
    assert all(set(row)=={'symbol','status'} for row in quality['unresolved_mappings'])


def test_crsp_completed_metrics_reconcile_with_cash_fees_and_daily_returns():
    for row in pd.read_csv(ROOT/'summary.csv').itertuples():
        daily=pd.read_csv(ROOT/(row.case+'-daily.csv'))
        r=daily.net_return.to_numpy()
        assert len(r)==row.observations==757
        assert np.isfinite(r).all()
        assert r==pytest.approx((daily.gross_pnl-daily.trading_cost-daily.borrow_cost).to_numpy(),abs=1e-13)
        assert np.mean(r)/np.std(r,ddof=1)*np.sqrt(252)==pytest.approx(row.sharpe,abs=1e-12)
        assert np.prod(1+r)-1==pytest.approx(row.total_return,abs=1e-12)
        assert daily.turnover.mean()*252==pytest.approx(row.annual_turnover,abs=1e-12)


def test_crsp_annual_aggregate_requires_all_fifteen_years():
    windows=pd.read_csv(ROOT/'annual-windows.csv')
    for source,group in windows.groupby('source'):
        path=ROOT/(source+'-annual-summary.json')
        if len(group)<15:
            assert not path.exists()
            continue
        summary=json.loads(path.read_text())
        daily=pd.read_csv(ROOT/(source+'-annual-daily.csv'),parse_dates=['date'])
        assert sorted(daily.date.dt.year.unique())==list(range(2010,2025))
        r=daily.net_return.to_numpy()
        assert len(r)==summary['observations']==3774
        assert np.mean(r)/np.std(r,ddof=1)*np.sqrt(252)==pytest.approx(summary['sharpe'],abs=1e-12)
        assert np.prod(1+r)**(252/len(r))-1==pytest.approx(summary['cagr'],abs=1e-12)


def test_crsp_second_implementation_reconciles_primary_signals_and_windows():
    audit=json.loads((ROOT/'numerical-audit.json').read_text())
    assert audit['status']=='passed' and audit['signal_dates_checked']==300
    assert audit['training_return_observations']==11325
    assert audit['evaluation_return_observations']==2271
    assert audit['signal_weight_max_absolute_error']<1e-12
    assert audit['training_scale_max_absolute_error']<1e-10
    assert len(audit['ledger_comparisons'])==9
    assert audit['audited_run_sha256']==hashlib.sha256((ROOT/'source-run-receipt.json').read_bytes()).hexdigest()
