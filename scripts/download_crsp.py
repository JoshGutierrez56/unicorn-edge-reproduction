"""Bounded, read-only WRDS acquisition. Licensed rows must stay outside the repo."""
import argparse
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess


HOST = 'wrds-pgdata.wharton.upenn.edu'
START, END = '2003-01-01', '2024-12-31'
REPO = Path(__file__).resolve().parents[1]
IDENTITY_SQL = '''SELECT permno, ticker, tradingsymbol, shareclass, securitynm,
secinfostartdt, secinfoenddt, securitybegdt, securityenddt
FROM crsp.stksecurityinfohist
WHERE (ticker = ANY(%s) OR tradingsymbol = ANY(%s))
AND secinfostartdt <= %s AND secinfoenddt >= %s
ORDER BY ticker, secinfoenddt DESC, permno'''
MEMBERSHIP_SQL = '''SELECT permno,start,ending FROM crsp.dsp500list
WHERE start <= %s AND ending >= %s ORDER BY permno,start'''
CALENDAR_SQL = '''SELECT caldt AS date FROM crsp.metaexchangecalendar
WHERE caldt BETWEEN %s AND %s AND tradingflg='Y' AND exchangegroup='CIZ'
ORDER BY caldt'''
DAILY_SQL = '''SELECT permno,dlycaldt AS date,ticker,dlyprc,dlycumfacpr,
dlyret,dlyretx,dlyretmissflg,dlyretdurflg,dlydelflg,tradingstatusflg,dlyprcflg
FROM crsp.dsf_v2 WHERE permno=ANY(%s) AND dlycaldt BETWEEN %s AND %s
ORDER BY dlycaldt,permno'''


