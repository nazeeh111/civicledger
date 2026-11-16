"""Real warehouse failure points cannot replace the published generation."""
import fcntl
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest
from civicledger.generation import publish
from civicledger.warehouse import ROOT


def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture(scope='module')
def project(tmp_path_factory):
    root=tmp_path_factory.mktemp('civicledger')/'project'
    shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','generations','current','.venv','__pycache__','.pytest_cache','.generation.lock','*.duckdb','*.duckdb.wal'))
    publish(root)
    return root


@pytest.mark.parametrize('point',['raw','validation','json','csv'])
def test_failed_build_preserves_whole_generation(project,point):
    old=(project/'data/current').resolve(); before=hashes(old)
    original=subprocess.run
    code='''
import os
from pathlib import Path
import civicledger.warehouse as w
point=os.environ['TEST_POINT']
connect=w.duckdb.connect; save=w.save_json
class Proxy:
 def __init__(self,c):self.c=c
 def execute(self,sql,*a,**kw):
  r=self.c.execute(sql,*a,**kw)
  if point=='raw' and sql.startswith('CREATE OR REPLACE TABLE raw_transactions'):raise RuntimeError('fault raw')
  if point=='csv' and sql.startswith('COPY '):raise RuntimeError('fault csv')
  return r
 def __getattr__(self,k):return getattr(self.c,k)
def saver(p,obj):
 save(p,obj)
 if (point=='validation' and p.name=='validation.json') or (point=='json' and p==w.ROOT/'app/dist/data.json'):raise RuntimeError('fault '+point)
w.duckdb.connect=lambda *a,**kw:Proxy(connect(*a,**kw))
w.save_json=saver
w._build_in_place()
'''
    def fault(args,**kwargs):
        kwargs['env']['TEST_POINT']=point
        return original([sys.executable,'-c',code],**kwargs)
    with patch('civicledger.generation.subprocess.run',side_effect=fault), pytest.raises(subprocess.CalledProcessError):
        publish(project)
    assert (project/'data/current').resolve()==old
    assert hashes(old)==before
    assert not list((project/'data/generations').glob('.staging-*'))


def test_concurrent_publisher_refused(project):
    with (project/'data/.generation.lock').open('a+b') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='Another generation'):
            publish(project)


def test_verified_workspace_rejects_missing_or_changed_artifact(project,tmp_path):
    from civicledger.workspace import resolve_generation
    import json
    isolated=tmp_path/'project'; (isolated/'data/generations').mkdir(parents=True)
    current=(project/'data/current').resolve(); copied=isolated/'data/generations'/current.name
    shutil.copytree(current,copied);(isolated/'data/current').symlink_to('generations/'+current.name)
    assert resolve_generation(isolated)==copied
    manifest_path=copied/'generation.json'; manifest=json.loads(manifest_path.read_text())
    original=manifest_path.read_text();manifest['artifact_sha256'].pop('app/dist/data.json');manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='manifest is incomplete'):resolve_generation(isolated)
    manifest_path.write_text(original)
    with (copied/'app/dist/data.json').open('a') as out:out.write(' ')
    with pytest.raises(ValueError,match='artifact mismatch'):resolve_generation(isolated)


