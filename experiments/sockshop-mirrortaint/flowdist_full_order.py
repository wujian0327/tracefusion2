#!/usr/bin/env python3
"""Full original newOrder + Spring async HTTP + real RabbitMQ compatibility.

Use only cached, digest-locked images. Fresh project and volumes; pause its own
consumer to verify enqueue, then restart it to verify delivery. Shipment worker
processing is a separate, unverified stage. Not an accuracy experiment.
"""
import argparse
import copy
import hashlib
import json
import re
import secrets
import shutil
import time
from pathlib import Path

from host import ROOT, HERE, prepare, submit
from sockshop import Deployment, HEALTH_JS, save, check_spec
import flowdist_preflight as tool
from audit_flowdist_coverage import coverage


class CachedDeployment(Deployment):
    def start(self):
        self.command(['docker', 'version'])
        self.compose('config', '--quiet')
        spec = json.loads(self.file.read_text())
        images = {}
        for cfg in spec['services'].values():
            image = cfg['image']
            if image in images: continue
            inspected = json.loads(self.command(['docker', 'image', 'inspect', image]).stdout)[0]
            digests = inspected.get('RepoDigests') or []
            if not digests: raise ValueError('Cached image has no digest: ' + image)
            images[image] = {'id': inspected['Id'], 'digests': digests}
        locked = copy.deepcopy(spec)
        for cfg in locked['services'].values(): cfg['image'] = images[cfg['image']]['digests'][0]
        save(self.out / 'images.json', images)
        self.file = self.out / 'compose.lock.json'
        save(self.file, locked)
        self.compose('up', '-d', '--pull', 'never', timeout=180)
        deadline = time.monotonic() + self.args.ready_timeout
        while time.monotonic() < deadline:
            state = self.compose('ps', '--all', '--format', 'json').stdout
            for row in state.splitlines():
                if not row.strip(): continue
                parsed = json.loads(row)
                entries = parsed if isinstance(parsed, list) else [parsed]
                if any(e.get('State') in ('exited', 'dead') for e in entries):
                    raise RuntimeError('Original service exited during startup; inspect compose.log')
            startup=self.compose('logs','--no-color','--tail','250','orders','shipping').stdout
            if 'java.lang.VerifyError' in startup or 'APPLICATION FAILED TO START' in startup:
                raise RuntimeError('Java service failed during startup; inspect compose.log')
            status = self.compose('exec', '-T', 'front-end', 'node', '-e', HEALTH_JS, check=False, timeout=15)
            if status.returncode == 0:
                queues = self.queue_status()
                if queues.get('shipping-task', {}).get('consumers', 0) > 0:
                    save(self.out / 'readiness.json', {'health': status.stdout, 'queues': queues})
                    return
            print('Waiting for original services and RabbitMQ consumer...', flush=True)
            time.sleep(3)
        raise RuntimeError('Full deployment readiness timeout')

    def queue_status(self):
        result = self.compose('exec', '-T', 'rabbitmq', 'rabbitmqctl', 'list_queues',
            'name', 'messages_ready', 'messages_unacknowledged', 'consumers', timeout=30)
        queues = {}
        for line in result.stdout.splitlines():
            match = re.fullmatch(r'([^\s]+)\s+(\d+)\s+(\d+)\s+(\d+)', line.strip())
            if match:
                queues[match[1]] = dict(zip(('ready', 'unacknowledged', 'consumers'), map(int, match.groups()[1:])))
        return queues


