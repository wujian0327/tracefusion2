#!/usr/bin/env python3
"""Rate-controlled, independently deployed Sock Shop cost comparison (stdlib only).

The measurement unit is POST /orders. Fixtures are prepared before warmup.
Answers are produced offline after graceful collector shutdown; freshness includes
the remaining batch window and shutdown, and is not a streaming latency claim.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import http.client
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import secrets
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from run_distributed_paths import check, observed
from run_planned_service import ROOT, HERE, load, save, sha
from experiment_environment import pin_images
from host import prepare, submit
from flowdist_full_order import CachedDeployment
from sockshop import Client, validate_payload

ROLES = ('orders', 'carts', 'shipping')
JVM = '-Xms64m -Xmx256m -XX:+UseG1GC -Djava.security.egd=file:/dev/urandom -Dspring.zipkin.enabled=false'


def percentiles(values):
    """Nearest-rank percentiles; no interpolation or pooling between trials."""
    values = sorted(values)
    return {f'p{p}': values[max(0, math.ceil(len(values)*p/100)-1)] if values else None
            for p in (50, 95, 99)}


class MeasuredClient(Client):
    def request(self, method, url, body=None, label='request', redact=False):
        if label != 'target-order':
            return super().request(method, url, body, label, redact)
        request = urllib.request.Request(url, data=json.dumps(body).encode(), method=method,
                                        headers={'Content-Type': 'application/json', **self.headers})
        self.online_start_ns = time.monotonic_ns()
        try:
            try:
                with self.opener.open(request, timeout=20) as response:
                    status, raw = response.status, response.read()
            except urllib.error.HTTPError as exc:
                status, raw = exc.code, exc.read()
        finally:
            self.online_end_ns = time.monotonic_ns()
        result = json.loads(raw)
        self.events.append({'label': label, 'method': method, 'url': url,
                            'status': status, 'request': body, 'response': result})
        save(self.out/'http-client-observations.json', self.events)
        return validate_payload(status, result)


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=10)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def docker_get(path):
    host = os.environ.get('DOCKER_HOST')
    if not host:
        context = json.loads(subprocess.check_output(['docker', 'context', 'inspect']))[0]
        host = context['Endpoints']['docker']['Host']
    if not host.startswith('unix://'):
        raise ValueError('Resource sampler requires a local Unix Docker socket: '+host)
    connection = UnixHTTP(host[7:])
    try:
        connection.request('GET', '/v1.41'+path)
        response = connection.getresponse()
        raw = response.read()
        if response.status != 200:
            raise RuntimeError(f'Docker API {response.status}: {raw[:300]!r}')
        return json.loads(raw)
    finally:
        connection.close()


def resource_snapshot(containers):
    rows = {}
    for role, ident in containers.items():
        stats = docker_get('/containers/'+ident+'/stats?stream=false&one-shot=true')
        cpu_time = time.monotonic_ns()
        # Docker top invokes host ps, without injecting a sampler into the service.
        top = docker_get('/containers/'+ident+'/top?'+urllib.parse.urlencode({'ps_args': '-eo pid,rss,comm'}))
        column = top['Titles'].index('RSS')
        rows[role] = {'monotonic_ns': cpu_time,
                      'cpu_ns': stats['cpu_stats']['cpu_usage']['total_usage'],
                      'rss_bytes': sum(int(p[column])*1024 for p in top['Processes']),
                      'container_memory_bytes': stats['memory_stats'].get('usage'),
                      'raw_stats': stats, 'raw_top': top}
    return rows


class Sampler:
    def __init__(self, containers, interval, path, observed_roles=None):
        self.containers, self.interval, self.path = containers, interval, path
        self.observed_roles = tuple(observed_roles) if observed_roles is not None else ROLES
        self.stop = threading.Event()
        self.rows, self.errors = [], []

    def sample(self):
        try:
            row = resource_snapshot(self.containers)
            self.rows.append(row)
            with self.path.open('a') as file:
                file.write(json.dumps(row)+'\n')
        except Exception as exc:
            self.errors.append(str(exc))

    def loop(self):
        while not self.stop.wait(self.interval):
            self.sample()

    def __enter__(self):
        self.sample()
        if self.errors:
            raise RuntimeError('Resource sampler failed: '+str(self.errors))
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=60)
        if self.thread.is_alive():
            raise RuntimeError('Resource sampler did not terminate')
        self.sample()

    def summary(self, start, end):
        result = {}
        for role in self.containers:
            rows = [r[role] for r in self.rows if start <= r[role]['monotonic_ns'] <= end]
            if len(rows) < 2:
                raise ValueError('Insufficient steady-state samples for '+role)
            if any(b['cpu_ns']<a['cpu_ns'] for a,b in zip(rows,rows[1:])):
                raise ValueError('Container CPU counter reset: '+role)
            cpu = (rows[-1]['cpu_ns']-rows[0]['cpu_ns'])/(rows[-1]['monotonic_ns']-rows[0]['monotonic_ns'])*100
            result[role] = {'samples': len(rows), 'cpu_one_core_percent_mean': cpu,
                            'rss_bytes_mean': statistics.mean(r['rss_bytes'] for r in rows),
                            'rss_bytes_peak': max(r['rss_bytes'] for r in rows)}
        for group, members in [('observed_jvms', self.observed_roles), ('deployment', self.containers)]:
            snapshots = [r for r in self.rows if all(start <= r[m]['monotonic_ns'] <= end for m in members)]
            if len(snapshots) < 2:
                raise ValueError('Insufficient aligned resource snapshots')
            result[group] = {
                'cpu_one_core_percent_mean': sum(result[m]['cpu_one_core_percent_mean'] for m in members),
                'rss_bytes_mean': statistics.mean(sum(r[m]['rss_bytes'] for m in members) for r in snapshots),
                'rss_bytes_peak': max(sum(r[m]['rss_bytes'] for m in members) for r in snapshots)}
        if self.errors:
            raise ValueError('Resource sampling errors: '+str(self.errors))
        return result


def spec_for(mode, dest, build, cpu, memory):
    spec = pin_images(load(ROOT/'scenarios/sockshop/compose.json'), 'sockshop')
    spec['networks'] = {'default': {'ipam': {'config': [{'subnet': '10.254.249.0/24'}]}}}
    for config in spec['services'].values():
        config.update(restart='no', cpus=cpu, mem_limit=memory)
    for role, port in [('front-end', 18580), ('carts', 18581), ('orders', 18582), ('shipping', 18583)]:
        spec['services'][role]['ports'] = [f'127.0.0.1:{port}:{8079 if role=="front-end" else 80}']
    spec['services']['rabbitmq']['environment'] = {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS': '+S 2:2 +A 8'}
    for role in ROLES:
        config = spec['services'][role]
        if mode == 'tracefusion':
            observed(spec, role, role, dest, build)
        else:
            config.setdefault('volumes', []).append(str(build/role/'original.jar')+':/tf2/app.jar:ro')
            config['entrypoint'] = ['sh', '-c', 'exec java $$JAVA_OPTS -jar /tf2/app.jar']
        config['entrypoint'][2] += ' --port=80'
        suffix = (' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json'
                  ' -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode=selective') if mode=='tracefusion' else ''
        config.setdefault('environment', {})['JAVA_OPTS'] = JVM+suffix
    spec['services']['queue-master']['environment']['JAVA_OPTS'] = JVM
    return spec


def log_position(dest):
    result = {}
    for role in ROLES:
        result[role]={'events':0,'bytes':0}
        for path in (dest/role).rglob('*'):
            if path.is_file():
                result[role]['bytes']+=path.stat().st_size
                if path.suffix=='.jsonl':
                    with path.open('rb') as file:result[role]['events']+=sum(1 for _ in file)
    return result


def phase(prepared, duration, rate, concurrency, dest, allow_errors=False):
    start = time.monotonic_ns()
    records = []

    def issue(index, item):
        name = item[-1]['case']
        client = item[1]
        scheduled = start+round(index/rate*1e9)
        result = submit(item, 'http://127.0.0.1:18582', dest/name)
        result.update(message=item[-1]['message'], scheduled_ns=scheduled,
                      online_start_ns=getattr(client, 'online_start_ns', None),
                      online_end_ns=getattr(client, 'online_end_ns', None))
        result['http_status']=client.events[-1].get('status') if client.events and client.events[-1].get('label')=='target-order' else None
        save(dest/name/'cost-request.json', result)
        return result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = []
        for index, item in enumerate(prepared):
            delay = (start+round(index/rate*1e9)-time.monotonic_ns())/1e9
            if delay > 0:
                time.sleep(delay)
            futures.append(pool.submit(issue, index, item))
        remaining = (start+round(duration*1e9)-time.monotonic_ns())/1e9
        if remaining > 0:
            time.sleep(remaining)
        for future in futures:
            records.append(future.result())
    end = time.monotonic_ns()
    if not allow_errors and not all(r['business_passed'] for r in records):
        raise ValueError('Business oracle failed; inspect cost-request.json')
    return {'start_ns': start, 'scheduled_end_ns': start+round(duration*1e9),
            'drain_end_ns': end, 'requests': records}


def offline(trial, build):
    from infer_distributed_fields import Reconstruction
    from evaluate_distributed_paths import sockshop
    started = time.monotonic_ns()
    graph = Reconstruction(build, trial/'sockshop', list(ROLES))
    built = time.monotonic_ns()
    report = sockshop(trial, build, graph=graph)
    ready = time.monotonic_ns()
    summary = report['summary']
    background = {}
    for node in graph.nodes.values():
        if node.get('unknown'):
            field = node.get('field', '<unknown>')
            background[field] = background.get(field, 0)+1
    save(trial/'offline.json', {'graph_build_seconds': (built-started)/1e9,
                               'restore_score_export_seconds': (ready-started)/1e9,
                               'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                               'answers_ready_ns': ready, 'summary': summary,
                               'background_unknown': background})
    if summary['exact'] != summary['queries'] or summary['fp'] or summary['fn'] or summary['unknown']:
        raise ValueError('Provenance correctness failed')


def trial_run(args, trial, mode, build):
    trial.mkdir()
    if hasattr(args,'observation_policy'):
        save(trial/'observation-policy.json',{'policy':args.observation_policy})
    dest = trial/'sockshop'
    dest.mkdir()
    common=getattr(args,'query_scope','paths')=='total'
    if common:
        from calibrate_mirrortaint_total import common_spec
        spec=common_spec(mode,dest,build,args.mt_bundle,args.cpus,args.memory,
                         observation_policy=getattr(args,'observation_policy','selective'))
    else:spec = spec_for(mode, dest, build, args.cpus, args.memory)
    save(dest/'compose.json', spec)
    project = 'tf2-cost-'+secrets.token_hex(6)
    dep = CachedDeployment(argparse.Namespace(project=project, ready_timeout=240), dest, dest/'compose.json')
    result = {'status': 'failed', 'mode': mode, 'project': project, 'cases': []}
    save(dest/'run.json', result)
    try:
        dep.start()
        inspected = json.loads(dep.command(['docker', 'inspect', *dep.compose('ps', '-q').stdout.split()]).stdout)
        save(dest/'containers.json', inspected)
        containers = {i['Config']['Labels']['com.docker.compose.service']: i['Id'] for i in inspected}
        # Verify actual limits, not just requested Compose settings.
        for entry in inspected:
            if entry['HostConfig']['Memory'] <= 0 or entry['HostConfig']['NanoCpus'] != round(args.cpus*1e9):
                raise ValueError('Docker resource limits were not applied')
        save(dest/'jvm-versions.json', {role: dep.compose('exec', '-T', role, 'java', '-version').stdout for role in ROLES})
        template = load(args.correctness/'cases.json')['sockshop']
        template = [c for c in template if c['expected_target']]
        phases = {}
        for label, duration in [('warmup', args.warmup), ('steady', args.seconds)]:
            phases[label] = []
            trace = secrets.token_hex(16)
            for i in range(round(duration*args.rate)):
                name = f'{label}-{i:05d}'
                prepared = list(prepare(template[i % len(template)], name, dest/name,
                                        'http://127.0.0.1:18580', 'http://127.0.0.1:18581'))
                old = prepared[1]
                client = MeasuredClient(old.out)
                client.opener, client.events = old.opener, old.events
                span = secrets.token_hex(8)
                client.headers = {'traceparent': f'00-{trace}-{span}-01', 'tracestate': 'research=cost'}
                prepared[1] = client
                prepared[-1]['message'] = trace+'/'+span
                save(dest/name/'query-contract.json', prepared[-1])
                phases[label].append(prepared)
        warmup = phase(phases['warmup'], args.warmup, args.rate, args.concurrency, dest, args.allow_errors)
        save(trial/'warmup.json', warmup)
        before = log_position(dest)
        with Sampler(containers, args.sample_interval, trial/'resources.jsonl') as sampler:
            steady = phase(phases['steady'], args.seconds, args.rate, args.concurrency, dest, args.allow_errors)
        after = log_position(dest)
        save(trial/'capture-window.json',{'before':before,'after':after,'start_ns':steady['start_ns'],'scheduled_end_ns':steady['scheduled_end_ns'],'drain_end_ns':steady['drain_end_ns']})
        save(trial/'steady.json', steady)
        result['cases'] = [load(dest/p[-1]['case']/'cost-request.json')
                           for label in ('warmup', 'steady') for p in phases[label]]
        result['status'] = 'business-passed'
        save(dest/'run.json', result)
        resource_summary = sampler.summary(steady['start_ns'], steady['scheduled_end_ns'])
        # Stop only these three JVMs so every capture has its shutdown metrics.
        shutdown_started_ns=time.monotonic_ns()
        for role in ROLES:
            dep.compose('stop', '-t', '20', role, timeout=40)
        capture_closed_ns=time.monotonic_ns()
        save(trial/'result-timeline.json',{'steady_start_ns':steady['start_ns'],
            'steady_scheduled_end_ns':steady['scheduled_end_ns'],'steady_drain_end_ns':steady['drain_end_ns'],
            'shutdown_started_ns':shutdown_started_ns,'capture_closed_upper_bound_ns':capture_closed_ns,
            'scope':'Host CLOCK_MONOTONIC. Per-response completion in steady.json. Capture closed is a conservative upper bound for raw result durability, not the first native tag availability. Target-field creation is not separately timestamped.'})
        offline_result = None
        if mode in ('tracefusion','mirrortaint'):
            command = [sys.executable, str(getattr(args,'offline_program',Path(__file__).resolve())), 'offline', '--out', str(trial), '--build', str(build)]
            if common:command+=['--query-scope','total','--mode',mode]
            if args.allow_errors:command+=['--allow-errors']
            started = time.monotonic_ns()
            completed = subprocess.run(command, capture_output=True, text=True, timeout=args.offline_timeout)
            (trial/'offline.log').write_text(completed.stdout+completed.stderr)
            save(trial/'offline-command.json', {'command': command, 'returncode': completed.returncode})
            if completed.returncode:
                raise ValueError('Offline provenance check failed; inspect offline.log')
            offline_result = load(trial/'offline.json')
            offline_result['subprocess_wall_seconds'] = (time.monotonic_ns()-started)/1e9
        records = steady['requests']
        successful=[r for r in records if r['business_passed']]
        completed_in_window = [r for r in successful if r['online_end_ns'] <= steady['scheduled_end_ns']]
        latency = [(r['online_end_ns']-r['online_start_ns'])/1e6 for r in successful]
        offered_latency = [(r['online_end_ns']-r['scheduled_ns'])/1e6 for r in successful]
        freshness = None if offline_result is None or not successful else percentiles(
            [(offline_result['answers_ready_ns']-r['online_end_ns'])/1e9 for r in successful])
        if offline_result is not None:
            with (trial/'answer-readiness.jsonl').open('w') as file:
                for record in records:
                    file.write(json.dumps({'case': record['case'], 'response_complete_ns': record['online_end_ns'],
                                           'batch_answers_ready_ns': offline_result['answers_ready_ns'],
                                           'answer_status':'available' if record['business_passed'] else 'N/A: business request failed',
                                           'delay_seconds': (offline_result['answers_ready_ns']-record['online_end_ns'])/1e9 if record['business_passed'] else None})+'\n')
        events = {role: {key: after[role][key]-before[role][key] for key in ('events', 'bytes')} for role in ROLES}
        console = dep.compose('logs', '--no-color', timeout=90).stdout
        (trial/'container-console.log').write_text(console)
        provenance_passed=offline_result is None or offline_result['summary']['exact']==offline_result['summary']['queries'] and not offline_result['summary']['unknown']
        metrics = {'mode': mode, 'status': 'passed' if provenance_passed else 'provenance-failed', 'steady_requests': len(records),
                   'successful_requests':len(successful),'failed_requests':len(records)-len(successful),
                   'error_rate':1-len(successful)/len(records),'offered_rate_rps':args.rate,
                   'http_status_counts':{str(s):sum(r['http_status']==s for r in records) for s in {r['http_status'] for r in records}},
                   'completed_within_window': len(completed_in_window),
                   'throughput_rps': len(completed_in_window)/args.seconds,
                   'drained_throughput_rps': len(successful)/((steady['drain_end_ns']-steady['start_ns'])/1e9),
                   'online_latency_ms': percentiles(latency), 'scheduled_to_response_ms': percentiles(offered_latency),
                   'max_dispatch_lag_ms': max((r['online_start_ns']-r['scheduled_ns'])/1e6 for r in records),
                   'resources': resource_summary, 'steady_capture': events,
                   'total_capture': log_position(dest), 'container_console_bytes': len(console.encode()),
                   'offline': offline_result, 'completion_to_batch_answers_seconds': freshness,
                   'provenance_status': ('passed' if provenance_passed else 'failed/unknown') if offline_result else 'N/A: original services emit no field provenance'}
        save(trial/'metrics.json', metrics)
        print(trial.name, mode, metrics['status'], flush=True)
        return metrics
    except BaseException as exc:
        save(trial/'failure.json', {'error': str(exc), 'mode': mode, 'project': project})
        raise
    finally:
        dep.diagnostics()
        cleaned = dep.compose('down', '--volumes', '--remove-orphans', timeout=120, check=False)
        save(trial/'cleanup.json', {'returncode': cleaned.returncode, 'project': project})
        if cleaned.returncode:
            raise RuntimeError('Experiment cleanup failed for '+project)


def environment(out):
    commands = [['uname', '-a'], ['lscpu'], ['free', '-b'], ['df', '-h', str(out)],
                ['docker', 'version'], ['docker', 'compose', 'version'], ['docker', 'info'],
                ['java', '-version'], ['javac', '-version'], ['git', 'rev-parse', 'HEAD'],
                ['docker', 'ps', '--no-trunc']]
    records = []
    for command in commands:
        r = subprocess.run(command, capture_output=True, text=True, timeout=30)
        records.append({'command': command, 'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
    save(out/'environment.json', {'platform': platform.platform(), 'python': sys.version,
                                 'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                                 'commands': records})


def report(out):
    config = load(out/'config.json')
    state = load(out/'run-status.json') if (out/'run-status.json').exists() else {'status': 'unknown'}
    rows = []
    for name, mode in config['order']:
        path = out/name/'metrics.json'
        rows.append({'trial': name, 'mode': mode, **load(path)} if path.exists()
                    else {'trial': name, 'mode': mode, 'status': 'N/A: not completed'})
    summaries = {}
    modes=config.get('modes',['original','tracefusion'])
    for mode in modes:
        valid = [r for r in rows if r['mode']==mode and r['status']=='passed']
        if not valid:
            summaries[mode] = None
            continue
        metrics = {'throughput_rps': [r['throughput_rps'] for r in valid]}
        metrics['error_rate']=[r.get('error_rate',0) for r in valid]
        for p in ('p50', 'p95', 'p99'):
            values=[r['online_latency_ms'][p] for r in valid if r['online_latency_ms'][p] is not None]
            if values:metrics['latency_ms_'+p]=values
        summaries[mode] = {'trials': len(valid), 'metrics': {
            k: {'median': statistics.median(v), 'min': min(v), 'max': max(v),
                'cv': statistics.stdev(v)/statistics.mean(v) if len(v)>1 and statistics.mean(v) else None}
            for k, v in metrics.items()}}
    summary = {'rows': rows, 'summary': summaries, 'mirrortaint': 'measured: disclosed native agent plus adapters' if 'mirrortaint' in modes else 'N/A: common query contract and adapter not qualified',
               'run_status': state,
               'performance_eligible': state['status']=='passed' and all(r['status']=='passed' for r in rows) and config['rounds']>=5,
               'scope': 'Selected Sock Shop HTTP/JSON paths; fixed offered rate, not saturation throughput.'}
    paired = []
    for round_index in range(config['rounds']):
        pair = {r['mode']: r for r in rows if r['trial'].startswith(f'round-{round_index+1:02d}-') and r['status']=='passed'}
        if not {'original','tracefusion'}<=pair.keys():
            continue
        paired.append({'round': round_index+1, **{
            'latency_'+p+'_overhead_percent': (pair['tracefusion']['online_latency_ms'][p]/pair['original']['online_latency_ms'][p]-1)*100
            for p in ('p50', 'p95', 'p99')}})
    summary['paired_latency_overhead_percent'] = paired
    method_ratios=[]
    for round_index in range(config['rounds']):
        pair={r['mode']:r for r in rows if r['trial'].startswith(f'round-{round_index+1:02d}-') and r['status']=='passed'}
        if not {'tracefusion','mirrortaint'}<=pair.keys():continue
        tf,mt=pair['tracefusion'],pair['mirrortaint']
        ratio={'round':round_index+1}
        for p in ('p50','p95','p99'):
            if mt['online_latency_ms'][p]:ratio['latency_'+p]=tf['online_latency_ms'][p]/mt['online_latency_ms'][p]
        for key in ('cpu_one_core_percent_mean','rss_bytes_mean'):
            ratio[key]=tf['resources']['observed_jvms'][key]/mt['resources']['observed_jvms'][key]
        for key in ('events','bytes'):
            denominator=sum(x[key] for x in mt['steady_capture'].values())
            if denominator:ratio['capture_'+key]=sum(x[key] for x in tf['steady_capture'].values())/denominator
        for key in ('restore_score_export_seconds','subprocess_wall_seconds','peak_rss_bytes'):
            ratio['offline_'+key]=tf['offline'][key]/mt['offline'][key]
        method_ratios.append(ratio)
    summary['tracefusion_to_mirrortaint_ratios']=method_ratios
    save(out/'comparison.json', summary)
    lines = ['# Sock Shop 成本实验', '',
             '测量单位为原版 POST /orders；固定输入模板，预先准备独立购物车。每个配置每轮重新部署并创建新数据卷。', '',
             f"运行状态：{state['status']}；正式成本资格：{'满足' if summary['performance_eligible'] else '未满足（至少五轮且整次运行通过）'}。", '',
             f"预热 {config['warmup']} 秒；稳态 {config['seconds']} 秒；到达率 {config['rate']} 请求/秒；最大并发 {config['concurrency']}；{config['rounds']} 轮；顺序种子 {config['seed']}。", '',
             '| 轮次 | 配置 | 状态 | 成功请求 p50 / p95 / p99 (ms) | 窗内成功吞吐 (req/s) | 错误率 |',
             '| --- | --- | --- | --- | --- | --- |']
    for r in rows:
        latency = 'N/A' if r['status']!='passed' or r['online_latency_ms']['p50'] is None else ' / '.join(f'{r["online_latency_ms"][p]:.3f}' for p in ('p50','p95','p99'))
        throughput = 'N/A' if r['status']!='passed' else f'{r["throughput_rps"]:.3f}'
        error='N/A' if r['status']!='passed' else f'{r.get("error_rate",0)*100:.2f}%'
        lines.append(f'| {r["trial"]} | {r["mode"]} | {r["status"]} | {latency} | {throughput} | {error} |')
    lines += ['', '| 轮次 | 三个业务 JVM CPU 单核 % | JVM RSS 均值 / 峰值 MiB | 采集增量事件 / 字节（含排空） | 离线图还原或标签解码 / 评分导出总秒 / 进程墙时 | 离线峰值 MiB | 答案延迟 p50 / p95 / p99 秒 |',
              '| --- | ---: | --- | --- | --- | ---: | --- |']
    for r in rows:
        if r['status']!='passed':
            lines.append(f'| {r["trial"]} | N/A | N/A | N/A | N/A | N/A | N/A |')
            continue
        res = r['resources']['observed_jvms']
        events = sum(e['events'] for e in r['steady_capture'].values())
        size = sum(e['bytes'] for e in r['steady_capture'].values())
        off = r['offline']
        off_time = 'N/A' if off is None else f'{off["graph_build_seconds"]:.3f} / {off["restore_score_export_seconds"]:.3f} / {off["subprocess_wall_seconds"]:.3f}'
        peak = 'N/A' if off is None else f'{off["peak_rss_bytes"]/2**20:.2f}'
        fresh = 'N/A' if off is None or r['completion_to_batch_answers_seconds'] is None else ' / '.join(f'{r["completion_to_batch_answers_seconds"][p]:.3f}' for p in ('p50','p95','p99'))
        lines.append(f'| {r["trial"]} | {res["cpu_one_core_percent_mean"]:.2f} | {res["rss_bytes_mean"]/2**20:.2f} / {res["rss_bytes_peak"]/2**20:.2f} | {events} / {size} | {off_time} | {peak} | {fresh} |')
    if paired:
        lines += ['', '同轮 TraceFusion 相对原版的在线延迟开销（各轮比值的中位数）：'+
                  '；'.join(p+' '+f'{statistics.median(r["latency_"+p+"_overhead_percent"] for r in paired):.2f}%'
                           for p in ('p50','p95','p99'))+'。']
    if method_ratios:
        lines+=['','TraceFusion / MirrorTaint＋披露适配器：各同轮成本比值的中位数，低于1表示该项更低；不合并为未定义的总成本。','',
                '| 成本项 | TF / MT |','| --- | ---: |']
        for key in sorted(set().union(*(r.keys() for r in method_ratios))-{'round'}):
            values=[r[key] for r in method_ratios if key in r]
            lines.append(f'| {key} | {statistics.median(values):.4f} |')
    lines += ['', '| 轮次 | 指定字段 exact / queries | TP / FP / FN | 目标 unknown | 背景 unknown |',
              '| --- | --- | --- | ---: | ---: |']
    for r in rows:
        if r['status']=='passed' and r['offline'] is not None:
            s = r['offline']['summary']
            unknown = 'N/A（未枚举）' if r['mode']=='mirrortaint' else sum(r['offline']['background_unknown'].values())
            lines.append(f'| {r["trial"]} | {s["exact"]} / {s["queries"]} | {s["tp"]} / {s["fp"]} / {s["fn"]} | {s["unknown"]} | {unknown} |')
    lines += ['', 'CPU 为单核百分比；RSS 是 Docker top 中容器所有进程 RSS 之和，包含共享页重复计数，不能解释为每请求分配。原始 Docker stats/top 在各轮 resources.jsonl。', '',
              '在线延迟从客户端开始 HTTP 调用到响应体读取完成；另保存计划到达至响应的延迟与调度滞后，避免负载不足被隐藏。吞吐为稳态窗口内完成数除以窗口长度，另列排空吞吐。固定到达率不测系统最大吞吐。', '',
              '结构化事件数计入采集目录所有 JSONL；字节计入采集目录全部文件（含 MirrorTaint 原生日志和类转储），分别保存请求批次采集增量和部署总量。增量包含排空与采样边界，过载时不能直接除以计划窗口解释成稳态字节/秒；窗口见 capture-window.json。容器控制台日志另存。预热和准备流量不计入在线分位数。', '',
              '离线图构建时间与还原、评分、证据导出总时间分别报告；峰值内存为独立 Python 子进程 ru_maxrss。答案新鲜度按整批答案写出时刻减去每次响应完成时刻，包含剩余采样窗口和采集器关闭，不能解释为流式逐请求延迟。', '',
              '原版服务来源答案及离线代价为 N/A；业务响应逐请求核验。观测配置对预热和稳态的成功请求独立评分，失败请求计入错误率并不伪造来源答案。保留 field-results.json、原始事件和 unknown。其他未运行查询和外部基线为 N/A。', '',
              '完整逐轮 CPU、RSS、事件数、字节、离线及答案延迟见 comparison.json。跨轮分别报告分位数中位数、范围和变异系数，不合并请求伪装为独立部署样本。不引用旧机器开销值。环境记录中的其他运行中容器可能造成主机争用，独立配置顺序已随机化。', '',
              '配置及输入/源码哈希：config.json；机器环境：environment.json；命令：command.json 和各轮 sockshop/commands.log；失败：failure.json；清理：cleanup.json。', '']
    if config.get('query_scope')=='total':
        lines+=['本轮共同查询仅为 Carts 实际序列化响应字段到 Orders.total。Shipping 未安装观测器；MirrorTaint 只在 Orders 加载原版传播核心，Carts 和 Orders 额外安装披露的 HTTP 实例绑定探针。探针不计算业务依赖，原版标签决定来源。对象/字段/应用写计数及具体调用 span 均须匹配；反射和数据库内部写历史不在边界内。', '']
        profile=config.get('mt_output_profile',{'diagnostics':'default','label_format':'native-history'})
        lines+=['MirrorTaint 使用固定公开 JAR＋披露的 receiver、来源、字符串、stream、thread、日志和通信绑定适配器。本轮导出配置为 '+json.dumps(profile,ensure_ascii=False)+'。这是当前配置的比较，不代表 MirrorTaint 调优后的最低成本；结构化事件格式和原生标签表示不同，不能从跨工具事件数或日志量直接归因于少采。严格观测消融另行报告。', '',
                'MT 未枚举未查询字段的图注记，背景 unknown 为 N/A；TF 保留的背景 Item.id unknown 不属于本轮 total 目标。返回 Item、Shipment 和 Train Ticket 的 MT 查询均为 N/A。', '']
    (out/'results.md').write_text('\n'.join(lines))


def run(args):
    args.build, args.out, args.correctness = args.build.resolve(), args.out.resolve(), args.correctness.resolve()
    check(args.correctness, args.build)
    for application, queries in [('sockshop', 198), ('trainticket', 31)]:
        scored = load(args.correctness/application/'field-results.json')['summary']
        if scored['exact']!=queries or scored['queries']!=queries or scored['fp'] or scored['fn'] or scored['unknown']:
            raise ValueError('Desktop correctness acceptance required before cost experiment')
    for filename in ('algorithm-audit.json', 'protocol-checks.json'):
        if not load(args.correctness/filename)['all_passed']:
            raise ValueError('Desktop acceptance failed: '+filename)
    if not load(args.correctness/'original-image-verification.json')['all_matched']:
        raise ValueError('Original image verification required')
    if getattr(args,'acceptance',None):
        from audit_current_acceptance import verify
        verify(args.acceptance.resolve(),args.correctness,args.build)
    elif not load(args.correctness/'w3c-comparison.json')['all_passed']:
        raise ValueError('Legacy W3C comparison failed; use --acceptance for a current audit receipt')
    if args.query_scope=='total':
        import mirrortaint_instances as mt
        args.mt_bundle=args.mt_bundle.resolve();mt.verify(args.mt_bundle)
        for path in (args.mt_calibration,args.tf_calibration):
            receipt=load(path/'calibration.json')
            if not receipt['passed'] or receipt['summary']['queries']!=24:raise ValueError('Common total calibration required')
            if receipt.get('bundle_sha256')!=sha(args.mt_bundle/'build.json') or receipt.get('evaluator_sha256')!=sha(HERE/'mirrortaint_instances.py'):
                raise ValueError('Calibration does not match the frozen adapter/evaluator')
            if receipt.get('build_sha256')!=sha(args.build/'build.json') or receipt.get('cases_sha256')!=sha(args.correctness/'cases.json'):
                raise ValueError('Calibration application/input contract differs')
        if not load(args.mt_calibration/'instance-audit.json')['all_passed']:raise ValueError('Native instance controls required')
    if 'mirrortaint' in args.modes and args.query_scope!='total':raise ValueError('MirrorTaint is qualified only for common total queries')
    args.out.mkdir(parents=True, exist_ok=False)
    environment(args.out)
    rng = random.Random(args.seed)
    order = []
    for round_index in range(args.rounds):
        modes = list(args.modes)
        rng.shuffle(modes)
        order += [(f'round-{round_index+1:02d}-{i+1}-{m}', m) for i, m in enumerate(modes)]
    config = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    config.update(order=order, jvm=JVM, source_sha256={str(p.relative_to(ROOT)): sha(p)
                  for p in [*HERE.glob('*.py'), ROOT/'scripts/sockshop.py']}, build_sha256=sha(args.build/'build.json'),
                  cases_sha256=sha(args.correctness/'cases.json'),
                  images_sha256=sha(ROOT/'artifacts/desktop-inputs/images-lock.json'))
    if args.query_scope=='total':
        bundle_contract=load(args.mt_bundle/'build.json')
        config['mt_output_profile']={k:bundle_contract.get(k,'default' if k=='diagnostics' else 'native-history') for k in ('diagnostics','label_format')}
        config['mt_output_profile']['export_target']=bundle_contract.get('export_target')
        config['mt_bundle_sha256']=sha(args.mt_bundle/'build.json')
    save(args.out/'config.json', config)
    templates = [c for c in load(args.correctness/'cases.json')['sockshop'] if c['expected_target']]
    save(args.out/'workload.json', {'templates': templates,
                                  'warmup_template_indices': [i % len(templates) for i in range(round(args.warmup*args.rate))],
                                  'steady_template_indices': [i % len(templates) for i in range(round(args.seconds*args.rate))],
                                  'queries': 'Carts response fields -> Orders.total' if args.query_scope=='total' else 'Carts response fields -> Orders.total/returned item fields; Orders outbound Shipment -> returned Shipment'})
    save(args.out/'command.json', {'argv': [sys.executable, *sys.argv], 'cwd': str(Path.cwd())})
    save(args.out/'run-status.json', {'status': 'running'})
    def verify_sources():
        for source, expected in config['source_sha256'].items():
            if sha(ROOT/source)!=expected:
                raise ValueError('Frozen cost experiment source changed: '+source)
        if args.query_scope=='total':
            import mirrortaint_instances as mt
            mt.verify(args.mt_bundle)
    try:
        for name, mode in order:
            check(args.correctness, args.build)
            verify_sources()
            trial_run(args, args.out/name, mode, args.build)
            verify_sources()
            report(args.out)
        save(args.out/'run-status.json', {'status': 'passed'})
    except BaseException as exc:
        save(args.out/'run-status.json', {'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)})
        raise
    finally:
        report(args.out)
    manifest = {str(p.relative_to(args.out)): sha(p) for p in sorted(args.out.rglob('*')) if p.is_file()}
    save(args.out/'evidence-sha256.json', manifest)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('run', 'offline', 'report'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--build', type=Path)
    p.add_argument('--correctness', type=Path)
    p.add_argument('--acceptance',type=Path,help='Current two-application audit directory; otherwise requires the legacy W3C migration receipt')
    p.add_argument('--rounds', type=int, default=5)
    p.add_argument('--warmup', type=float, default=30)
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--rate', type=float, default=2)
    p.add_argument('--concurrency', type=int, default=2)
    p.add_argument('--sample-interval', type=float, default=2)
    p.add_argument('--cpus', type=float, default=1)
    p.add_argument('--memory', default='768m')
    p.add_argument('--seed', type=int, default=151031)
    p.add_argument('--offline-timeout', type=float, default=600)
    p.add_argument('--query-scope', choices=('paths','total'),default='paths')
    p.add_argument('--modes', nargs='+',choices=('original','tracefusion','mirrortaint'),default=['original','tracefusion'])
    p.add_argument('--mode', choices=('tracefusion','mirrortaint'),default='tracefusion')
    p.add_argument('--mt-bundle',type=Path)
    p.add_argument('--mt-calibration',type=Path)
    p.add_argument('--tf-calibration',type=Path)
    p.add_argument('--allow-errors',action='store_true',help='Load scans: retain failed requests; never synthesize source answers')
    return p


if __name__ == '__main__':
    p = parser()
    a = p.parse_args()
    if a.stage=='offline':
        if not a.build:
            p.error('--build is required')
        if a.query_scope=='total':
            import mirrortaint_instances as mt
            result=mt.evaluate(a.out.resolve(),a.build.resolve(),a.mode)
            if not a.allow_errors and (result['summary']['exact']!=result['summary']['queries'] or result['summary']['unknown']):
                raise ValueError('Common query provenance failed')
        else:offline(a.out.resolve(), a.build.resolve())
    elif a.stage=='report':
        report(a.out.resolve())
    else:
        if not a.build or not a.correctness:
            p.error('--build and --correctness are required')
        if a.query_scope=='total' and not all((a.mt_bundle,a.mt_calibration,a.tf_calibration)):
            p.error('total scope requires --mt-bundle --mt-calibration --tf-calibration')
        if len(set(a.modes))!=len(a.modes):p.error('Configurations must be unique')
        if min(a.rounds, a.warmup, a.seconds, a.rate, a.concurrency, a.sample_interval, a.cpus)<=0:
            p.error('load, duration and resource settings must be positive')
        if a.seconds < a.sample_interval*3:
            p.error('steady window must contain at least three sampling intervals')
        if any(not math.isclose(t*a.rate, round(t*a.rate)) or round(t*a.rate)<1 for t in (a.warmup,a.seconds)):
            p.error('duration * rate must be a positive integer')
        run(a)
