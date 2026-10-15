"""Validate private CIZ extracts without redistributing licensed security rows."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_crsp_cache(folder: Path):
    receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
    if receipt['status']!='complete':raise ValueError('Incomplete CRSP acquisition')
    for name,item in receipt['files'].items():
        if Path(name).name!=name:raise ValueError('Unsafe cache filename')
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('CRSP source checksum differs')
    metadata=json.loads((folder/'identities-and-membership.json').read_text(encoding='utf-8'))
    mappings={int(row['permno']):row['symbol'] for row in metadata['mappings'] if row['status']=='matched'}
    frames=[pd.read_csv(folder/name,keep_default_na=False,low_memory=False)
            for name in sorted(receipt['files']) if name.startswith('daily-')]
    rows=pd.concat(frames,ignore_index=True)
    if rows.duplicated(['permno','date']).any():raise ValueError('Duplicate CRSP security/date')
    if set(rows.permno)-set(mappings):raise ValueError('Unmapped CRSP permanent identifier')
    rows['symbol']=rows.permno.map(mappings)
    rows['date']=pd.to_datetime(rows.date)
    calendar=pd.DatetimeIndex(pd.to_datetime([r['date'] for r in metadata['calendar']]),name='date')
    if not calendar.is_unique or not calendar.is_monotonic_increasing:raise ValueError('Invalid CRSP calendar')
    if not rows.date.isin(calendar).all():raise ValueError('Observation outside trading calendar')
    for column in ('dlyprc','dlycumfacpr','dlyret'):
        rows[column]=pd.to_numeric(rows[column],errors='coerce')
        if np.isinf(rows[column]).any():raise ValueError('Infinite source observation')
    if rows.dlyret.le(-1).any():raise ValueError('Total-loss event needs explicit treatment')
    observed=rows.dlyretmissflg.eq('NA') & rows.dlyretdurflg.isin(['D1','D2','D3','D4','DU'])
    rows['total_return']=rows.dlyret.where(observed)
    rows['nominal']=rows.dlyprc.abs().where(rows.dlyprc.ne(0))
    rows['split_adjusted']=rows.nominal/rows.dlycumfacpr.where(rows.dlycumfacpr.gt(0))
    columns=sorted(mappings.values())
    def panel(field):return rows.pivot(index='date',columns='symbol',values=field).reindex(index=calendar,columns=columns)
    quality={'source':'WRDS / CRSP CIZ, current vintage','rows':len(rows),'calendar_sessions':len(calendar),
             'mapped_symbols':len(mappings),'observed_symbols':int(rows.symbol.nunique()),
             'excluded_flagged_returns':int((~observed).sum()),
             'return_flags':rows.dlyretmissflg.value_counts().to_dict(),
             'duration_flags':rows.dlyretdurflg.value_counts().to_dict(),
             'price_flags':rows.dlyprcflg.value_counts().to_dict(),
             'membership_status':metadata['membership_status'],
             'unresolved_mappings':[r for r in metadata['mappings'] if r['status']!='matched'],
             'acquisition_receipt_sha256':hashlib.sha256((folder/'receipt.json').read_bytes()).hexdigest()}
    return panel('nominal'),panel('split_adjusted'),panel('total_return'),quality
