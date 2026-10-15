from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SignalConfig:
    window: int = 63
    threshold: float = .60
    reversal_window: int = 10
    value_weight: float = .70
    mode: str = "gated_blend"
    equal_side: bool = False
    random_seed: int = 0

    def __post_init__(self):
        if self.window < 1 or self.reversal_window < 1:
            raise ValueError("Lookbacks must be positive")
        if not 0 <= self.threshold <= 1 or not 0 <= self.value_weight <= 1:
            raise ValueError("Threshold and blend weight must lie in [0,1]")
        if self.mode not in {"gated_blend", "ungated", "gated_value", "gated_reversal", "random_gate", "equal_weight"}:
            raise ValueError("Unknown signal mode")


def cross_section_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    scale = frame.std(axis=1, ddof=0)
    scale = scale.where(scale > 1e-12)
    return frame.sub(mean, axis=0).div(scale, axis=0)


def make_signals(prices: pd.DataFrame, total_return_prices: pd.DataFrame | None, config: SignalConfig,
                 *, explicit_returns: pd.DataFrame | None = None,
                 universe_mask: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Weights labeled t use only observations through t; the gate excludes t.

    These are target weights, not portfolio returns. The accounting engine applies
    an explicit decision-to-return lag. Prelisting NaNs remain missing throughout.
    """
    reference = explicit_returns if explicit_returns is not None else total_return_prices
    if reference is None:
        raise ValueError("Total-return prices or explicit total returns are required")
    if not prices.index.equals(reference.index) or not prices.columns.equals(reference.columns):
        raise ValueError("Price panels must have identical labels")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Dates must be sorted and unique")
    for panel in (prices,) if explicit_returns is not None else (prices, total_return_prices):
        if ((panel <= 0) | np.isinf(panel)).any().any():
            raise ValueError("Observed prices must be positive and finite")
    returns = explicit_returns if explicit_returns is not None else total_return_prices.pct_change(fill_method=None)
    if (np.isinf(returns) | returns.le(-1)).any().any():
        raise ValueError("Invalid return or total-loss event needs explicit treatment")
    if universe_mask is not None:
        if not prices.index.equals(universe_mask.index) or not prices.columns.equals(universe_mask.columns):
            raise ValueError("Universe mask labels differ")
        if universe_mask.isna().any().any() or not all(t==bool for t in universe_mask.dtypes):
            raise ValueError("Universe mask must contain nonmissing booleans")
        rank_prices=prices.where(universe_mask)
    else:
        rank_prices=prices
    positive = (returns > 0).astype(float).where(returns.notna())
    up_fraction = positive.shift(1).rolling(config.window, min_periods=config.window).mean()
    value = (1 / rank_prices).rank(axis=1, pct=True, method="average")
    if explicit_returns is None:
        reversal_return=total_return_prices.pct_change(config.reversal_window, fill_method=None)
    else:
        # Direct CIZ returns already include distributions/delisting treatment.
        # A full observed lookback is required; missing returns are not zeroed.
        reversal_return=np.expm1(np.log1p(returns).rolling(config.reversal_window,min_periods=config.reversal_window).sum())
    if universe_mask is not None:reversal_return=reversal_return.where(universe_mask)
    reversal = cross_section_zscore(-reversal_return)
    if config.mode == "gated_value":
        base = value
    elif config.mode == "gated_reversal":
        base = reversal
    else:
        base = config.value_weight * value + (1-config.value_weight) * reversal
    valid_today = returns.notna() if explicit_returns is not None else total_return_prices.notna()
    eligible = base.notna() & up_fraction.notna() & rank_prices.notna() & valid_today
    gate = (up_fraction > config.threshold) & eligible
    if config.mode in {"ungated", "equal_weight"}:
        gate = eligible
    elif config.mode == "random_gate":
        # Match observed daily counts, not regime spell lengths or autocorrelation.
        rng = np.random.default_rng(config.random_seed)
        mask = np.zeros(gate.shape, dtype=bool)
        for i, (available, count) in enumerate(zip(eligible.to_numpy(), gate.sum(axis=1))):
            choices = np.flatnonzero(available)
            if count:
                mask[i, rng.choice(choices, int(count), replace=False)] = True
        gate = pd.DataFrame(mask, index=gate.index, columns=gate.columns)
    if config.mode == "equal_weight":
        weights = gate.astype(float).div(gate.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
    else:
        scores = cross_section_zscore(base.where(gate & base.ne(0)))
        long = scores.clip(lower=0).fillna(0)
        short = (-scores).clip(lower=0).fillna(0)
        if config.equal_side:
            long, short = long.gt(0).astype(float), short.gt(0).astype(float)
        long = long.div(long.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
        short = short.div(short.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
        both_sides = long.sum(axis=1).gt(0) & short.sum(axis=1).gt(0)
        weights = (.5 * (long-short)).where(both_sides,0,axis=0)
    return {"weights": weights, "up_fraction": up_fraction, "eligible": eligible, "gate": gate, "base": base}
