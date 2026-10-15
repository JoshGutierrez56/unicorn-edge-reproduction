"""Export only aggregate experiment outputs, never the licensed source cache."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('results','audit','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('Use a new output directory')
    source=json.loads((args.results/'receipt.json').read_text())
    exact={'specification.json','data-quality.json','coverage.csv','provider-return-comparison.json',
           'summary.csv','windows.csv','annual-windows.csv'}
    for name,digest in source['files'].items():
        if Path(name).name!=name or sha(args.results/name)!=digest:raise ValueError('Source experiment checksum mismatch')
        if name not in exact and name!='blocked-windows.json' and not re.fullmatch(r'(?:PARTIAL-)?(?:yahoo|crsp)_[a-z_0-9-]+-(?:daily.csv|gate-counts.csv|summary.json)',name):
            raise ValueError('Unrecognized aggregate artifact; manual review required')
    args.output.mkdir(parents=True)
    for name in source['files']:
        if name=='blocked-windows.json':continue
        shutil.copyfile(args.results/name,args.output/name)
    blocked=json.loads((args.results/'blocked-windows.json').read_text())
    public=[]
    for row in blocked:
        reason=row['reason']
        if reason.startswith('Missing held return at '):category='Unresolved held return; source-security/date detail retained privately'
        elif reason=='Final liquidation is blocked by an unavailable closing quote':category=reason
        else:raise ValueError('Unreviewed failure detail; do not publish automatically')
        public.append({'case':row['case'],'year':row['year'],'reason':category})
    (args.output/'blocked-windows.json').write_text(json.dumps(public,indent=2),encoding='utf-8')
    shutil.copyfile(args.audit,args.output/'numerical-audit.json')
    shutil.copyfile(args.results/'receipt.json',args.output/'source-run-receipt.json')
    receipt={'source_run_receipt_sha256':sha(args.results/'receipt.json'),
             'code_commit':source['code_commit'],'complete_cases':source['complete_cases'],
             'declared_cases':source['declared_cases'],'failed_windows':source['failed_windows'],
             'publication_transform':'Only blocked-window source-security/date details removed. All other run artifacts byte-preserved. Raw licensed cache, mappings and identity review not exported.',
             'files':{f.name:sha(f) for f in sorted(args.output.iterdir()) if f.is_file()}}
    (args.output/'publication-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ('complete_cases','declared_cases','failed_windows')}))


if __name__=='__main__':main()
