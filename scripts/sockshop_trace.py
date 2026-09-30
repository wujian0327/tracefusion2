#!/usr/bin/env python3
"""Collect instrumented Sock Shop order call graphs, including the shipment queue."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

import sockshop as base
from trace_validation import validate_all
from http_dataset import export_dataset

ROOT = base.ROOT
HOOKS = ROOT / 'instrumentation/sockshop'
AGENT_VERSION = '1.32.0'
AGENT_URL = ('https://github.com/open-telemetry/opentelemetry-java-instrumentation/'
             'releases/download/v%s/opentelemetry-javaagent.jar' % AGENT_VERSION)
PYTHON_IMAGE = 'python:3.12-alpine'


def make_spec(agent, data):
    spec = json.loads(base.COMPOSE.read_text())
    services = spec['services']
    endpoint = 'http://trace-collector:9411/api/v2/spans'
    hook_volume = str(HOOKS.resolve()) + ':/tf2:ro'
    services['trace-collector'] = {
        'image': PYTHON_IMAGE, 'platform': 'linux/amd64',
        'command': ['python', '/tf2/trace_gateway.py'],
        'environment': {'TRACE_MODE': 'collector', 'PORT': '9411', 'TRACE_FILE': '/data/spans.jsonl'},
        'volumes': [hook_volume, str(data.resolve()) + ':/data'],
        'ports': ['127.0.0.1:${TF2_TRACE_PORT:-18082}:9411']}
    for name in ('user', 'payment'):
        backend = copy.deepcopy(services[name])
        services[name + '-backend'] = backend
        services[name] = {
            'image': PYTHON_IMAGE, 'platform': 'linux/amd64',
            'command': ['python', '/tf2/trace_gateway.py'],
            'environment': {'TRACE_SERVICE': name, 'UPSTREAM_HOST': name + '-backend',
                            'TRACE_ENDPOINT': endpoint},
            'volumes': [hook_volume], 'depends_on': [name + '-backend', 'trace-collector']}
    front = services['front-end']
    front['command'] = ['node', '-r', '/tf2/node-tracing.js', 'server.js']
    front['volumes'] = [hook_volume]
    front['environment'] = {'TRACE_SERVICE': 'front-end', 'TRACE_ENDPOINT': endpoint}
    front['depends_on'].append('trace-collector')
    for name in ('orders', 'carts', 'shipping', 'queue-master'):
        cfg = services[name]
        cfg['volumes'] = [str(agent.resolve()) + ':/tf2/opentelemetry-javaagent.jar:ro']
        env = cfg.setdefault('environment', {})
        env['JAVA_OPTS'] = env.get('JAVA_OPTS', '').replace('-Xmx256m', '-Xmx384m') + ' -Dspring.sleuth.enabled=false'
        env.update({'JAVA_TOOL_OPTIONS': '-javaagent:/tf2/opentelemetry-javaagent.jar',
                    'OTEL_SERVICE_NAME': name, 'OTEL_PROPAGATORS': 'tracecontext',
                    'OTEL_TRACES_EXPORTER': 'zipkin', 'OTEL_EXPORTER_ZIPKIN_ENDPOINT': endpoint,
                    'OTEL_METRICS_EXPORTER': 'none', 'OTEL_LOGS_EXPORTER': 'none',
                    'OTEL_TRACES_SAMPLER': 'always_on', 'OTEL_BSP_SCHEDULE_DELAY': '200',
                    'OTEL_BSP_MAX_QUEUE_SIZE': '8192',
                    'OTEL_INSTRUMENTATION_MONGO_ENABLED': 'false'})
        cfg.setdefault('depends_on', []).append('trace-collector')
    return spec


def prepare_agent(out, supplied=None):
    destination = out / 'opentelemetry-javaagent.jar'
    if supplied:
        shutil.copyfile(supplied, destination)
        origin = str(supplied)
    else:
        print('Downloading Java agent ' + AGENT_VERSION, flush=True)
        with urllib.request.urlopen(AGENT_URL, timeout=60) as source, destination.open('wb') as target:
            shutil.copyfileobj(source, target)
        origin = AGENT_URL
    if not zipfile.is_zipfile(destination):
        raise RuntimeError('Java agent is not a valid JAR: ' + str(destination))
    with zipfile.ZipFile(destination) as archive:
        manifest = archive.read('META-INF/MANIFEST.MF').decode()
        if 'Premain-Class:' not in manifest or 'Implementation-Version: ' + AGENT_VERSION not in manifest:
            raise RuntimeError('Expected OpenTelemetry agent version ' + AGENT_VERSION)
    base.save(out / 'agent.json', {'version': AGENT_VERSION, 'source': origin,
              'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'manifest': manifest})
    return destination


class TraceClient(base.Client):
    def __init__(self, out):
        super().__init__(out)
        self.spans, self.roots = [], []

    def request(self, method, url, body=None, label='request', redact=False):
        trace, ident = secrets.token_hex(16), secrets.token_hex(8)
        self.headers = {'traceparent': '00-%s-%s-01' % (trace, ident)}
        start, clock = time.time_ns() // 1000, time.monotonic_ns()
        span = {'traceId': trace, 'id': ident, 'name': label, 'kind': 'CLIENT',
                'timestamp': start, 'localEndpoint': {'serviceName': 'test-client'},
                'tags': {'http.method': method, 'http.url': url}}
        try:
            result = super().request(method, url, body, label, redact)
            span['tags']['http.status_code'] = str(self.events[-1]['status'])
            return result
        except Exception as exc:
            span['tags']['error'] = type(exc).__name__
            raise
        finally:
            span['duration'] = max(1, (time.monotonic_ns() - clock) // 1000)
            self.spans.append(span)
            self.roots.append({'label': label, 'trace_id': trace, 'span_id': ident})
            base.save(self.out / 'oracle-client-spans.json', self.spans)
            base.save(self.out / 'oracle-requests.json', self.roots)
            self.headers = {}


def run_fixture(out, number, front, carts):
    directory = out / 'requests' / ('request-%03d' % number)
    directory.mkdir(parents=True)
    client = TraceClient(directory)
    result = base.smoke(directory, front, carts, client=client)
    base.save(directory / 'result.json', result)
    fixture = json.loads((directory / 'fixture.json').read_text())
    request = next(r.copy() for r in client.roots if r['label'] == 'create-order')
    request.update({k: fixture[k] for k in ('customer_id', 'address_id', 'card_id')})
    request.update(order_id=result['order_id'], directory=str(directory.relative_to(out)))
    return request, client.spans


def read_collector(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:' + port + '/spans', timeout=5) as response:
        return json.load(response)


def collect(out, requests, client_spans, port, timeout, scope='full'):
    deadline, previous, stable_since = time.monotonic() + timeout, None, None
    report = validate_all([], requests, scope=scope)
    while time.monotonic() < deadline:
        spans = read_collector(port) + client_spans
        report = validate_all(spans, requests, scope=scope)
        base.save(out / 'oracle' / 'spans.json', spans)
        base.save(out / 'oracle' / 'callgraphs.json', report)
        # Allow late agent batches to arrive before accepting the snapshot.
        signature = json.dumps([r['spans'] for r in report['orders']], sort_keys=True)
        if report['status'] == 'passed' and signature == previous:
            if stable_since is not None and time.monotonic() - stable_since >= 2:
                return report
        else:
            stable_since = time.monotonic()
        previous = signature
        time.sleep(0.5)
    return report


def package(out):
    bundle = out.with_suffix('.zip')
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.suffix != '.jar':
                archive.write(path, str(path.relative_to(out)))
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'check', 'down'])
    parser.add_argument('--project', default='tracefusion2-sockshop')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--agent-jar', type=Path, help='pre-downloaded official 1.32.0 agent')
    parser.add_argument('--requests', type=int, default=2)
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--ready-timeout', type=int, default=300)
    parser.add_argument('--trace-timeout', type=int, default=30)
    parser.add_argument('--scope', choices=['synchronous-http', 'full'], default='synchronous-http')
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]*', args.project):
        parser.error('invalid project name')
    if min(args.requests, args.concurrency, args.ready_timeout, args.trace_timeout) < 1:
        parser.error('request counts, concurrency and timeouts must be positive')
    if args.action == 'down':
        if not shutil.which('docker'):
            print('Docker is not installed.', file=sys.stderr); return 1
        return subprocess.call(['docker', 'compose', '-p', args.project, '-f', str(base.COMPOSE),
                                'down', '--remove-orphans'])
    if args.action == 'check':
        spec = make_spec(ROOT / 'unused-agent.jar', ROOT / 'artifacts/unused-data')
        assert len(spec['services']) == 14
        assert spec['services']['user-backend']['environment']['HATEAOS'] == 'user'
        for name in ('orders', 'carts', 'shipping', 'queue-master'):
            assert spec['services'][name]['environment']['OTEL_TRACES_SAMPLER'] == 'always_on'
        print('PASS: trace configuration (14 containers). No live deployment has been performed.')
        return 0
    out = (args.out or ROOT / 'artifacts' / ('sockshop-trace-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S')
                                            + '-' + secrets.token_hex(2))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'oracle' / 'raw').mkdir(parents=True)
    deployment = None
    requests, client_spans = [], []
    result = {'status': 'failed', 'stage': 'deployment', 'project': args.project,
              'evaluation_scope': args.scope,
              'field_lineage_oracle': False, 'requested_orders': args.requests,
              'concurrency': args.concurrency}
    try:
        if not shutil.which('docker'):
            raise RuntimeError('Docker is not installed; use a host with Docker Engine and Compose v2.')
        base.save(out / 'instrumentation.json', {
            'agent_version': AGENT_VERSION,
            'code_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [HOOKS / 'node-tracing.js', HOOKS / 'trace_gateway.py',
                                     Path(__file__), ROOT / 'scripts/trace_validation.py',
                                     ROOT / 'scripts/http_dataset.py',
                                     ROOT / 'scripts/sockshop.py']}})
        shutil.copyfile(ROOT / 'scenarios/sockshop/sources.json', out / 'sources.json')
        agent = prepare_agent(out, args.agent_jar)
        spec = make_spec(agent, out / 'oracle' / 'raw')
        filename = out / 'compose.trace.json'
        base.save(filename, spec)
        deployment = base.Deployment(args, out, compose_file=filename)
        deployment.start()
        result['stage'] = 'order-smoke'
        front = 'http://127.0.0.1:' + os.environ.get('TF2_FRONT_PORT', '18080')
        carts = 'http://127.0.0.1:' + os.environ.get('TF2_CART_PORT', '18081')
        failures = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(run_fixture, out, n, front, carts) for n in range(args.requests)]
            for future in as_completed(futures):
                try:
                    request, spans = future.result()
                    requests.append(request); client_spans.extend(spans)
                except Exception as exc:
                    failures.append(str(exc))
        base.save(out / 'oracle' / 'orders.json', requests)
        result['completed_orders'] = len(requests)
        result['stage'] = 'trace-validation'
        report = collect(out, requests, client_spans, os.environ.get('TF2_TRACE_PORT', '18082'),
                         args.trace_timeout, scope=args.scope)
        result['trace_validation'] = report['status']
        result['execution_status'] = report['execution_status']
        result['overlapping_order_interval_pairs'] = report['overlapping_order_interval_pairs']
        result['order_errors'] = failures
        if failures or len(requests) != args.requests:
            raise RuntimeError('Some order fixtures failed; inspect requests/ and compose.log')
        if report['status'] != 'passed':
            raise RuntimeError('Trace collection is incomplete; inspect oracle/callgraphs.json. No missing edges were inferred.')
        if report['execution_status'] == 'failed':
            result['stage'] = 'application-runtime'
            raise RuntimeError('Trace structure passed, but recorded application operations failed; '
                               'inspect runtime_errors in oracle/callgraphs.json and compose.log.')
        result.update(status='passed', stage='complete')
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        if deployment:
            deployment.diagnostics()
            try:
                final_spans = read_collector(os.environ.get('TF2_TRACE_PORT', '18082')) + client_spans
                base.save(out / 'oracle' / 'spans-final.json', final_spans)
                final_report = validate_all(final_spans, requests, scope=args.scope)
                base.save(out / 'oracle' / 'callgraphs.json', final_report)
                full_report = validate_all(final_spans, requests, scope='full')
                base.save(out / 'oracle' / 'full-callgraphs.json', full_report)
                result['full_trace_execution_status'] = full_report['execution_status']
                result['trace_validation'] = final_report['status']
                result['execution_status'] = final_report['execution_status']
                if result['status'] == 'passed' and final_report['status'] != 'passed':
                    result.update(status='failed', stage='trace-validation',
                                  error='Late spans failed final trace validation')
                elif result['status'] == 'passed' and final_report['execution_status'] == 'failed':
                    result.update(status='failed', stage='application-runtime',
                                  error='Late spans contain application errors; trace structure passed')
                if requests and len(requests) == args.requests:
                    try:
                        result['http_dataset'] = export_dataset(out, out / 'http-evaluation')
                    except Exception as exc:
                        result['http_dataset_error'] = str(exc)
                        if result['status'] == 'passed':
                            result.update(status='failed', stage='http-dataset')
            except Exception as exc:
                result['final_collection_error'] = str(exc)
                if result['status'] == 'passed':
                    result.update(status='failed', stage='trace-validation')
        base.save(out / 'result.json', result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('RESULT BUNDLE: ' + str(package(out)))
        print('Stop: python3 scripts/sockshop_trace.py down --project ' + args.project)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
