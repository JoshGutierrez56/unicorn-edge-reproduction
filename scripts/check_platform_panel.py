"""Run only the compatible existing Alpha & Risk Lab panel validator, read-only."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--platform',type=Path,required=True)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    a = p.parse_args()
    if a.receipt.exists():
        raise FileExistsError(a.receipt)
    source = a.platform/'portfolio_lab/accounting.py'
    spec = importlib.util.spec_from_file_location('readonly_alpha_accounting',source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    names = ['crsp_nominal_stale_freeze','crsp_split_stale_freeze','yahoo_close_quote_freeze']
    series = [pd.read_csv(a.input/(n+'-annual-daily.csv'),index_col='date',parse_dates=True).net_return.rename(n) for n in names]
    if not all(s.index.equals(series[0].index) for s in series):
        raise ValueError('Calendars do not match')
    panel = pd.concat(series,axis=1)
    module.validate_panel(panel,universe=names)
    failures = {}
    for name,corrupt in [('missing',panel.mask(np.arange(len(panel))[:,None]==3)),
                         ('duplicate',pd.concat([panel.iloc[:1],panel])),
                         ('unsorted',panel.iloc[::-1]),
                         ('bankrupt',panel.where(panel.index!=panel.index[0],-1,axis=0))]:
        try:
            module.validate_panel(corrupt,universe=names)
        except ValueError:
            failures[name] = 'rejected'
        else:
            raise AssertionError(f'Fault not caught: {name}')
    a.receipt.write_text(json.dumps({'platform_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.platform,text=True).strip(),
        'source_file':'portfolio_lab/accounting.py','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'observations':len(panel),'series':names,'panel_validation':'passed','injected_faults':failures,
        'not_used':'Long-only funded ledger: incompatible with this signed long/short portfolio.',
        'scope':'Aggregate-return contract only; not security identity, holdings or strategy validation.'},indent=2)+'\n',encoding='utf-8')
    print('Existing panel contract passed; four injected faults rejected.')


if __name__ == '__main__':
    main()