def test_retained_generation_reopens_after_new_publication(project,tmp_path):
    import json, os, re, urllib.request
    from civicledger.workspace import resolve_generation
    old=resolve_generation(project)
    saved=tmp_path/'investigation.json'
    subprocess.run(['node',str(old/'app/check-data.mjs'),'--export-investigation',str(saved)],check=True,capture_output=True)
    original=json.loads(saved.read_text())
    new=publish(project)
    assert new != old and resolve_generation(project)==new
    def serve(generation=None):
        env=os.environ.copy();env['PYTHONPATH']=str(project)
        args=[sys.executable,'-m','civicledger.workspace','--port','0']
        if generation is not None:args += ['--generation',generation]
        proc=subprocess.Popen(args,cwd=project,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            line=proc.stdout.readline(); match=re.search(r'http://127\.0\.0\.1:(\d+)/',line)
            assert match, (line,proc.stderr.read())
            with urllib.request.urlopen('http://127.0.0.1:'+match.group(1)+'/data.json',timeout=10) as response:
                return json.load(response)['meta']['generation_id']
        finally:
            proc.terminate();proc.wait(timeout=10)
    assert serve()==new.name
    assert serve(old.name)==old.name
    subprocess.run(['node',str(old/'app/check-data.mjs'),'--open-investigation',str(saved)],check=True,capture_output=True)
    assert json.loads(saved.read_text())==original
    wrong=subprocess.run(['node',str(new/'app/check-data.mjs'),'--open-investigation',str(saved)],capture_output=True,text=True)
    assert wrong.returncode!=0 and '--generation '+old.name in wrong.stderr
    assert resolve_generation(project)==new


def test_generation_selector_rejects_invalid_missing_and_symlink(project):
    from civicledger.workspace import resolve_generation
    for bad in ('../current','/tmp/outside','A'*32,'.'*32,'a'*31):
        with pytest.raises(ValueError,match='Generation ID'):resolve_generation(project,bad)
    with pytest.raises(FileNotFoundError):resolve_generation(project,'f'*32)
    alias=project/'data/generations'/('e'*32)
    alias.symlink_to((project/'data/current').resolve())
    try:
        with pytest.raises(ValueError,match='not a link'):resolve_generation(project,alias.name)
    finally: alias.unlink()


def test_public_inventory_blocks_unlisted_source_and_live_http_sentinel(project,tmp_path):
    import threading, urllib.error, urllib.request
    from functools import partial
    from http.server import ThreadingHTTPServer
    from civicledger.workspace import PublicHandler, resolve_generation
    old=resolve_generation(project); external=tmp_path/'external'; external.write_text('review-only sentinel')
    source=project/'app/dist/unlisted.txt'; source.symlink_to(external)
    try:
        with pytest.raises(ValueError,match='Symbolic link'):publish(project)
        assert resolve_generation(project)==old
    finally:source.unlink()
    source.write_text('undeclared ordinary file')
    try:
        with pytest.raises(ValueError,match='Public file inventory mismatch'):publish(project)
        assert resolve_generation(project)==old
    finally:source.unlink()
    import json
    expected=json.loads((old/'generation.json').read_text())['artifact_sha256']
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(PublicHandler,generation=old,expected=expected))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    illicit=old/'app/dist/unlisted.txt'
    try:
        illicit.symlink_to(external)
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/unlisted.txt')
        assert error.value.code==404
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/assets/fonts/dm-sans-0.woff2') as response:assert response.status==200
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/cases.json') as response:
            assert response.status==200 and response.read()==(old/'app/dist/cases.json').read_bytes()
        css=old/'app/dist/styles.css'; manifest_file=old/'generation.json'
        original_css=css.read_bytes();original_manifest=manifest_file.read_bytes()
        try:
            css.write_text('changed after startup')
            changed=json.loads(original_manifest);changed['artifact_sha256']['app/dist/styles.css']=hashlib.sha256(css.read_bytes()).hexdigest()
            manifest_file.write_text(json.dumps(changed))
            with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/styles.css')
            assert error.value.code==404
        finally:
            css.write_bytes(original_css);manifest_file.write_bytes(original_manifest)
    finally:
        illicit.unlink();server.shutdown();server.server_close();thread.join(2)


def test_publication_and_reader_reject_external_generation_parent(project,tmp_path):
    from civicledger.workspace import resolve_generation
    root=tmp_path/'workspace'; (root/'data').mkdir(parents=True)
    (root/'data/generations').symlink_to(project/'data/generations',target_is_directory=True)
    with pytest.raises(ValueError,match='symbolic link'):resolve_generation(root,resolve_generation(project).name)
    with pytest.raises(ValueError,match='symbolic link'):publish(root)
    other=tmp_path/'other';other.mkdir();(other/'data').symlink_to(project/'data',target_is_directory=True)
    with pytest.raises(ValueError,match='symbolic link'):resolve_generation(other)
    with pytest.raises(ValueError,match='symbolic link'):publish(other)


