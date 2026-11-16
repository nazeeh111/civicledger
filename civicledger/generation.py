"""Publish an immutable local warehouse generation with one atomic pointer."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from decimal import Decimal, InvalidOperation

import duckdb


MAX_PUBLIC_BYTES = 16 * 1024 * 1024

PUBLIC_FILES = frozenset((
    'index.html','app.js','styles.css','favicon.svg','data.json','linkage.json',
    'reports.json','cases.json','peer_award_year.json','revision_lag.json',
    'assets/fonts/SOURCES.txt','assets/fonts/dm-sans-0.woff2','assets/fonts/dmsans-OFL.txt',
    'assets/fonts/ibm-plex-mono-1.woff2','assets/fonts/ibm-plex-mono-2.woff2',
    'assets/fonts/ibmplexmono-OFL.txt','assets/fonts/libre-caslon-display-3.woff2',
    'assets/fonts/librecaslondisplay-OFL.txt',
))

ARTIFACTS = ('data/warehouse.duckdb','data/processed/validation.json','data/processed/analytics.json',
             'app/dist/data.json','app/dist/app.js','app/dist/index.html','app/dist/styles.css',
             'app/dist/linkage.json','app/dist/reports.json','app/dist/cases.json',
             'app/dist/peer_award_year.json','app/dist/revision_lag.json',
             'data/processed/transactions.csv','data/processed/manifest.json',
             'data/processed/dbt_validation.json','data/processed/peer_award_year.json',
             'data/processed/revision_lag.json','data/processed/performance.json',
             'data/reports/analysis.json','data/reports/cases.json','data/linkage/linkage.json',
             'sql/01_warehouse.sql','sql/02_validation.sql') + tuple(
                 f'data/processed/{name}.csv' for name in ('annual_summary','peer_competition',
                 'recipient_year','monthly_patterns','recipient_entry_exit','composition','mart_awards'))
ARTIFACTS = tuple(dict.fromkeys(ARTIFACTS + tuple('app/dist/'+name for name in sorted(PUBLIC_FILES))))

def digest(path):
    checksum=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024),b''):
            checksum.update(block)
    return checksum.hexdigest()


def _ignore(directory, names):
    ignored = {'.git', '.venv', '__pycache__', '.pytest_cache', 'generations',
               'current', 'warehouse.duckdb', 'warehouse.duckdb.wal', 'target', 'logs'}
    return ignored.intersection(names)



def real_child(parent, name, create=False):
    path=parent/name
    if path.is_symlink():
        raise ValueError('Directory must not be a symbolic link: '+str(path))
    if create:
        path.mkdir(exist_ok=True)
    if not path.is_dir() or path.resolve(strict=True) != parent/name:
        raise ValueError('Directory must be a contained real directory: '+str(path))
    return path


def no_links(root):
    if root.is_symlink():
        raise ValueError('Symbolic link is not permitted: '+str(root))
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs+files:
            path=Path(directory)/name
            if path.is_symlink():
                raise ValueError('Symbolic link is not permitted: '+str(path))
            if not (path.is_dir() or path.is_file()):
                raise ValueError('Special file is not permitted: '+str(path))


def public_inventory(root):
    no_links(root)
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if actual != PUBLIC_FILES:
        raise ValueError('Public file inventory mismatch: missing '+str(sorted(PUBLIC_FILES-actual))+'; unexpected '+str(sorted(actual-PUBLIC_FILES)))
    for name in PUBLIC_FILES:
        if (root/name).stat().st_size > MAX_PUBLIC_BYTES:
            raise ValueError('Public file exceeds 16 MiB: '+name)


def stage_inputs(root, staging):
    # Only the actual source and evidence inputs are copied; generated generations,
    # arbitrary root files, and any symlink targets remain outside this boundary.
    real_child(root,'app')
    real_child(root,'data')
    staging.mkdir()
    for name in ('civicledger','sql','dbt','tests','docs','data/processed','data/linkage','data/reports','data/raw'):
        source=root/name
        if not source.exists() and not source.is_symlink():
            if name=='data/raw': continue
            raise ValueError('Missing input directory: '+name)
        no_links(source)
        target=staging/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,target,ignore=_ignore,symlinks=True)
    public=root/'app/dist';public_inventory(public)
    for name in sorted(PUBLIC_FILES):
        target=staging/'app/dist'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(public/name,target,follow_symlinks=False)
    for name in ('app/check-data.mjs','app/README.md','pyproject.toml','README.md','LICENSE'):
        source=root/name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing or linked input file: '+name)
        target=staging/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target,follow_symlinks=False)
    no_links(staging)


def validate_cases(staging, identity):
    cases=json.loads((staging/'data/reports/cases.json').read_text())
    if not isinstance(cases,list):
        raise ValueError('Cases must be a list tied to the staged source')
    con=duckdb.connect(str(staging/'data/warehouse.duckdb'),read_only=True)
    try:
        for case in cases:
            if not isinstance(case,dict) or not isinstance(case.get('record'),dict):
                raise ValueError('Case lacks its source record')
            record=case['record']; award=record.get('award_id'); transaction=record.get('transaction_id')
            if not isinstance(award,str) or not award:
                raise ValueError('Case lacks a source award ID')
            if not con.execute('SELECT count(*) FROM fact_transactions WHERE award_id=?',[award]).fetchone()[0]:
                raise ValueError('Case award is absent from staged source: '+award)
            if transaction is not None:
                if not isinstance(transaction,str): raise ValueError('Invalid case transaction ID')
                row=con.execute('SELECT obligation,fiscal_year,action_date,piid,recipient_name,modification_number FROM fact_transactions WHERE award_id=? AND transaction_id=?',[award,transaction]).fetchone()
                if row is None: raise ValueError('Case transaction is absent from staged source: '+transaction)
                for key,value in zip(('obligation','fy','action','piid','recipient','modification'),row):
                    if key not in record: continue
                    try: matches = Decimal(str(record[key]))==value if key=='obligation' else str(record[key])==str(value)
                    except InvalidOperation: matches=False
                    if not matches: raise ValueError('Case transaction field differs from staged source: '+key)
            else:
                row=con.execute('SELECT net_obligations,positive_obligations,transaction_count,first_action,last_action,piid,recipient_name FROM mart_awards WHERE award_id=?',[award]).fetchone()
                for key,value in zip(('net','positive','actions','first_observed','last_observed','piid','recipient'),row):
                    if key not in record: continue
                    try: matches = Decimal(str(record[key]))==value if key in ('net','positive') else str(record[key])==str(value)
                    except InvalidOperation: matches=False
                    if not matches: raise ValueError('Case award field differs from staged source: '+key)
            for ref in case.get('evidence',[]):
                if not isinstance(ref,dict): raise ValueError('Invalid case evidence reference')
                ref_award=ref.get('award_id',award); ref_tx=ref.get('transaction_id')
                if not isinstance(ref_award,str) or not con.execute('SELECT count(*) FROM fact_transactions WHERE award_id=?',[ref_award]).fetchone()[0]:
                    raise ValueError('Case evidence award is absent from staged source')
                if ref_tx is not None and (not isinstance(ref_tx,str) or not con.execute('SELECT count(*) FROM fact_transactions WHERE award_id=? AND transaction_id=?',[ref_award,ref_tx]).fetchone()[0]):
                    raise ValueError('Case evidence transaction is absent from staged source')
    finally:
        con.close()
    return {**identity,'sha256':digest(staging/'data/reports/cases.json'),
            'scope':'Case identifiers checked against staged transactions; narrative is not independently verified.'}

def publish(root: Path, mode='warehouse', arguments=()):
    root = Path(root).resolve()
    if mode not in {'warehouse', 'reproduce'}:
        raise ValueError('Unsupported generation mode')
    data = real_child(root, 'data', create=True)
    generations = real_child(data, 'generations', create=True)
    lock_fd=os.open(data/'.generation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(lock_fd,'a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another generation is being published') from None
        generation_id = uuid.uuid4().hex
        staging = generations / ('.staging-' + generation_id)
        final = generations / generation_id
        try:
            stage_inputs(root, staging)
            manifest_path = staging / 'data/processed/manifest.json'
            manifest = json.loads(manifest_path.read_text())
            source_hash = digest(staging / 'data/processed/transactions.csv')
            if source_hash != manifest['public_csv']['sha256']:
                raise ValueError('Source CSV does not match its manifest')
            identity = {'snapshot_id': manifest['snapshot_id'], 'public_csv_sha256': source_hash}
            if mode == 'warehouse':
                linkage = json.loads((staging / 'data/linkage/linkage.json').read_text())
                report = json.loads((staging / 'data/reports/analysis.json').read_text())
                dbt = json.loads((staging / 'data/processed/dbt_validation.json').read_text())
                if linkage.get('source') != identity or report.get('source_snapshot') != identity['snapshot_id'] or report.get('source_csv_sha256') != source_hash or not dbt.get('all_passed') or any(dbt.get(k) != v for k,v in identity.items()):
                    raise ValueError('Existing supporting evidence belongs to another source snapshot; run complete reproduction')
            manifest['generation_id'] = generation_id
            manifest['query_sha256'] = digest(staging / 'app/dist/app.js')
            manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
            env = os.environ.copy()
            env['PYTHONPATH'] = str(staging)
            env['CIVICLEDGER_STAGED'] = '1'
            env['CIVICLEDGER_GENERATION_ID'] = generation_id
            env['CIVICLEDGER_QUERY_SHA256'] = manifest['query_sha256']
            if mode == 'warehouse':
                command = [sys.executable, '-c', 'from civicledger.warehouse import _build_in_place; _build_in_place()']
            else:
                command = [sys.executable, '-m', 'civicledger.reproduce', *arguments]
            subprocess.run(command, cwd=staging, env=env, check=True)
            manifest = json.loads(manifest_path.read_text())
            source_hash = digest(staging / 'data/processed/transactions.csv')
            if manifest.get('generation_id') != generation_id or source_hash != manifest['public_csv']['sha256'] or manifest.get('query_sha256') != digest(staging / 'app/dist/app.js'):
                raise ValueError('Staged source or query identity changed during build')
            identity = {'snapshot_id':manifest['snapshot_id'], 'public_csv_sha256':source_hash}
            linkage = json.loads((staging / 'data/linkage/linkage.json').read_text())
            report = json.loads((staging / 'data/reports/analysis.json').read_text())
            dbt = json.loads((staging / 'data/processed/dbt_validation.json').read_text())
            if linkage.get('source') != identity or report.get('source_snapshot') != identity['snapshot_id'] or report.get('source_csv_sha256') != source_hash or not dbt.get('all_passed') or any(dbt.get(k) != v for k,v in identity.items()):
                raise ValueError('Supporting evidence does not match the staged source')
            for source,public in [('data/linkage/linkage.json','linkage.json'),('data/reports/analysis.json','reports.json'),('data/reports/cases.json','cases.json'),('data/processed/peer_award_year.json','peer_award_year.json'),('data/processed/revision_lag.json','revision_lag.json')]:
                if digest(staging / source) != digest(staging / 'app/dist' / public):
                    raise ValueError('Public evidence differs from its staged source: ' + public)
            validation = json.loads((staging / 'data/processed/validation.json').read_text())
            projection = json.loads((staging / 'app/dist/data.json').read_text())
            if not validation['all_passed'] or validation['generation_id'] != generation_id or projection['meta']['generation_id'] != generation_id or projection['meta']['public_csv_sha256'] != source_hash:
                raise ValueError('Incomplete or mismatched generation')

            no_links(staging)
            public_inventory(staging/'app/dist')
            case_evidence=validate_cases(staging,identity)
            (staging / 'generation.json').write_text(json.dumps({'generation_id':generation_id, **identity, 'mode':mode, 'query_sha256':manifest['query_sha256'], 'case_evidence':case_evidence, 'artifact_sha256':{name:digest(staging/name) for name in ARTIFACTS}}, indent=2)+'\n')
            os.rename(staging, final)
            pointer = data / ('.current-' + generation_id)
            os.symlink('generations/' + generation_id, pointer)
            try:
                os.replace(pointer, data / 'current')
            finally:
                if pointer.is_symlink(): pointer.unlink()
            print('Published generation', generation_id, flush=True)
            return final
        finally:
            if staging.exists(): shutil.rmtree(staging)
