"""Create a PRIVATE, unapproved issuer-review template. Never auto-approve tickers."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    cache=args.cache.resolve()
    if cache==root or cache.is_relative_to(root):raise ValueError('Review belongs outside the public repository')
    output=cache/'identity-review.json'
    if output.exists():raise ValueError('Existing identity review is never overwritten')
    path=cache/'identities-and-membership.json'
    metadata=json.loads(path.read_text(encoding='utf-8'))
    universe={r['Symbol'].replace('.','-'):r['Security'] for r in csv.DictReader((root/'docs/universe.csv').open(encoding='utf-8'))}
    decisions=[]
    for row in metadata['mappings']:
        if row['status']!='matched':continue
        candidates=[r for r in metadata['identities'] if int(r['permno'])==int(row['permno'])]
        latest=max(candidates,key=lambda r:r['secinfoenddt'])
        decisions.append({'symbol':row['symbol'],'permno':row['permno'],
            'expected_issuer':universe[row['symbol']], 'candidate_identity':latest,
            'decision':'PENDING','reason':''})
    review={'metadata_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'reviewer':'REQUIRED: identify who performed the issuer/share-class review',
            'instructions':'Compare every issuer and share class, including renamed and reused symbols. Enter approved or excluded with a reason. A ticker string alone is not identity evidence. No market-result-based selection.',
            'decisions':decisions}
    output.write_text(json.dumps(review,indent=2),encoding='utf-8')
    print(f'Created an unapproved private review for {len(decisions)} candidates. Research refuses pending decisions.')


if __name__=='__main__':main()