@pytest.mark.parametrize('mode',['warehouse','reproduce'])
def test_wrong_cohort_case_never_switches_pointer(project,mode):
    import json
    from civicledger.workspace import resolve_generation
    previous=resolve_generation(project)
    source=project/'data/reports/cases.json'; public=project/'app/dist/cases.json'
    original_source=source.read_bytes();original_public=public.read_bytes()
    cases=json.loads(original_source);cases[0]['record']['award_id']='NOT-IN-STAGED-SOURCE'
    replacement=json.dumps(cases).encode();source.write_bytes(replacement);public.write_bytes(replacement)
    original_run=subprocess.run
    def staged_build(args,**kwargs):
        # Execute the actual staged warehouse calculation; preserve the stale
        # cases so the common post-build validation is exercised in both modes.
        return original_run([sys.executable,'-c','from civicledger.warehouse import _build_in_place; _build_in_place()'],**kwargs)
    try:
        with patch('civicledger.generation.subprocess.run',side_effect=staged_build):
            with pytest.raises(ValueError,match='Case award is absent'):publish(project,mode=mode)
        assert resolve_generation(project)==previous
    finally:
        source.write_bytes(original_source);public.write_bytes(original_public)


def test_case_values_are_checked_against_staged_warehouse(project):
    import json
    from civicledger.workspace import resolve_generation
    old=resolve_generation(project); source=project/'data/reports/cases.json';public=project/'app/dist/cases.json'
    src=source.read_bytes();pub=public.read_bytes();cases=json.loads(src);cases[0]['record']['net']+=1
    changed=json.dumps(cases).encode();source.write_bytes(changed);public.write_bytes(changed)
    try:
        with pytest.raises(ValueError,match='Case award field differs'):publish(project)
        assert resolve_generation(project)==old
    finally:source.write_bytes(src);public.write_bytes(pub)


@pytest.mark.parametrize('method',['GET','HEAD'])
def test_http_returns_only_verified_bytes_despite_file_swap(project,tmp_path,method):
    import http.client, json, threading
    from functools import partial
    from http.server import ThreadingHTTPServer
    from civicledger.workspace import PublicHandler, resolve_generation
    generation=resolve_generation(project);expected=json.loads((generation/'generation.json').read_text())['artifact_sha256']
    path=generation/'app/dist/favicon.svg'; original=path.read_bytes()
    outside=tmp_path/'outside';outside.write_bytes(b'external sentinel')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(PublicHandler,generation=generation,expected=expected))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    ready=threading.Event();swapped=threading.Event(); actual=PublicHandler._verified_bytes
    def hook(handler,name):
        result=actual(handler,name)
        if name=='favicon.svg':ready.set();assert swapped.wait(5)
        return result
    def replace():
        assert ready.wait(5);path.unlink();path.symlink_to(outside);swapped.set()
    racer=threading.Thread(target=replace);racer.start()
    try:
        with patch.object(PublicHandler,'_verified_bytes',hook):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10);conn.request(method,'/favicon.svg');response=conn.getresponse();body=response.read()
            assert response.status==200 and int(response.getheader('Content-Length'))==len(original)
            assert body==(original if method=='GET' else b'')
            conn.close()
        racer.join(5);assert not racer.is_alive()
    finally:
        if path.is_symlink():path.unlink()
        path.write_bytes(original);server.shutdown();server.server_close();thread.join(2)


def test_http_rejects_oversized_replacement_and_preserves_conditional_headers(project):
    import http.client,json,threading
    from functools import partial
    from http.server import ThreadingHTTPServer
    from civicledger.workspace import PublicHandler, resolve_generation
    generation=resolve_generation(project);expected=json.loads((generation/'generation.json').read_text())['artifact_sha256']
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(PublicHandler,generation=generation,expected=expected))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    path=generation/'app/dist/favicon.svg';original=path.read_bytes()
    def request(method,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10);conn.request(method,'/favicon.svg',headers=headers or {});response=conn.getresponse();body=response.read();result=(response.status,dict(response.getheaders()),body);conn.close();return result
    try:
        status,headers,body=request('GET');assert status==200 and body==original and headers['Content-Type']=='image/svg+xml'
        assert request('HEAD')[2]==b''
        assert request('GET',{'If-Modified-Since':headers['Last-Modified']})[0]==304
        with path.open('wb') as f:f.truncate(PublicHandler.MAX_PUBLIC_BYTES+1)
        assert request('GET')[0]==404 and request('HEAD')[0]==404
    finally:
        path.write_bytes(original);server.shutdown();server.server_close();thread.join(2)
