"""Retrospective diagnostics; never strategy selection or a new holdout.

Paired circular blocks adapt the design of personalized-model-portfolios /
walkforward.py::paired_block_bootstrap (412cb55); estimands and segmentation
are changed here. See the frozen PLATFORM_STRESS_TEST_PLAN and reuse receipt.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .engine import metrics


def check_dates(frame: pd.DataFrame | pd.Series) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.empty:
        raise ValueError("Nonempty DatetimeIndex required")
    if frame.index.hasnans or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Dates must be finite, unique and sorted")
    if np.iscomplexobj(frame.to_numpy()) or not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Finite real observations required; no silent dropping")


def read_french_zip(path: Path, expected: list[str]) -> pd.DataFrame:
    with ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith('.csv')]
        if len(members) != 1:
            raise ValueError("Expected exactly one factor CSV")
        lines = archive.read(members[0]).decode('utf-8-sig').splitlines()
    header = None
    rows = []
    for line in lines:
        parts = [p.strip() for p in next(csv.reader([line]))]
        if parts and not parts[0] and len(parts) > 1:
            candidate = ['MOM' if p.lower() in ('mom', 'momentum') else p for p in parts[1:]]
            if candidate == expected:
                header = candidate
                continue
        if parts and re.fullmatch(r'\d{8}', parts[0]):
            if header is None or len(parts) != len(expected) + 1:
                raise ValueError("Unexpected daily factor schema")
            rows.append(parts)
    if not rows:
        raise ValueError("No daily factor observations")
    frame = pd.DataFrame(rows, columns=['date', *expected])
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop('date'), format='%Y%m%d', errors='raise'))
    frame = frame.apply(pd.to_numeric, errors='raise')
    if frame.isin([-99.99, -999.0]).any().any():
        raise ValueError("French missing-value sentinel")
    check_dates(frame)
    return frame / 100.0


def factor_regression(returns: pd.Series, factors: pd.DataFrame, columns: list[str], lag: int) -> dict:
    check_dates(returns)
    check_dates(factors)
    if lag < 0 or len(returns) <= lag + len(columns) + 2:
        raise ValueError("Insufficient observations for specified HAC regression")
    missing = returns.index.difference(factors.index)
    if len(missing):
        raise ValueError(f"Missing {len(missing)} factor dates; no complete-case deletion")
    aligned = factors.loc[returns.index, [*columns, 'RF']]
    x = sm.add_constant(aligned[columns], has_constant='add')
    if np.linalg.matrix_rank(x.to_numpy()) != x.shape[1]:
        raise ValueError("Rank-deficient factor design")
    y = returns - aligned.RF
    fit = sm.OLS(y, x, missing='raise').fit(cov_type='HAC', cov_kwds={'maxlags':lag, 'use_correction':True}, use_t=False)
    interval = fit.conf_int(alpha=.05)
    terms = {name:{'coefficient':float(fit.params[name]), 'hac_se':float(fit.bse[name]),
                   'z_stat':float(fit.tvalues[name]), 'p_value_unadjusted':float(fit.pvalues[name]),
                   'lower_95':float(interval.loc[name, 0]), 'upper_95':float(interval.loc[name, 1])}
             for name in x.columns}
    return {'observations':len(y), 'first_date':str(y.index[0].date()), 'last_date':str(y.index[-1].date()),
            'hac_lag':lag, 'kernel':'Bartlett', 'small_sample_correction':True, 'inference':'normal, unadjusted',
            'r_squared':float(fit.rsquared), 'terms':terms,
            'annual_intercept_arithmetic':float(fit.params['const'] * 252),
            'annual_intercept_lower_95':float(interval.loc['const', 0] * 252),
            'annual_intercept_upper_95':float(interval.loc['const', 1] * 252),
            'excess_return_sharpe':metrics(y)['sharpe']}


def circular_indices(n: int, block: int, repetitions: int, rng: np.random.Generator) -> np.ndarray:
    if block < 1 or repetitions < 1 or n < 2 * block:
        raise ValueError("Each segment requires at least two blocks")
    starts = rng.integers(0, n, size=(repetitions, int(np.ceil(n/block))))
    return ((starts[:, :, None] + np.arange(block)) % n).reshape(repetitions, -1)[:, :n]


def paired_bootstrap(left: pd.Series, right: pd.Series, *, block: int, segmented_years: bool,
                     repetitions: int = 2000, seed: int = 20261014) -> dict:
    check_dates(left)
    check_dates(right)
    if not left.index.equals(right.index):
        raise ValueError("Paired bootstrap requires identical dates")
    if (left <= -1).any() or (right <= -1).any():
        raise ValueError("Non-bankrupt returns required")
    groups = [np.flatnonzero(left.index.year == y) for y in sorted(set(left.index.year))] if segmented_years else [np.arange(len(left))]
    rng = np.random.default_rng(seed)
    indices = np.concatenate([group[circular_indices(len(group), block, repetitions, rng)] for group in groups], axis=1)
    a, b = left.to_numpy()[indices], right.to_numpy()[indices]
    mean_diff = (a.mean(axis=1) - b.mean(axis=1))*252
    av, bv = a.std(axis=1, ddof=1), b.std(axis=1, ddof=1)
    valid = (av > 1e-14) & (bv > 1e-14)
    sharpes = (a[valid].mean(axis=1)/av[valid] - b[valid].mean(axis=1)/bv[valid])*np.sqrt(252)
    lm, rm = metrics(left), metrics(right)
    return {'observations':len(left), 'block_days':block, 'repetitions':repetitions, 'seed':seed,
            'segments':[{'first':str(left.index[g[0]].date()), 'last':str(left.index[g[-1]].date()), 'count':len(g)} for g in groups],
            'annual_mean_difference':lm['annual_mean']-rm['annual_mean'],
            'annual_mean_difference_95':np.quantile(mean_diff,[.025,.975]).tolist(),
            'sharpe_difference':None if lm['sharpe'] is None or rm['sharpe'] is None else lm['sharpe']-rm['sharpe'],
            'sharpe_difference_95':np.quantile(sharpes,[.025,.975]).tolist() if len(sharpes) else None,
            'undefined_sharpe_resamples':int((~valid).sum()), 'sharpe_convention':'zero risk-free rate',
            'scope':'paired descriptive intervals conditional on this sample, not selection-adjusted tests'}


def validate_ledger(frame: pd.DataFrame) -> dict:
    fields = ['net_return','gross_pnl','trading_cost','borrow_cost','turnover','gross_exposure','net_exposure']
    check_dates(frame[fields])
    if (frame[['trading_cost','borrow_cost','turnover','gross_exposure']] < -1e-13).any().any():
        raise ValueError("Negative cost/turnover/exposure")
    if (frame.gross_exposure + 1e-12 < frame.net_exposure.abs()).any():
        raise ValueError("Gross exposure smaller than absolute net exposure")
    error = frame.net_return - (frame.gross_pnl-frame.trading_cost-frame.borrow_cost)
    cost_error = frame.trading_cost - frame.turnover*.6/10000
    if error.abs().max() > 1e-12 or cost_error.abs().max() > 1e-12:
        raise ValueError("Published ledger/base-cost identity does not reconcile")
    if frame.borrow_cost.abs().max() > 1e-12:
        raise ValueError("Extension assumes original zero borrow cost")
    return {'max_return_identity_error':float(error.abs().max()), 'max_base_cost_error':float(cost_error.abs().max())}


def cost_overlay(frame: pd.DataFrame, fee_bps: float, borrow_rate: float) -> pd.Series:
    validate_ledger(frame)
    if not np.isfinite([fee_bps,borrow_rate]).all() or min(fee_bps,borrow_rate) < 0:
        raise ValueError("Nonnegative finite costs required")
    short = ((frame.gross_exposure-frame.net_exposure)/2).clip(lower=0)
    return frame.gross_pnl-frame.turnover*fee_bps/10000-short*borrow_rate/252


def cost_summary(frame: pd.DataFrame) -> dict:
    reconciliation = validate_ledger(frame)
    turnover = float(frame.turnover.mean())
    return {**reconciliation, 'annualized_turnover':turnover*252,
            'mean_gross_exposure':float(frame.gross_exposure.mean()),
            'mean_short_exposure':float(((frame.gross_exposure-frame.net_exposure)/2).mean()),
            'arithmetic_break_even_fee_bps_zero_borrow':float(frame.gross_pnl.mean()/turnover*10000) if turnover > 0 else None,
            'gross_metrics':metrics(frame.gross_pnl), 'net_metrics':metrics(frame.net_return)}
