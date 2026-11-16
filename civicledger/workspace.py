"""Serve one verified immutable generation for a local investigation session."""
import argparse
import datetime
import email.utils
import hashlib
import io
import os
import stat
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .generation import ARTIFACTS, PUBLIC_FILES, MAX_PUBLIC_BYTES as PUBLIC_BYTE_LIMIT, digest, real_child, no_links, public_inventory
from .warehouse import ROOT


def resolve_generation(root=ROOT, generation_id=None, *, _with_manifest=False):
    root=Path(root).resolve()
    data=real_child(root,'data')
    generations=real_child(data,'generations')
    if generation_id is None:
        pointer=root/'data/current'
        if not pointer.is_symlink():
            raise ValueError('No current generation. Build one with python -m civicledger.warehouse.')
        current=pointer.resolve(strict=True)
    else:
        if not re.fullmatch(r'[0-9a-f]{32}', generation_id):
            raise ValueError('Generation ID must be 32 lowercase hexadecimal characters.')
        candidate=generations/generation_id
        if candidate.is_symlink():
            raise ValueError('Retained generation must be a real directory, not a link.')
        current=candidate.resolve(strict=True)
    if current.parent != generations or not current.is_dir() or not re.fullmatch(r'[0-9a-f]{32}',current.name):
        raise ValueError('Generation must be a retained directory under data/generations.')
    no_links(current)
    public_inventory(current/'app/dist')
    manifest=json.loads((current/'generation.json').read_text())
    if manifest.get('generation_id') != current.name:
        raise ValueError('Generation identity mismatch')
    if not isinstance(manifest.get('artifact_sha256'),dict) or set(manifest['artifact_sha256']) != set(ARTIFACTS):
        raise ValueError('Generation artifact manifest is incomplete')
    for name,expected in manifest['artifact_sha256'].items():
        path=(current/name).resolve(strict=True)
        if not path.is_relative_to(current) or not path.is_file() or digest(path)!=expected:
            raise ValueError('Generation artifact mismatch: '+name)
    case=manifest.get('case_evidence')
    if not isinstance(case,dict) or case.get('snapshot_id') != manifest.get('snapshot_id') or case.get('public_csv_sha256') != manifest.get('public_csv_sha256') or case.get('sha256') != manifest['artifact_sha256']['data/reports/cases.json']:
        raise ValueError('Case source identity mismatch')
    if digest(current/'app/dist/app.js') != manifest['query_sha256']:
        raise ValueError('Investigation query definition mismatch')
    projection=json.loads((current/'app/dist/data.json').read_text())['meta']
    if any(projection.get(k)!=manifest[k] for k in ('generation_id','snapshot_id','public_csv_sha256','query_sha256')):
        raise ValueError('Projection identity mismatch')
    return (current,manifest) if _with_manifest else current


class PublicHandler(SimpleHTTPRequestHandler):
    """Only declared, hash-verified files are exposed; directory listings are disabled."""
    def __init__(self,*args,generation,expected,**kwargs):
        self.generation=generation
        self.expected=expected
        super().__init__(*args,directory=str(generation/'app/dist'),**kwargs)

    # A fixed bound prevents an untrusted replacement from causing an unbounded
    # allocation. The largest current public artifact is the ~9 MiB data JSON.
    MAX_PUBLIC_BYTES = PUBLIC_BYTE_LIMIT

    def _verified_bytes(self, name):
        """Read once from no-follow directory/file descriptors, then hash those bytes."""
        fd=None
        try:
            fd=os.open(self.generation,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            parts=('app','dist',*name.split('/'))
            for part in parts[:-1]:
                next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=next_fd
            file_fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            try:
                info=os.fstat(file_fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size>self.MAX_PUBLIC_BYTES:
                    return None
                with os.fdopen(file_fd,'rb') as file:
                    file_fd=None
                    content=file.read(self.MAX_PUBLIC_BYTES+1)
                if len(content)>self.MAX_PUBLIC_BYTES or hashlib.sha256(content).hexdigest()!=self.expected['app/dist/'+name]:
                    return None
                return content,info.st_mtime
            finally:
                if file_fd is not None:os.close(file_fd)
        except (OSError,KeyError,ValueError):
            return None
        finally:
            if fd is not None:os.close(fd)

    def send_head(self):
        raw=unquote(urlsplit(self.path).path)
        name='index.html' if raw=='/' else raw.removeprefix('/')
        if not raw.startswith('/') or name not in PUBLIC_FILES:
            self.send_error(404);return None
        verified=self._verified_bytes(name)
        if verified is None:
            self.send_error(404);return None
        content,mtime=verified
        if 'If-Modified-Since' in self.headers and 'If-None-Match' not in self.headers:
            try:
                since=email.utils.parsedate_to_datetime(self.headers['If-Modified-Since'])
                if since.tzinfo is None:since=since.replace(tzinfo=datetime.timezone.utc)
                modified=datetime.datetime.fromtimestamp(mtime,datetime.timezone.utc).replace(microsecond=0)
                if since.tzinfo is datetime.timezone.utc and modified<=since:
                    self.send_response(304);self.end_headers();return None
            except (TypeError,IndexError,OverflowError,ValueError):
                pass
        self.send_response(200)
        self.send_header('Content-Type',self.guess_type(name))
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Last-Modified',self.date_time_string(mtime))
        self.end_headers()
        return io.BytesIO(content)

def main():
    parser=argparse.ArgumentParser(prog="python -m civicledger.workspace", description=__doc__)
    parser.add_argument('--port',type=int,default=8000,help='loopback port (default: 8000; 0 chooses a free port)')
    parser.add_argument('--generation', help='Explicit retained 32-character generation ID')
    args=parser.parse_args()
    if not 0 <= args.port <= 65535: parser.error('Port must be between 0 and 65535')
    try:
        generation,manifest=resolve_generation(generation_id=args.generation,_with_manifest=True)
    except FileNotFoundError:
        parser.error('Generation is missing. Check its ID or build a generation with python -m civicledger.warehouse.')
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(PublicHandler,generation=generation,expected=manifest['artifact_sha256']))
    print(f'Serving generation {generation.name} at http://127.0.0.1:{server.server_port}/',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__':main()
