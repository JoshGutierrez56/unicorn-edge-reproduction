"""Validate private CIZ extracts without redistributing licensed security rows."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def reviewed_mappings(metadata, metadata_hash, review):
    """Require a complete issuer/share-class review, not ticker-only inference."""
    if review.get('metadata_sha256') != metadata_hash:
        raise ValueError('Identity review does not match the private source metadata')
    original = {r['symbol']: r for r in metadata['mappings'] if r['status'] == 'matched'}
    decisions = review.get('decisions', [])
    if len(decisions) != len(original) or {r['symbol'] for r in decisions} != set(original):
        raise ValueError('Identity review must account for every candidate exactly once')
    approved = {}
    for decision in decisions:
        source = original[decision['symbol']]
        if int(decision['permno']) != int(source['permno']):
            raise ValueError('Identity review cannot silently substitute a permanent ID')
        if decision['decision'] not in ('approved', 'excluded') or not decision.get('reason'):
            raise ValueError('Every identity needs a reviewed decision and reason')
        if decision['decision'] == 'approved':
            permno = int(source['permno'])
            if permno in approved: raise ValueError('Duplicate approved permanent ID')
            approved[permno] = source['symbol']
    return approved


def documented_gap_marks(rows):
    """Optional valuation convention, never observed daily returns or trade prices.

    Only MP gaps closed by documented P1/P2 multi-period returns are bridged.
    All other missing returns remain missing. Signals use the original returns.
    """
    marked = rows['total_return'].copy()
    gaps = []
    for _, group in rows.groupby('permno', sort=False):
        group = group.sort_values('date')
        indices = list(group.index)
        for position in np.flatnonzero(group.dlyretdurflg.isin(['P1', 'P2']).to_numpy()):
            last = group.iloc[position]
            missing_days = {'P1': 1, 'P2': 2}[last.dlyretdurflg]
            if position <= missing_days:
                raise ValueError('Multi-period return lacks a preceding valid valuation')
            gap = group.iloc[position-missing_days:position]
            prior = group.iloc[position-missing_days-1]
            if not (gap.dlyprc.isna().all() and gap.dlyret.isna().all()
                    and gap.dlyprcflg.eq('MP').all() and gap.dlyretmissflg.eq('MP').all()
                    and np.isfinite(prior.dlyprc) and np.isfinite(last.dlyprc)
                    and np.isfinite(last.dlyret) and last.dlyret > -1):
                raise ValueError('Multi-period return does not close the documented missing-price interval')
            # Calendar consecutiveness is verified by the caller's session ordinal.
            interval = group.iloc[position-missing_days-1:position+1]
            if not np.all(np.diff(interval.session_ordinal.to_numpy()) == 1):
                raise ValueError('Unobserved calendar rows within a multi-period return')
            for index in indices[position-missing_days:position]: marked.loc[index] = 0.
            marked.loc[indices[position]] = float(last.dlyret)
            gaps.append({'missing_sessions': missing_days})
    return marked, {'bridged_intervals': len(gaps), 'stale_valuation_sessions': sum(r['missing_sessions'] for r in gaps),
                    'policy': 'Last valuation carried during documented MP gaps; no trading without a quote. Full P1/P2 return applied on resumption. These are modeled valuations, not observed zero returns. Signal lookbacks remain missing.'}


def load_crsp_cache(folder: Path):
    receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
    if receipt['status']!='complete':raise ValueError('Incomplete CRSP acquisition')
    for name,item in receipt['files'].items():
        if Path(name).name!=name:raise ValueError('Unsafe cache filename')
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('CRSP source checksum differs')
    metadata=json.loads((folder/'identities-and-membership.json').read_text(encoding='utf-8'))
    review_file=folder/'identity-review.json'
    review=json.loads(review_file.read_text(encoding='utf-8'))
    mappings=reviewed_mappings(metadata, receipt['files']['identities-and-membership.json']['sha256'], review)
    frames=[pd.read_csv(folder/name,keep_default_na=False,low_memory=False)
            for name in sorted(receipt['files']) if name.startswith('daily-')]
    rows=pd.concat(frames,ignore_index=True)
    if rows.duplicated(['permno','date']).any():raise ValueError('Duplicate CRSP security/date')
    acquired={int(r['permno']) for r in metadata['mappings'] if r['status']=='matched'}
    if set(rows.permno)-acquired:raise ValueError('Unmapped CRSP permanent identifier')
    source_rows=len(rows)
    rows=rows.loc[rows.permno.isin(mappings)].copy()
    rows['symbol']=rows.permno.map(mappings)
    rows['date']=pd.to_datetime(rows.date)
    calendar=pd.DatetimeIndex(pd.to_datetime([r['date'] for r in metadata['calendar']]),name='date')
    if not calendar.is_unique or not calendar.is_monotonic_increasing:raise ValueError('Invalid CRSP calendar')
    if not rows.date.isin(calendar).all():raise ValueError('Observation outside trading calendar')
    for column in ('dlyprc','dlycumfacpr','dlyret'):
        rows[column]=pd.to_numeric(rows[column].replace('', np.nan),errors='raise')
        if np.isinf(rows[column]).any():raise ValueError('Infinite source observation')
    if rows.dlyret.le(-1).any():raise ValueError('Total-loss event needs explicit treatment')
    observed=rows.dlyretmissflg.eq('NA') & rows.dlyretdurflg.isin(['D1','D2','D3','D4','DU'])
    rows['total_return']=rows.dlyret.where(observed)
    rows['nominal']=rows.dlyprc.abs().where(rows.dlyprc.ne(0))
    rows['split_adjusted']=rows.nominal/rows.dlycumfacpr.where(rows.dlycumfacpr.gt(0))
    rows['session_ordinal']=rows.date.map({date:i for i,date in enumerate(calendar)})
    rows['valuation_return'],gap_quality=documented_gap_marks(rows)
    rows['tradable']=rows.nominal.notna() & rows.tradingstatusflg.eq('A') & rows.dlyprcflg.isin(['TR','BA'])
    columns=sorted(mappings.values())
    def panel(field):return rows.pivot(index='date',columns='symbol',values=field).reindex(index=calendar,columns=columns)
    quality={'source':'WRDS / CRSP CIZ, current vintage','rows':len(rows),'acquired_rows':source_rows,'calendar_sessions':len(calendar),
             'mapped_symbols':len(mappings),'observed_symbols':int(rows.symbol.nunique()),
             'excluded_flagged_returns':int((~observed).sum()),
             'return_flags':rows.dlyretmissflg.value_counts().to_dict(),
             'duration_flags':rows.dlyretdurflg.value_counts().to_dict(),
             'price_flags':rows.dlyprcflg.value_counts().to_dict(),
             'membership_status':metadata['membership_status'],
             'unresolved_mappings':[r for r in metadata['mappings'] if r['status']!='matched'],
             'identity_review_sha256':hashlib.sha256(review_file.read_bytes()).hexdigest(),
             'excluded_identity_candidates':[{k:r[k] for k in ('symbol','reason')} for r in review['decisions'] if r['decision']=='excluded'],
             'modeled_gap_valuation':gap_quality,
             'acquisition_receipt_sha256':hashlib.sha256((folder/'receipt.json').read_bytes()).hexdigest()}
    return panel('nominal'),panel('split_adjusted'),panel('total_return'),panel('valuation_return'),panel('tradable').fillna(False).astype(bool),quality
