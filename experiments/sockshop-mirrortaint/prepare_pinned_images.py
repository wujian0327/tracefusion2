#!/usr/bin/env python3
"""Prepare digest-locked Docker Hub images through the shell's HTTPS proxy.

No daemon restart/configuration change. Download and hash-check OCI/Docker v2
manifests/blobs, serve them on a temporary loopback registry, populate Docker's
layer cache, then pull canonical references and verify RepoDigests and image IDs.
The local registry is stopped before this command returns.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request

ACCEPT = ', '.join(['application/vnd.docker.distribution.manifest.v2+json',
                    'application/vnd.docker.distribution.manifest.list.v2+json',
                    'application/vnd.oci.image.manifest.v1+json',
                    'application/vnd.oci.image.index.v1+json'])


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024*1024), b''):
            h.update(chunk)
    return 'sha256:'+h.hexdigest()


def prepare(args):
    cache = args.out.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    blobs = cache/'blobs'
    blobs.mkdir(exist_ok=True)
    lock = json.loads(args.manifest.read_text())
    allowed, media, jobs, manifests = set(), {}, {}, {}
    token_cache = {}

    def token(repo):
        if repo not in token_cache or time.monotonic()-token_cache[repo][0]>180:
            query = urllib.parse.urlencode({'service': 'registry.docker.io', 'scope': 'repository:'+repo+':pull'})
            with urllib.request.urlopen('https://auth.docker.io/token?'+query, timeout=30) as response:
                token_cache[repo] = time.monotonic(), json.load(response)['token']
        return token_cache[repo][1]

    def download(repo, kind, expected):
        if not expected.startswith('sha256:') or len(expected)!=71:
            raise ValueError('Only SHA-256 content addresses are supported')
        path = blobs/expected.split(':')[1]
        if path.exists() and digest(path)==expected:
            return path
        last_error = None
        for attempt in range(3):
            try:
                request = urllib.request.Request('https://registry-1.docker.io/v2/'+repo+'/'+kind+'/'+expected,
                                                 headers={'Authorization': 'Bearer '+token(repo), 'Accept': ACCEPT})
                temporary = path.with_suffix('.part')
                with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as file:
                    shutil.copyfileobj(response, file, 1024*1024)
                if digest(temporary)!=expected:
                    raise ValueError('Content digest mismatch: '+expected)
                temporary.replace(path)
                return path
            except Exception as exc:
                last_error = exc
                time.sleep(attempt+1)
        raise RuntimeError('Download failed '+repo+'/'+expected+': '+str(last_error))

    def manifest(repo, expected, image_id):
        path = download(repo, 'manifests', expected)
        record = json.loads(path.read_text())
        media[expected] = record.get('mediaType', 'application/vnd.docker.distribution.manifest.v2+json')
        allowed.add((repo, 'manifests', expected))
        if 'manifests' in record:
            children = [r for r in record['manifests'] if r.get('platform', {}).get('os')=='linux'
                        and r['platform'].get('architecture')=='amd64']
            if len(children)!=1:
                raise ValueError('Expected one linux/amd64 image')
            manifest(repo, children[0]['digest'], image_id)
        else:
            if record['config']['digest']!=image_id:
                raise ValueError('Manifest config differs from pinned image ID')
            for blob in [record['config'], *record['layers']]:
                allowed.add((repo, 'blobs', blob['digest']))
                jobs.setdefault(blob['digest'], (repo, 'blobs', blob['digest']))
        manifests[repo+'@'+expected] = record

    for reference, record in lock.items():
        repo, expected = reference.split('@')
        if '/' not in repo:
            repo = 'library/'+repo
        manifest(repo, expected, record['image_id'])
        print('Manifest verified', reference, flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download, *job): job for job in jobs.values()}
        for future in as_completed(futures):
            path = future.result()
            print('Blob verified', path.name, path.stat().st_size, flush=True)
    (cache/'upstream-manifests.json').write_text(json.dumps(manifests, indent=2)+'\n')

    class Registry(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_HEAD(self):
            self.serve(False)

        def do_GET(self):
            self.serve(True)

        def serve(self, body):
            path = urllib.parse.urlsplit(self.path).path
            if path in ('/v2', '/v2/'):
                self.send_response(200)
                self.send_header('Docker-Distribution-API-Version', 'registry/2.0')
                self.send_header('Content-Length', '2')
                self.end_headers()
                if body:
                    self.wfile.write(b'{}')
                return
            try:
                repo, kind, expected = path[4:].rsplit('/', 2)
                if not path.startswith('/v2/') or (repo, kind, expected) not in allowed:
                    self.send_error(404)
                    return
                file = blobs/expected.split(':')[1]
                self.send_response(200)
                self.send_header('Docker-Distribution-API-Version', 'registry/2.0')
                self.send_header('Docker-Content-Digest', expected)
                self.send_header('Content-Type', media.get(expected, 'application/octet-stream'))
                self.send_header('Content-Length', str(file.stat().st_size))
                self.end_headers()
                if body:
                    with file.open('rb') as source:
                        shutil.copyfileobj(source, self.wfile, 1024*1024)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Registry)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        for reference, expected in lock.items():
            local = f'127.0.0.1:{server.server_port}/'+reference
            if '/' not in reference.split('@')[0]:
                local = f'127.0.0.1:{server.server_port}/library/'+reference
            commands = []
            log = cache/(reference.split('@')[0].replace('/', '_')+'.pull.log')
            with log.open('a') as output:
                for target in (local, reference):
                    command = ['docker', 'pull', '--platform', 'linux/amd64', target]
                    commands.append(command)
                    subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=180)
            info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', reference], timeout=30))[0]
            if info['Id']!=expected['image_id'] or reference not in info.get('RepoDigests', []):
                raise ValueError('Docker image identity/digest mismatch: '+reference)
            results.append({'reference': reference, 'verified': True, 'id': info['Id'],
                            'repo_digests': info['RepoDigests'], 'commands': commands})
            (cache/'results.json').write_text(json.dumps(results, indent=2)+'\n')
            print('Canonical Docker reference verified', reference, flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('artifacts/desktop-inputs/images-lock.json'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    arguments = parser.parse_args()
    prepare(arguments)
