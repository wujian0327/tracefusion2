#!/usr/bin/env python3
"""Five original controllers: frozen field contracts and serial cost workload."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import subprocess
import time
from urllib.parse import urlencode
from host import HERE, ROOT, compose_spec, prepare, submit
from sockshop import Client, Deployment, save

METHODS = {'get': 'works/weave/socks/cart/controllers/CartsController.get',
           'delete': 'works/weave/socks/cart/controllers/CartsController.delete',
           'mergeCarts': 'works/weave/socks/cart/controllers/CartsController.mergeCarts',
           'postShipping': 'works/weave/socks/shipping/controllers/ShippingController.postShipping',
           'newOrder': 'works/weave/socks/orders/controllers/OrdersController.newOrder'}


DB_CONTAINER = None


def database_snapshot(customer, folder, label):
    script = ('var c=db.cart.findOne({customerId:' + json.dumps(customer) + '});'
              'if(!c){print("null");}else{print(JSON.stringify({id:c._id.valueOf(),customerId:c.customerId,'
              'items:c.items.map(function(r){var i=db.item.findOne({_id:r.$id});return {id:i._id.valueOf(),'
              'itemId:i.itemId,quantity:i.quantity,unitPrice:i.unitPrice};})}));}')
    raw = subprocess.check_output(['docker', 'exec', DB_CONTAINER, 'mongo', 'data', '--quiet', '--eval', script], text=True, timeout=20)
    document = json.loads(raw)
    save(folder / (label + '-independent-mongo.json'), document)
    return document


def carts_fixture(client, base, key, items):
    customer = 'tf2five_' + secrets.token_hex(10)
    for i, item in enumerate(items):
        client.request('POST', base + '/carts/' + customer + '/items',
                       dict(item, itemId=key + '_' + str(i)), 'setup')
    cart = client.request('GET', base + '/carts/' + customer, label='setup-cart-read')
    assert cart['customerId'] == customer
    return customer, database_snapshot(customer, client.out, 'before-' + key)


def scalar_contract(cart):
    rows = [{'record_id': cart['id'], 'field': f, 'value': cart[f]}
            for f in ('id', 'customerId')]
    rows.extend({'record_id': i['id'], 'field': f, 'value': i[f]}
                for i in cart['items'] for f in ('id', 'itemId', 'quantity', 'unitPrice'))
    return rows


def additional_case(method, case_id, out, cart_url, shipping_url, variant='single', phase='accuracy'):
    folder = out / case_id
    folder.mkdir()
    client = Client(folder)
    items = [] if variant == 'empty' else [{'quantity': 2, 'unitPrice': 5.0}]
    if variant == 'multi':
        items.append({'quantity': 3, 'unitPrice': 5.0})
    if method == 'postShipping':
        body = {'id': 'tf2shipment_' + secrets.token_hex(10), 'name': 'SharedShipment'}
        if variant == 'same-value':
            body['name'] = body['id']
        contract = [{'record_id': body['id'], 'field': f, 'value': body[f]}
                    for f in ('id', 'name')]
        request_method, url = 'POST', shipping_url + '/shipping'
        sink = 'return'
    else:
        customer, before = carts_fixture(client, cart_url, case_id, items)
        body = None
        url = cart_url + '/carts/' + customer
        if method == 'mergeCarts':
            session, source = carts_fixture(client, cart_url, case_id + '_source', items)
            url += '/merge?' + urlencode({'sessionId': session})
            contract = scalar_contract(before) + [r for r in scalar_contract(source)
                                                   if r['record_id'] != source['id']]
            sink = 'save-final' if items else 'no-save'
            if not items: contract = []
        else:
            contract = scalar_contract(before)
            sink = 'return' if method == 'get' else 'delete'
        request_method = 'DELETE' if method == 'delete' else 'GET'
    trace = secrets.token_hex(8)
    client.headers = {'X-B3-TraceId': trace, 'X-B3-SpanId': secrets.token_hex(8), 'X-B3-Sampled': '1'}
    frozen = {'case': case_id, 'method': method, 'phase': phase, 'trace_id': trace,
              'sink': sink, 'queries': contract,
              'source_boundary': 'controller request body' if method == 'postShipping' else 'actual CartDAO.findByCustomerId result fields',
              'oracle_basis': 'original business semantics and independently seeded/read fixture identity before target',
              'second_human_reviewed': False}
    save(folder / 'query-contract.json', frozen)
    start = time.perf_counter_ns()
    response = client.request(request_method, url, body, 'target')
    duration = time.perf_counter_ns() - start
    if method == 'postShipping':
        assert response == body, 'Shipping response differs from request DTO'
    elif method == 'get':
        assert response['customerId'] == customer, 'Cart get returned wrong fixture'
    elif method == 'mergeCarts':
        after = database_snapshot(customer, folder, 'after')
        assert scalar_contract(after) == scalar_contract(before) + [r for r in scalar_contract(source) if r['record_id'] != source['id']], 'Merge contents/identity differs from frozen contract'
        source_after = database_snapshot(session, folder, 'after-source')
        assert source_after is None, 'Session cart was not deleted'
    else:
        after = database_snapshot(customer, folder, 'after')
        assert after is None, 'Cart was not deleted'
    result = {'case': case_id, 'method': method, 'trace_id': trace, 'phase': phase,
              'business_passed': True, 'http_runtime_ns': duration}
    save(folder / 'business-result.json', result)
    return result


def order_case(case, name, out, front, cart, orders, phase):
    prepared = prepare(case, name, out / name, front, cart)
    result = submit(prepared, orders, out / name)
    result.update(method='newOrder', phase=phase, trace_id=prepared[-1]['trace_id_requested'])
    return result


def run(args):
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    args.project = args.project or 'tf2-five-' + secrets.token_hex(5)
    global DB_CONTAINER
    DB_CONTAINER = args.project + '-carts-db-1'
    boundary = args.boundary_agent.resolve()
    shutil.copyfile(boundary, out / 'boundary-agent.jar')
    spec = compose_spec(args.mode, out, args.agent.resolve() if args.agent else None,
                        args.integration_adapter.resolve() if args.integration_adapter else None,
                        args.tracefusion_agent.resolve() if args.tracefusion_agent else None)
    spec['services']['shipping']['ports'] = ['127.0.0.1:${TF2_SHIPPING_PORT:-18483}:80']
    spec['networks'] = {'default': {'ipam': {'config': [{'subnet': args.subnet}]}}}
    for service in ('orders', 'carts', 'shipping'):
        cfg = spec['services'][service]
        cost = out / 'cost-events' / service; cost.mkdir(parents=True); cost.chmod(0o777)
        cfg.setdefault('volumes', []).extend([str(out / 'boundary-agent.jar') + ':/tf2/boundary-agent.jar:ro',
                                               str(cost) + ':/tf2/cost-output:rw'])
        if service != 'orders' and args.mode != 'plain':
            capture = out / 'boundary-events' / service; capture.mkdir(parents=True); capture.chmod(0o777)
            cfg['volumes'].append(str(capture) + ':/tf2/boundary-output:rw')
            cfg['environment']['JAVA_OPTS'] = (
                ' -javaagent:/tf2/boundary-agent.jar -Dtracefusion.boundary.mode=' + args.mode +
                ' -Dtracefusion.boundary.output=/tf2/boundary-output ' + cfg['environment']['JAVA_OPTS'])
        # Always last: the common timer encloses all tracing and source/sink hooks.
        cfg['environment']['JAVA_OPTS'] += (' -javaagent:/tf2/boundary-agent.jar=cost'
            ' -Dtracefusion.cost.output=/tf2/cost-output')
    file = out / 'compose.preflight.json'; save(file, spec)
    shutil.copyfile(HERE / 'cases.json', out / 'cases.json')
    save(out / 'protocol.json', {'methods': METHODS, 'warmup': args.warmup, 'repetitions': args.repetitions,
        'runtime': 'controller inclusive wall time and separately client HTTP latency; serial targets',
        'memory': 'JVM process-wide/current-thread allocated bytes per controller; separately post-call JVM VmRSS kB',
        'rss_limitations': 'resident size is the whole service JVM at sampling time, not bytes attributable to one call',
        'allocation_limitations': 'process-wide includes background activity; terminated threads can invalidate a sample; current-thread excludes async workers',
        'offline_cost_reported_separately': True, 'paper_numeric_reproduction': False,
        'boundary_agent_sha256': hashlib.sha256(boundary.read_bytes()).hexdigest()})
    deployment = Deployment(args, out, file)
    results = []
    status = {'project': args.project, 'mode': args.mode, 'status': 'failed',
              'configuration': 'MirrorTaint original JAR + disclosed instrumentation/library/thread/log/source-boundary adapters' if args.mode == 'mirrortaint' else args.mode,
              'accuracy_eligible': False, 'performance_eligible': False}
    try:
        if deployment.compose('ps', '--all', '--quiet').stdout.strip():
            raise ValueError('Fresh project required')
        deployment.start()
        front = 'http://127.0.0.1:' + os.environ.get('TF2_FRONT_PORT', '18480')
        cart = 'http://127.0.0.1:' + os.environ.get('TF2_CART_PORT', '18481')
        orders = 'http://127.0.0.1:' + os.environ.get('TF2_ORDERS_PORT', '18482')
        shipping = 'http://127.0.0.1:' + os.environ.get('TF2_SHIPPING_PORT', '18483')
        manifest = json.loads((HERE / 'cases.json').read_text())
        for case in manifest['cases']:
            results.append(order_case(case, case['id'], out, front, cart, orders, 'accuracy'))
        # Retain the frozen Orders case registry, including independent same-value customer records.
        base = manifest['cases'][0]
        from concurrent.futures import ThreadPoolExecutor
        import threading
        parallel = [prepare(base, 'parallel-' + str(i), out / ('parallel-' + str(i)), front, cart, shared=True)
                    for i in range(manifest['concurrent']['count'])]
        barrier = threading.Barrier(len(parallel))
        with ThreadPoolExecutor(max_workers=len(parallel)) as pool:
            futures = [pool.submit(submit, item, orders, out / ('parallel-' + str(i)), barrier)
                       for i, item in enumerate(parallel)]
            for item, future in zip(parallel, futures):
                r = future.result(); r.update(method='newOrder', phase='accuracy', trace_id=item[-1]['trace_id_requested']); results.append(r)
        for method in ('get', 'delete', 'mergeCarts', 'postShipping'):
            variants = ('single', 'multi', 'empty') if method != 'postShipping' else ('single', 'same-value')
            for variant in variants:
                results.append(additional_case(method, method + '-' + variant, out, cart, shipping, variant))
        for phase, count in [('warmup', args.warmup), ('measurement', args.repetitions)]:
            for i in range(count):
                for method in METHODS:
                    name = phase + '-' + method + '-' + str(i)
                    if method == 'newOrder':
                        results.append(order_case(base, name, out, front, cart, orders, phase))
                    else:
                        results.append(additional_case(method, name, out, cart, shipping, phase=phase))
        if not all(r['business_passed'] for r in results):
            raise ValueError('Business workload failed')
        status['status'] = 'business-passed'
    except Exception as error:
        status['error'] = str(error)
    finally:
        deployment.diagnostics()
        status['cases'] = results
        log = (out / 'compose.log').read_text(errors='replace')
        status['frontend_errors'] = [l for l in log.splitlines() if 'TF2_BOUNDARY error=' in l or 'TF2_SERVICE_FRONTEND error=' in l or 'TF2_MT_ADAPTER error' in l]
        save(out / 'result.json', status)
        print(json.dumps({k:v for k,v in status.items() if k != 'cases'}, indent=2))
    return int(status['status'] != 'business-passed' or bool(status['frontend_errors']))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['plain', 'mirrortaint', 'tracefusion'], required=True)
    p.add_argument('--agent', type=Path); p.add_argument('--integration-adapter', type=Path)
    p.add_argument('--tracefusion-agent', type=Path); p.add_argument('--boundary-agent', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--project'); p.add_argument('--subnet', required=True)
    p.add_argument('--ready-timeout', type=int, default=300)
    p.add_argument('--warmup', type=int, default=5); p.add_argument('--repetitions', type=int, default=20)
    raise SystemExit(run(p.parse_args()))
