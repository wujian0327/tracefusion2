#!/usr/bin/env python3
"""Run an isolated Sock Shop + eBPF HTTP evidence experiment on a Linux host."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import zipfile

import sockshop as base
from ebpf_provenance import analyze

APP_SERVICES = {'front-end', 'user', 'carts', 'orders', 'payment', 'shipping'}


def preflight():
    findings = {'platform': platform.platform(), 'python': sys.executable,
                'root': hasattr(os, 'geteuid') and os.geteuid() == 0,
                'docker': bool(shutil.which('docker')), 'bcc_importable': False}
    try:
        from bcc import BPF  # noqa: F401
        findings['bcc_importable'] = True
    except ImportError as exc:
        findings['bcc_error'] = str(exc)
    findings['compatible_host'] = sys.platform == 'linux' and platform.machine() in ('x86_64', 'amd64')
    findings['ready_for_kernel_load_attempt'] = all(findings[k] for k in (
        'root', 'docker', 'bcc_importable', 'compatible_host'))
    findings['note'] = 'Import checks do not prove BPF compilation/attachment; run performs that check.'
    return findings


def discover(deployment):
    ids = deployment.compose('ps', '-q').stdout.split()
    containers = json.loads(deployment.command(['docker', 'inspect', *ids]).stdout)
    services, networks = {}, set()
    for obj in containers:
        name = obj['Config']['Labels'].get('com.docker.compose.service')
        if name not in APP_SERVICES:
            continue
        for network, props in obj['NetworkSettings']['Networks'].items():
            if props.get('IPAddress'):
                services[props['IPAddress']] = name
                networks.add(network)
    if set(services.values()) != APP_SERVICES or len(networks) != 1:
        raise RuntimeError('Expected six applications on one dedicated Docker bridge')
    network = json.loads(deployment.command(['docker', 'network', 'inspect', next(iter(networks))]).stdout)[0]
    if network['Driver'] != 'bridge' or network.get('EnableIPv6'):
        raise RuntimeError('Only an IPv4 Docker bridge is supported')
    if network.get('Labels', {}).get('com.docker.compose.project') != deployment.args.project:
        raise RuntimeError('Refusing to capture a bridge outside the selected Compose project')
    interface = network.get('Options', {}).get('com.docker.network.bridge.name') or 'br-' + network['Id'][:12]
    return {'network_id': network['Id'], 'network_name': network['Name'],
            'interface': interface, 'ip_to_service': services}


def fixture(out, number, front, carts):
    directory = out / 'workload' / ('request-%03d' % number)
    directory.mkdir(parents=True)
    result = base.smoke(directory, front, carts)
    base.save(directory / 'result.json', result)
    return {'order_id': result['order_id'], 'directory': str(directory.relative_to(out))}


def validate_capture(out, queries, stats, summary):
    """Independent client-vs-wire payload coverage, never lineage accuracy."""
    transactions = json.loads((out / 'analysis/transactions.json').read_text())
    checks = []
    for q in queries:
        expected = json.loads((out / q['directory'] / 'order-response.json').read_text())
        fixture_data = json.loads((out / q['directory'] / 'fixture.json').read_text())
        matching = [t for t in transactions if t['server'] == 'front-end' and t['method'] == 'POST'
                    and t['target'].split('?')[0] == '/orders' and t['response']['json'] == expected]
        internal = [t for t in transactions if t['client'] == 'front-end' and t['server'] == 'orders'
                    and t['method'] == 'POST' and t['target'].split('?')[0] == '/orders'
                    and t['response']['json'] == expected]
        check = {'order_id': q['order_id'], 'wire_matches_client_order': len(matching) == 1,
                 'front_orders_payload_observed': len(internal) == 1}
        if internal:
            begin, end = internal[0]['request']['start_us'], internal[0]['response']['end_us']
            relevant = [t for t in transactions if t['client'] == 'orders'
                        and begin <= t['request']['start_us'] <= t['response']['end_us'] <= end]
            check['orders_downstream_services_seen'] = sorted({t['server'] for t in relevant})
            check['downstream_coverage'] = {'user', 'carts', 'payment', 'shipping'} <= {
                t['server'] for t in relevant}
            check['card_read_payload_observed'] = any(
                t['server'] == 'user' and t['method'] == 'GET'
                and t['target'].split('?')[0].rstrip('/').endswith('/' + fixture_data['card_id'])
                and isinstance(t['response']['json'], dict)
                and t['response']['json'].get('longNum') == fixture_data['card']['longNum']
                and t['response']['json'].get('ccv') == fixture_data['card']['ccv'] for t in relevant)
        else:
            check.update(downstream_coverage=False, card_read_payload_observed=False)
        check['passed'] = all(check[k] for k in ('wire_matches_client_order',
            'front_orders_payload_observed', 'downstream_coverage', 'card_read_payload_observed'))
        checks.append(check)
    complete = (stats.get('status') == 'stopped' and stats.get('socket_drops') == 0
                and stats.get('fragmented_packets') == 0 and not summary['reconstruction_issues'])
    return {'status': 'passed' if checks and all(c['passed'] for c in checks) and complete else 'incomplete',
            'capture_checks': checks, 'recorder_clean': complete,
            'meaning': 'Wire/client agreement and selected HTTP path coverage only',
            'field_lineage_accuracy': None,
            'downstream_interval_checks_are_not_request_attribution_truth': True}


def package(out):
    archive = out.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out.rglob('*')):
            if path.is_file():
                z.write(path, str(path.relative_to(out)))
    return archive


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check', 'run', 'analyze', 'down'])
    p.add_argument('--project', default='tracefusion2-ebpf')
    p.add_argument('--out', type=Path, help='New run directory, or existing run for analyze')
    p.add_argument('--requests', type=int, default=1)
    p.add_argument('--concurrency', type=int, default=1)
    p.add_argument('--front-port', type=int, default=28080)
    p.add_argument('--cart-port', type=int, default=28081)
    p.add_argument('--ready-timeout', type=int, default=300)
    p.add_argument('--capture-seconds', type=int, default=300)
    p.add_argument('--max-mib', type=int, default=64)
    args = p.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]*', args.project):
        p.error('Invalid project name')
    if min(args.requests, args.concurrency, args.ready_timeout, args.capture_seconds, args.max_mib) < 1:
        p.error('Counts, timeouts and limits must be positive')
    if not all(1024 <= port <= 65535 for port in (args.front_port, args.cart_port)) or args.front_port == args.cart_port:
        p.error('Choose two distinct unprivileged ports')
    if args.action == 'check':
        report = preflight(); print(json.dumps(report, indent=2))
        return int(not report['ready_for_kernel_load_attempt'])
    if args.action == 'analyze':
        if not args.out:
            p.error('analyze requires --out EXISTING_RUN_DIRECTORY')
        out = args.out.resolve()
        report = analyze(out / 'capture/packets.pcap',
            json.loads((out / 'services.json').read_text())['ip_to_service'], out / 'analysis',
            json.loads((out / 'queries-input.json').read_text()))
        print(json.dumps(report, indent=2)); return int(report['status'] != 'parsed')
    if args.action == 'down':
        return subprocess.call(['docker', 'compose', '-p', args.project, '-f', str(base.COMPOSE), 'down'])
    out = (args.out or base.ROOT / 'artifacts' / ('sockshop-ebpf-' +
        dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(2))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.chmod(out, 0o700)
    (out / 'capture').mkdir()
    deployment = process = log = None
    queries = []
    result = {'status': 'failed', 'stage': 'preflight', 'project': args.project,
              'mechanism': 'eBPF socket filter + persisted PCAP + offline graph',
              'new_business_instrumentation': False, 'field_lineage_ground_truth': False,
              'evaluation_scope': 'synchronous HTTP; no database or RabbitMQ provenance',
              'requested_orders': args.requests, 'concurrency': args.concurrency,
              'full_shipping_worker_success': 'not_asserted; existing Docker socket dependency remains'}
    try:
        report = preflight(); base.save(out / 'preflight.json', report)
        if not report['ready_for_kernel_load_attempt']:
            raise RuntimeError('Preflight failed; inspect preflight.json and docs/ebpf-provenance.md')
        deployment = base.Deployment(args, out)
        context = json.loads(deployment.command(['docker', 'context', 'inspect']).stdout)[0]
        endpoint = os.environ.get('DOCKER_HOST', context['Endpoints']['docker']['Host'])
        if not endpoint.startswith('unix://'):
            raise RuntimeError('Run on the native Linux Docker host, not a remote Docker context')
        info = json.loads(deployment.command(['docker', 'info', '--format', '{{json .}}']).stdout)
        if any('rootless' in s for s in info.get('SecurityOptions', [])) or 'Docker Desktop' in info.get('OperatingSystem', ''):
            raise RuntimeError('Rootless Docker / Docker Desktop are outside this prototype scope')
        os.environ['TF2_FRONT_PORT'], os.environ['TF2_CART_PORT'] = str(args.front_port), str(args.cart_port)
        result['stage'] = 'deployment'
        deployment.start()
        services = discover(deployment); base.save(out / 'services.json', services)
        code = ['scripts/ebpf_capture.py', 'scripts/ebpf_provenance.py',
                'scripts/sockshop_ebpf.py', 'scripts/sockshop.py', 'instrumentation/ebpf/http_capture.c']
        base.save(out / 'code.json', {name: hashlib.sha256((base.ROOT / name).read_bytes()).hexdigest() for name in code})
        result['stage'] = 'ebpf-attach'
        log = (out / 'capture/recorder.log').open('w')
        process = subprocess.Popen([sys.executable, str(base.ROOT / 'scripts/ebpf_capture.py'),
            '--interface', services['interface'], '--services', str(out / 'services.json'),
            '--out', str(out / 'capture'), '--seconds', str(args.capture_seconds),
            '--max-mib', str(args.max_mib)], stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while not (out / 'capture/ready.json').exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('BPF did not attach; inspect capture/recorder.log')
            time.sleep(0.2)
        result['stage'] = 'workload'
        front, carts = 'http://127.0.0.1:%d' % args.front_port, 'http://127.0.0.1:%d' % args.cart_port
        failures = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            jobs = [pool.submit(fixture, out, n, front, carts) for n in range(args.requests)]
            for job in as_completed(jobs):
                try:
                    queries.append(job.result())
                except Exception as exc:
                    failures.append(str(exc))
        base.save(out / 'workload-errors.json', failures)
        result['completed_orders'] = len(queries)
        time.sleep(1)  # drain TCP tails; not evidence of completeness
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=10)
        result['recorder_returncode'] = process.returncode
        base.save(out / 'queries-input.json', queries)
        result['stage'] = 'offline-analysis'
        summary = analyze(out / 'capture/packets.pcap', services['ip_to_service'], out / 'analysis', queries)
        stats = json.loads((out / 'capture/capture.json').read_text())
        verification = validate_capture(out, queries, stats, summary)
        base.save(out / 'capture-validation.json', verification)
        result['capture_validation'] = verification['status']
        result['analysis_summary'] = summary
        result['status'] = ('capture_verified' if verification['status'] == 'passed'
                            and not failures and process.returncode == 0 else 'incomplete')
        result['stage'] = 'complete'
    except Exception as exc:
        result['error'] = '%s: %s' % (type(exc).__name__, exc)
        print(result['error'], file=sys.stderr)
    finally:
        if process and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
                result['capture_force_killed'] = True
        if log:
            log.close()
        if deployment:
            deployment.diagnostics()
        base.save(out / 'queries-input.json', queries)
        base.save(out / 'result.json', result)
        bundle = package(out)
        os.chmod(bundle, 0o600)
        if os.environ.get('SUDO_UID') and os.environ.get('SUDO_GID'):
            uid, gid = int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID'])
            for path in [out, *out.rglob('*'), bundle]:
                os.chown(path, uid, gid)
        print('RESULT BUNDLE: ' + str(bundle), flush=True)
    return 0 if result['status'] == 'capture_verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
