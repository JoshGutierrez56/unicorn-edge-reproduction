import numpy as np
import pandas as pd
import pytest

from unicorn_edge.crsp_data import documented_gap_marks, reviewed_mappings
from unicorn_edge.engine import BacktestConfig, DataGapError, backtest, rebalance


def test_locked_position_is_unchanged_and_fee_only_uses_executable_trades():
    held, cash, fee, turnover = rebalance(100., np.array([30., -20.]), np.array([0., .5]), .01,
                                        np.array([False, True]))
    expected_fee = .7 / 1.005
    assert held[0] == 30
    assert held[1] == pytest.approx(.5 * (100-expected_fee))
    assert fee == pytest.approx(expected_fee)
    assert turnover == pytest.approx(held[1]+20)
    assert cash+held.sum()+fee == pytest.approx(100)


def example():
    dates = pd.date_range('2020-01-01', periods=5)
    returns = pd.DataFrame({'A':[0., 0., 0., -.2, 0.], 'B':[0.]*5}, index=dates)
    weights = pd.DataFrame({'A':[.5, 0., 0., 0., 0.], 'B':[-.5, 0., 0., 0., 0.]}, index=dates)
    quotes = pd.DataFrame({'A':[True, False, False, True, True], 'B':[True]*5}, index=dates)
    return dates, returns, weights, quotes


def test_stale_position_cannot_be_sold_before_resumption_and_takes_entire_loss():
    dates, returns, weights, quotes = example()
    path = backtest(returns, weights, str(dates[1]), '2020-01-06',
                    BacktestConfig(cost_bps=0, kill_switch=False), close_tradable=quotes)
    # Short B closes normally; the unavailable A position remains 0.5 dollars.
    assert path.iloc[1].long_count == 1
    assert path.iloc[1].short_count == 0
    assert path.net_return.tolist() == pytest.approx([0., 0., -.1, 0.])
    assert path.iloc[-1].nav == pytest.approx(.9)
    assert path.reconciliation_error.abs().max() < 1e-14


def test_missing_quote_prevents_new_entry_even_with_stale_positive_target():
    dates, returns, weights, quotes = example()
    quotes.loc[dates[0], 'A'] = False
    path = backtest(returns, weights, str(dates[1]), '2020-01-06',
                    BacktestConfig(cost_bps=0, kill_switch=False), close_tradable=quotes)
    assert path.nav.tolist() == pytest.approx([1.]*4)
    assert path.long_count.eq(0).all()


def test_pending_stop_waits_for_quote_then_charges_exit_fee():
    dates, returns, weights, quotes = example()
    returns.loc[dates[1], 'B'] = .4  # short loss trips stop while A has no closing quote
    config = BacktestConfig(cost_bps=10, max_drawdown=.1, rolling_loss=.9)
    path = backtest(returns, weights, str(dates[1]), '2020-01-06', config, close_tradable=quotes)
    assert path.iloc[0].stop_reason == 'drawdown'
    assert path.iloc[1].long_count == 1
    assert path.iloc[2].gross_pnl < 0  # stop cannot magic away locked A exposure
    assert path.iloc[2].trading_cost > 0
    assert path.iloc[3].long_count == 0
    assert path.reconciliation_error.abs().max() < 1e-14


def test_unavailable_final_liquidation_is_not_reported_as_cash():
    dates, returns, weights, quotes = example()
    with pytest.raises(DataGapError, match='Final liquidation'):
        backtest(returns, weights, str(dates[1]), str(dates[3]), BacktestConfig(cost_bps=0),
                 close_tradable=quotes)


def test_tradability_does_not_hide_unresolved_held_returns():
    dates, returns, weights, quotes = example()
    returns.loc[dates[1], 'A'] = np.nan
    with pytest.raises(DataGapError, match='Missing held return'):
        backtest(returns, weights, str(dates[1]), '2020-01-06', close_tradable=quotes)


def test_all_quotes_available_is_identical_to_original_engine():
    dates, returns, weights, _ = example()
    config = BacktestConfig(cost_bps=2, kill_switch=False)
    old = backtest(returns, weights, str(dates[1]), '2020-01-06', config)
    new = backtest(returns, weights, str(dates[1]), '2020-01-06', config,
                   close_tradable=pd.DataFrame(True, index=dates, columns=returns.columns))
    pd.testing.assert_frame_equal(old, new)


@pytest.mark.parametrize('days', [1, 2])
def test_documented_gap_keeps_observed_signal_returns_missing(days):
    rows = pd.DataFrame({'permno':[1]*(days+2), 'date':pd.date_range('2020-01-01', periods=days+2),
        'dlyret':[0.]+[np.nan]*days+[-.2], 'dlyprc':[100.]+[np.nan]*days+[80.],
        'dlyretmissflg':['NA']+['MP']*days+['NA'], 'dlyprcflg':['TR']+['MP']*days+['TR'],
        'dlyretdurflg':['D1']+['MR']*days+['P'+str(days)], 'session_ordinal':range(days+2),
        'total_return':[0.]+[np.nan]*(days+1)})
    before = rows.copy(deep=True)
    valuation, info = documented_gap_marks(rows)
    assert valuation.tolist() == pytest.approx([0.]*(days+1)+[-.2])
    assert (1+valuation).prod() == pytest.approx(.8)
    assert info['stale_valuation_sessions'] == days
    pd.testing.assert_frame_equal(rows, before)
    rows.loc[1, 'dlyretmissflg'] = 'NT'
    with pytest.raises(ValueError, match='documented missing-price'):
        documented_gap_marks(rows)


def test_identity_review_rejects_incomplete_or_changed_metadata_and_ids():
    metadata = {'mappings':[{'symbol':'NEW','permno':1,'status':'matched'},
                            {'symbol':'OTHER','permno':2,'status':'matched'}]}
    review = {'metadata_sha256':'abc','decisions':[
        {'symbol':'NEW','permno':1,'decision':'excluded','reason':'Different issuer behind reused ticker'},
        {'symbol':'OTHER','permno':2,'decision':'approved','reason':'Issuer and class checked'}]}
    assert reviewed_mappings(metadata, 'abc', review) == {2:'OTHER'}
    with pytest.raises(ValueError, match='source metadata'):
        reviewed_mappings(metadata, 'changed', review)
    review['decisions'][0]['permno'] = 9
    with pytest.raises(ValueError, match='substitute'):
        reviewed_mappings(metadata, 'abc', review)
    review['decisions'].pop()
    with pytest.raises(ValueError, match='every candidate'):
        reviewed_mappings(metadata, 'abc', review)
