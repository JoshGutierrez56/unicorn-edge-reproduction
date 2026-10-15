"""Synthetic contract checks only; no WRDS credentials/data needed in CI."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from unicorn_edge.signals import SignalConfig,make_signals


def panels():
    rng=np.random.default_rng(24)
    index=pd.bdate_range('2001-01-01',periods=200)
    returns=pd.DataFrame(rng.normal(.002,.02,(200,8)),index=index)
    returns.iloc[0]=np.nan
    prices=100*(1+returns.fillna(0)).cumprod()
    return prices,returns


def test_direct_return_route_matches_original_complete_price_history():
    prices,returns=panels();config=SignalConfig(threshold=.5)
    original=make_signals(prices,prices,config)
    direct=make_signals(prices,None,config,explicit_returns=returns)
    np.testing.assert_allclose(original['weights'],direct['weights'],atol=1e-12)
    assert original['gate'].equals(direct['gate'])


def test_missing_direct_return_invalidates_lookback_without_zero_fill():
    prices,returns=panels();returns.iloc[80,0]=np.nan
    result=make_signals(prices,None,SignalConfig(),explicit_returns=returns)
    assert not result['eligible'].iloc[80:144,0].any()
    assert result['up_fraction'].iloc[81:144,0].isna().all()


def test_membership_filters_cross_section_but_preserves_prior_lookback():
    prices,returns=panels();mask=pd.DataFrame(True,index=prices.index,columns=prices.columns)
    mask.iloc[:120,0]=False;mask.iloc[150:,0]=False
    result=make_signals(prices,None,SignalConfig(threshold=0),explicit_returns=returns,universe_mask=mask)
    assert result['weights'].iloc[:120,0].eq(0).all()
    assert result['weights'].iloc[150:,0].eq(0).all()
    assert result['eligible'].iloc[120:150,0].all()
    np.testing.assert_allclose(result['base'].iloc[100,1:],make_signals(prices.iloc[:,1:],None,SignalConfig(threshold=0),explicit_returns=returns.iloc[:,1:])['base'].iloc[100],atol=1e-12)


def test_invalid_return_and_mask_are_rejected():
    prices,returns=panels();returns.iloc[90,0]=-1
    with pytest.raises(ValueError,match='total-loss'):make_signals(prices,None,SignalConfig(),explicit_returns=returns)
    _,returns=panels()
    with pytest.raises(ValueError,match='booleans'):make_signals(prices,None,SignalConfig(),explicit_returns=returns,universe_mask=prices*0)


def test_identity_does_not_guess_ambiguous_share_classes():
    path=Path(__file__).resolve().parents[1]/'scripts/download_crsp.py'
    spec=importlib.util.spec_from_file_location('download_crsp',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[{'permno':i,'ticker':'AAA','tradingsymbol':f'AAA{cls}','shareclass':cls,'secinfoenddt':'2025-12-31'} for i,cls in [(1,'A'),(2,'B')]]
    assert module.resolve_identity('AAA',rows)['status']=='ambiguous'
    assert module.resolve_identity('AAA-B',rows)['permno']==2
    assert module.resolve_identity('BBB',rows)['status']=='unmatched'