def run(args):
    tool.verify_repository(args.repo.resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    build = args.apps.resolve()
    manifest = json.loads((build / 'manifest.json').read_text())
    if manifest['kind'] != 'sockshop-spring-flowdist-boundary-runtime' or manifest['upstream_commit'] != tool.COMMIT:
        raise ValueError('Unexpected build')
    spec = json.loads((ROOT / 'scenarios/sockshop/compose.json').read_text())
    check_spec(spec)
    spec['networks'] = {'default': {'ipam': {'config': [{'subnet': args.subnet}]}}}
    spec['services']['front-end']['ports'] = ['127.0.0.1:18580:8079']
    spec['services']['carts']['ports'] = ['127.0.0.1:18581:80']
    spec['services']['orders']['ports'] = ['127.0.0.1:18582:80']
    spec['services']['rabbitmq']['environment'] = {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS': '+S 2:2 +A 8'}
    for role in ('orders', 'shipping'):
        jar = build / (role + '-flowdist.jar')
        if hashlib.sha256(jar.read_bytes()).hexdigest() != manifest['apps'][role]['adapted_sha256']:
            raise ValueError('Adapted application digest mismatch')
        shutil.copyfile(jar, out / jar.name)
        capture = out / 'runtime' / role
        (capture / 'test1').mkdir(parents=True)
        capture.chmod(0o777)
        (capture / 'test1').chmod(0o777)
        if manifest.get('branch_models'):
            model=manifest['branch_models'][role]
            for key,filename in (('mapping','entitystmt.out.branch'),('statements','stmtids.out')):
                source=Path(model[key])
                if hashlib.sha256(source.read_bytes()).hexdigest()!=model[key+'_sha256']:
                    raise ValueError('Branch mapping/statement digest mismatch')
                shutil.copyfile(source,capture/filename)
        cfg = spec['services'][role]
        cfg.setdefault('volumes', []).extend([str(out / jar.name) + ':/tf2/app.jar:ro', str(capture) + ':/tf2/output:rw'])
        cfg['entrypoint'] = ['sh', '-c', 'cd /tf2/output && exec java $$JAVA_OPTS -jar /tf2/app.jar --port=80']
        cfg['environment']['JAVA_OPTS'] += ' -Dflowdist.http.peer=http://shipping/shipping -Dflowdist.audit=/tf2/output/spring-events.jsonl'
        if manifest.get('branch_models',{}).get(role,{}).get('author_method_instrumentation'):
            cfg['environment']['JAVA_OPTS']+=' -Dflowdist.method.instrumented=true'
    for cfg in spec['services'].values(): cfg['restart'] = 'no'
    file = out / 'compose.preflight.json'
    save(file, spec)
    args.project = args.project or 'tf2-flowdist-full-' + secrets.token_hex(5)
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.project): raise ValueError('Invalid Docker project name')
    deployment = CachedDeployment(args, out, file)
    # Verify ownership before entering the cleanup region: never tear down a
    # pre-existing user project if a supplied name collides.
    for command in (['docker', 'ps', '--all', '--quiet'], ['docker', 'network', 'ls', '--quiet'],
                    ['docker', 'volume', 'ls', '--quiet']):
        if deployment.command(command + ['--filter', 'label=com.docker.compose.project=' + args.project]).stdout.strip():
            raise ValueError('Fresh Docker project required')
    full_methods=all(manifest.get('branch_models',{}).get(role,{}).get('author_method_instrumentation')
        for role in ('orders','shipping'))
    status = {'kind': 'sockshop-flowdist-full-order-compatibility', 'project': args.project,
        'status': 'failed', 'boundary_method_hooks_only': not full_methods,
        'author_application_method_events':full_methods,'accuracy_eligible': False, 'performance_eligible': False}
    try:
        deployment.start()
        case = json.loads((HERE / 'cases.json').read_text())['cases'][0]
        fixture = prepare(case, 'single', out / 'single', 'http://127.0.0.1:18580', 'http://127.0.0.1:18581')
        deployment.compose('stop', '-t', '15', 'queue-master', timeout=30)
        baseline = deployment.queue_status()
        queue = baseline.get('shipping-task')
        if not queue or queue != {'ready': 0, 'unacknowledged': 0, 'consumers': 0}:
            raise ValueError('Fresh queue not empty with consumer paused')
        business = submit(fixture, 'http://127.0.0.1:18582', out / 'single')
        if not business['business_passed']: raise ValueError('Original newOrder business check failed')
        queued = deployment.queue_status()
        if queued.get('shipping-task') != {'ready': 1, 'unacknowledged': 0, 'consumers': 0}:
            raise ValueError('Expected exactly one real Shipping queue message')
        deployment.compose('start', 'queue-master', timeout=30)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            consumed = deployment.queue_status()
            if consumed.get('shipping-task') == {'ready': 0, 'unacknowledged': 0, 'consumers': 1}: break
            time.sleep(1)
        else: raise ValueError('Shipping consumer did not drain the real message')
        consumer_log = deployment.compose('logs', '--no-color', '--tail', '250', 'queue-master').stdout
        shipment = json.loads((out / 'single/order-response.json').read_text())['shipment']
        marker = 'Received shipment task: ' + shipment['name']
        if marker not in consumer_log:
            raise ValueError('Original consumer did not log this order Shipment identity')
        (out / 'queue-master-delivery.log').write_text(consumer_log)
        save(out / 'queue-proof.json', {'baseline': baseline, 'after_order': queued, 'after_consumer_restart': consumed,
            'isolated_fresh_project': True, 'single_target_order': True, 'broker_payload_read': False,
            'consumer_logged_shipment_name': shipment['name'], 'shipment_worker_processing_verified': False})
        # Author trace names use millisecond timestamps. Stop sequentially and
        # reject collisions so two simultaneous flushes cannot overwrite a PID.
        for role in ('orders', 'shipping'):
            deployment.compose('stop', '-t', '30', role, timeout=45)
        branch_reports={}
        if manifest.get('branch_models'):
            for role in ('orders','shipping'):
                home=out/'runtime'/role
                mapping=[set(map(int,row.split())) for row in (home/'entitystmt.out.branch').read_text().splitlines()]
                statements=(home/'stmtids.out').read_text().splitlines()
                branches,covered=coverage(home/'stmtCoverage1.out',mapping,len(statements))
                controller=' newOrder(' if role=='orders' else ' postShipping('
                if not any(controller in statements[i] for i in covered):
                    raise ValueError('Controller absent from actual branch coverage')
                branch_reports[role]={'branches_hit':len(branches),'branch_count':len(mapping),
                    'statements_hit':len(covered),'mapped_statements':len(statements)}
        events = {}
        for role in ('orders', 'shipping'):
            path = out / 'runtime' / role / 'spring-events.jsonl'
            events[role] = [json.loads(row) for row in path.read_text().splitlines()]
        order = [e for e in events['orders'] if e['phase'] == 'enter' and ' newOrder(' in e['method']]
        client = [e for e in events['orders'] if e['phase'] == 'enter' and ' postResource(' in e['method']]
        shipping = [e for e in events['shipping'] if e['phase'] == 'enter' and ' postShipping(' in e['method']]
        if len(order) != 1 or len(client) != 1 or len(shipping) != 1 or order[0]['thread_id'] == client[0]['thread_id']:
            raise ValueError('Missing original async worker/controller boundary events')
        work = out / 'work'
        traces = work / 'traces/test1'
        traces.mkdir(parents=True)
        for role in ('orders', 'shipping'):
            files = sorted((out / 'runtime' / role / 'test1').glob('Remote*.em'))
            if not files or (not full_methods and len(files)!=1):
                raise ValueError('Missing unique original process trace for ' + role)
            # Original method instrumentation flushes at Spring main return and
            # again at shutdown. Preserve both raw files; query final snapshot.
            selected=files[-1]
            target = traces / selected.name
            if target.exists(): raise ValueError('Author process trace filename collision; refusing to overwrite')
            shutil.copyfile(selected, target)
        inspection = tool.inspect_traces(args.repo.resolve(), out, client[0]['method'], shipping[0]['method'])
        if inspection['status'] != 'peer-correlation-validated': raise ValueError('Full HTTP process correlation failed')
        query = order[0]['method'] + '; ' + shipping[0]['method']
        tool.execute(args.repo.resolve(), out, 'method-query', ['-Xmx1g', '-ea', '-cp', tool.CP,
            'disttaint.OTAnalysisAll', query, '/work/traces', '/work', '', '-prec'])
        log = (out / 'method-query.log').read_text()
        length = re.search(r'\[The method path length\]: (\d+)', log)
        candidates = (work / 'methodList.out').read_text().splitlines()
        if not length or order[0]['method'] not in candidates or shipping[0]['method'] not in candidates:
            raise ValueError('Full order-to-shipping method candidate query missing')
        status.update(status='order-async-mq-delivery-and-peer-compatibility-passed', business=business,
            original_async_thread_verified=True, events=events, candidate_method_count=int(length[1]), query=query,
            queue_consumer_delivery_verified=True, shipment_worker_processing_verified=False)
        if branch_reports:status.update(actual_branch_coverage=branch_reports,statement_graph_verified=False)
    finally:
        deployment.diagnostics()
        log = (out / 'compose.log').read_text()
        status['queue_master_docker_worker_error_observed'] = 'AFUNIXSocketException' in log and '/var/run/docker.sock' in log
        deployment.compose('down', '--volumes', '--remove-orphans', check=False, timeout=90)
        save(out / 'result.json', status)
    print(status['status'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo', 'apps', 'out'): p.add_argument('--' + flag, type=Path, required=True)
    p.add_argument('--project'); p.add_argument('--ready-timeout', type=int, default=180)
    p.add_argument('--subnet', default='10.254.243.0/24')
    args = p.parse_args()
    run(args)
