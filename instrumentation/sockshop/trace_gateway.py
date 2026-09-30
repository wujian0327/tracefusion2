"""Experiment-only Zipkin v2 receiver / leaf-service HTTP boundary observer.

No inferred spans, request bodies, or field lineage. A proxy SERVER span measures
its complete forwarding operation, not the Go process's internal execution.
"""
import gzip
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.request

LOCK = threading.Lock()
HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
       'te', 'trailer', 'transfer-encoding', 'upgrade', 'content-length'}


def context(header):
    m = re.fullmatch(r'00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})', header or '')
    if m and int(m[1], 16) and int(m[2], 16):
        return m[1], m[2]
    return secrets.token_hex(16), None


def export(span):
    request = urllib.request.Request(os.environ['TRACE_ENDPOINT'],
        json.dumps([span]).encode(), {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except Exception as exc:
        print('TF2_EXPORT_ERROR ' + str(exc), flush=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def respond(self, code, body, content_type='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
            data = bytearray()
            while True:
                size = int(self.rfile.readline().split(b';', 1)[0], 16)
                if size == 0:
                    while self.rfile.readline() not in (b'\r\n', b'\n', b''):
                        pass
                    return bytes(data)
                data.extend(self.rfile.read(size))
                if self.rfile.read(2) != b'\r\n':
                    raise ValueError('Invalid chunk framing')
        return self.rfile.read(int(self.headers.get('Content-Length', '0')))

    def handle_collector(self):
        path = Path(os.environ.get('TRACE_FILE', '/data/spans.jsonl'))
        if self.command == 'GET' and self.path == '/health':
            self.respond(200, b'{"status":"ready"}')
        elif self.command == 'GET' and self.path == '/spans':
            with LOCK:
                rows = [json.loads(x) for x in path.read_text().splitlines() if x] if path.exists() else []
            self.respond(200, json.dumps(rows).encode())
        elif self.command == 'POST' and self.path == '/api/v2/spans':
            body = self.read_body()
            if self.headers.get('Content-Encoding') == 'gzip':
                body = gzip.decompress(body)
            try:
                spans = json.loads(body)
                if not isinstance(spans, list) or any(not isinstance(s, dict) or
                        not all(k in s for k in ('traceId', 'id', 'name')) for s in spans):
                    raise ValueError('Expected Zipkin v2 spans')
            except (ValueError, TypeError):
                self.respond(400, b'{"error":"invalid spans"}')
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            with LOCK, path.open('a') as out:
                for span in spans:
                    out.write(json.dumps(span, separators=(',', ':')) + '\n')
                out.flush()
            self.respond(202, b'{}')
        else:
            self.respond(404, b'{}')

    def handle_proxy(self):
        trace, parent = context(self.headers.get('traceparent'))
        ident = secrets.token_hex(8)
        start, clock = time.time_ns() // 1000, time.monotonic_ns()
        service = os.environ['TRACE_SERVICE']
        span = {'traceId': trace, 'id': ident, 'name': self.command + ' ' + self.path.split('?')[0],
                'kind': 'SERVER', 'timestamp': start, 'localEndpoint': {'serviceName': service},
                'tags': {'http.method': self.command, 'http.target': self.path,
                         'tf2.observer': 'leaf-http-proxy'}}
        if parent:
            span['parentId'] = parent
        connection = None
        try:
            connection = http.client.HTTPConnection(os.environ['UPSTREAM_HOST'],
                                                    int(os.environ.get('UPSTREAM_PORT', '80')), timeout=30)
            connection_tokens = {x.strip().lower() for x in self.headers.get('Connection', '').split(',')}
            excluded = HOP | connection_tokens | {'traceparent', 'tracestate'}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in excluded}
            headers['traceparent'] = '00-%s-%s-01' % (trace, ident)
            connection.request(self.command, self.path, self.read_body(), headers)
            response = connection.getresponse()
            body = response.read()
            span['tags']['http.status_code'] = str(response.status)
            self.send_response(response.status)
            response_tokens = {x.strip().lower() for x in (response.getheader('Connection') or '').split(',')}
            for key, value in response.getheaders():
                if key.lower() not in HOP | response_tokens:
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            span['tags']['error'] = type(exc).__name__
            try:
                self.respond(502, b'{"error":"trace proxy upstream failure"}')
            except OSError:
                pass
        finally:
            if connection:
                connection.close()
            span['duration'] = max(1, (time.monotonic_ns() - clock) // 1000)
            export(span)

    def dispatch(self):
        if os.environ.get('TRACE_MODE') == 'collector':
            self.handle_collector()
        else:
            self.handle_proxy()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = dispatch


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '80'))), Handler).serve_forever()
