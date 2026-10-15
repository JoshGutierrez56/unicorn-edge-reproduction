from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

from unicorn_edge.stress import (read_french_zip, factor_regression, circular_indices,
                                paired_bootstrap, cost_overlay, cost_summary, validate_ledger)


def archive(tmp_path, text):
    path = tmp_path/'factors.zip'
    with ZipFile(path, 'w') as z:
        z.writestr('factor.csv', text)
    return path


def test_factor_units_and_header(tmp_path):
    p = archive(tmp_path, 'Vintage note\n, Mom   \n20200102,1.25\n20200103,-0.50\nCopyright\n')
    actual = read_french_zip(p, ['MOM'])
    np.testing.assert_allclose(actual.MOM, [.0125,-.005])
    assert actual.index[0] == pd.Timestamp('2020-01-02')


@pytest.mark.parametrize('text', [',MOM\n20200102,-99.99', ',MOM\n20200102,-999',
    ',MOM\n20200102,NaN', ',MOM\n20200102,inf', ',MOM\n20200102,1\n20200102,2',
    ',MOM\n20200103,1\n20200102,2', ',Wrong\n20200102,1', ',MOM\n20200102,1,2'])
def test_factor_bad_input_fails(tmp_path, text):
    with pytest.raises(ValueError):
        read_french_zip(archive(tmp_path,text), ['MOM'])


@pytest.mark.parametrize('lag', [5,20])
def test_hac_matches_direct_newey_west_matrix(lag):
    rng = np.random.default_rng(92)
    n = 300
    idx = pd.bdate_range('2020-01-01', periods=n)
    market = rng.normal(0,.01,n)
    noise = rng.normal(0,.002,n)
    noise[1:] += .35*noise[:-1]
    rf = np.full(n,.00005)
    y = .0004+.7*market+noise
    f = pd.DataFrame({'Mkt-RF':market, 'RF':rf}, index=idx)
    result = factor_regression(pd.Series(y+rf,index=idx), f, ['Mkt-RF'], lag)
    x = np.column_stack([np.ones(n),market])
    inv = np.linalg.inv(x.T@x)
    coef = inv@x.T@y
    residual = y-x@coef
    scores = x*residual[:,None]
    meat = scores.T@scores
    for j in range(1,lag+1):
        cross = scores[j:].T@scores[:-j]
        meat += (1-j/(lag+1))*(cross+cross.T)
    se = np.sqrt(np.diag(inv@meat@inv*n/(n-x.shape[1])))
    np.testing.assert_allclose([result['terms'][k]['coefficient'] for k in ['const','Mkt-RF']], coef, atol=1e-14)
    np.testing.assert_allclose([result['terms'][k]['hac_se'] for k in ['const','Mkt-RF']], se, rtol=1e-12)


def test_factor_alignment_missing_dates_and_rank():
    idx = pd.bdate_range('2020-01-01',periods=100)
    r = pd.Series(np.sin(np.arange(100))*.01,index=idx)
    f = pd.DataFrame({'Mkt-RF':r*.5,'RF':.0001},index=idx)
    with pytest.raises(ValueError,match='factor dates'):
        factor_regression(r,f.iloc[1:],['Mkt-RF'],5)
    with pytest.raises(ValueError,match='Rank-deficient'):
        factor_regression(r,f.assign(duplicate=f['Mkt-RF']),['Mkt-RF','duplicate'],5)
    with pytest.raises(ValueError,match='Finite'):
        factor_regression(r.mask(np.arange(100)==20),f,['Mkt-RF'],5)


def test_blocks_are_contiguous_circular_and_paired():
    idx = circular_indices(24,5,10,np.random.default_rng(4))
    assert idx.shape == (10,24)
    for start in range(0,24,5):
        assert np.all(np.diff(idx[:,start:min(start+5,24)],axis=1)%24 == 1)
    dates = pd.bdate_range('2010-01-01',periods=140).append(pd.bdate_range('2015-01-01',periods=140))
    a = pd.Series(np.sin(np.arange(280))*.01,index=dates)
    out = paired_bootstrap(a,a,block=60,segmented_years=True,repetitions=100)
    assert [s['count'] for s in out['segments']] == [140,140]
    assert out['annual_mean_difference_95'] == [0.,0.]
    assert out['sharpe_difference_95'] == [0.,0.]
    assert out == paired_bootstrap(a,a,block=60,segmented_years=True,repetitions=100)
    with pytest.raises(ValueError,match='identical dates'):
        paired_bootstrap(a,a.iloc[1:],block=5,segmented_years=True)


def test_bootstrap_undefined_variance_reported():
    a = pd.Series(np.zeros(130),index=pd.bdate_range('2020-01-01',periods=130))
    out = paired_bootstrap(a,a,block=60,segmented_years=False,repetitions=30)
    assert out['undefined_sharpe_resamples'] == 30
    assert out['sharpe_difference_95'] is None


def ledger():
    f = pd.DataFrame({'gross_pnl':[.01,-.005], 'turnover':[2.,1.],
        'gross_exposure':[2.,1.], 'net_exposure':[0.,-.2], 'borrow_cost':[0.,0.]},
        index=pd.bdate_range('2020-01-01',periods=2))
    f['trading_cost'] = f.turnover*.6/10000
    f['net_return'] = f.gross_pnl-f.trading_cost
    return f


def test_cost_overlay_hand_accounting():
    f = ledger()
    np.testing.assert_allclose(cost_overlay(f,.6,0),f.net_return)
    np.testing.assert_allclose(cost_overlay(f,10,.03), [.01-.002-.03/252,-.005-.001-.6*.03/252])
    assert cost_summary(f)['arithmetic_break_even_fee_bps_zero_borrow'] == pytest.approx(16.6666666667)
    assert np.all(cost_overlay(f,2,.01) < cost_overlay(f,1,0))


@pytest.mark.parametrize('column,value', [('net_return',.5),('trading_cost',-.1),('net_exposure',3),('turnover',np.nan)])
def test_ledger_rejects_corruption(column,value):
    f = ledger()
    f.loc[f.index[0],column] = value
    with pytest.raises(ValueError):
        validate_ledger(f)