def connection():
    import psycopg2
    default = Path(os.environ.get('APPDATA', Path.home()/'AppData/Roaming'))/'postgresql/pgpass.conf' if os.name=='nt' else Path.home()/'.pgpass'
    passfile=Path(os.environ.get('PGPASSFILE',str(default)))
    username=os.environ.get('WRDS_USERNAME')
    if not username and passfile.exists():
        entries=[line.split(':',4) for line in passfile.read_text().splitlines() if line and not line.startswith('#')]
        users={x[3] for x in entries if len(x)==5 and x[0]==HOST and x[1] in {'9737','*'} and x[2] in {'wrds','*'}}
        del entries
        if len(users)==1:username=users.pop()
    if not username or not passfile.exists():
        raise RuntimeError('Configure authorized WRDS access through a local libpq passfile.')
    try:
        db=psycopg2.connect(host=HOST,port=9737,dbname='wrds',user=username,passfile=str(passfile),
                            sslmode='require',connect_timeout=45,options='-c statement_timeout=180000')
    except psycopg2.Error:
        raise RuntimeError('WRDS connection failed; account/network/Duo may require attention. Credentials not logged.') from None
    db.set_session(readonly=True,autocommit=True)
    return db


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def write_json(path, value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')
    temp.replace(path)


def fetch_small(db, query, params):
    with db.cursor() as c:
        c.execute(query,params)
        names=[x[0] for x in c.description]
        return [dict(zip(names,row)) for row in c.fetchall()]


def resolve_identity(symbol, rows):
    """Latest available matching identity, with explicit share-class handling."""
    base,separator,shareclass=symbol.partition('-')
    matches=[]
    for row in rows:
        ticker=(row['ticker'] or '').strip()
        trading=(row['tradingsymbol'] or '').strip().replace('.','-').replace('/','-')
        cls=(row['shareclass'] or '').strip()
        if separator:
            match=(trading==symbol or (ticker in {base,symbol} and cls==shareclass))
        else:
            match=(ticker==symbol or trading==symbol)
        if match:matches.append(row)
    if not matches:return {'symbol':symbol,'status':'unmatched'}
    latest=max(str(row['secinfoenddt']) for row in matches)
    selected=[r for r in matches if str(r['secinfoenddt'])==latest]
    ids=sorted({int(r['permno']) for r in selected})
    if len(ids)!=1:return {'symbol':symbol,'status':'ambiguous','candidate_permnos':ids}
    return {'symbol':symbol,'status':'matched','permno':ids[0],'latest_identity_end':latest}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args();folder=args.cache.resolve()
    if folder==REPO or folder.is_relative_to(REPO):
        raise ValueError('Licensed data must be stored outside this public repository.')
    folder.mkdir(parents=True,exist_ok=True)
    universe=REPO/'docs/universe.csv'
    symbols=[r['Symbol'].replace('.','-') for r in csv.DictReader(universe.open(encoding='utf-8',newline=''))]
    specification={'source':'WRDS / CRSP CIZ','start':START,'end':END,
                   'identity_asof':'2026-10-14','universe_sha256':digest(universe),
                   'queries':{'identity':IDENTITY_SQL,'membership':MEMBERSHIP_SQL,'calendar':CALENDAR_SQL,'daily':DAILY_SQL}}
    receipt_file=folder/'receipt.json'
    if receipt_file.exists():
        receipt=json.loads(receipt_file.read_text(encoding='utf-8'))
        if receipt['specification']!=specification:raise ValueError('Acquisition specification changed; use a fresh directory.')
        for name,item in receipt['files'].items():
            if Path(name).name!=name or digest(folder/name)!=item['sha256']:
                raise ValueError('Acquisition checkpoint integrity failure.')
    else:
        receipt={'specification':specification,'started_utc':datetime.now(timezone.utc).isoformat(),
                 'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                 'script_sha256':digest(Path(__file__)),'files':{},'status':'in_progress'}
    db=connection()
    try:
        metadata=folder/'identities-and-membership.json'
        if metadata.name in receipt['files']:
            info=json.loads(metadata.read_text(encoding='utf-8'))
        else:
            aliases=sorted(set(symbols+[s.replace('-','.') for s in symbols]+[s.replace('-','/') for s in symbols]))
            tickers=sorted(set(symbols+[s.split('-')[0] for s in symbols]))
            rows=fetch_small(db,IDENTITY_SQL,(tickers,aliases,'2026-10-14',START))
            import psycopg2
            try:
                members=fetch_small(db,MEMBERSHIP_SQL,(END,START))
                membership_status='available'
            except psycopg2.errors.InsufficientPrivilege:
                members=[]
                membership_status='blocked: licensed account lacks permission for the index-membership schema; no historical-membership backtest authorized by this extract'
            calendar=fetch_small(db,CALENDAR_SQL,(START,END))
            mappings=[resolve_identity(s,rows) for s in symbols]
            matched=[r['permno'] for r in mappings if r['status']=='matched']
            if len(set(matched))!=len(matched):raise ValueError('Two current symbols map to one PERMNO; investigate before download.')
            info={'identities':rows,'mappings':mappings,'membership':members,'membership_status':membership_status,'calendar':calendar}
            write_json(metadata,info)
            receipt['files'][metadata.name]={'sha256':digest(metadata),'kind':'private metadata'}
            write_json(receipt_file,receipt)
        ids=sorted({int(x['permno']) for x in info['membership']} | {int(x['permno']) for x in info['mappings'] if x['status']=='matched'})
        if not 400<=len(ids)<=2500:raise ValueError('Unexpected universe size; refusing an unbounded extract.')
        counts={status:sum(x['status']==status for x in info['mappings']) for status in ('matched','unmatched','ambiguous')}
        print(json.dumps({'identity_counts':counts,'total_permanent_ids':len(ids),'membership_status':info['membership_status']}),flush=True)
        for year in range(2003,2025):
            name=f'daily-{year}.csv.gz'
            if name in receipt['files']:continue
            path=folder/name;temp=folder/(name+'.part');count=0
            with db.cursor() as c, gzip.open(temp,'wt',encoding='utf-8',newline='') as output:
                c.execute(DAILY_SQL,(ids,date(year,1,1),date(year,12,31)))
                writer=csv.writer(output);writer.writerow([x[0] for x in c.description])
                while True:
                    rows=c.fetchmany(10000)
                    if not rows:break
                    count+=len(rows)
                    if count>1000000:raise ValueError('Yearly row bound exceeded.')
                    writer.writerows(rows)
            if count==0:raise ValueError('Empty licensed-data year; do not silently continue.')
            temp.replace(path)
            receipt['files'][name]={'sha256':digest(path),'rows':count}
            write_json(receipt_file,receipt)
            print(f'{year}: {count} private rows saved; {year-2002}/22 years',flush=True)
        receipt['status']='complete';receipt['completed_utc']=datetime.now(timezone.utc).isoformat()
        receipt['daily_rows']=sum(x.get('rows',0) for x in receipt['files'].values())
        write_json(receipt_file,receipt)
        print(json.dumps({'status':'complete','daily_rows':receipt['daily_rows']}),flush=True)
    finally:db.close()


if __name__=='__main__':main()
