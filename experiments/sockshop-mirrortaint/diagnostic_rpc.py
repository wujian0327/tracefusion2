#!/usr/bin/env python3
"""Separate, observer-assisted RPC lifecycle diagnosis; never a baseline/accuracy run."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil

from host import compose_spec, prepare, submit, HERE, Deployment, save


def observer_summary(lines):
    pattern = re.compile(r'TF2_RPC_OBSERVER phase=(enter|exit) thread=(\S+) available=(true|false) method=(\S+) url=(\S+)')
    events = []
    for line in lines:
        match = pattern.search(line)
        if match:
            phase, thread, available, method, url = match.groups()
            events.append(dict(phase=phase, thread=thread, available=available == 'true', method=method, url=url))
    enters = {(e['thread'], e['method'], e['url']) for e in events if e['phase'] == 'enter'}
    exits = {(e['thread'], e['method'], e['url']) for e in events if e['phase'] == 'exit'}
    complete = (len(events) == 12 and len(enters) == 6 and enters == exits
                and not any('-error' in line for line in lines))
    return {'events': events, 'six_rpc_pairs_complete': complete,
            'all_six_workers_unavailable': complete and all(not e['available'] for e in events)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', type=Path, required=True)
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--subnet', help='Explicit unused diagnostic subnet if Docker default pools are exhausted')
    parser.add_argument('--ready-timeout', type=int, default=300)
    args = parser.parse_args()
    args.mode = 'mirrortaint'
    args.project = 'tf2-rpc-diag-' + secrets.token_hex(5)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'project': args.project, 'status': 'blocked', 'diagnostic_observer_installed': True,
              'accuracy_eligible': False, 'performance_eligible': False}
    deployment = None
    try:
        # Separate loopback ports, independent fixtures, containers, volumes and agent logs.
        for key, port in [('TF2_FRONT_PORT', '18180'), ('TF2_CART_PORT', '18181'), ('TF2_ORDERS_PORT', '18182')]:
            os.environ[key] = port
        spec = compose_spec('mirrortaint', out, args.agent.resolve())
        if args.subnet:
            spec['networks'] = {'default': {'ipam': {'config': [{'subnet': args.subnet}]}}}
            result['explicit_subnet'] = args.subnet
        observer = out / 'rpc-state-observer.jar'
        shutil.copyfile(args.observer, observer)
        spec['services']['orders']['volumes'].append(str(observer) + ':/tf2/rpc-state-observer.jar:ro')
        spec['services']['orders']['environment']['JAVA_OPTS'] += ' -javaagent:/tf2/rpc-state-observer.jar'
        config = out / 'compose.diagnostic.json'
        save(config, spec)
        deployment = Deployment(args, out, config)
        deployment.start()
        case = json.loads((HERE / 'cases.json').read_text())['cases'][0]
        case_out = out / 'single'
        prepared = prepare(case, 'single', case_out, 'http://127.0.0.1:18180', 'http://127.0.0.1:18181')
        business = submit(prepared, 'http://127.0.0.1:18182', case_out)
        result.update(status='diagnostic-business-passed' if business['business_passed'] else 'diagnostic-business-failed',
                      business=business)
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        if deployment:
            deployment.diagnostics()
            # Preserve the standalone diagnostic project while releasing resources.
            try:
                deployment.compose('stop', timeout=90)
            except Exception as exc:
                result['stop_error'] = str(exc)
        log = out / 'compose.log'
        if log.exists():
            result['observer_lines'] = [line for line in log.read_text().splitlines() if 'TF2_RPC_OBSERVER' in line]
            result['observer_summary'] = observer_summary(result['observer_lines'])
        save(out / 'result.json', result)
        print(json.dumps(result, indent=2))
    return int(result['status'] != 'diagnostic-business-passed')


if __name__ == '__main__':
    raise SystemExit(main())
