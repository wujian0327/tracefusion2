#!/usr/bin/env python3
"""Fresh cached deployments: five controllers, three analyzers, common observer.

Keep field calibrations and native FlowDist queries distinct. Never treat
business success or method events as field/path accuracy.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading

from flowdist_full_order import CachedDeployment
from flowdist_runtime_comparison import configuration, digest, events
from host import HERE, compose_spec, prepare, submit
from sockshop import save
import five_methods as five
import flowdist_preflight as tool
from evaluate_five_methods import costs


def configured(args, mode, out):
    spec = configuration(args, 'plain' if mode == 'mirrortaint' else mode, out)
    spec['services']['shipping']['ports'] = ['127.0.0.1:18583:80']
    manifest = json.loads((args.apps / 'manifest.json').read_text())
    role = 'carts'
    original = args.carts.resolve()
    if digest(original) != manifest['apps'][role]['original_sha256']:
        raise ValueError('Carts differs from FlowDist original input')
    jar = args.apps / 'carts-flowdist.jar' if mode == 'flowdist' else original
    if mode == 'flowdist' and digest(jar) != manifest['apps'][role]['adapted_sha256']:
        raise ValueError('FlowDist Carts build changed')
    shutil.copyfile(jar, out / 'carts.jar')
    runtime = out / 'runtime/carts'
    (runtime / 'test1').mkdir(parents=True)
    runtime.chmod(0o777)
    (runtime / 'test1').chmod(0o777)
    cost = out / 'cost-events/carts'
    cost.mkdir(parents=True)
    cost.chmod(0o777)
    cfg = spec['services']['carts']
    cfg.setdefault('volumes', []).extend([str(out / 'carts.jar') + ':/tf2/app.jar:ro',
        str(runtime) + ':/tf2/output:rw', str(out / 'observer.jar') + ':/tf2/observer.jar:ro',
        str(cost) + ':/tf2/cost:rw'])
    cfg['entrypoint'] = ['sh', '-c', 'cd /tf2/output && exec java $$JAVA_OPTS -jar /tf2/app.jar --port=80']
    if mode == 'flowdist':
        model = manifest['branch_models']['carts']
        if not model['author_method_instrumentation']:
            raise ValueError('Original Carts application method events required')
        for key, name in (('mapping', 'entitystmt.out.branch'), ('statements', 'stmtids.out')):
            path = Path(model[key])
            if digest(path) != model[key + '_sha256']:
                raise ValueError('Carts branch mapping changed')
            shutil.copyfile(path, runtime / name)
        cfg['environment']['JAVA_OPTS'] += ' -Dflowdist.method.instrumented=true'
    if mode == 'tracefusion':
        capture = out / 'boundary-events/carts'
        capture.mkdir(parents=True)
        capture.chmod(0o777)
        cfg['volumes'].append(str(capture) + ':/tf2/boundary:rw')
        cfg['environment']['JAVA_OPTS'] += ' -javaagent:/tf2/observer.jar -Dtracefusion.boundary.mode=tracefusion -Dtracefusion.boundary.output=/tf2/boundary'
    cfg['environment']['JAVA_OPTS'] += ' -javaagent:/tf2/observer.jar=cost -Dtracefusion.cost.output=/tf2/cost'
    if mode == 'mirrortaint':
        adapted = compose_spec(mode, out, args.mirrortaint.resolve(), args.integration_adapter.resolve())
        for role in ('orders', 'carts', 'shipping'):
            cfg = spec['services'][role]
            mt = adapted['services'][role]
            cfg['volumes'].extend(mt['volumes'])
            cfg['environment']['JAVA_OPTS'] = mt['environment']['JAVA_OPTS']
            if role != 'orders':
                capture = out / 'boundary-events' / role
                capture.mkdir(parents=True)
                capture.chmod(0o777)
                cfg['volumes'].append(str(capture) + ':/tf2/boundary:rw')
                cfg['environment']['JAVA_OPTS'] = (' -javaagent:/tf2/observer.jar -Dtracefusion.boundary.mode=mirrortaint'
                    ' -Dtracefusion.boundary.output=/tf2/boundary ' + cfg['environment']['JAVA_OPTS'])
            cfg['environment']['JAVA_OPTS'] += ' -javaagent:/tf2/observer.jar=cost -Dtracefusion.cost.output=/tf2/cost'
    return spec


def execute_workload(args, out, result):
    front, cart, orders, shipping = ['http://127.0.0.1:' + str(port) for port in (18580, 18581, 18582, 18583)]
    registry = json.loads((HERE / 'cases.json').read_text())
    def remember(item):
        result['cases'].append(item)
        save(out / 'progress.json', {'cases_completed': len(result['cases']), 'last_case': item})
        if not item['business_passed']:
            raise ValueError('Business failure: ' + item['case'])
    for case in registry['cases']:
        remember(five.order_case(case, case['id'], out, front, cart, orders, 'accuracy'))
    base = registry['cases'][0]
    parallel = [prepare(base, 'parallel-' + str(i), out / ('parallel-' + str(i)), front, cart, shared=True)
                for i in range(registry['concurrent']['count'])]
    barrier = threading.Barrier(len(parallel))
    with ThreadPoolExecutor(max_workers=len(parallel)) as pool:
        futures = [pool.submit(submit, item, orders, out / ('parallel-' + str(i)), barrier)
                   for i, item in enumerate(parallel)]
        for prepared, future in zip(parallel, futures):
            item = future.result()
            item.update(method='newOrder', phase='accuracy', trace_id=prepared[-1]['trace_id_requested'])
            remember(item)
    for method in ('get', 'delete', 'mergeCarts', 'postShipping'):
        variants = ('single', 'multi', 'empty') if method != 'postShipping' else ('single', 'same-value')
        for variant in variants:
            remember(five.additional_case(method, method + '-' + variant, out, cart, shipping, variant))
    print(result['mode'], 'accuracy business cases passed', flush=True)
    for phase, count in (('warmup', args.warmup), ('measurement', args.repetitions)):
        for index in range(count):
            for method in five.METHODS:
                name = phase + '-' + method + '-' + str(index)
                if method == 'newOrder':
                    item = five.order_case(base, name, out, front, cart, orders, phase)
                else:
                    item = five.additional_case(method, name, out, cart, shipping, phase=phase)
                remember(item)
            print(result['mode'], phase, index, 'all five passed', flush=True)


def run_mode(args, mode, out, protocol):
    out.mkdir()
    spec = configured(args, mode, out)
    file = out / 'compose.preflight.json'
    save(file, spec)
    save(out / 'protocol.json', protocol)
    shutil.copyfile(HERE / 'cases.json', out / 'cases.json')
    project = 'tf2-three-five-' + secrets.token_hex(5)
    deployment = CachedDeployment(argparse.Namespace(project=project, ready_timeout=args.ready_timeout), out, file)
    for cmd in (['docker', 'ps', '--all', '--quiet'], ['docker', 'network', 'ls', '--quiet'], ['docker', 'volume', 'ls', '--quiet']):
        if deployment.command(cmd + ['--filter', 'label=com.docker.compose.project=' + project]).stdout.strip():
            raise ValueError('Fresh project required')
    result = {'mode': mode, 'project': project, 'status': 'failed', 'cases': [], 'frontend_errors': [],
              'configuration': {'mirrortaint': 'MirrorTaint + disclosed propagation/library/thread/source/logging adapters',
                                'flowdist': 'FlowDist + original application branch/method events and disclosed compatibility/lambda adapters'}.get(mode, mode),
              'accuracy_eligible': False, 'performance_eligible': False}
    try:
        deployment.start()
        five.DB_CONTAINER = deployment.compose('ps', '-q', 'carts-db').stdout.strip()
        if not five.DB_CONTAINER or '\n' in five.DB_CONTAINER:
            raise ValueError('Unique owned Carts database required')
        execute_workload(args, out, result)
        for role in ('orders', 'carts', 'shipping'):
            deployment.compose('stop', '-t', '30', role, timeout=45)
        for path in (out / 'cost-events').glob('*/events.jsonl'):
            events(path)
        result['status'] = 'business-passed'
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        deployment.diagnostics()
        log = (out / 'compose.log').read_text(errors='replace')
        result['frontend_errors'] = [line for line in log.splitlines() if any(marker in line for marker in
            ('TF2_COST error=', 'TF2_BOUNDARY error=', 'TF2_SERVICE_FRONTEND error=', 'TF2_MT_ADAPTER error'))]
        deployment.compose('down', '--volumes', '--remove-orphans', check=False, timeout=90)
        save(out / 'result.json', result)
    if result['frontend_errors']:
        raise ValueError('Frontend errors; inspect preserved run')
    if mode == 'flowdist':
        evaluation = {'mode': mode, 'cost': costs(out, result['cases']), 'field_accuracy': None,
                      'reason': 'Native statement queries are evaluated separately, never inferred from business or method events.',
                      'accuracy_eligible': False, 'performance_eligible': False}
    else:
        # ru_maxrss is cumulative for a process. A fresh worker prevents the
        # preceding deployments/analyses from contaminating offline memory.
        command=[sys.executable,str(HERE/'evaluate_five_methods.py'),'--run',str(out),'--out',str(out/'evaluation.json')]
        worker=subprocess.run(command,capture_output=True,text=True,timeout=120)
        (out/'offline-evaluation.log').write_text(worker.stdout+worker.stderr)
        if worker.returncode:raise ValueError('Isolated offline evaluator failed: '+mode)
        evaluation=json.loads((out/'evaluation.json').read_text())
        evaluation['offline_process_scope']='Fresh Python worker for this configuration; batch decoding/reconstruction/scoring, whole-worker peak RSS'
    save(out / 'evaluation.json', evaluation)
    return evaluation


def run(args):
    tool.verify_repository(args.repo.resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = {'methods': five.METHODS, 'warmup': args.warmup, 'repetitions': args.repetitions,
                'boundary_agent_sha256': digest(args.boundary), 'offline_cost_reported_separately': True,
                'runtime': 'Inclusive controller wall time, common observer loaded last; serial measurement targets',
                'memory': 'Whole service JVM RSS and separately process-wide/current-thread allocation deltas; KiB',
                'paper_numeric_reproduction': False, 'deployment_rounds_per_configuration': 1,
                'scope': 'Frozen five-controller scalar boundary calibrations; no full distributed path qualification'}
    save(out / 'protocol.json', protocol)
    reports = {mode: run_mode(args, mode, out / mode, protocol) for mode in args.modes}
    images = [{key: value['image'] for key, value in json.loads((out / mode / 'compose.lock.json').read_text())['services'].items()}
              for mode in reports]
    if any(image != images[0] for image in images):
        raise ValueError('Different cached images')
    rows = []
    for method in five.METHODS:
        row = {'method': method}
        for mode, report in reports.items():
            cost = report['cost'][method]
            row[mode] = {key: cost[key] for key in ('n', 'controller_ms', 'allocated_kB', 'resident_kB')}
            row[mode]['accuracy'] = report.get('accuracy', {}).get(method)
            if mode != 'plain' and 'plain' in reports:
                row[mode]['runtime_overhead_percent'] = 100 * (cost['controller_ms']['mean'] / reports['plain']['cost'][method]['controller_ms']['mean'] - 1)
        rows.append(row)
    save(out / 'comparison.json', {'kind': 'three-method-five-controller-pilot', 'methods': rows, 'protocol': protocol,
        'same_protocol_and_images': True, 'runs': {mode: str(out / mode) for mode in reports},
        'accuracy_eligible': False, 'performance_eligible': False,
        'limitations': ['One fixed-order deployment per configuration; no stable ranking claim.',
                       'FlowDist native statement results are separate and required before three-way field accuracy scoring.',
                       'Scalar boundary calibrations do not qualify complete cross-process paths or request-instance reconstruction.',
                       'Online costs exclude static preprocessing, offline reconstruction/query and shutdown serialization.',
                       'Tracing/retention models differ; RSS is whole JVM and allocation includes background activity.']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo', 'apps', 'orders', 'carts', 'shipping', 'boundary', 'tracefusion', 'mirrortaint', 'integration-adapter', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--modes', nargs='+', choices=('plain', 'flowdist', 'mirrortaint', 'tracefusion'),
                        default=['plain', 'flowdist', 'mirrortaint', 'tracefusion'])
    parser.add_argument('--warmup', type=int, default=5)
    parser.add_argument('--repetitions', type=int, default=20)
    parser.add_argument('--subnet', default='10.254.243.0/24')
    parser.add_argument('--ready-timeout', type=int, default=180)
    args = parser.parse_args()
    if args.warmup < 0 or args.repetitions < 1 or len(set(args.modes)) != len(args.modes):
        parser.error('Invalid workload or duplicate modes')
    run(args)
