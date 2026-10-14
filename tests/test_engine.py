import numpy as np
import pandas as pd
import pytest

from unicorn_edge.engine import BacktestConfig, DataGapError, backtest, metrics, rebalance, training_scale


def panels(returns, weights):
    dates = pd.date_range('2020-01-01',periods=len(returns),freq='B')
    return pd.DataFrame(returns,index=dates),pd.DataFrame(weights,index=dates)


def test_entry_is_self_financing_closed_form():
    held,cash,fee,turnover=rebalance(100.,np.zeros(2),np.array([.5,-.5]),.01)
    post=100/1.01
    assert held==pytest.approx([post/2,-post/2])
    assert cash==pytest.approx(post)
    assert fee==pytest.approx(100-post)
    assert turnover==pytest.approx(post)


def test_liquidating_both_sides_charges_full_absolute_notional():
    held,cash,fee,turnover=rebalance(100.,np.array([50.,-50.]),np.zeros(2),.001)
    assert fee==pytest.approx(.1)
    assert turnover==100
    assert cash==pytest.approx(99.9)
    assert np.array_equal(held,np.zeros(2))


def test_one_day_long_short_entry_mark_and_exit_matches_hand_nav():
    r,w=panels([[0.,0.],[.1,-.1]],[[.5,-.5],[0,0]])
    result=backtest(r,w,'2020-01-02','2020-01-03',BacktestConfig(cost_bps=100,kill_switch=False))
    # At entry: cash=100/101, long=50/101, short=-50/101.
    # At close: long=55/101, short=-45/101. Exit fees=(100/101)*1%.
    expected=(110/101)-(1/101)
    assert result.iloc[0]['nav']==pytest.approx(expected)
    assert result.iloc[0]['gross_pnl']==pytest.approx(10/101)
    assert result.iloc[0]['trading_cost']==pytest.approx(2/101)


def test_drifted_holdings_require_a_trade_even_when_target_does_not_change():
    r,w=panels([[0.,0.],[.2,0.],[0.,0.]],[[.5,.5]]*3)
    result=backtest(r,w,'2020-01-02','2020-01-06',BacktestConfig(cost_bps=0,kill_switch=False,liquidate_final=False))
    # Initial [.5,.5] become [.6,.5], NAV1.1; restoring [.55,.55] trades .1.
    assert result.iloc[1]['turnover']==pytest.approx(.1/1.1)
    assert result.iloc[-1]['nav']==pytest.approx(1.1)


def test_primary_lag_cannot_earn_same_day_signal_return():
    r,w=panels([[0.],[.5],[0.]],[[0.],[1.],[0.]])
    valid=backtest(r,w,'2020-01-01','2020-01-06',BacktestConfig(cost_bps=0,kill_switch=False))
    invalid=backtest(r,w,'2020-01-01','2020-01-06',BacktestConfig(cost_bps=0,kill_switch=False,signal_lag=0))
    assert valid.iloc[-1]['nav']==1
    assert invalid.iloc[-1]['nav']==1.5


def test_extra_execution_lag_is_a_full_additional_session():
    r,w=panels([[0.],[.2],[.3],[.4]],[[1.],[0.],[0.],[0.]])
    result=backtest(r,w,'2020-01-01','2020-01-07',BacktestConfig(cost_bps=0,kill_switch=False,signal_lag=2))
    assert result.iloc[-1]['nav']==pytest.approx(1.3)


def test_missing_held_return_fails_but_prelisting_unheld_observation_is_not_filled_into_a_signal():
    r,w=panels([[np.nan,0.],[np.nan,0.]],[[0.,1.],[0.,1.]])
    result=backtest(r,w,'2020-01-01','2020-01-03',BacktestConfig(cost_bps=0,kill_switch=False))
    assert result.iloc[-1]['nav']==1
    w.iloc[0]=[1.,0.]
    with pytest.raises(DataGapError,match='Missing held return'):
        backtest(r,w,'2020-01-01','2020-01-03')


def test_stop_is_after_the_loss_and_does_not_capture_a_later_rebound():
    r,w=panels([[0.],[-.4],[1.]],[[1.],[1.],[1.]])
    result=backtest(r,w,'2020-01-01','2020-01-06',BacktestConfig(cost_bps=0))
    assert result.iloc[1]['stop_reason']=='drawdown'
    assert result.iloc[1]['nav']==pytest.approx(.6)
    assert result.iloc[2]['nav']==pytest.approx(.6)


def test_rolling_loss_requires_the_full_number_of_observed_sessions():
    r,w=panels([[0.],[-.06],[-.06],[.5]],[[1.]]*4)
    result=backtest(r,w,'2020-01-01','2020-01-07',BacktestConfig(cost_bps=0,rolling_days=3))
    assert result.iloc[1]['stop_reason']==''
    assert result.iloc[2]['stop_reason']=='rolling_loss'
    assert result.iloc[-1]['nav']==pytest.approx(.94**2)


def test_short_borrow_is_an_expense_even_when_prices_are_flat():
    r,w=panels([[0.,0.],[0.,0.]],[[.5,-.5]]*2)
    result=backtest(r,w,'2020-01-02','2020-01-03',BacktestConfig(cost_bps=0,borrow_bps_annual=252))
    assert result.iloc[0]['borrow_cost']==pytest.approx(.00005)
    assert result.iloc[0]['net_return']==pytest.approx(-.00005)


def test_metrics_reconcile_compounding_and_include_initial_nav_in_drawdown():
    m=metrics(pd.Series([-.2,.25]))
    assert m['total_return']==pytest.approx(0)
    assert m['max_drawdown']==pytest.approx(-.2)
    assert m['annual_mean']==pytest.approx(.025*252)
    assert m['sharpe']==pytest.approx(np.mean([-.2,.25])/np.std([-.2,.25],ddof=1)*np.sqrt(252))


def test_training_scale_uses_training_variation_and_optional_leverage_cap():
    train=pd.Series([.001,-.001]*100)
    assert training_scale(train)>1
    assert training_scale(train,cap=1)==1
    with pytest.raises(ValueError,match='No training variation'):
        training_scale(pd.Series([0.,0.]))


def test_nonfinite_targets_are_rejected_not_flattened():
    r,w=panels([[0.],[0.]],[[np.nan],[1.]])
    with pytest.raises(ValueError,match='Target weights must be finite'):
        backtest(r,w,'2020-01-01','2020-01-03')


def test_zero_cost_ledger_matches_an_independent_share_and_cash_calculation():
    rng=np.random.default_rng(7)
    prices=np.vstack([np.ones(4),np.cumprod(1+rng.normal(0,.01,(15,4)),axis=0)])
    returns=np.vstack([np.zeros(4),prices[1:]/prices[:-1]-1])
    desired=rng.normal(size=(16,4));desired-=desired.mean(axis=1,keepdims=True)
    desired/=np.abs(desired).sum(axis=1,keepdims=True)
    r,w=panels(returns,desired)
    result=backtest(r,w,'2020-01-01','2021-01-01',BacktestConfig(cost_bps=0,kill_switch=False))
    nav=1.; path=[1.]
    for t in range(1,16):
        shares=nav*desired[t-1]/prices[t-1]
        cash=nav-float(shares@prices[t-1])
        nav=cash+float(shares@prices[t])
        path.append(nav)
    assert result['nav'].to_numpy()==pytest.approx(path)
