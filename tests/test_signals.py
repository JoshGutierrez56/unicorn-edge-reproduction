import numpy as np
import pandas as pd
import pytest

from unicorn_edge.signals import SignalConfig, cross_section_zscore, make_signals


def sample():
    rng=np.random.default_rng(42)
    return pd.DataFrame(np.exp(np.cumsum(rng.normal(.001,.02,(100,8)),axis=0))*np.arange(10,90,10),
                        index=pd.bdate_range('2020-01-01',periods=100))


def test_gate_uses_previous_returns_and_strict_threshold():
    prices=sample()
    cfg=SignalConfig(window=3,threshold=2/3,reversal_window=2)
    result=make_signals(prices,prices,cfg)
    raw=prices.pct_change(fill_method=None)
    for t in (7,10,50):
        expected=(raw.iloc[t-3:t]>0).mean()
        assert result['up_fraction'].iloc[t].to_numpy()==pytest.approx(expected.to_numpy())
        assert np.array_equal(result['gate'].iloc[t],expected.gt(2/3))


def test_missing_lookback_is_not_counted_as_a_down_day():
    prices=sample();prices.iloc[30,0]=np.nan
    result=make_signals(prices,prices,SignalConfig(window=3,reversal_window=2))
    assert np.isnan(result['up_fraction'].iloc[32,0])
    assert not result['gate'].iloc[32,0]


@pytest.mark.parametrize('mode',['gated_blend','gated_value','gated_reversal','ungated','random_gate'])
def test_long_short_normalization_and_future_perturbation(mode):
    prices=sample();cfg=SignalConfig(window=5,threshold=.2,reversal_window=2,mode=mode)
    before=make_signals(prices,prices,cfg)
    changed=prices.copy();changed.iloc[70:]*=np.arange(2,10)
    after=make_signals(changed,changed,cfg)
    pd.testing.assert_frame_equal(before['weights'].iloc[:70],after['weights'].iloc[:70])
    weights=before['weights']
    assert np.max(np.abs(weights.sum(axis=1)))<1e-12
    active=weights.abs().sum(axis=1)>0
    assert weights.clip(lower=0).sum(axis=1)[active].to_numpy()==pytest.approx(np.full(active.sum(),.5))
    assert weights.clip(upper=0).sum(axis=1)[active].to_numpy()==pytest.approx(np.full(active.sum(),-.5))


def test_random_gate_matches_the_daily_active_count_not_signal_values():
    prices=sample();base=make_signals(prices,prices,SignalConfig(window=5,reversal_window=2))
    random=make_signals(prices,prices,SignalConfig(window=5,reversal_window=2,mode='random_gate',random_seed=2))
    assert np.array_equal(base['gate'].sum(axis=1),random['gate'].sum(axis=1))
    assert not np.array_equal(base['gate'],random['gate'])


def test_constant_cross_section_does_not_create_floating_point_signals():
    frame=pd.DataFrame(np.full((3,500),.35))
    assert cross_section_zscore(frame).isna().all().all()


def test_inverse_price_rank_is_not_invariant_to_a_stock_unit_change():
    prices=sample();cfg=SignalConfig(window=5,reversal_window=2,mode='gated_value',threshold=0)
    before=make_signals(prices,prices,cfg)
    unit_changed=prices.copy();unit_changed.iloc[:,0]*=10
    after=make_signals(unit_changed,prices,cfg)
    assert not before['base'].equals(after['base'])


def test_prelisting_prices_never_backfill():
    prices=sample();prices.iloc[:50,0]=np.nan
    result=make_signals(prices,prices,SignalConfig(window=5,reversal_window=2))
    assert not result['eligible'].iloc[:56,0].any()
    assert result['weights'].iloc[:56,0].eq(0).all()
