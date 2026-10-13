#!/usr/bin/env python3
"""Run frozen workload on an existing deployment with independent callee captures."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
import host

HERE = Path(__file__).resolve().parent
IMAGE = 'python@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111'


def command(argv, **kwargs):
    capture = {'stdout': subprocess.PIPE} if 'stderr' in kwargs else {'capture_output': True}
    return subprocess.run(argv, check=True, text=True, timeout=30, **capture, **kwargs).stdout


def run(args):
    prior = json.loads((args.deployment / 'result.json').read_text())
    if prior['status'] != 'business-preflight-passed' or not prior.get('integration_adapter_sha256'):
        raise ValueError('Requires existing completed adapted deployment')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    project = prior['project']
    containers = {}
    for name in ('orders', 'carts', 'user', 'payment', 'shipping'):
        inspected = json.loads(command(['docker', 'inspect', project + '-' + name + '-1']))[0]
        if not inspected['State']['Running']:
            raise ValueError('Existing service is stopped: ' + name)
        network = inspected['NetworkSettings']['Networks'][project + '_default']
        containers[name] = {'id': inspected['Id'], 'ip': network['IPAddress'], 'image': inspected['Image']}
    command(['docker', 'image', 'inspect', IMAGE])
    for file in ('compose.lock.json', 'images.json', 'cases.json', 'sources.json'):
        shutil.copyfile(args.deployment / file, out / file)
    original_logs = {name: next((args.deployment / 'agent-logs' / name).glob('**/adapted-events.jsonl'))
                     for name in ('orders', 'carts', 'shipping')}
    offsets = {name: log.stat().st_size for name, log in original_logs.items()}
    server_logs = ({name: args.server_logs / name / 'server-events.jsonl' for name in ('carts', 'shipping')}
                   if args.server_logs else {})
    server_offsets = {name: log.stat().st_size if log.exists() else 0 for name, log in server_logs.items()}
    captures = []
    metadata = {'capture_image': IMAGE, 'containers': containers, 'deployment_project': project,
                'reused_deployment': True, 'existing_agent_log_start_offsets': offsets,
                'existing_server_log_start_offsets': server_offsets,
                'capture_source_sha256': hashlib.sha256((HERE / 'capture_http_peer.py').read_bytes()).hexdigest()}
    if args.server_logs:
        observer_build = args.server_logs.resolve().parent
        metadata['server_observer'] = json.loads((observer_build / 'result.json').read_text())
        shutil.copyfile(observer_build / 'compose.observer.json', out / 'compose.observer.json')
    result = {'status': 'blocked', 'mode': 'mirrortaint', 'project': project,
              'integration_adapter_sha256': prior['integration_adapter_sha256'],
              'configuration': 'MirrorTaint original JAR + instrumentation/library/source/thread/logging adapters + independent callee network observers',
              'accuracy_eligible': False, 'performance_eligible': False, 'cross_service_join_validated': False}
    result['independent_server_observer_installed'] = bool(args.server_logs)
    if args.server_logs:
        result['configuration'] += ' + independent Java HTTP entry/dispatch/exit observer'
    try:
        for name in ('carts', 'user', 'payment', 'shipping'):
            folder = out / 'wire' / name
            folder.mkdir(parents=True)
            folder.chmod(0o777)  # New evidence folder only; observer has no DAC override capability.
            capture = 'tf2-capture-' + secrets.token_hex(5)
            command(['docker', 'run', '-d', '--name', capture, '--network', 'container:' + containers[name]['id'],
                     '--cap-drop', 'ALL', '--cap-add', 'NET_RAW', '--read-only',
                     '-v', str(HERE / 'capture_http_peer.py') + ':/capture.py:ro',
                     '-v', str(folder) + ':/output:rw', IMAGE, 'python', '/capture.py',
                     '--orders-ip', containers['orders']['ip'], '--peer-ip', containers[name]['ip'], '--out', '/output'])
            captures.append((capture, folder))
        metadata['observers'] = [{'container': name, 'output': str(folder)} for name, folder in captures]
        deadline = time.monotonic() + 15
        while not all((p / 'ready.json').exists() for _, p in captures):
            if time.monotonic() > deadline:
                raise RuntimeError('Capture startup timeout')
            time.sleep(.1)
        print('Callee observers ready; running 15 real business requests.', flush=True)
        manifest = json.loads((HERE / 'cases.json').read_text())
        cases = []
        for case in manifest['cases']:
            folder = out / case['id']
            cases.append(host.submit(host.prepare(case, case['id'], folder, args.front, args.cart), args.orders, folder))
        base = next(c for c in manifest['cases'] if c['id'] == manifest['concurrent']['case'])
        count = manifest['concurrent']['count']
        prepared = [host.prepare(base, 'parallel-' + str(i), out / ('parallel-' + str(i)), args.front, args.cart, shared=True)
                    for i in range(count)]
        barrier = threading.Barrier(count)
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(host.submit, p, args.orders, out / ('parallel-' + str(i)), barrier)
                       for i, p in enumerate(prepared)]
            cases.extend(f.result() for f in futures)
        result.update(status='business-preflight-passed' if all(c['business_passed'] for c in cases)
                      else 'business-preflight-failed', cases=cases, workload_count=len(cases))
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        capture_errors = []
        for capture, folder in captures:
            try:
                command(['docker', 'stop', '--time', '5', capture])
                (folder / 'observer.log').write_text(command(['docker', 'logs', capture], stderr=subprocess.STDOUT))
                command(['docker', 'rm', capture])
            except Exception as exc:
                capture_errors.append(str(exc))
        result['capture_errors'] = capture_errors
        for name, original_log in original_logs.items():
            target_log = out / original_log.relative_to(args.deployment.resolve())
            target_log.parent.mkdir(parents=True)
            with original_log.open('rb') as src:
                src.seek(offsets[name])
                target_log.write_bytes(src.read())
        for name, original_log in server_logs.items():
            target_log = out / 'server' / name / 'server-events.jsonl'
            target_log.parent.mkdir(parents=True)
            with original_log.open('rb') as src:
                src.seek(server_offsets[name])
                target_log.write_bytes(src.read())
        for name in ('orders', 'carts', 'shipping'):
            source = args.deployment / 'agent-logs' / name
            for file in source.rglob('*error*.log'):
                target = out / file.relative_to(args.deployment)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, target)
        logs = command(['docker', 'compose', '-p', project, '-f', str(args.deployment / 'compose.lock.json'), 'logs', '--no-color'])
        (out / 'compose.log').write_text(logs)
        (out / 'capture-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        for name in ('carts', 'user', 'payment', 'shipping'):
            pcap = out / 'wire' / name / 'http.pcap'
            if pcap.exists():
                decoded = command(['tshark', '-2', '-r', str(pcap), '-Y', 'http', '-T', 'json', '--no-duplicate-keys'])
                (pcap.parent / 'http.json').write_text(decoded)
        print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2))
    return result['status'] == 'business-preflight-passed' and not result['capture_errors']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--front', default='http://127.0.0.1:18280')
    parser.add_argument('--cart', default='http://127.0.0.1:18281')
    parser.add_argument('--orders', default='http://127.0.0.1:18282')
    parser.add_argument('--server-logs', type=Path, help='Optional independently mounted Java server observer output root')
    raise SystemExit(0 if run(parser.parse_args()) else 1)
