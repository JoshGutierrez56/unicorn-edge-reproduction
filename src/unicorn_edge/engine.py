from dataclasses import dataclass

import numpy as np
import pandas as pd


class DataGapError(ValueError):
    pass


class NoTrainingVariationError(ValueError):
    """The requested strategy has no calibratable training variation."""


@dataclass(frozen=True)
class BacktestConfig:
    cost_bps: float = .6
    borrow_bps_annual: float = 0
    signal_lag: int = 1
    scale: float = 1
    kill_switch: bool = True
    max_drawdown: float = .30
    rolling_loss: float = .10
    rolling_days: int = 63
    liquidate_final: bool = True

    def __post_init__(self):
        if self.cost_bps < 0 or self.borrow_bps_annual < 0 or self.scale < 0:
            raise ValueError("Costs, borrow fees and scale cannot be negative")
        if self.signal_lag < 0 or self.rolling_days < 1:
            raise ValueError("Invalid timing configuration")
        if not 0 < self.max_drawdown < 1 or not 0 < self.rolling_loss < 1:
            raise ValueError("Stop thresholds must lie in (0,1)")


def rebalance(nav: float, held: np.ndarray, target: np.ndarray, rate: float,
              tradable: np.ndarray | None = None) -> tuple[np.ndarray, float, float, float]:
    """Solve fee = rate * sum(abs(target * (NAV-fee) - held)).

    Target weights are relative to post-cost NAV. Signed holdings and a separate
    cash account preserve self-financing long/short accounting.
    """
    if nav <= 0 or not np.isfinite(nav) or not np.isfinite(held).all() or not np.isfinite(target).all():
        raise ValueError("Nonfinite holdings/targets or nonpositive NAV")
    if tradable is None:
        tradable = np.ones(held.shape, dtype=bool)
    if tradable.shape != held.shape or tradable.dtype != bool:
        raise ValueError("Tradability must be a matching boolean vector")
    if rate < 0 or not np.isfinite(rate) or rate * np.abs(target[tradable]).sum() >= 1:
        raise ValueError("Cost equation is not contractive")
    fee = 0.
    for _ in range(100):
        next_fee = rate * np.abs(target[tradable]*(nav-fee)-held[tradable]).sum()
        if abs(next_fee-fee) <= 1e-14 * max(nav, 1e-12):
            fee = next_fee
            break
        fee = next_fee
    else:
        raise ValueError("Cost equation did not converge")
    if fee >= nav:
        raise ValueError("Fees exhaust NAV")
    holdings = np.where(tradable, target * (nav-fee), held)
    cash = nav-fee-holdings.sum()
    turnover = np.abs(holdings-held).sum()
    if not np.isclose(fee, rate*turnover, rtol=1e-11, atol=1e-14):
        raise AssertionError("Self-financing fee equation failed")
    return holdings, float(cash), float(fee), float(turnover)


