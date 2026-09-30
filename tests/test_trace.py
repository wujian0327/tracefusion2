import copy
import gzip
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from trace_validation import validate_all, validate_trace
from sockshop_trace import make_spec


def graph():
    trace = 'a' * 32
    request = {'trace_id': trace, 'span_id': '%016x' % 1,
               'customer_id': 'customer-A', 'address_id': 'address-A', 'card_id': 'card-A'}
    spans = []
    def add(name, parent, kind='SERVER', path=''):
        ident = '%016x' % (len(spans) + 1)
        span = {'traceId': trace, 'id': ident, 'name': 'test', 'kind': kind,
                'localEndpoint': {'serviceName': name}, 'timestamp': 100, 'duration': 10,
                'tags': {'http.target': path}}
        if parent: span['parentId'] = parent
        spans.append(span)
        return ident
    root = add('test-client', None, 'CLIENT')
    front = add('front-end', root, path='/orders')
    add('user', front, path='/customers/customer-A')
    orders = add('orders', front, path='/orders')
    for path in ['/customers/customer-A', '/addresses/address-A', '/cards/card-A']:
        add('user', orders, path=path)
    add('carts', orders, path='/carts/customer-A/items')
    add('payment', orders)
    ship = add('shipping', orders)
    producer = add('shipping', ship, 'PRODUCER')
    add('queue-master', producer, 'CONSUMER')
    return spans, request


class GraphTests(unittest.TestCase):
    def test_connected_graph_and_duplicate_delivery(self):
        spans, request = graph()
        self.assertEqual(validate_trace(spans + [copy.deepcopy(spans[0])], request)['status'], 'passed')

    def test_missing_parent_cannot_be_filled_from_topology(self):
        spans, request = graph()
        spans[4]['parentId'] = 'f' * 16
        report = validate_trace(spans, request)
        self.assertEqual(report['status'], 'incomplete')
        self.assertTrue(any('missing parent' in x for x in report['errors']))

    def test_wrong_trace_and_wrong_fixture_fail(self):
        spans, request = graph()
        spans[-1]['traceId'] = 'b' * 32
        self.assertEqual(validate_trace(spans, request)['status'], 'incomplete')
        spans, request = graph()
        spans[4]['tags']['http.target'] = '/customers/customer-B'
        report = validate_trace(spans, request, ['customer-B'])
        self.assertTrue(any('other fixture' in x for x in report['errors']))

    def test_cycle_and_conflicting_ids_fail(self):
        spans, request = graph()
        spans[1]['parentId'] = spans[3]['id']
        self.assertTrue(any('cycle' in x for x in validate_trace(spans, request)['errors']))
        spans, request = graph()
        other = copy.deepcopy(spans[-1]); other['name'] = 'different'
        self.assertEqual(validate_trace(spans + [other], request)['status'], 'incomplete')

    def test_queue_requires_producer_ancestor(self):
        spans, request = graph()
        spans[-1]['parentId'] = spans[9]['id']
        self.assertEqual(validate_trace(spans, request)['status'], 'incomplete')

    def test_runtime_failure_does_not_imply_a_missing_trace_edge(self):
        spans, request = graph()
        spans[5]['tags']['http.status_code'] = '500'
        report = validate_trace(spans, request)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['execution_status'], 'failed')
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['runtime_errors'][0]['span_id'], spans[5]['id'])

    def test_zipkin_empty_error_tag_is_preserved_as_runtime_failure(self):
        spans, request = graph()
        spans[-1]['tags']['error'] = ''
        report = validate_all(spans, [request])
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['execution_status'], 'failed')
        self.assertEqual(report['orders'][0]['runtime_errors'][0]['span_id'], spans[-1]['id'])

    def test_no_orders_cannot_pass(self):
        self.assertEqual(validate_all([], [])['status'], 'incomplete')

    def test_overlay_preserves_backend_and_adds_three_observers(self):
        spec = make_spec(Path('/tmp/agent.jar'), Path('/tmp/data'))
        self.assertEqual(len(spec['services']), 14)
        self.assertEqual(spec['services']['user-backend']['environment']['HATEAOS'], 'user')
        self.assertEqual(spec['services']['user']['environment']['UPSTREAM_HOST'], 'user-backend')


class HttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.processes, self.servers, self.spans, self.received = [], [], [], []
        self.lock = threading.Lock()
        case = self
        class Collector(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                with case.lock: case.spans.extend(json.loads(body))
                self.send_response(202); self.end_headers()
            def log_message(self, *args): pass
        class Upstream(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def do_GET(self):
                with case.lock: case.received.append((self.path, self.headers.get('traceparent')))
                body = json.dumps({'path': self.path}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Set-Cookie', 'one=1'); self.send_header('Set-Cookie', 'two=2')
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        self.collector = self.server(Collector)
        self.upstream = self.server(Upstream)
        self.endpoint = 'http://127.0.0.1:%d/api/v2/spans' % self.collector.server_port

    def server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def spawn(self, args, env):
        log = open(Path(self.tmp.name) / ('child-%d.log' % len(self.processes)), 'w+')
        child = subprocess.Popen(args, env=dict(os.environ, **env), stdout=log, stderr=log)
        self.processes.append((child, log))
        return child

    def wait_port(self, filename, child):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if Path(filename).exists(): return int(Path(filename).read_text())
            if child.poll() is not None: break
            time.sleep(.02)
        for p, log in self.processes:
            if p is child:
                log.seek(0); self.fail('service failed: ' + log.read())
        self.fail('service did not start')

    def wait_spans(self, count):
        deadline = time.monotonic() + 5
        while len(self.spans) < count and time.monotonic() < deadline: time.sleep(.02)
        self.assertGreaterEqual(len(self.spans), count)

    def tearDown(self):
        for child, log in self.processes:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
            log.close()
        for server in self.servers: server.shutdown(); server.server_close()
        self.tmp.cleanup()

    @unittest.skipUnless(shutil.which('node'), 'Node required for callback propagation test')
    def test_node_parallel_and_nested_callbacks_keep_request_context(self):
        port_file = Path(self.tmp.name) / 'node-port'
        app = Path(self.tmp.name) / 'app.js'
        app.write_text("""
var http=require('http'),fs=require('fs');
var s=http.createServer(function(req,res){
 var left=2;
 function done(){if(--left===0){res.end('ok');}}
 function call(suffix,cb){http.get('http://127.0.0.1:'+process.env.UPSTREAM_PORT+req.url+suffix,function(r){
  r.resume();r.on('end',cb);});}
 setTimeout(function(){call('/a',function(){call('/nested',done);});},30);
 setTimeout(function(){call('/b',done);},5);
});s.listen(0,'127.0.0.1',function(){fs.writeFileSync(process.env.PORT_FILE,String(s.address().port));});
""")
        child = self.spawn(['node', '-r', str(ROOT / 'instrumentation/sockshop/node-tracing.js'), str(app)],
                           {'TRACE_ENDPOINT': self.endpoint, 'PORT_FILE': str(port_file),
                            'UPSTREAM_PORT': str(self.upstream.server_port)})
        port = self.wait_port(port_file, child)
        def send(n):
            req = urllib.request.Request('http://127.0.0.1:%d/%d' % (port, n),
                headers={'traceparent': '00-%032x-%016x-01' % (n, n + 100)})
            with urllib.request.urlopen(req) as r: self.assertEqual(r.read(), b'ok')
        with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(send, range(1, 9)))
        self.wait_spans(32)
        for n in range(1, 9):
            spans = [s for s in self.spans if s['traceId'] == '%032x' % n]
            servers = [s for s in spans if s['kind'] == 'SERVER']
            clients = [s for s in spans if s['kind'] == 'CLIENT']
            self.assertEqual(len(servers), 1); self.assertEqual(len(clients), 3)
            self.assertEqual(servers[0]['parentId'], '%016x' % (n + 100))
            self.assertTrue(all(s['parentId'] == servers[0]['id'] for s in clients))
        for path, header in self.received:
            self.assertEqual(header.split('-')[1], '%032x' % int(path.split('/')[1]))

    def test_leaf_proxy_preserves_body_cookies_and_parent(self):
        port_file = Path(self.tmp.name) / 'proxy-port'
        launcher = Path(self.tmp.name) / 'launch.py'
        launcher.write_text("""
import sys,os
sys.path.insert(0,os.environ['HOOK_DIR'])
from trace_gateway import Handler,ThreadingHTTPServer
s=ThreadingHTTPServer(('127.0.0.1',0),Handler)
open(os.environ['PORT_FILE'],'w').write(str(s.server_port))
s.serve_forever()
""")
        child = self.spawn([sys.executable, str(launcher)], {
            'HOOK_DIR': str(ROOT / 'instrumentation/sockshop'), 'PORT_FILE': str(port_file),
            'TRACE_SERVICE': 'user', 'TRACE_ENDPOINT': self.endpoint,
            'UPSTREAM_HOST': '127.0.0.1', 'UPSTREAM_PORT': str(self.upstream.server_port)})
        port = self.wait_port(port_file, child)
        trace, parent = 'a' * 32, 'b' * 16
        request = urllib.request.Request('http://127.0.0.1:%d/cards/C1' % port,
                     headers={'traceparent': '00-%s-%s-01' % (trace, parent)})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(json.load(response), {'path': '/cards/C1'})
            self.assertEqual(response.headers.get_all('Set-Cookie'), ['one=1', 'two=2'])
        self.wait_spans(1)
        span = self.spans[0]
        self.assertEqual((span['traceId'], span['parentId']), (trace, parent))
        self.assertEqual(self.received[0][1], '00-%s-%s-01' % (trace, span['id']))

    def test_real_collector_accepts_gzip_batches_and_exports_persisted_spans(self):
        port_file = Path(self.tmp.name) / 'collector-port'
        launcher = Path(self.tmp.name) / 'collector.py'
        launcher.write_text("""
import sys,os
sys.path.insert(0,os.environ['HOOK_DIR'])
from trace_gateway import Handler,ThreadingHTTPServer
s=ThreadingHTTPServer(('127.0.0.1',0),Handler)
open(os.environ['PORT_FILE'],'w').write(str(s.server_port))
s.serve_forever()
""")
        data_file = Path(self.tmp.name) / 'raw.jsonl'
        child = self.spawn([sys.executable, str(launcher)], {
            'HOOK_DIR': str(ROOT / 'instrumentation/sockshop'), 'PORT_FILE': str(port_file),
            'TRACE_MODE': 'collector', 'TRACE_FILE': str(data_file)})
        port = self.wait_port(port_file, child)
        spans, _ = graph()
        req = urllib.request.Request('http://127.0.0.1:%d/api/v2/spans' % port,
            gzip.compress(json.dumps(spans).encode()),
            {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
        with urllib.request.urlopen(req) as response: self.assertEqual(response.status, 202)
        with urllib.request.urlopen('http://127.0.0.1:%d/spans' % port) as response:
            self.assertEqual(json.load(response), spans)
        self.assertEqual([json.loads(x) for x in data_file.read_text().splitlines()], spans)


if __name__ == '__main__': unittest.main()
