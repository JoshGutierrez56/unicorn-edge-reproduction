"""Acquire official public French daily archives into a new private directory."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    root = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/'
    files = {'ff5-daily.zip':'F-F_Research_Data_5_Factors_2x3_daily_CSV.zip',
             'momentum-daily.zip':'F-F_Momentum_Factor_daily_CSV.zip'}
    receipt = []
    for filename,remote in files.items():
        url = root+remote
        with urlopen(Request(url,headers={'User-Agent':'UnicornEdgeResearch/1.0'}),timeout=60) as response:
            if response.status != 200:
                raise RuntimeError(f'Unexpected HTTP {response.status}')
            payload = response.read(10_000_001)
        if len(payload)>10_000_000:
            raise ValueError('Archive exceeds size cap')
        path = a.output/filename
        path.write_bytes(payload)
        with ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith('.csv')]
            if len(members)!=1:
                raise ValueError('Unexpected archive contents')
            header = archive.read(members[0]).decode('utf-8-sig').splitlines()[:4]
        receipt.append({'file':filename,'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),
                        'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'header':header})
    (a.output/'factor-source-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print('Two official archives recorded; current downloads may differ from the published vintage.')


if __name__ == '__main__':
    main()
