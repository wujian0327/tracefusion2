#!/usr/bin/env python3
"""Collect real serial/concurrent HTTP-instance evidence; no accuracy ranking."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import secrets
import threading

from flowdist_runtime_comparison import configuration, digest, events
from flowdist_full_order import CachedDeployment
from host import HERE, prepare, submit
from sockshop import Client, save
import flowdist_preflight as tool


def run_mode(args, mode, out):
    out.mkdir()
    spec = configuration(args, mode, out)
    if mode == 'tracefusion':
        spec['services']['orders']['environment']['JAVA_OPTS'] += ' -Dtracefusion.http.instances=true'
    file = out / 'compose.preflight.json'
    save(file, spec)
    project = 'tf2-fd-http-' + secrets.token_hex(5)
    deployment = CachedDeployment(argparse.Namespace(project=project, ready_timeout=args.ready_timeout), out, file)
    for command in (['docker', 'ps', '--all', '--quiet'], ['docker', 'network', 'ls', '--quiet'], ['docker', 'volume', 'ls', '--quiet']):
        if deployment.command(command + ['--filter', 'label=com.docker.compose.project=' + project]).stdout.strip():
            raise ValueError('Fresh Docker project required')
    registry = json.loads((HERE / 'cases.json').read_text())
    result = {'mode': mode, 'project': project, 'status': 'failed', 'cases': []}
    try:
        deployment.start()
        for case in registry['cases']:
            folder = out / case['id']
            fixture = prepare(case, case['id'], folder, 'http://127.0.0.1:18580', 'http://127.0.0.1:18581')
            item = submit(fixture, 'http://127.0.0.1:18582', folder)
            item['phase'] = 'serial'
            result['cases'].append(item)
            if not item['business_passed']:
                raise ValueError('Business failure: ' + case['id'])
        count = registry['concurrent']['count']
        # Independent customers, equal business content: retain original registry.
        fixtures = [prepare(registry['cases'][0], 'distinct-' + str(i), out / ('distinct-' + str(i)),
                            'http://127.0.0.1:18580', 'http://127.0.0.1:18581', shared=True) for i in range(count)]
        groups = [('distinct', fixtures)]
        # Reuse customer/input/B3 trace: name and trace cannot disambiguate calls.
        seed = prepare(registry['cases'][0], 'shared-seed', out / 'shared-seed',
                       'http://127.0.0.1:18580', 'http://127.0.0.1:18581', shared=True)
        shared = []
        for i in range(count):
            name = 'shared-' + str(i)
            folder = out / name
            folder.mkdir()
            case, previous, fixture, request, contract = seed
            client = Client(folder)
            client.headers = dict(previous.headers)
            client.headers['X-Tracefusion-Case'] = name
            contract = copy.deepcopy(contract)
            contract['case'] = name
            save(folder / 'query-contract.json', contract)
            save(folder / 'fixture.json', fixture)
            shared.append((case, client, fixture, request, contract))
        groups.append(('shared', shared))
        for phase, prepared in groups:
            barrier = threading.Barrier(count)
            with ThreadPoolExecutor(max_workers=count) as pool:
                futures = [pool.submit(submit, item, 'http://127.0.0.1:18582', out / (phase + '-' + str(i)), barrier)
                           for i, item in enumerate(prepared)]
                for future in futures:
                    item = future.result()
                    item['phase'] = phase
                    result['cases'].append(item)
                    if not item['business_passed']:
                        raise ValueError('Concurrent business failure: ' + item['case'])
            print(mode, phase, count, 'business passed', flush=True)
        for role in ('orders', 'shipping'):
            deployment.compose('stop', '-t', '30', role, timeout=45)
        if mode == 'tracefusion':
            for path in (out / 'tracefusion-events/events.jsonl', out / 'boundary-events/shipping/events.jsonl'):
                events(path)
        result['status'] = 'serial-and-concurrent-business-passed'
    finally:
        deployment.diagnostics()
        deployment.compose('down', '--volumes', '--remove-orphans', check=False, timeout=90)
        save(out / 'result.json', result)
    return result


def run(args):
    tool.verify_repository(args.repo.resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'protocol.json', {
        'kind': 'sockshop-http-instance-evidence-pilot', 'serial_cases': 7,
        'parallel_groups': [{'count': 8, 'distinct_customers': True},
                            {'count': 8, 'same_customer_and_trace': True}],
        'target': 'Orders outbound Shipment fields -> Shipping controller return fields',
        'query_patterns_frozen_before_execution': ['same message and field', 'same message different field', 'different message same field'],
        'tracefusion_transport_extension': 'UUID HTTP header plus outbound DTO snapshot; no taint labels in header',
        'flowdist_transport': 'existing original process clock adapter, no instance graph extension',
        'original_jars': {'orders': digest(args.orders), 'shipping': digest(args.shipping)},
        'builds': {'boundary': digest(args.boundary), 'tracefusion': digest(args.tracefusion),
                   'flowdist_manifest': digest(args.apps / 'manifest.json')},
        'accuracy_ranking_available': False, 'performance_comparison_available': False})
    reports = {mode: run_mode(args, mode, out / mode) for mode in args.modes}
    locks = [json.loads((out / mode / 'compose.lock.json').read_text()) for mode in reports]
    images = [{key: value['image'] for key, value in lock['services'].items()} for lock in locks]
    if any(image != images[0] for image in images):
        raise ValueError('Different cached business images')
    save(out / 'result.json', {'runs': reports, 'same_business_images': True,
                             'accuracy_ranking_available': False, 'performance_comparison_available': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo', 'apps', 'orders', 'shipping', 'boundary', 'tracefusion', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--modes', nargs='+', choices=('flowdist', 'tracefusion'), default=['flowdist', 'tracefusion'])
    parser.add_argument('--ready-timeout', type=int, default=180)
    parser.add_argument('--subnet', default='10.254.243.0/24')
    args = parser.parse_args()
    if len(set(args.modes)) != len(args.modes):
        parser.error('Duplicate modes')
    run(args)
