#!/usr/bin/env python3
"""Real Sock Shop API/agent preflight, not a field-provenance inference engine."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import threading
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sockshop import Client, Deployment, check_spec, require_id, save


def final_items(case):
    items = copy.deepcopy(case['items'])
    for item in items:
        if case.get('patch', {}).get('key') == item['key']:
            item['quantity'] = case['patch']['quantity']
        if case.get('repost', {}).get('key') == item['key']:
            item['quantity'] += 1
    return items


def compose_spec(mode, out, agent=None):
    spec = json.loads((ROOT / 'scenarios/sockshop/compose.json').read_text())
    check_spec(spec)
    spec['services']['orders']['ports'] = ['127.0.0.1:${TF2_ORDERS_PORT:-18082}:80']
    if mode == 'mirrortaint':
        pinned = json.loads((HERE / 'sources.json').read_text())['mirrortaint']['agent_sha256']
        if agent is None or hashlib.sha256(agent.read_bytes()).hexdigest() != pinned:
            raise ValueError('Provide the exact pinned MirrorTaint JAR with --agent')
        copied = out / 'mirrorTaint.jar'
        shutil.copyfile(agent, copied)
        for name in ('carts', 'orders', 'shipping'):
            cfg = spec['services'][name]
            home = out / 'agent-logs' / name
            home.mkdir(parents=True)
            # Only these newly created result directories become container-writable.
            home.chmod(0o777)
            cfg.setdefault('volumes', []).extend([
                str(copied) + ':/tf2/mirrorTaint.jar:ro',
                str(home) + ':/tf2/agent-home:rw'])
            cfg['environment']['JAVA_OPTS'] += (
                ' -javaagent:/tf2/mirrorTaint.jar -Dtaint.env=remote'
                ' -Dtaint.app=works.weave.socks -Duser.home=/tf2/agent-home'
                ' -Dtaint.version=tf2-preflight')
    return spec


def prepare(case, case_id, out, front, cart, shared=False):
    out.mkdir()
    client = Client(out)
    token = secrets.token_hex(6)
    name = 'TF2_shared' if shared else 'TF2_' + token
    street = name if case.get('equal_name_street') else ('SharedStreet' if shared else name + '_Street')
    fixture = {'firstName': name,
               'address': {'number': '17', 'street': street, 'city': 'TestCity',
                           'postcode': '000000', 'country': 'TestCountry'},
               'card': {'longNum': '4111111111111111', 'expires': '12/30', 'ccv': '123'}}
    customer = client.request('POST', front + '/register',
                              {'username': 'tf2_' + token, 'password': secrets.token_hex(16),
                               'email': 'tf2_' + token + '@example.invalid',
                               'firstName': name, 'lastName': 'Synthetic'},
                              'register', redact=True)
    fixture['customer_id'] = require_id(customer, 'register')
    fixture['address_id'] = require_id(client.request('POST', front + '/addresses',
                                                     fixture['address'], 'create-address'), 'address')
    fixture['card_id'] = require_id(client.request('POST', front + '/cards',
                                                  fixture['card'], 'create-card'), 'card')
    cart_path = '/carts/' + fixture['customer_id'] + '/items'
    prefix = 'parallel' if shared else case_id
    ids = {item['key']: 'tf2_' + prefix + '_' + item['key'] for item in case['items']}
    def body(item):
        return {k: item[k] for k in ('quantity', 'unitPrice')} | {'itemId': ids[item['key']]}
    for item in case['items']:
        client.request('POST', cart + cart_path, body(item), 'add-item')
    if 'patch' in case:
        client.request('PATCH', cart + cart_path, body(case['patch']), 'patch-item')
    if 'repost' in case:
        client.request('POST', cart + cart_path, body(case['repost']), 'repost-item')
    # A separate client read checks fixture setup; it is NOT the read used by Orders.
    observed = client.request('GET', cart + cart_path, label='fixture-check-only')
    expected = {ids[item['key']]: body(item) for item in final_items(case)}
    if not isinstance(observed, list) or len(observed) != len(expected):
        raise RuntimeError('Cart fixture has unexpected size')
    for item in observed:
        wanted = expected.get(item.get('itemId'))
        if not wanted or any(item.get(k) != wanted[k] for k in ('quantity', 'unitPrice')):
            raise RuntimeError('Original cart update behavior differs from frozen contract')
    fixture['expected_items'] = expected
    fixture['fixture_read_items'] = observed
    save(out / 'fixture.json', fixture)
    request = {'customer': 'http://user/customers/' + fixture['customer_id'],
               'address': 'http://user/addresses/' + fixture['address_id'],
               'card': 'http://user/cards/' + fixture['card_id'],
               'items': 'http://carts' + cart_path}
    trace_id = secrets.token_hex(8)
    client.headers = {'X-B3-TraceId': trace_id, 'X-B3-SpanId': secrets.token_hex(8),
                      'X-B3-Sampled': '1', 'X-Tracefusion-Case': case_id}
    queries = []
    def source(service, route, field, record=None):
        return {'service': service, 'route': route, 'field': field, 'record_id': record,
                'invocation': 'actual upstream response consumed by this Orders call; runtime ID pending oracle'}
    all_amount_sources = []
    for item in observed:
        for field in ('quantity', 'unitPrice'):
            all_amount_sources.append(source('carts', cart_path, field, item['id']))
            queries.append({'target': 'items[itemId=' + item['itemId'] + '].' + field,
                            'sources': [all_amount_sources[-1]], 'profile': 'java-service-boundary'})
    queries.append({'target': 'total', 'sources': all_amount_sources,
                    'profile': 'java-service-boundary'})
    for target, route, field, record in [
        ('customer.firstName', '/customers/' + fixture['customer_id'], 'firstName', fixture['customer_id']),
        ('address.street', '/addresses/' + fixture['address_id'], 'street', fixture['address_id']),
        ('card.longNum', '/cards/' + fixture['card_id'], 'longNum', fixture['card_id']),
        ('card.ccv', '/cards/' + fixture['card_id'], 'ccv', fixture['card_id'])]:
        queries.append({'target': target, 'sources': [source('user', route, field, record)],
                        'profile': 'external-source-boundary'})
    if not case['expected_target']:
        for query in queries:
            query['sources'] = None
            query['expected_status'] = 'no-target'
    contract = {'case': case_id, 'expected_target': case['expected_target'],
                'trace_id_requested': trace_id, 'queries': queries,
                'source_basis': 'predeclared source semantics and fixture identity; not engine output',
                'execution_oracle_available': False, 'second_human_reviewed': False}
    # Freeze the query contract before submitting the target Orders request.
    save(out / 'query-contract.json', contract)
    return case, client, fixture, request, contract


def submit(prepared, orders, out, barrier=None):
    case, client, fixture, request, contract = prepared
    if barrier is not None:
        barrier.wait(timeout=30)
    start = time.monotonic_ns()
    result = {'case': contract['case'], 'business_passed': False,
              'expected_target': case['expected_target'], 'start_monotonic_ns': start}
    try:
        try:
            response = client.request('POST', orders + '/orders', request, 'target-order')
        except RuntimeError:
            event = client.events[-1]
            if case['expected_target'] or event.get('label') != 'target-order' or event['status'] != 406:
                raise
            if isinstance(event['response'], dict) and event['response'].get('id'):
                raise RuntimeError('Declined order unexpectedly has a target object')
            result.update(business_passed=True, target_exists=False, http_status=406)
            return result
        if not case['expected_target']:
            raise RuntimeError('Expected payment decline but original service returned success')
        if not isinstance(response, dict) or not response.get('id') or response.get('customerId') != fixture['customer_id']:
            raise RuntimeError('Wrong order/customer identity')
        expected = fixture['expected_items']
        actual = response.get('items')
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise RuntimeError('Unexpected order item count')
        seen = set()
        for item in actual:
            ident = item.get('itemId')
            if ident in seen or ident not in expected:
                raise RuntimeError('Wrong/duplicate item identity, including same-value substitutions')
            seen.add(ident)
            if any(item.get(k) != expected[ident][k] for k in ('quantity', 'unitPrice')):
                raise RuntimeError('Order fields differ from frozen cart version')
        total = sum(i['quantity'] * i['unitPrice'] for i in expected.values()) + 4.99
        if not math.isclose(response.get('total', float('nan')), total, abs_tol=0.01):
            raise RuntimeError('Order total differs from original formula')
        for obj, field, wanted in [('customer', 'firstName', fixture['firstName']),
                                    ('address', 'street', fixture['address']['street']),
                                    ('card', 'longNum', fixture['card']['longNum']),
                                    ('card', 'ccv', fixture['card']['ccv'])]:
            if (response.get(obj) or {}).get(field) != wanted:
                raise RuntimeError('Original response field differs from fixture: ' + obj + '.' + field)
        save(out / 'order-response.json', response)
        result.update(business_passed=True, target_exists=True, order_id=response['id'],
                      http_status=client.events[-1]['status'])
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        result['end_monotonic_ns'] = time.monotonic_ns()
        save(out / 'business-result.json', result)
    return result


def run(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if not args.project:
        args.project = 'tf2-mt-' + secrets.token_hex(5)
    if not re.fullmatch('[a-z0-9][a-z0-9_-]*', args.project):
        raise ValueError('Invalid Compose project name')
    result = {'status': 'blocked', 'project': args.project, 'mode': args.mode,
              'business_workload_run': False, 'provenance_engine_run': False,
              'cross_service_join_validated': False, 'execution_oracle_available': False,
              'accuracy_eligible': False, 'performance_eligible': False,
              'otel_or_our_collector_installed': False}
    deployment = None
    try:
        spec = compose_spec(args.mode, out, args.agent.resolve() if args.agent else None)
        file = out / 'compose.preflight.json'
        save(file, spec)
        for name in ('cases.json', 'sources.json'):
            shutil.copyfile(HERE / name, out / name)
        if not shutil.which('docker'):
            raise RuntimeError('Docker Engine/Compose unavailable; no services or field engine executed')
        deployment = Deployment(args, out, file)
        existing = deployment.compose('ps', '--all', '--quiet')
        if existing.stdout.strip():
            raise RuntimeError('Refusing to reuse an existing Compose project; choose a fresh project')
        deployment.start()
        front = 'http://127.0.0.1:' + os.environ.get('TF2_FRONT_PORT', '18080')
        cart = 'http://127.0.0.1:' + os.environ.get('TF2_CART_PORT', '18081')
        orders = 'http://127.0.0.1:' + os.environ.get('TF2_ORDERS_PORT', '18082')
        manifest = json.loads((HERE / 'cases.json').read_text())
        results = []
        result['business_workload_run'] = True
        for case in manifest['cases']:
            case_out = out / case['id']
            results.append(submit(prepare(case, case['id'], case_out, front, cart), orders, case_out))
        base = next(c for c in manifest['cases'] if c['id'] == manifest['concurrent']['case'])
        count = manifest['concurrent']['count']
        parallel = [prepare(base, 'parallel-' + str(i), out / ('parallel-' + str(i)),
                            front, cart, shared=True) for i in range(count)]
        barrier = threading.Barrier(count)
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(submit, item, orders, out / ('parallel-' + str(i)), barrier)
                       for i, item in enumerate(parallel)]
            results.extend(f.result() for f in futures)
        result.update(status='business-preflight-passed' if all(r['business_passed'] for r in results) else 'business-preflight-failed',
                      cases=results, workload_count=len(results),
                      concurrent_client_requests=count, actual_service_overlap_verified=False)
        if args.mode == 'mirrortaint':
            result['agent_logs'] = {name: [{'path': str(p.relative_to(out)), 'bytes': p.stat().st_size}
                                          for p in sorted((out / 'agent-logs' / name).rglob('*')) if p.is_file()]
                                    for name in ('carts', 'orders', 'shipping')}
            result['agent_error_logs_nonempty'] = [str(p.relative_to(out))
                for p in (out / 'agent-logs').rglob('*error*.log') if p.stat().st_size]
            result['agent_compatibility_status'] = 'raw logs retained; field labels and RPC-instance join still require independent validation'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        if deployment:
            deployment.diagnostics()
        save(out / 'result.json', result)
        bundle = out.with_suffix('.zip')
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(out.rglob('*')):
                if path.is_file() and path.suffix not in ('.jar', '.class'):
                    archive.write(path, path.relative_to(out))
        print(json.dumps(result, indent=2))
        print('RESULT BUNDLE: ' + str(bundle))
        if (out / 'compose.lock.json').exists():
            print('Containers/volumes retained. Stop this project using compose.lock.json and project=' + args.project)
    return int(result['status'] != 'business-preflight-passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'run'))
    parser.add_argument('--mode', choices=('plain', 'mirrortaint'), default='plain')
    parser.add_argument('--agent', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--project')
    parser.add_argument('--ready-timeout', type=int, default=300)
    args = parser.parse_args()
    if args.action == 'check':
        check_spec(json.loads((ROOT / 'scenarios/sockshop/compose.json').read_text()))
        manifest = json.loads((HERE / 'cases.json').read_text())
        assert len(manifest['cases']) == 7 and manifest['concurrent']['count'] == 8
        for case in manifest['cases']:
            assert len({i['key'] for i in case['items']}) == len(case['items'])
            total = sum(i['quantity'] * i['unitPrice'] for i in final_items(case)) + 4.99
            assert (total <= 100) == case['expected_target']
        print('PASS: original deployment subset and frozen source-derived cases; no runtime/accuracy result')
        return 0
    if args.out is None:
        args.out = ROOT / 'artifacts' / ('sockshop-mt-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
