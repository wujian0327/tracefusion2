#!/usr/bin/env python3
import hashlib
import http.client
import ssl
import urllib.parse
import queue
import json
import os
from pathlib import Path
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import argparse
import sys
parser = argparse.ArgumentParser(description='Build unmodified, pinned Java services using a logged Maven Central loopback mirror')
parser.add_argument('--sources-dir', type=Path, required=True)
parser.add_argument('--jdk', type=Path, required=True)
parser.add_argument('--maven', type=Path, required=True, help='Path to mvn executable')
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.sources_dir = args.sources_dir.resolve()
args.jdk = args.jdk.resolve()
args.maven = args.maven.resolve()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
(out / 'tmp').mkdir()
subprocess.run([sys.executable, str(Path(__file__).with_name('source_audit.py')), '--sources-dir', str(args.sources_dir), '--out', str(out/'source-audit.json')], check=True)
cache = out / 'central-downloads'
cache.mkdir(exist_ok=True)
lock = threading.Lock()
connections = queue.LifoQueue()
proxy_url = urllib.request.getproxies().get('https')
proxy = urllib.parse.urlsplit(proxy_url) if proxy_url else None
def download(path):
    try:
        connection = connections.get_nowait()
    except queue.Empty:
        connection = http.client.HTTPSConnection(proxy.hostname if proxy else 'repo.maven.apache.org', proxy.port if proxy else 443, timeout=60, context=ssl.create_default_context())
        if proxy:
            connection.set_tunnel('repo.maven.apache.org', 443)
    try:
        connection.request('GET', '/maven2' + path)
        response = connection.getresponse()
        payload = response.read()
        status = response.status
        connections.put(connection)
        if status != 200:
            raise urllib.error.HTTPError(path, status, 'Upstream response', {}, None)
        return payload
    except urllib.error.HTTPError:
        raise
    except Exception:
        connection.close()
        raise
class Mirror(BaseHTTPRequestHandler):
    def do_GET(self):
        if '..' in self.path or '?' in self.path or not self.path.startswith('/'):
            self.send_error(400); return
        target = cache / self.path.lstrip('/')
        try:
            if not target.exists():
                payload = download(self.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            payload = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            with lock, (out / 'central-downloads.jsonl').open('a') as stream:
                stream.write(json.dumps({'path': self.path, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}) + '\n')
        except urllib.error.HTTPError as exc:
            self.send_error(exc.code)
        except Exception as exc:
            self.send_error(502, type(exc).__name__)
    def log_message(self, *args):
        pass
server = ThreadingHTTPServer(('127.0.0.1', 0), Mirror)
threading.Thread(target=server.serve_forever, daemon=True).start()
settings = out / 'maven-local-settings.xml'
settings.write_text('<settings><mirrors><mirror><id>central-loopback</id><mirrorOf>*</mirrorOf><url>http://127.0.0.1:%d</url></mirror></mirrors></settings>' % server.server_port)
jdk = args.jdk
libs = [str(p.parent) for name in ['libjli.so','libjvm.so','libjava.so'] for p in jdk.rglob(name)]
env = dict(os.environ, JAVA_HOME=str(jdk), LD_LIBRARY_PATH=':'.join(libs), MAVEN_OPTS='-Xmx512m -Djava.io.tmpdir=' + str(out / 'tmp'))
cmd = [str(args.maven), '-B', '-U', '-s', str(settings), '-Dmaven.repo.local=' + str(out/'maven-cache'), '-Dmaven.test.skip=true', 'package']
try:
    for app in ['orders', 'carts', 'shipping']:
        print('Building original ' + app, flush=True)
        timed_out = False
        with (out / (app + '-build-local.log')).open('w') as stream:
            try:
                run = subprocess.run(cmd, cwd=args.sources_dir/('sockshop-'+app), env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
                code = run.returncode
            except subprocess.TimeoutExpired:
                code = 124
                timed_out = True
        result = {'command':cmd, 'returncode':code, 'timeout':timed_out, 'jdk':str(jdk), 'mirror_upstream':'https://repo.maven.apache.org/maven2', 'source_changed':False, 'tests_run':False}
        (out / (app + '-build-local-command.json')).write_text(json.dumps(result, indent=2))
        print(app + ' returncode=' + str(code), flush=True)
        if code:
            print((out / (app + '-build-local.log')).read_text()[-5000:], flush=True)
            raise RuntimeError(app + ' original build failed; see persisted log')
finally:
    server.shutdown()
    while not connections.empty():
        connections.get_nowait().close()
