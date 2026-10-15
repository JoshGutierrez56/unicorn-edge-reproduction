"""Public delivery checks: completeness, exact provenance, economic identities."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from unicorn_edge.engine import metrics
from unicorn_edge.stress import cost_overlay


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/2026-10-14/platform-stress'


def test_complete_release_and_exact_inputs():
    manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest) == 10
    for name,digest in manifest.items():
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest() == digest
    run = json.loads((OUT/'run-receipt.json').read_text(encoding='utf-8'))
    for name,digest in run['input_hashes'].items():
        assert hashlib.sha256((ROOT/'results/2026-10-14/crsp-followup'/name).read_bytes()).hexdigest() == digest
    regression = json.loads((OUT/'factor-regressions.json').read_text(encoding='utf-8'))
    assert len(regression) == 3
    for models in regression.values():
        assert set(models) == {'CAPM_HAC5','CAPM_HAC20','FF5_MOM_HAC5','FF5_MOM_HAC20'}
        for result in models.values():
            assert result['observations'] == 3774
            assert result['annual_intercept_arithmetic'] == result['terms']['const']['coefficient']*252
    paired = json.loads((OUT/'paired-block-bootstrap.json').read_text(encoding='utf-8'))
    assert len(paired) == 5
    for name,rows in paired.items():
        assert [row['block_days'] for row in rows] == [5,20,60]
        for row in rows:
            assert row['repetitions'] == 2000
            assert row['undefined_sharpe_resamples'] == 0
            assert len(row['segments']) == (3 if name.startswith('three_year') else 1)
    assert len(pd.read_csv(OUT/'periods.csv')) == 54


def test_all_cost_overlays_reconcile_to_recorded_ledger():
    table = pd.read_csv(OUT/'fixed-path-cost-overlays.csv')
    assert len(table) == 45
    sources = {'crsp_nominal':'crsp_nominal_stale_freeze','crsp_split':'crsp_split_stale_freeze','yahoo_matched':'yahoo_close_quote_freeze'}
    for name,source in sources.items():
        frame = pd.read_csv(ROOT/f'results/2026-10-14/crsp-followup/{source}-annual-daily.csv',index_col='date',parse_dates=True)
        np.testing.assert_allclose(cost_overlay(frame,.6,0),frame.net_return,atol=1e-12,rtol=0)
        rows = table[table.source==name]
        assert set(zip(rows.fee_bps,rows.annual_borrow_rate)) == {(b,r) for b in [.6,1,2,5,10] for r in [0,.01,.03]}
        for row in rows.itertuples():
            reference = metrics(cost_overlay(frame,row.fee_bps,row.annual_borrow_rate))
            for column in ['sharpe','cagr','max_drawdown']:
                np.testing.assert_allclose(getattr(row,column),reference[column],atol=1e-12,rtol=0)


def test_optional_platform_checks_have_explicit_boundaries():
    audit = json.loads((OUT/'autopsy-qualified-receipt.json').read_text(encoding='utf-8'))
    assert len(audit['series']) == 3
    assert audit['compatibility_probes']['initial_loss_drawdown']['compatible'] is False
    assert 'platform_cost_scenarios_and_COST_ECONOMIC_ERASURE' in audit['withheld_statistics']
    for result in audit['series'].values():
        ids = {f['finding_id'] for f in result['findings']}
        assert 'PROCESS_HOLDOUT' in ids
        assert 'COST_ZERO_TURNOVER' in ids
        assert 'COST_ECONOMIC_ERASURE' not in ids
    contract = json.loads((OUT/'alpha-panel-contract.json').read_text(encoding='utf-8'))
    assert contract['observations'] == 3774
    assert contract['injected_faults'] == {k:'rejected' for k in ['missing','duplicate','unsorted','bankrupt']}