def backtest(returns: pd.DataFrame, weights: pd.DataFrame, start: str, end: str,
             config: BacktestConfig = BacktestConfig(), *,
             close_tradable: pd.DataFrame | None = None) -> pd.DataFrame:
    """Half-open date interval; prior-close trading, then today's close-to-close return.

    lag=1 assumes signals computed at the close can transact at that same close.
    lag=2 provides one full extra session. lag=0 is an INVALID same-day leakage
    diagnostic supported explicitly for audit, never a valid performance estimate.
    """
    if not returns.index.equals(weights.index) or not returns.columns.equals(weights.columns):
        raise ValueError("Returns and target labels must match exactly")
    if returns.index.has_duplicates or not returns.index.is_monotonic_increasing:
        raise ValueError("Return dates must be sorted and unique")
    if not np.isfinite(weights.to_numpy(float)).all():
        raise ValueError("Target weights must be finite before the explicit lag")
    if close_tradable is not None:
        if not returns.index.equals(close_tradable.index) or not returns.columns.equals(close_tradable.columns):
            raise ValueError("Tradability labels differ")
        if close_tradable.isna().any().any() or not all(t == bool for t in close_tradable.dtypes):
            raise ValueError("Tradability must contain nonmissing booleans")
        if config.signal_lag < 1:
            raise ValueError("Tradability modeling cannot use the invalid same-day diagnostic")
        at_close = close_tradable.to_numpy(bool)
        before_return = close_tradable.shift(1, fill_value=False).to_numpy(bool)
    else:
        at_close = before_return = np.ones(returns.shape, dtype=bool)
    targets = weights.shift(config.signal_lag).fillna(0).to_numpy(float) * config.scale
    locations = np.flatnonzero((returns.index >= pd.Timestamp(start)) & (returns.index < pd.Timestamp(end)))
    if not len(locations):
        raise ValueError("No observations in evaluation interval")
    raw_returns = returns.to_numpy(float)
    nav, cash, peak = 1., 1., 1.
    held = np.zeros(len(returns.columns))
    stopped = False
    wealth_history = [1.]
    records = []
    rate = config.cost_bps / 10000
    for j, t in enumerate(locations):
        opening_nav = nav
        target = np.zeros_like(held) if stopped else targets[t]
        held, cash, fee, traded = rebalance(nav, held, target, rate, before_return[t])
        current_return = raw_returns[t]
        exposed = np.abs(held) > 1e-14
        bad = exposed & ~np.isfinite(current_return)
        if bad.any():
            raise DataGapError(f"Missing held return at {returns.index[t].date()}: {list(returns.columns[bad])}")
        if (current_return[exposed] <= -1).any():
            raise DataGapError("Return at/below -100% requires explicit corporate-action treatment")
        observed = np.where(np.isfinite(current_return),current_return,0.)
        gross_pnl = float(held @ observed)
        borrow = float(np.maximum(-held,0).sum()*config.borrow_bps_annual/10000/252)
        gross_exposure = float(np.abs(held).sum()/opening_nav)
        net_exposure = float(held.sum()/opening_nav)
        long_count, short_count = int((held>1e-14).sum()), int((held < -1e-14).sum())
        held = held*(1+observed)
        cash -= borrow
        nav = float(cash+held.sum())
        if nav <= 0 or not np.isfinite(nav):
            raise ValueError(f"Insolvent/nonfinite portfolio at {returns.index[t]}")
        peak = max(peak,nav)
        drawdown = nav/peak-1
        rolling = nav/wealth_history[-config.rolling_days]-1 if len(wealth_history)>=config.rolling_days else None
        stop_reason = ""
        if config.kill_switch and not stopped:
            if drawdown <= -config.max_drawdown:
                stop_reason = "drawdown"
            elif rolling is not None and rolling <= -config.rolling_loss:
                stop_reason = "rolling_loss"
            if stop_reason:
                stopped = True
        final_exit = config.liquidate_final and j == len(locations)-1
        if stopped or final_exit:
            held, cash, exit_fee, exit_traded = rebalance(nav, held, np.zeros_like(held), rate, at_close[t])
            nav = float(cash + held.sum())
            fee += exit_fee
            traded += exit_traded
            if final_exit and np.any(np.abs(held) > 1e-14):
                raise DataGapError("Final liquidation is blocked by an unavailable closing quote")
        # Independent balance identity uses opening NAV and monetary P&L/fees.
        reconciliation = nav - (opening_nav + gross_pnl - fee - borrow)
        if abs(reconciliation) > 1e-10*opening_nav:
            raise AssertionError("Daily cash/holdings/P&L reconciliation failed")
        net_return = nav/opening_nav-1
        wealth_history.append(nav)
        records.append({"date":returns.index[t],"net_return":net_return,"nav":nav,
                        "gross_pnl":gross_pnl/opening_nav,"trading_cost":fee/opening_nav,
                        "borrow_cost":borrow/opening_nav,"turnover":traded/opening_nav,
                        "gross_exposure":gross_exposure,"net_exposure":net_exposure,
                        "long_count":long_count,"short_count":short_count,"stopped":stopped,
                        "stop_reason":stop_reason,"reconciliation_error":reconciliation})
    return pd.DataFrame(records).set_index("date")


def metrics(series: pd.Series) -> dict[str, float | int | None]:
    values = series.to_numpy(float)
    if not len(values) or not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("Metrics require finite, non-bankrupt returns")
    wealth = np.concatenate([[1.], np.cumprod(1+values)])
    volatility = float(np.std(values,ddof=1)*np.sqrt(252)) if len(values)>1 else 0.
    mean = float(values.mean()*252)
    return {"observations":len(values),"annual_mean":mean,"annual_volatility":volatility,
            "sharpe":mean/volatility if volatility>1e-14 else None,
            "total_return":float(wealth[-1]-1),"cagr":float(wealth[-1]**(252/len(values))-1),
            "max_drawdown":float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
            "winning_fraction":float(np.mean(values>0)),"best_day":float(values.max()),"worst_day":float(values.min())}


def training_scale(series: pd.Series, cap: float | None = None) -> float:
    m = metrics(series)
    vol, dd = float(m["annual_volatility"]), abs(float(m["max_drawdown"]))
    if vol <= 1e-14:
        raise NoTrainingVariationError("No training variation; cannot calibrate scale")
    scale = min(.12/vol, .15/dd if dd>1e-14 else np.inf)
    return float(min(scale,cap)) if cap is not None else float(scale)
